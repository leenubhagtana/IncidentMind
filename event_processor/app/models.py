from datetime import datetime

from sqlalchemy import Column, String, DateTime, JSON

from app.database import Base


class Event(Base):
    __tablename__ = "events"

    event_id = Column(String, primary_key=True)
    event_type = Column(String, nullable=False)
    service = Column(String, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    data = Column(JSON, nullable=False)