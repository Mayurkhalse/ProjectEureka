"""SQLAlchemy declarative models for Project EUREKA SQLite datastore."""

from sqlalchemy import Boolean, Column, DateTime, Float, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class MediaEvent(Base):
    __tablename__ = "media_events"

    record_id = Column(String, primary_key=True, index=True)
    district = Column(String, index=True)
    event_type = Column(String, index=True)
    english_content = Column(String, nullable=True)
    event_timestamp = Column(DateTime)
    turnaround_time_mins = Column(Float)
    sentiment_score = Column(Float)
    crisis_resolved = Column(Boolean)
