import os
import uuid
import time
import json
import azure.cognitiveservices.speech as speechsdk

SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY")
SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION")

if not SPEECH_KEY or not SPEECH_REGION:
    raise RuntimeError("Azure Speech credentials not configured")


def transcribe_audio(audio_path: str):

    # -------------------------------
    # 1️⃣ Configure Speech Service
    # -------------------------------
    speech_config = speechsdk.SpeechConfig(
        subscription=SPEECH_KEY,
        region=SPEECH_REGION
    )

    # Detailed output for better metadata
    speech_config.output_format = speechsdk.OutputFormat.Detailed

    # Force primary language (better stability than auto-detect)
    speech_config.speech_recognition_language = "en-IN"

    # Silence tuning (important for meetings)
    speech_config.set_property(
        speechsdk.PropertyId.SpeechServiceConnection_InitialSilenceTimeoutMs,
        "60000"
    )
    speech_config.set_property(
        speechsdk.PropertyId.SpeechServiceConnection_EndSilenceTimeoutMs,
        "3000"
    )

    audio_config = speechsdk.AudioConfig(filename=audio_path)

    transcriber = speechsdk.transcription.ConversationTranscriber(
        speech_config=speech_config,
        audio_config=audio_config
    )

    # -------------------------------
    # 2️⃣ Phrase Boosting (HIGH IMPACT)
    # -------------------------------
    phrase_list = speechsdk.PhraseListGrammar.from_recognizer(transcriber)

    boosted_phrases = [
        "Redis",
        "PostgreSQL",
        "Kubernetes",
        "Azure",
        "DevOps",
        "Sprint",
        "Scrum",
        "CI/CD",
        "API",
        "FastAPI",
        "Celery",
        "Docker",
        "deployment",
        "production",
        "backend",
        "frontend",
        "deadline",
        "deliverable"
    ]

    for phrase in boosted_phrases:
        phrase_list.addPhrase(phrase)

    # -------------------------------
    # 3️⃣ Collect Results
    # -------------------------------
    transcript_segments = []
    done = False
    total_duration = 0

    def recognized(evt):
        nonlocal total_duration

        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:

            start_sec = evt.result.offset / 10_000_000
            duration_sec = evt.result.duration / 10_000_000
            end_sec = start_sec + duration_sec

            total_duration = max(total_duration, end_sec)

            speaker_id = evt.result.speaker_id or "Unknown"

            # Extract confidence if available
            confidence = None
            try:
                json_result = evt.result.properties.get(
                    speechsdk.PropertyId.SpeechServiceResponse_JsonResult
                )
                if json_result:
                    parsed = json.loads(json_result)
                    confidence = parsed.get("NBest", [{}])[0].get("Confidence")
            except Exception:
                confidence = None

            transcript_segments.append({
                "id": str(uuid.uuid4()),
                "speaker": f"Speaker {speaker_id}",
                "start": round(start_sec, 2),
                "end": round(end_sec, 2),
                "text": evt.result.text.strip(),
                "confidence": round(confidence, 3) if confidence else None
            })

    def stop_cb(evt):
        nonlocal done
        done = True

    transcriber.transcribed.connect(recognized)
    transcriber.session_stopped.connect(stop_cb)
    transcriber.canceled.connect(stop_cb)

    # -------------------------------
    # 4️⃣ Start Transcription
    # -------------------------------
    transcriber.start_transcribing_async()

    while not done:
        time.sleep(0.1)

    transcriber.stop_transcribing_async()

    # -------------------------------
    # 5️⃣ Metadata
    # -------------------------------
    metadata = {
        "language": "en-IN",
        "duration_seconds": round(total_duration, 2),
        "segment_count": len(transcript_segments)
    }

    return {
        "segments": transcript_segments,
        "metadata": metadata
    }