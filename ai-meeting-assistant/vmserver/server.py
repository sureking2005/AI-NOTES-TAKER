import os
import uuid
import tempfile
import logging
import uvicorn
import whisperx
import torch
import gc
import json

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse, StreamingResponse
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="WhisperX Transcription Server")

# ------------------------------------------------
# MODEL CONFIG
# ------------------------------------------------

MODEL_SIZE = os.getenv("WHISPER_MODEL", "small")
DEVICE     = "cuda" if torch.cuda.is_available() else "cpu"
COMPUTE    = "float16" if DEVICE == "cuda" else "int8"
BATCH_SIZE = 4

logger.info(f"Device      : {DEVICE}")
logger.info(f"Model       : {MODEL_SIZE}")
logger.info(f"Compute type: {COMPUTE}")

# ------------------------------------------------
# LOAD WHISPER MODEL (once at startup)
# ------------------------------------------------

logger.info("Loading WhisperX model...")

MODEL = whisperx.load_model(
    MODEL_SIZE,
    device=DEVICE,
    compute_type=COMPUTE
)

logger.info("WhisperX model loaded ✅")

# ------------------------------------------------
# LOAD DIARIZATION MODEL (once at startup)
# ------------------------------------------------

HF_TOKEN      = os.getenv("HF_TOKEN")
DIARIZE_MODEL = None

if HF_TOKEN:
    try:
        from whisperx.diarize import DiarizationPipeline

        DIARIZE_MODEL = DiarizationPipeline(
            token=HF_TOKEN,
            device=DEVICE
        )
        logger.info("WhisperX DiarizationPipeline loaded ✅")

    except Exception as e:
        logger.warning(f"Diarization model failed to load: {e}")
        logger.warning("Continuing without diarization — speakers will show as 'Speaker Unknown'")
        DIARIZE_MODEL = None
else:
    logger.warning(
        "HF_TOKEN not set in .env — diarization disabled. "
        "Add HF_TOKEN=hf_xxx to your .env and restart."
    )


# ------------------------------------------------
# TRANSCRIBE ENDPOINT
# ------------------------------------------------

@app.post("/transcribe")
async def transcribe(
    audio:        UploadFile = File(...),
    language:     str        = Form("hi"),
    min_speakers: int        = Form(1),
    max_speakers: int        = Form(10)
):
    logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info(f"Received file    : {audio.filename}")
    logger.info(f"Language hint    : {language}")
    logger.info(f"Speakers range   : {min_speakers} – {max_speakers}")
    logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    suffix   = os.path.splitext(audio.filename)[1] or ".wav"
    tmp_path = None

    # ── Save uploaded file to temp ──────────────────────────────
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            bytes_written = 0
            while chunk := await audio.read(1024 * 1024):  # 1MB chunks
                tmp.write(chunk)
                bytes_written += len(chunk)
            tmp_path = tmp.name

        logger.info(f"Saved to temp : {tmp_path} ({bytes_written / 1024 / 1024:.2f} MB)")

    except Exception as e:
        logger.error(f"Failed to save uploaded file: {e}")
        return JSONResponse(
            status_code=400,
            content={"error": f"File upload failed: {str(e)}"}
        )

    try:

        # ────────────────────────────────────────────────────────
        # STEP 1: Load audio
        # ────────────────────────────────────────────────────────
        logger.info("Step 1/4: Loading audio...")
        audio_data = whisperx.load_audio(tmp_path)
        duration_s = len(audio_data) / 16000
        logger.info(f"Audio duration: {duration_s:.1f}s ({duration_s/60:.1f} min)")

        if duration_s < 0.5:
            logger.warning("Audio too short — likely empty or corrupt")
            # ✅ FIX: Return JSONResponse (not plain dict)
            return JSONResponse(content={
                "segments": [],
                "metadata": {
                    "language":         language,
                    "duration": duration_s,
                    "segment_count":    0,
                    "model":            MODEL_SIZE
                }
            })

        # ────────────────────────────────────────────────────────
        # STEP 2: Transcribe with WhisperX
        # ────────────────────────────────────────────────────────
        logger.info("Step 2/4: Running WhisperX transcription...")
        logger.info(f"  Model: {MODEL_SIZE}, Device: {DEVICE}, Compute: {COMPUTE}")

        transcribe_result = MODEL.transcribe(
            audio_data,
            batch_size=BATCH_SIZE,
            language=language
        )

        # ── Keep transcription result separate to avoid overwrite bugs ──
        raw_segments      = transcribe_result.get("segments", [])
        detected_language = transcribe_result.get("language", language)

        logger.info(f"Segments        : {len(raw_segments)}")
        logger.info(f"Detected lang   : {detected_language}")

        if not raw_segments:
            logger.warning("No segments detected — returning empty result")
            # ✅ FIX: Return JSONResponse (not plain dict)
            return JSONResponse(content={
                "segments": [],
                "metadata": {
                    "language":         detected_language,
                    "duration": duration_s,
                    "segment_count":    0,
                    "model":            MODEL_SIZE
                }
            })

        # ────────────────────────────────────────────────────────
        # STEP 3: Forced alignment (word-level timestamps)
        # ────────────────────────────────────────────────────────
        logger.info("Step 3/4: Running forced alignment...")

        # Use a separate variable — never overwrite raw_segments
        aligned_result = {"segments": raw_segments}

        try:
            model_a, align_metadata = whisperx.load_align_model(
                language_code=detected_language,
                device=DEVICE
            )

            aligned_result = whisperx.align(
                raw_segments,
                model_a,
                align_metadata,
                audio_data,
                DEVICE,
                return_char_alignments=False
            )

            logger.info("Alignment complete ✅")

        except Exception as e:
            logger.warning(f"Alignment failed (non-fatal): {e}")
            logger.warning("Continuing with unaligned segments")

        finally:
            # Always free alignment model from memory
            try:
                del model_a
            except Exception:
                pass
            gc.collect()
            if DEVICE == "cuda":
                torch.cuda.empty_cache()

        # ────────────────────────────────────────────────────────
        # STEP 4: Speaker diarization
        # ────────────────────────────────────────────────────────
        diarization_status = "disabled"
        final_result       = aligned_result

        if DIARIZE_MODEL:
            try:
                logger.info("Step 4/4: Running speaker diarization...")
                logger.info(f"  Device       : {DEVICE}")
                logger.info(f"  min_speakers : {min_speakers}")
                logger.info(f"  max_speakers : {max_speakers}")

                diarize_segments = DIARIZE_MODEL(
                    audio_data,
                    min_speakers=min_speakers,
                    max_speakers=max_speakers
                )

                final_result = whisperx.assign_word_speakers(
                    diarize_segments,
                    aligned_result
                )

                diarization_status = "whisperx"

                unique_speakers = set()
                for seg in final_result.get("segments", []):
                    spk = seg.get("speaker")
                    if spk:
                        unique_speakers.add(spk)

                logger.info(
                    f"Diarization complete ✅ — "
                    f"{len(unique_speakers)} speakers: {sorted(unique_speakers)}"
                )

            except Exception as e:
                logger.error(f"Diarization failed: {e}", exc_info=True)
                logger.warning("Falling back to aligned segments without speaker labels")
                diarization_status = "failed"
                final_result       = aligned_result

        else:
            logger.info("Step 4/4: Diarization skipped (no HF_TOKEN or model not loaded)")

        # ────────────────────────────────────────────────────────
        # FORMAT OUTPUT
        # ────────────────────────────────────────────────────────
        formatted_segments = []

        for seg in final_result.get("segments", []):
            speaker = seg.get("speaker") or "Speaker Unknown"

            formatted_segments.append({
                "id":         str(uuid.uuid4()),
                "speaker":    speaker,
                "start":      round(float(seg.get("start", 0)), 2),
                "end":        round(float(seg.get("end", 0)), 2),
                "text":       seg.get("text", "").strip(),
                "confidence": None
            })

        final_duration = formatted_segments[-1]["end"] if formatted_segments else duration_s

        logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.info(f"DONE — {len(formatted_segments)} segments, {final_duration:.1f}s, diarization={diarization_status}")
        logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # ✅ FIX: Return JSONResponse for main endpoint (not plain dict)
        return JSONResponse(content={
            "segments": formatted_segments,
            "metadata": {
                "language": detected_language,
                "duration": final_duration,
                "segment_count": len(formatted_segments),
                "model": MODEL_SIZE
            }
        })

    except Exception as e:
        logger.error(f"Transcription pipeline failed: {e}", exc_info=True)
        # ✅ FIX: Return JSONResponse for error (not plain dict)
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
            logger.info(f"Temp file removed: {tmp_path}")


# ------------------------------------------------
# HEALTH CHECK
# ------------------------------------------------

@app.get("/health")
def health():
    return {
        "status":      "ok",
        "model":       MODEL_SIZE,
        "device":      DEVICE,
        "diarization": "enabled" if DIARIZE_MODEL else "disabled — set HF_TOKEN in .env"
    }


# ------------------------------------------------
# RUN SERVER
# ------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8079,
        reload=False
    )
