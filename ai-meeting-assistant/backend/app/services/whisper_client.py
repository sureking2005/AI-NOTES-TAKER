import os
import logging
import requests

logger = logging.getLogger(__name__)

WHISPER_VM_URL = os.getenv("WHISPER_VM_URL", "http://localhost:8079")

# (connect_timeout, read_timeout)
TIMEOUT = (10, 1800)


def transcribe_audio(audio_path: str, glossary_path: str = None):
    """
    Sends audio to Whisper VM and returns transcription result.
    """

    logger.info(f"Sending audio to Whisper VM: {WHISPER_VM_URL}")

    # ---------------------------------------------------
    # Health Check
    # ---------------------------------------------------

    try:
        health = requests.get(
            f"{WHISPER_VM_URL}/health",
            timeout=10
        )

        health.raise_for_status()

        logger.info(f"VM health OK: {health.json()}")

    except Exception as e:
        raise ConnectionError(
            f"Cannot reach Whisper VM at {WHISPER_VM_URL}: {e}"
        )

    # ---------------------------------------------------
    # Validate audio
    # ---------------------------------------------------

    if not os.path.exists(audio_path):
        raise FileNotFoundError(audio_path)

    file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)

    logger.info(f"Audio size: {file_size_mb:.2f} MB")

    # ---------------------------------------------------
    # Send request
    # ---------------------------------------------------

    try:

        with open(audio_path, "rb") as f:

            files = {
                "audio": (
                    os.path.basename(audio_path),
                    f,
                    "audio/wav"
                )
            }

            logger.info("Sending POST request to VM /transcribe")

            response = requests.post(
                f"{WHISPER_VM_URL}/transcribe",
                files=files,
                data={"language": "hi"},
                timeout=TIMEOUT
            )

        logger.info(f"Response received: {response.status_code}")

        response.raise_for_status()

    except requests.exceptions.Timeout:
        raise TimeoutError(
            "Whisper VM transcription timed out"
        )

    except requests.exceptions.ConnectionError as e:
        raise ConnectionError(
            f"Connection lost to Whisper VM: {e}"
        )

    except requests.exceptions.RequestException as e:
        raise RuntimeError(
            f"Whisper VM request failed: {e}"
        )

    # ---------------------------------------------------
    # Parse JSON
    # ---------------------------------------------------

    try:

        raw_text = response.text

        logger.info(f"Response length: {len(raw_text)} bytes")
        logger.info(f"Response preview: {raw_text[:200]}")

        result = response.json()

    except Exception as e:

        logger.error("Failed to parse VM JSON response")
        logger.error(response.text[:500])

        raise RuntimeError(
            f"Invalid JSON from Whisper VM: {e}"
        )

    # ---------------------------------------------------
    # Validate result
    # ---------------------------------------------------

    if "error" in result:
        raise RuntimeError(result["error"])

    segments = result.get("segments")
    metadata = result.get("metadata", {})

    if segments is None:
        raise RuntimeError(
            "Whisper VM response missing 'segments'"
        )

    # ---------------------------------------------------
    # Clean segments
    # ---------------------------------------------------

    cleaned_segments = []

    for i, seg in enumerate(segments):

        cleaned_segments.append({
            "id": seg.get("id", str(i)),
            "speaker": seg.get("speaker", "Speaker Unknown"),
            "start": float(seg.get("start", 0)),
            "end": float(seg.get("end", 0)),
            "text": seg.get("text", "").strip(),
            "confidence": seg.get("confidence", None)
        })

    result["segments"] = cleaned_segments

    logger.info(
        f"Whisper transcription complete: "
        f"{len(cleaned_segments)} segments"
    )

    return result