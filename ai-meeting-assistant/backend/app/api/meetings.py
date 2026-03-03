import os
import shutil
import json
from fastapi import APIRouter, UploadFile, File, Form, Depends
from sqlalchemy.orm import Session
from ..database import SessionLocal
from ..models import Meeting
from backend.worker.tasks import process_meeting
from fastapi.responses import FileResponse
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter
from uuid import uuid4
# from backend.app.services.r2_storage import upload_file_to_r2
from backend.app.services.azure_blob_storage import upload_file_to_blob
from backend.app.services.azure_search import upload_glossary_to_search
from docx import Document
from fastapi import HTTPException


router = APIRouter()



def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()









@router.post("/upload")
async def upload_meeting(
    title: str = Form(...),
    attendees: str = Form(""),
    audio: UploadFile = File(None),
    glossary: UploadFile = File(None),
    reference: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    if not audio:
        raise HTTPException(status_code=400, detail="Audio file required")

    meeting_id = uuid4()

    # Upload Audio
    audio_key = f"{meeting_id}_{audio.filename}"
    upload_file_to_blob(audio, "audio", audio_key)

    glossary_key = None

    if glossary:
        if not glossary.filename.endswith(".json"):
            raise HTTPException(status_code=400, detail="Glossary must be .json")

        glossary_key = f"glossary/{meeting_id}_{glossary.filename}"

        # Save to Blob
        upload_file_to_blob(glossary, "glossary", glossary_key)

        # 🔥 AUTO PUSH TO AZURE SEARCH
        glossary.file.seek(0)
        glossary_data = json.load(glossary.file)

        upload_glossary_to_search(glossary_data, meeting_id)

    reference_key = None

    if reference:
        if not reference.filename.endswith(".txt"):
            raise HTTPException(status_code=400, detail="Reference must be .txt")

        reference_key = f"reference/{meeting_id}_{reference.filename}"
        upload_file_to_blob(reference, "reference", reference_key)

    new_meeting = Meeting(
        id=meeting_id,
        title=title,
        audio_path=audio_key,
        glossary_path=glossary_key,
        reference_path=reference_key,
        attendees=attendees,
        status="processing"
    )

    db.add(new_meeting)
    db.commit()

    process_meeting.delay(meeting_id)

    return {
        "message": "Uploaded successfully",
        "meeting_id": str(meeting_id)
    }







# ==========================
# DOWNLOAD PDF
# ==========================
@router.get("/{meeting_id}/pdf")
def download_pdf(meeting_id: str, db: Session = Depends(get_db)):


    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()

    if not meeting or meeting.status != "ready":
        return {"error": "Meeting not ready"}

    file_path = f"{meeting_id}_mom.pdf"

    doc = SimpleDocTemplate(file_path, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph(f"Meeting Title: {meeting.title}", styles["Heading1"]))
    elements.append(Spacer(1, 20))
    elements.append(Paragraph("Minutes of Meeting:", styles["Heading2"]))
    elements.append(Spacer(1, 15))

    mom_data = meeting.mom

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

    print("MOM DATA:", meeting.mom)

    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename="meeting_mom.pdf"
    )






# ==========================
# GET SINGLE MEETING
# ==========================
@router.get("/{meeting_id}")
def get_meeting(meeting_id: str, db: Session = Depends(get_db)):
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()

    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    return {
    "id": str(meeting.id),
    "title": meeting.title,
    "status": meeting.status,
    "transcript": meeting.transcript,
    "mom": meeting.mom,
    "attendees": meeting.attendees,
    "duration": meeting.duration,
    "evaluation_score": meeting.evaluation_score,
    "transcript_accuracy": meeting.transcript_accuracy,
    "correction_stats": meeting.correction_stats,
    "correction_log": meeting.correction_log,
    "created_at": meeting.created_at.isoformat() if meeting.created_at else None
}






# ==========================
# LIST ALL MEETINGS (DASHBOARD)
# ==========================
@router.get("/")
def list_meetings(db: Session = Depends(get_db)):
    meetings = db.query(Meeting).order_by(Meeting.created_at.desc()).all()

    return [
        {
            "id": str(m.id),
            "title": m.title,
            "status": m.status,
            "attendees": m.attendees,
            "duration": m.duration,
            "created_at": m.created_at.isoformat() if m.created_at else None
        }
        for m in meetings
    ]







@router.get("/{meeting_id}/corrections")
def get_corrections(meeting_id: str, db: Session = Depends(get_db)):
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()

    

    return {
        "corrections": meeting.correction_log 
         # store JSON in DB
    }
    














@router.get("/{meeting_id}/docx")
def download_docx(meeting_id: str, db: Session = Depends(get_db)):
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()

    if not meeting or meeting.status != "ready":
        return {"error": "Meeting not ready"}

    temp_dir = "temp_docx"
    os.makedirs(temp_dir, exist_ok=True)

    file_path = os.path.join(temp_dir, f"{meeting_id}_mom.docx")

    doc = Document()

    doc.add_heading(f"Meeting Title: {meeting.title}", level=1)
    doc.add_paragraph("")

    try:
        mom_data = json.loads(meeting.mom)

        for section, content in mom_data.items():
            doc.add_heading(section, level=2)

            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        # Action item formatting
                        doc.add_paragraph(
                            f"Task: {item.get('task')}",
                            style="List Bullet"
                        )
                        doc.add_paragraph(f"Owner: {item.get('owner')}")
                        doc.add_paragraph(f"Due Date: {item.get('due_date')}")
                        doc.add_paragraph(f"Priority: {item.get('priority')}")
                    else:
                        doc.add_paragraph(str(item), style="List Bullet")
            else:
                doc.add_paragraph(str(content))

    except:
        doc.add_paragraph(meeting.mom)

    doc.save(file_path)

    return FileResponse(
        path=file_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="meeting_mom.docx"
    )
