import uuid
from sqlalchemy import Column, String, Text, DateTime, JSON,Float
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
from .database import Base





class Meeting(Base):
    __tablename__ = "meetings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    audio_path = Column(String, nullable=False)
    transcript = Column(JSON, nullable=True)
    mom = Column(JSON, nullable=True)
    status = Column(String, default="processing")
    created_at = Column(DateTime, default=datetime.utcnow)
    duration = Column(Float)
    attendees = Column(String)
    corrections = Column(JSON)
    glossary_path = Column(String, nullable=True)
    correction_log = Column(JSON, nullable=True)
    correction_stats = Column(JSON, nullable=True)
    evaluation_score = Column(Float, default=0.0)
    # correction_rate = Column(Float, default=0.0)
    reference_path = Column(String, nullable=True)
    transcript_accuracy = Column(Float, nullable=True)

