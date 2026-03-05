# """
# CELERY TASK FOR MEETING PROCESSING
# Pipeline: Download → Convert → Transcribe (Whisper VM) → Correct → MoM → Save
# """

# from backend.worker.celery_app import celery_app
# from backend.app.database import SessionLocal
# from backend.app.models import Meeting
# from backend.app.services.whisper_client import transcribe_audio        # ✅ Whisper VM
# from backend.app.services.mom_generator import generate_mom
# from backend.app.services.evaluation import evaluate_action_items, evaluate_transcription
# from backend.app.services.azure_blob_storage import download_file_from_blob
# from backend.app.services.correction import correct_transcript

# import json
# import os
# import subprocess
# import traceback
# import logging
# import numpy as np
# from typing import Any
# from datetime import datetime

# # ============================================================================
# # LOGGING
# # ============================================================================
# logging.basicConfig(
#     level=logging.INFO,
#     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
#     handlers=[
#         logging.FileHandler('meeting_processing.log'),
#         logging.StreamHandler()
#     ]
# )
# logger = logging.getLogger(__name__)


# # ============================================================================
# # CLEAN NON-SERIALIZABLE DATA (numpy → plain Python)
# # ============================================================================
# def clean_non_serializable_data(data: Any) -> Any:
#     if isinstance(data, dict):
#         return {k: clean_non_serializable_data(v) for k, v in data.items()}
#     elif isinstance(data, list):
#         return [clean_non_serializable_data(item) for item in data]
#     elif isinstance(data, np.ndarray):
#         return data.tolist()
#     elif isinstance(data, (np.integer, np.floating)):
#         return data.item()
#     elif isinstance(data, np.bool_):
#         return bool(data)
#     elif hasattr(data, '__dict__') and not isinstance(data, (str, int, float, bool, type(None))):
#         return None
#     else:
#         return data


# # ============================================================================
# # CONVERT AUDIO TO WAV (16kHz mono) via ffmpeg
# # ============================================================================
# def convert_to_wav(input_path: str) -> str:
#     output_path = input_path.rsplit(".", 1)[0] + ".wav"
#     logger.info(f"Converting audio: {input_path} → {output_path}")

#     command = [
#         "ffmpeg", "-y",
#         "-i", input_path,
#         "-ac", "1",       # Mono
#         "-ar", "16000",   # 16kHz — required by Whisper
#         output_path
#     ]

#     try:
#         result = subprocess.run(
#             command,
#             stdout=subprocess.DEVNULL,
#             stderr=subprocess.PIPE,
#             text=True,
#             timeout=300
#         )

#         if result.returncode != 0:
#             raise Exception(f"FFmpeg error: {result.stderr}")

#         if not os.path.exists(output_path):
#             raise Exception("Output WAV file was not created")

#         logger.info("Audio conversion complete")
#         return output_path

#     except subprocess.TimeoutExpired:
#         raise Exception("Audio conversion timed out (> 5 minutes)")
#     except Exception as e:
#         logger.error(f"Audio conversion failed: {e}")
#         raise


# # ============================================================================
# # GET AUDIO DURATION via ffprobe
# # ============================================================================
# def get_audio_duration(file_path: str) -> float:
#     cmd = [
#         "ffprobe", "-v", "error",
#         "-show_entries", "format=duration",
#         "-of", "json",
#         file_path
#     ]

#     try:
#         result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

#         if result.returncode != 0:
#             logger.warning(f"ffprobe failed: {result.stderr}")
#             return 0.0

#         output   = json.loads(result.stdout)
#         duration = float(output.get("format", {}).get("duration", 0.0))
#         logger.info(f"Audio duration: {duration:.2f}s ({duration/60:.2f} min)")
#         return duration

#     except (json.JSONDecodeError, KeyError, ValueError) as e:
#         logger.warning(f"Could not parse audio duration: {e}")
#         return 0.0
#     except subprocess.TimeoutExpired:
#         logger.warning("ffprobe timed out")
#         return 0.0


# # ============================================================================
# # MAIN CELERY TASK
# # ============================================================================
# @celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
# def process_meeting(self, meeting_id: str):
#     """
#     End-to-end meeting processing pipeline.

#     Steps:
#      1.  Fetch meeting from DB
#      2.  Mark status = processing
#      3.  Download audio from Azure Blob
#      4.  Convert to WAV (16kHz mono)
#      5.  Get audio duration
#      6.  Load glossary (optional)
#      7.  Transcribe via Whisper VM (Whisper large-v3 + Pyannote diarization)
#      8.  Log diarization result — NO local re-clustering needed
#      9.  Apply glossary + Azure Search term corrections
#      10. Evaluate transcript accuracy (only if reference .txt uploaded)
#      11. Generate Minutes of Meeting via Ollama
#      12. Evaluate MoM quality score
#          Save everything → PostgreSQL
#     """
#     print(f"\n{'='*70}")
#     print(f"STARTING MEETING PROCESSING: {meeting_id}")
#     print(f"{'='*70}\n")

#     logger.info("=" * 70)
#     logger.info(f"Meeting processing started : {meeting_id}")
#     logger.info(f"Task attempt               : {self.request.retries + 1}/{self.max_retries + 1}")
#     logger.info("=" * 70)

#     db               = SessionLocal()
#     meeting          = None
#     temp_dir         = "temp_files"
#     local_audio_path = None
#     wav_path         = None
#     glossary_text    = ""
#     start_time       = datetime.utcnow()

#     try:
#         os.makedirs(temp_dir, exist_ok=True)

#         # ────────────────────────────────────────────────────────
#         # STEP 1: Fetch meeting from DB
#         # ────────────────────────────────────────────────────────
#         logger.info("Step 1/12: Fetching meeting from database...")
#         meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()

#         if not meeting:
#             raise ValueError(f"Meeting {meeting_id} not found in database")

#         logger.info(f"Meeting found: '{meeting.title}'")

#         # ────────────────────────────────────────────────────────
#         # STEP 2: Mark as processing
#         # ────────────────────────────────────────────────────────
#         logger.info("Step 2/12: Updating status → processing...")
#         meeting.status = "processing"
#         db.commit()

#         # ────────────────────────────────────────────────────────
#         # STEP 3: Download audio from Azure Blob
#         # ────────────────────────────────────────────────────────
#         logger.info("Step 3/12: Downloading audio from Azure Blob...")
#         file_ext         = meeting.audio_path.split(".")[-1]
#         local_audio_path = os.path.join(temp_dir, f"{meeting_id}.{file_ext}")

#         download_file_from_blob("audio", meeting.audio_path, local_audio_path)

#         if not os.path.exists(local_audio_path):
#             raise FileNotFoundError(f"Audio file missing after download: {local_audio_path}")

#         if os.path.getsize(local_audio_path) < 10_000:
#             raise ValueError("Audio file too small (< 10KB) — likely a broken recording")

#         file_size_mb = os.path.getsize(local_audio_path) / (1024 * 1024)
#         logger.info(f"Audio downloaded: {file_size_mb:.2f} MB")

#         # ────────────────────────────────────────────────────────
#         # STEP 4: Convert to WAV (16kHz mono)
#         # ────────────────────────────────────────────────────────
#         logger.info("Step 4/12: Converting to WAV (16kHz mono)...")
#         wav_path = convert_to_wav(local_audio_path)
#         logger.info(f"WAV ready: {wav_path}")

#         # ────────────────────────────────────────────────────────
#         # STEP 5: Get audio duration
#         # ────────────────────────────────────────────────────────
#         logger.info("Step 5/12: Getting audio duration...")
#         real_duration = get_audio_duration(wav_path)

#         # ────────────────────────────────────────────────────────
#         # STEP 6: Load glossary text (for MoM generation context)
#         # ────────────────────────────────────────────────────────
#         logger.info("Step 6/12: Loading glossary...")
#         if meeting.glossary_path:
#             try:
#                 glossary_local_path = os.path.join(temp_dir, f"{meeting_id}_glossary.json")
#                 download_file_from_blob("glossary", meeting.glossary_path, glossary_local_path)

#                 if os.path.exists(glossary_local_path):
#                     with open(glossary_local_path, "r", encoding="utf-8") as f:
#                         glossary_text = f.read()
#                     os.remove(glossary_local_path)
#                     logger.info("Glossary loaded successfully")
#                 else:
#                     logger.warning("Glossary file missing after download — continuing without it")
#             except Exception as e:
#                 logger.warning(f"Could not load glossary (non-fatal): {e}")
#                 glossary_text = ""
#         else:
#             logger.info("No glossary uploaded for this meeting")

#         # ────────────────────────────────────────────────────────
#         # STEP 7: Transcribe via Whisper VM
#         #
#         # Flow:
#         #   whisper_client.py
#         #     → GET  http://<VM_IP>:8001/health       (check alive)
#         #     → POST http://<VM_IP>:8001/transcribe   (send WAV)
#         #   vm_whisper_server.py  (your Windows machine)
#         #     → Whisper large-v3 transcribes audio
#         #     → Pyannote assigns speaker labels
#         #     → Returns { segments, metadata }
#         # ────────────────────────────────────────────────────────
#         logger.info("Step 7/12: Transcribing via Whisper VM...")
#         whisper_result = transcribe_audio(
#             wav_path,
#             glossary_path=meeting.glossary_path
#         )
#         transcript  = whisper_result.get("segments", [])
#         vm_metadata = whisper_result.get("metadata", {})

#         logger.info(f"VM transcription complete:")
#         logger.info(f"  Segments    : {len(transcript)}")
#         logger.info(f"  Language    : {vm_metadata.get('language', 'unknown')}")
#         logger.info(f"  Duration    : {vm_metadata.get('duration_seconds', 0):.1f}s")
#         logger.info(f"  Diarization : {vm_metadata.get('diarization', 'unknown')}")
#         logger.info(f"  Model       : {vm_metadata.get('model', 'unknown')}")

#         if not transcript:
#             meeting.status         = "failed"
#             meeting.correction_log = {"error": "No speech detected in audio"}
#             db.commit()
#             logger.error("Transcription returned 0 segments — marking as failed")
#             return

#         print(f"Transcript segments: {len(transcript)}")

#         # ────────────────────────────────────────────────────────
#         # STEP 8: Log diarization — NO local re-clustering
#         #
#         # Pyannote on the VM already assigned speaker labels
#         # correctly. production_diarization.py is NOT used.
#         #
#         # If diarization="disabled" → HF_TOKEN missing on VM.
#         # Fix: add HF_TOKEN to VM .env, restart vm_whisper_server.py
#         # ────────────────────────────────────────────────────────
#         vm_diarization  = vm_metadata.get("diarization", "disabled")
#         unique_speakers = len(set(s.get("speaker", "") for s in transcript))

#         logger.info(f"Step 8/12: Speaker diarization info:")
#         logger.info(f"  Source          : {vm_diarization}")
#         logger.info(f"  Unique speakers : {unique_speakers}")

#         if vm_diarization == "disabled":
#             logger.warning(
#                 "Pyannote disabled on VM — segments show 'Speaker Unknown'. "
#                 "Fix: set HF_TOKEN in VM .env and restart vm_whisper_server.py"
#             )

#         meeting.correction_log = {
#             "language_detected":  vm_metadata.get("language", "unknown"),
#             "diarization_source": vm_diarization,
#             "unique_speakers":    unique_speakers,
#             "model":              vm_metadata.get("model", "whisper-large-v3")
#         }

#         # ────────────────────────────────────────────────────────
#         # STEP 9: Apply term corrections
#         #
#         # correction.py:
#         #   → loads glossary from Azure Blob via glossary.py
#         #   → checks each word against glossary dict
#         #   → if miss → queries Azure Cognitive Search
#         #   → returns corrected segments + log + stats
#         # ────────────────────────────────────────────────────────
#         logger.info("Step 9/12: Applying term corrections...")
#         corrected_transcript, correction_log, correction_stats = correct_transcript(
#             transcript,
#             glossary_path=meeting.glossary_path
#         )

#         logger.info(f"Corrections applied:")
#         logger.info(f"  Words checked : {correction_stats['total_checked']}")
#         logger.info(f"  Corrected     : {correction_stats['total_corrected']}")
#         logger.info(f"  Rate          : {correction_stats['correction_rate']*100:.1f}%")
#         print(f"Terms corrected: {correction_stats['total_corrected']}")

#         predicted_text      = " ".join([seg.get("text", "") for seg in corrected_transcript])
#         transcript_accuracy = None

#         # ────────────────────────────────────────────────────────
#         # STEP 10: Evaluate transcript accuracy (optional)
#         #   Runs only if user uploaded a reference .txt file
#         #   Uses WER (Word Error Rate) via jiwer library
#         # ────────────────────────────────────────────────────────
#         logger.info("Step 10/12: Evaluating transcript accuracy...")
#         if meeting.reference_path:
#             try:
#                 reference_local_path = os.path.join(temp_dir, f"{meeting_id}_reference.txt")
#                 download_file_from_blob("reference", meeting.reference_path, reference_local_path)

#                 if os.path.exists(reference_local_path):
#                     with open(reference_local_path, "r", encoding="utf-8") as f:
#                         reference_text = f.read()

#                     transcript_accuracy = evaluate_transcription(reference_text, predicted_text)
#                     logger.info(f"Transcript accuracy: {transcript_accuracy*100:.2f}%")
#                     print(f"Accuracy: {transcript_accuracy*100:.2f}%")
#                     os.remove(reference_local_path)
#                 else:
#                     logger.warning("Reference file missing after download")
#             except Exception as e:
#                 logger.warning(f"Transcript evaluation failed (non-fatal): {e}")
#                 transcript_accuracy = None
#         else:
#             logger.info("No reference transcript — accuracy will show as N/A")

#         meeting.transcript_accuracy = transcript_accuracy

#         # ────────────────────────────────────────────────────────
#         # STEP 11: Generate Minutes of Meeting via Ollama
#         #
#         # mom_generator.py:
#         #   → formats corrected transcript into LLM prompt
#         #   → calls Ollama (neural-chat model) locally
#         #   → parses JSON response → validates via MoMSchema
#         #   → returns Summary, Decisions, Action Items,
#         #             Risks, Open Questions
#         # ────────────────────────────────────────────────────────
#         logger.info("Step 11/12: Generating Minutes of Meeting...")
#         mom_json_string = generate_mom(corrected_transcript, glossary_text)

#         try:
#             mom_dict        = json.loads(mom_json_string)
#             decisions_count = len(mom_dict.get("Decisions", []))
#             actions_count   = len(mom_dict.get("Action Items", []))

#             logger.info(f"MoM generated:")
#             logger.info(f"  Decisions    : {decisions_count}")
#             logger.info(f"  Action Items : {actions_count}")
#             print(f"Decisions: {decisions_count} | Actions: {actions_count}")

#         except json.JSONDecodeError as e:
#             logger.error(f"MoM JSON parse failed: {e}")
#             raise ValueError(f"MoM generation returned invalid JSON: {e}")

#         # ────────────────────────────────────────────────────────
#         # STEP 12: Evaluate MoM quality score
#         #
#         # evaluation.py → evaluate_action_items()
#         #   Scores each action item on 3 criteria:
#         #     task exists (+1) + owner assigned (+1) + due date (+1)
#         #   Returns float 0.0 - 1.0
#         # ────────────────────────────────────────────────────────
#         logger.info("Step 12/12: Evaluating MoM quality...")
#         evaluation_score = evaluate_action_items(mom_dict)
#         logger.info(f"MoM quality score: {evaluation_score*100:.2f}%")
#         print(f"MoM Quality: {evaluation_score*100:.2f}%")

#         # ────────────────────────────────────────────────────────
#         # FINAL: Clean + save to PostgreSQL
#         # ────────────────────────────────────────────────────────
#         logger.info("Saving results to database...")

#         corrected_transcript = clean_non_serializable_data(corrected_transcript)
#         correction_log       = clean_non_serializable_data(correction_log)
#         correction_stats     = clean_non_serializable_data(correction_stats)
#         mom_dict             = clean_non_serializable_data(mom_dict)

#         meeting.transcript       = corrected_transcript
#         meeting.mom              = mom_dict
#         meeting.duration         = real_duration
#         meeting.correction_log   = correction_log
#         meeting.correction_stats = correction_stats
#         meeting.evaluation_score = evaluation_score
#         meeting.status           = "ready"

#         db.commit()

#         processing_time = (datetime.utcnow() - start_time).total_seconds()
#         logger.info("=" * 70)
#         logger.info("MEETING PROCESSING COMPLETED SUCCESSFULLY")
#         logger.info(f"Total time: {processing_time:.1f}s ({processing_time/60:.2f} min)")
#         logger.info("=" * 70)

#         print(f"\n{'='*70}")
#         print(f"PROCESSING COMPLETE : {meeting_id}")
#         print(f"Total time          : {processing_time:.1f}s")
#         print(f"{'='*70}\n")

#     # ============================================================================
#     # ERROR HANDLING
#     # ============================================================================
#     except Exception as e:
#         error_msg  = str(e)
#         error_type = type(e).__name__

#         logger.error("=" * 70)
#         logger.error(f"ERROR PROCESSING MEETING : {meeting_id}")
#         logger.error(f"Error type               : {error_type}")
#         logger.error(f"Error message            : {error_msg}")
#         logger.error(f"Stack trace:\n{traceback.format_exc()}")
#         logger.error("=" * 70)

#         print(f"ERROR [{error_type}]: {error_msg}")

#         if meeting:
#             meeting.status         = "failed"
#             meeting.correction_log = {
#                 "error":      error_msg,
#                 "error_type": error_type,
#                 "timestamp":  datetime.utcnow().isoformat(),
#                 "attempt":    self.request.retries + 1
#             }
#             try:
#                 db.commit()
#             except Exception as db_error:
#                 logger.error(f"Failed to save error status: {db_error}")

#         # Retry only for transient network/service errors
#         retryable_errors = ["ConnectionError", "TimeoutError", "HTTPError", "ServiceBusyError"]
#         if error_type in retryable_errors and self.request.retries < self.max_retries:
#             logger.info(f"Scheduling retry {self.request.retries + 1}/{self.max_retries}...")
#             raise self.retry(exc=e, countdown=60)
#         else:
#             logger.critical("Task failed permanently — no more retries.")

#     # ============================================================================
#     # CLEANUP — always runs regardless of success or failure
#     # ============================================================================
#     finally:
#         try:
#             logger.info("Cleaning up temp files...")
#             if local_audio_path and os.path.exists(local_audio_path):
#                 os.remove(local_audio_path)
#                 logger.info(f"  Removed: {local_audio_path}")
#             if wav_path and os.path.exists(wav_path):
#                 os.remove(wav_path)
#                 logger.info(f"  Removed: {wav_path}")
#         except Exception as cleanup_error:
#             logger.error(f"Cleanup error: {cleanup_error}")

#         try:
#             db.close()
#             logger.info("Database connection closed")
#         except Exception as db_close_error:
#             logger.error(f"Failed to close DB: {db_close_error}")



















# #PRITHIKAAA





import os
import json
import subprocess
import traceback
import logging
import numpy as np

from datetime import datetime
from typing import Any

from backend.worker.celery_app import celery_app
from backend.app.database import SessionLocal
from backend.app.models import Meeting

from backend.app.services.whisper_client import transcribe_audio
from backend.app.services.mom_generator import generate_mom
from backend.app.services.evaluation import evaluate_action_items, evaluate_transcription
from backend.app.services.azure_blob_storage import download_file_from_blob
from backend.app.services.correction import correct_transcript


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)

logger = logging.getLogger(__name__)


# ============================================================
# CLEAN NON-SERIALIZABLE DATA
# ============================================================

def clean_non_serializable_data(data: Any) -> Any:

    if isinstance(data, dict):
        return {k: clean_non_serializable_data(v) for k, v in data.items()}

    elif isinstance(data, list):
        return [clean_non_serializable_data(i) for i in data]

    elif isinstance(data, np.ndarray):
        return data.tolist()

    elif isinstance(data, (np.integer, np.floating)):
        return data.item()

    elif isinstance(data, np.bool_):
        return bool(data)

    return data


# ============================================================
# AUDIO CONVERSION
# ============================================================

def convert_to_wav(input_path: str) -> str:

    output_path = input_path.rsplit(".", 1)[0] + ".wav"

    command = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-ac", "1",
        "-ar", "16000",
        output_path
    ]

    logger.info(f"Converting audio → WAV: {input_path}")

    result = subprocess.run(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        raise Exception(f"FFmpeg conversion failed: {result.stderr}")

    return output_path


# ============================================================
# GET AUDIO DURATION
# ============================================================

def get_audio_duration(file_path: str) -> float:

    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        file_path
    ]

    try:

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            return 0.0

        output = json.loads(result.stdout)

        return float(output["format"]["duration"])

    except Exception:
        return 0.0


# ============================================================
# MAIN CELERY TASK
# ============================================================

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_meeting(self, meeting_id: str):

    logger.info("=" * 60)
    logger.info(f"PROCESSING MEETING: {meeting_id}")
    logger.info("=" * 60)

    db = SessionLocal()
    meeting = None

    temp_dir = "temp_files"
    os.makedirs(temp_dir, exist_ok=True)

    local_audio_path = None
    wav_path = None

    start_time = datetime.utcnow()

    try:

        # ----------------------------------------------------
        # 1. Load meeting
        # ----------------------------------------------------

        meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()

        if not meeting:
            raise ValueError(f"Meeting {meeting_id} not found")

        meeting.status = "processing"
        db.commit()

        logger.info(f"Meeting title: {meeting.title}")


        # ----------------------------------------------------
        # 2. Download audio from Azure Blob
        # ----------------------------------------------------

        file_ext = meeting.audio_path.split(".")[-1]

        local_audio_path = os.path.join(temp_dir, f"{meeting_id}.{file_ext}")

        logger.info("Downloading audio from Azure Blob")

        download_file_from_blob(
            "audio",
            meeting.audio_path,
            local_audio_path
        )

        if not os.path.exists(local_audio_path):
            raise FileNotFoundError("Downloaded audio missing")


        # ----------------------------------------------------
        # 3. Convert audio → WAV
        # ----------------------------------------------------

        wav_path = convert_to_wav(local_audio_path)

        logger.info(f"WAV file ready: {wav_path}")


        # ----------------------------------------------------
        # 4. Get audio duration
        # ----------------------------------------------------

        duration = get_audio_duration(wav_path)

        logger.info(f"Audio duration: {duration:.2f} seconds")


        # ----------------------------------------------------
        # 5. Transcribe via Whisper VM
        # ----------------------------------------------------

        logger.info("Sending audio to Whisper VM")

        whisper_result = transcribe_audio(wav_path)

        transcript = whisper_result.get("segments", [])
        vm_metadata = whisper_result.get("metadata", {})

        if not transcript:
            raise RuntimeError("No speech detected")

        logger.info(f"Segments received: {len(transcript)}")


        # ----------------------------------------------------
        # SAVE transcript immediately
        # ----------------------------------------------------

        meeting.transcript = transcript
        db.commit()


        # ----------------------------------------------------
        # 6. Apply corrections
        # ----------------------------------------------------

        corrected_transcript, correction_log, correction_stats = correct_transcript(
            transcript,
            glossary_path=meeting.glossary_path
        )

        logger.info(f"Corrections applied: {correction_stats['total_corrected']}")


        # ----------------------------------------------------
        # 7. Generate MoM
        # ----------------------------------------------------

        logger.info("Generating Minutes of Meeting")

        mom_json = generate_mom(corrected_transcript, "")

        mom_dict = json.loads(mom_json)


        # ----------------------------------------------------
        # 8. Evaluate MoM quality
        # ----------------------------------------------------

        score = evaluate_action_items(mom_dict)

        logger.info(f"MoM score: {score:.2f}")


        # ----------------------------------------------------
        # 9. Save results
        # ----------------------------------------------------

        meeting.transcript = clean_non_serializable_data(corrected_transcript)
        meeting.mom = clean_non_serializable_data(mom_dict)
        meeting.duration = duration
        meeting.correction_log = clean_non_serializable_data(correction_log)
        meeting.correction_stats = clean_non_serializable_data(correction_stats)
        meeting.evaluation_score = score
        meeting.status = "ready"

        db.commit()

        elapsed = (datetime.utcnow() - start_time).total_seconds()

        logger.info(f"Meeting processing completed in {elapsed:.1f}s")


    except Exception as e:

        logger.error("Meeting processing failed")
        logger.error(str(e))
        logger.error(traceback.format_exc())

        if meeting:
            meeting.status = "failed"
            meeting.correction_log = {"error": str(e)}
            db.commit()

        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)

    finally:

        try:

            if local_audio_path and os.path.exists(local_audio_path):
                os.remove(local_audio_path)

            if wav_path and os.path.exists(wav_path):
                os.remove(wav_path)

        except Exception:
            pass

        db.close()