import os
import json
import logging
from fastapi import APIRouter, UploadFile, File, Form, Depends, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from uuid import uuid4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter
from docx import Document

from ..database import SessionLocal
from ..models import Meeting
from backend.worker.tasks import process_meeting
from backend.app.services.azure_blob_storage import upload_file_to_blob
from backend.app.services.azure_search import upload_glossary_to_search

router = APIRouter()
logger = logging.getLogger(__name__)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ================================================================
# ✅ FIXED: list_meetings is NOW FIRST — before /{meeting_id}
#    Without this, FastAPI matches "/" against "/{meeting_id}"
#    and list_meetings() is never called.
# ================================================================
@router.get("/")
def list_meetings(db: Session = Depends(get_db)):
    meetings = db.query(Meeting).order_by(Meeting.created_at.desc()).all()
    return [
        {
            "id":         str(m.id),
            "title":      m.title,
            "status":     m.status,
            "attendees":  m.attendees,
            "duration":   m.duration,
            "created_at": m.created_at.isoformat() if m.created_at else None
        }
        for m in meetings
    ]


# ================================================================
# UPLOAD
# ================================================================
@router.post("/upload")
async def upload_meeting(
    title:     str        = Form(...),
    attendees: str        = Form(""),
    audio:     UploadFile = File(None),
    glossary:  UploadFile = File(None),
    reference: UploadFile = File(None),
    db:        Session    = Depends(get_db)
):
    if not audio:
        raise HTTPException(status_code=400, detail="Audio file is required")

    meeting_id = uuid4()

    # ── Upload audio ─────────────────────────────────────────────
    audio_key = f"{meeting_id}_{audio.filename}"
    upload_file_to_blob(audio, "audio", audio_key)

    # ── Upload glossary (optional) ───────────────────────────────
    glossary_key = None
    if glossary:
        if not glossary.filename.endswith(".json"):
            raise HTTPException(status_code=400, detail="Glossary must be a .json file")

        glossary_key = f"glossary/{meeting_id}_{glossary.filename}"
        upload_file_to_blob(glossary, "glossary", glossary_key)

        # Push terms to Azure Cognitive Search for correction.py
        glossary.file.seek(0)
        glossary_data = json.load(glossary.file)
        upload_glossary_to_search(glossary_data, meeting_id)

    # ── Upload reference transcript (optional) ───────────────────
    reference_key = None
    if reference:
        if not reference.filename.endswith(".txt"):
            raise HTTPException(status_code=400, detail="Reference must be a .txt file")

        reference_key = f"reference/{meeting_id}_{reference.filename}"
        upload_file_to_blob(reference, "reference", reference_key)

    # ── Save meeting record to DB ────────────────────────────────
    new_meeting = Meeting(
        id             = meeting_id,
        title          = title,
        audio_path     = audio_key,
        glossary_path  = glossary_key,
        reference_path = reference_key,
        attendees      = attendees,
        status         = "processing"
    )
    db.add(new_meeting)
    db.commit()

    # ── Queue Celery task ────────────────────────────────────────
    process_meeting.delay(str(meeting_id))

    return {
        "message":    "Uploaded successfully",
        "meeting_id": str(meeting_id)
    }


# ================================================================
# GET SINGLE MEETING
# ================================================================
@router.get("/{meeting_id}")
def get_meeting(meeting_id: str, db: Session = Depends(get_db)):
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()

    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    return {
        "id":                  str(meeting.id),
        "title":               meeting.title,
        "status":              meeting.status,
        "transcript":          meeting.transcript,
        "mom":                 meeting.mom,
        "attendees":           meeting.attendees,
        "duration":            meeting.duration,
        "evaluation_score":    meeting.evaluation_score,
        "transcript_accuracy": meeting.transcript_accuracy,
        "correction_stats":    meeting.correction_stats,
        "correction_log":      meeting.correction_log,
        "created_at":          meeting.created_at.isoformat() if meeting.created_at else None
    }


# ================================================================
# GET CORRECTIONS
# ✅ FIXED: added 404 guard — was crashing on None.correction_log
# ================================================================
@router.get("/{meeting_id}/corrections")
def get_corrections(meeting_id: str, db: Session = Depends(get_db)):
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()

    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    return {"corrections": meeting.correction_log}


# ================================================================
# DOWNLOAD PDF
# ✅ FIXED: temp file is deleted after response via BackgroundTasks
# ================================================================
@router.get("/{meeting_id}/pdf")
def download_pdf(
    meeting_id:       str,
    background_tasks: BackgroundTasks,
    db:               Session = Depends(get_db)
):
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()

    if not meeting or meeting.status != "ready":
        raise HTTPException(status_code=400, detail="Meeting not ready")

    file_path = f"/tmp/{meeting_id}_mom.pdf"

    doc      = SimpleDocTemplate(file_path, pagesize=letter)
    styles   = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph(f"Meeting Title: {meeting.title}", styles["Heading1"]))
    elements.append(Spacer(1, 20))
    elements.append(Paragraph("Minutes of Meeting:", styles["Heading2"]))
    elements.append(Spacer(1, 15))

    mom_data = meeting.mom  # SQLAlchemy JSON column → already a dict

    if mom_data:
        for section, content in mom_data.items():
            elements.append(Paragraph(section, styles["Heading3"]))
            elements.append(Spacer(1, 10))

            if isinstance(content, list) and content:
                for item in content:
                    if isinstance(item, dict):
                        text = ", ".join([f"{k}: {v}" for k, v in item.items()])
                    else:
                        text = str(item)
                    elements.append(Paragraph(f"- {text}", styles["Normal"]))
                    elements.append(Spacer(1, 5))
            else:
                elements.append(Paragraph("No data available.", styles["Normal"]))
                elements.append(Spacer(1, 5))

            elements.append(Spacer(1, 15))

    doc.build(elements)

    # ✅ Clean up temp file after response is sent
    background_tasks.add_task(os.remove, file_path)

    return FileResponse(
        path       = file_path,
        media_type = "application/pdf",
        filename   = f"{meeting.title}_mom.pdf"
    )


# ================================================================
# DOWNLOAD DOCX
# ✅ FIXED: safe mom parsing (already dict from SQLAlchemy)
# ✅ FIXED: bare except replaced with typed except + logging
# ================================================================
@router.get("/{meeting_id}/docx")
def download_docx(
    meeting_id:       str,
    background_tasks: BackgroundTasks,
    db:               Session = Depends(get_db)
):
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()

    if not meeting or meeting.status != "ready":
        raise HTTPException(status_code=400, detail="Meeting not ready")

    os.makedirs("/tmp/docx", exist_ok=True)
    file_path = f"/tmp/docx/{meeting_id}_mom.docx"

    doc = Document()
    doc.add_heading(f"Meeting Title: {meeting.title}", level=1)
    doc.add_paragraph("")

    try:
        # ✅ FIXED: mom is already a dict (SQLAlchemy deserializes JSON columns)
        mom_data = meeting.mom if isinstance(meeting.mom, dict) else json.loads(meeting.mom)

        for section, content in mom_data.items():
            doc.add_heading(section, level=2)

            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        doc.add_paragraph(f"Task: {item.get('task', '')}", style="List Bullet")
                        doc.add_paragraph(f"Owner: {item.get('owner', '')}")
                        doc.add_paragraph(f"Due Date: {item.get('due_date', '')}")
                        doc.add_paragraph(f"Priority: {item.get('priority', '')}")
                    else:
                        doc.add_paragraph(str(item), style="List Bullet")
            else:
                doc.add_paragraph(str(content))

    except (json.JSONDecodeError, TypeError) as e:
        # ✅ FIXED: log the error instead of silently swallowing it
        logger.error(f"Failed to parse MoM data for meeting {meeting_id}: {e}")
        doc.add_paragraph(str(meeting.mom))

    doc.save(file_path)

    # ✅ Clean up temp file after response is sent
    background_tasks.add_task(os.remove, file_path)

    return FileResponse(
        path       = file_path,
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename   = f"{meeting.title}_mom.docx"
    )