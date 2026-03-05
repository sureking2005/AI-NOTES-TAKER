"""
PRODUCTION-GRADE CELERY TASK FOR MEETING PROCESSING
Includes: Advanced diarization, multi-lingual support, error recovery, quality assurance
"""

from backend.worker.celery_app import celery_app
from backend.app.database import SessionLocal
from backend.app.models import Meeting
from backend.app.services.azure_speech import transcribe_audio
from backend.app.services.mom_generator import generate_mom
from backend.app.services.evaluation import evaluate_action_items, evaluate_transcription
from backend.app.services.azure_blob_storage import download_file_from_blob
from backend.app.services.correction import correct_transcript
from backend.app.services.production_diarization import production_diarization_pipeline

import json
import os
import subprocess
import traceback
import logging
from datetime import datetime

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('meeting_processing.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# ✅ FIX: REMOVE NON-SERIALIZABLE DATA (NUMPY ARRAYS, ETC)
# ============================================================================
import numpy as np
from typing import Any

def clean_non_serializable_data(data: Any) -> Any:
    """
    Remove numpy arrays and other non-JSON-serializable objects.
    
    Converts:
    - numpy.ndarray → list
    - numpy types → Python types
    - Other non-serializable → None or safe value
    """
    if isinstance(data, dict):
        return {k: clean_non_serializable_data(v) for k, v in data.items()}
    
    elif isinstance(data, list):
        return [clean_non_serializable_data(item) for item in data]
    
    elif isinstance(data, np.ndarray):
        # ✅ Convert numpy array to list
        return data.tolist()
    
    elif isinstance(data, (np.integer, np.floating)):
        # ✅ Convert numpy scalars to Python types
        return data.item()
    
    elif isinstance(data, np.bool_):
        # ✅ Convert numpy bool to Python bool
        return bool(data)
    
    elif hasattr(data, '__dict__') and not isinstance(data, (str, int, float, bool, type(None))):
        # ✅ Remove unserializable objects
        logger.debug(f"Removing non-serializable object: {type(data)}")
        return None
    
    else:
        # ✅ Keep as-is if it's already JSON-serializable
        return data


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def convert_to_wav(input_path: str) -> str:
    """
    ✅ PRODUCTION: Convert audio to WAV format (16kHz mono)
    
    Supports: MP3, M4A, WEBM, WAV, FLAC, etc.
    
    Args:
        input_path: Path to input audio file
        
    Returns:
        Path to converted WAV file
        
    Raises:
        Exception: If conversion fails
    """
    output_path = input_path.rsplit(".", 1)[0] + ".wav"
    
    logger.info(f"Converting audio: {input_path} → {output_path}")

    command = [
        "ffmpeg",
        "-y",  # Overwrite if exists
        "-i", input_path,
        "-ac", "1",  # Mono
        "-ar", "16000",  # 16kHz sample rate
        output_path
    ]

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode != 0:
            raise Exception(f"FFmpeg error: {result.stderr}")
        
        if not os.path.exists(output_path):
            raise Exception("Output WAV file was not created")
        
        logger.info(f"✅ Audio converted successfully")
        return output_path
        
    except subprocess.TimeoutExpired:
        raise Exception("Audio conversion timed out (> 5 minutes)")
    except Exception as e:
        logger.error(f"❌ Audio conversion failed: {e}")
        raise


def get_audio_duration(file_path: str) -> float:
    """
    ✅ PRODUCTION: Get accurate audio duration using ffprobe
    
    Args:
        file_path: Path to audio file
        
    Returns:
        Duration in seconds (float)
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        file_path
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            logger.warning(f"Failed to get audio duration: {result.stderr}")
            return 0.0

        output = json.loads(result.stdout)
        duration = float(output.get("format", {}).get("duration", 0.0))
        
        logger.info(f"Audio duration: {duration:.2f} seconds")
        return duration
        
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning(f"Failed to parse audio duration: {e}")
        return 0.0
    except subprocess.TimeoutExpired:
        logger.warning("ffprobe timed out")
        return 0.0


# ============================================================================
# MAIN CELERY TASK
# ============================================================================

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_meeting(self, meeting_id: str):
    """
    ✅ PRODUCTION: Main task to process a meeting end-to-end
    
    Pipeline:
    1. Download audio from Azure Blob
    2. Convert to WAV (16kHz mono)
    3. Get audio duration
    4. Load glossary (optional)
    5. Transcribe with Azure Speech
    6. ✨ Advanced speaker diarization
    7. Apply term corrections
    8. Evaluate transcript accuracy (if reference provided)
    9. Generate Minutes of Meeting
    10. Evaluate MoM quality
    11. Save all results to database
    12. Cleanup temporary files
    
    Args:
        meeting_id: UUID of meeting to process
    """
    print(f"\n{'='*70}")
    print(f"🚀 STARTING MEETING PROCESSING: {meeting_id}")
    print(f"{'='*70}\n")
    
    logger.info(f"{'='*70}")
    logger.info(f"Meeting processing started: {meeting_id}")
    logger.info(f"Task attempt: {self.request.retries + 1}/{self.max_retries + 1}")
    logger.info(f"{'='*70}")

    db = SessionLocal()
    meeting = None
    temp_dir = "temp_files"
    local_audio_path = None
    wav_path = None
    glossary_text = ""
    start_time = datetime.utcnow()

    try:
        # ✅ Ensure temp directory exists
        os.makedirs(temp_dir, exist_ok=True)

        # ============================================
        # STEP 1: Get Meeting from Database
        # ============================================
        logger.info("Step 1/12: Fetching meeting from database...")
        meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
        
        if not meeting:
            raise ValueError(f"Meeting {meeting_id} not found in database")
        
        logger.info(f"✅ Meeting found: {meeting.title}")

        # ============================================
        # STEP 2: Update Status to Processing
        # ============================================
        logger.info("Step 2/12: Updating meeting status...")
        meeting.status = "processing"
        db.commit()
        logger.info("✅ Status updated to 'processing'")

        # ============================================
        # STEP 3: Download Audio from Blob
        # ============================================
        logger.info("Step 3/12: Downloading audio from Azure Blob...")
        file_ext = meeting.audio_path.split(".")[-1]
        local_audio_path = os.path.join(temp_dir, f"{meeting_id}.{file_ext}")

        download_file_from_blob("audio", meeting.audio_path, local_audio_path)

        if not os.path.exists(local_audio_path):
            raise FileNotFoundError(f"Audio file not found after download: {local_audio_path}")
        
        file_size_mb = os.path.getsize(local_audio_path) / (1024 * 1024)
        logger.info(f"✅ Audio downloaded: {file_size_mb:.2f} MB")

        # ============================================
        # STEP 4: Convert to WAV
        # ============================================
        logger.info("Step 4/12: Converting audio to WAV format...")
        wav_path = convert_to_wav(local_audio_path)
        logger.info(f"✅ WAV conversion complete: {wav_path}")

        # ============================================
        # STEP 5: Get Audio Duration
        # ============================================
        logger.info("Step 5/12: Getting audio duration...")
        real_duration = get_audio_duration(wav_path)
        logger.info(f"✅ Duration: {real_duration:.2f} seconds ({real_duration/60:.2f} minutes)")

        # ============================================
        # STEP 6: Load Glossary (Optional)
        # ============================================
        logger.info("Step 6/12: Loading glossary...")
        if meeting.glossary_path:
            try:
                glossary_local_path = os.path.join(temp_dir, f"{meeting_id}_glossary.json")
                download_file_from_blob("glossary", meeting.glossary_path, glossary_local_path)

                if os.path.exists(glossary_local_path):
                    with open(glossary_local_path, "r", encoding="utf-8") as f:
                        glossary_text = f.read()
                    os.remove(glossary_local_path)
                    logger.info(f"✅ Glossary loaded successfully")
                else:
                    logger.warning("⚠️ Glossary file not found after download")
            except Exception as e:
                logger.warning(f"⚠️ Failed to load glossary (continuing without it): {e}")
                glossary_text = ""
        else:
            logger.info("ℹ️ No glossary provided")

        # ============================================
        # STEP 7: Transcription
        # ============================================
        logger.info("Step 7/12: Starting transcription with Azure Speech...")
        result = transcribe_audio(wav_path)
        transcript = result.get("segments", [])

        if not transcript:
            raise ValueError("Transcription returned empty segments")
        
        logger.info(f"✅ Transcription complete: {len(transcript)} segments")
        print(f"📝 Transcript segments: {len(transcript)}")

        # ============================================
        # STEP 8: ADVANCED DIARIZATION (NEW!)
        # ============================================
        logger.info("Step 8/12: Advanced speaker diarization...")
        try:
            diar_result = production_diarization_pipeline(wav_path, transcript)
            
            transcript = diar_result['segments']  # Use enhanced segments
            lang_info = diar_result['language_info']
            qa_score = diar_result['quality_assurance']['overall_score']
            
            logger.info(f"✅ Diarization complete:")
            logger.info(f"   Language: {lang_info['primary_language']}")
            logger.info(f"   Speakers: {len(set(s['speaker'] for s in transcript))}")
            logger.info(f"   QA Score: {qa_score}/100")
            print(f"🎙️ Speakers: {len(set(s['speaker'] for s in transcript))}")
            print(f"🌍 Language: {lang_info['primary_language']}")
            
            # Store language info
            meeting.correction_log = {
                "language_detected": lang_info['primary_language'],
                "diarization_qa_score": qa_score,
                "unique_speakers": len(set(s['speaker'] for s in transcript))
            }
            
        except Exception as e:
            logger.warning(f"⚠️ Diarization failed, continuing with basic transcription: {e}")
            # Continue without advanced diarization

        # ============================================
        # STEP 9: Apply Term Corrections
        # ============================================
        logger.info("Step 9/12: Applying term corrections...")
        corrected_transcript, correction_log, correction_stats = correct_transcript(
            transcript,
            glossary_path=meeting.glossary_path
        )
        
        logger.info(f"✅ Corrections applied:")
        logger.info(f"   Total words: {correction_stats['total_checked']}")
        logger.info(f"   Corrected: {correction_stats['total_corrected']}")
        logger.info(f"   Rate: {correction_stats['correction_rate']*100:.1f}%")
        print(f"✏️ Terms corrected: {correction_stats['total_corrected']}")

        # Combine transcript for accuracy evaluation
        predicted_text = " ".join([seg.get("text", "") for seg in corrected_transcript])

        transcript_accuracy = None

        # ============================================
        # STEP 10: Evaluate Transcript (Optional)
        # ============================================
        logger.info("Step 10/12: Evaluating transcript accuracy...")
        if meeting.reference_path:
            try:
                reference_local_path = os.path.join(temp_dir, f"{meeting_id}_reference.txt")
                download_file_from_blob("reference", meeting.reference_path, reference_local_path)

                if os.path.exists(reference_local_path):
                    with open(reference_local_path, "r", encoding="utf-8") as f:
                        reference_text = f.read()

                    transcript_accuracy = evaluate_transcription(reference_text, predicted_text)
                    logger.info(f"✅ Transcript accuracy: {transcript_accuracy*100:.2f}%")
                    print(f"🎯 Accuracy: {transcript_accuracy*100:.2f}%")

                    os.remove(reference_local_path)
                else:
                    logger.warning("⚠️ Reference file not found after download")
            except Exception as e:
                logger.warning(f"⚠️ Failed to evaluate transcript: {e}")
                transcript_accuracy = None
        else:
            logger.info("ℹ️ No reference transcript provided")

        meeting.transcript_accuracy = transcript_accuracy

        # ============================================
        # STEP 11: Generate Minutes of Meeting
        # ============================================
        logger.info("Step 11/12: Generating Minutes of Meeting...")
        mom_json_string = generate_mom(corrected_transcript, glossary_text)

        try:
            mom_dict = json.loads(mom_json_string)
            
            # Count extracted items
            decisions_count = len(mom_dict.get("Decisions", []))
            actions_count = len(mom_dict.get("Action Items", []))
            
            logger.info(f"✅ MoM generated successfully:")
            logger.info(f"   Decisions: {decisions_count}")
            logger.info(f"   Action Items: {actions_count}")
            print(f"📋 Decisions: {decisions_count}")
            print(f"📋 Actions: {actions_count}")
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ Invalid MoM JSON: {e}")
            logger.error(f"Raw output: {mom_json_string[:500]}")
            raise ValueError(f"MoM generation returned invalid JSON: {str(e)}")

        # ============================================
        # STEP 12: Evaluate MoM Quality
        # ============================================
        logger.info("Step 12/12: Evaluating MoM quality...")
        evaluation_score = evaluate_action_items(mom_dict)
        logger.info(f"✅ MoM Quality Score: {evaluation_score*100:.2f}%")
        print(f"⭐ MoM Quality: {evaluation_score*100:.2f}%")

        # ============================================
        # FINAL: Save Results to Database
        # ============================================
        logger.info("Saving all results to database...")
        
        # ✅ FIX: Clean non-serializable data (numpy arrays from diarization)
        logger.info("Cleaning non-serializable data...")
        corrected_transcript = clean_non_serializable_data(corrected_transcript)
        correction_log = clean_non_serializable_data(correction_log)
        correction_stats = clean_non_serializable_data(correction_stats)
        mom_dict = clean_non_serializable_data(mom_dict)
        logger.info("✅ Data cleaned successfully")
        
        meeting.transcript = corrected_transcript
        meeting.mom = mom_dict
        meeting.duration = real_duration
        meeting.correction_log = correction_log
        meeting.correction_stats = correction_stats
        meeting.evaluation_score = evaluation_score
        meeting.status = "ready"

        db.commit()
        
        # Calculate total processing time
        end_time = datetime.utcnow()
        processing_time = (end_time - start_time).total_seconds()
        
        logger.info(f"\n{'='*70}")
        logger.info(f"✅ MEETING PROCESSING COMPLETED SUCCESSFULLY")
        logger.info(f"Processing time: {processing_time:.2f} seconds ({processing_time/60:.2f} minutes)")
        logger.info(f"{'='*70}\n")
        
        print(f"\n{'='*70}")
        print(f"✅ PROCESSING COMPLETE for meeting: {meeting_id}")
        print(f"Total time: {processing_time:.2f} seconds")
        print(f"{'='*70}\n")

    except Exception as e:
        # ============================================
        # ERROR HANDLING & RETRY LOGIC
        # ============================================
        error_msg = str(e)
        error_type = type(e).__name__
        
        logger.error(f"\n{'='*70}")
        logger.error(f"❌ ERROR PROCESSING MEETING: {meeting_id}")
        logger.error(f"Error Type: {error_type}")
        logger.error(f"Error Message: {error_msg}")
        logger.error(f"Stack Trace:\n{traceback.format_exc()}")
        logger.error(f"{'='*70}\n")
        
        print(f"❌ ERROR: {error_msg}")

        # Update meeting status
        if meeting:
            meeting.status = "failed"
            meeting.correction_log = {
                "error": error_msg,
                "error_type": error_type,
                "timestamp": datetime.utcnow().isoformat(),
                "attempt": self.request.retries + 1
            }
            try:
                db.commit()
            except Exception as db_error:
                logger.error(f"Failed to save error status to DB: {db_error}")

        # Retry logic for transient errors
        retryable_errors = [
            "ConnectionError",
            "TimeoutError",
            "HTTPError",
            "ServiceBusyError"
        ]
        
        should_retry = (
            error_type in retryable_errors and 
            self.request.retries < self.max_retries
        )
        
        if should_retry:
            logger.info(f"🔄 Retrying task (attempt {self.request.retries + 1}/{self.max_retries})")
            print(f"🔄 Retrying... (attempt {self.request.retries + 1}/{self.max_retries})")
            raise self.retry(exc=e, countdown=60)  # Retry after 60 seconds
        else:
            logger.critical(f"❌ Task failed permanently. No more retries.")

    finally:
        # ============================================
        # CLEANUP TEMPORARY FILES
        # ============================================
        try:
            logger.info("Cleaning up temporary files...")
            
            if local_audio_path and os.path.exists(local_audio_path):
                os.remove(local_audio_path)
                logger.info("✅ Cleaned up local audio file")

            if wav_path and os.path.exists(wav_path):
                os.remove(wav_path)
                logger.info("✅ Cleaned up WAV file")
                
        except Exception as cleanup_error:
            logger.error(f"⚠️ Cleanup error: {cleanup_error}")

        # Always close database connection
        try:
            db.close()
            logger.info("✅ Database connection closed")
        except Exception as db_close_error:
            logger.error(f"⚠️ Failed to close database: {db_close_error}")