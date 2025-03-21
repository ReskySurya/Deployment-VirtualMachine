from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Float, JSON, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum
from app.database import Base
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any, List
from datetime import datetime

class EventType(str, enum.Enum):
    # VM Events
    VM_CREATE = "vm_create"
    VM_START = "vm_start"
    VM_STOP = "vm_stop"
    VM_DELETE = "vm_delete"
    VM_STATUS_UPDATE = "vm_status_update"
    
    # Credential Events
    CREDENTIAL_CREATE = "credential_create"
    CREDENTIAL_UPDATE = "credential_update"
    CREDENTIAL_DELETE = "credential_delete"
    CREDENTIAL_VALIDATE = "credential_validate"

class EventStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"
    IN_PROGRESS = "in_progress"

class Event(Base):
    __tablename__ = "events"
    
    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String, index=True)
    status = Column(String, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    vm_id = Column(Integer, ForeignKey("vms.id"), nullable=True, index=True)
    credential_id = Column(Integer, ForeignKey("credentials.id"), nullable=True, index=True)
    
    # Parameters disimpan sebagai JSON
    parameters = Column(JSON, nullable=True)
    # Result disimpan sebagai JSON
    result = Column(JSON, nullable=True)
    # Error message jika ada
    error_message = Column(Text, nullable=True)
    # Durasi eksekusi dalam detik
    duration = Column(Float, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="events")
    vm = relationship("VM", back_populates="events")
    credential = relationship("Credential", back_populates="events")

# Pydantic models for API
class EventBase(BaseModel):
    event_type: EventType
    status: EventStatus
    
class EventCreate(EventBase):
    user_id: int
    vm_id: Optional[int] = None
    credential_id: Optional[int] = None
    parameters: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    duration: Optional[float] = None

class EventResponse(EventBase):
    id: int
    timestamp: datetime
    user_id: int
    vm_id: Optional[int] = None
    credential_id: Optional[int] = None
    parameters: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    duration: Optional[float] = None
    
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

class EventListResponse(BaseModel):
    events: List[EventResponse]
    total: int
    page: int = 1
    page_size: int = 100
    total_pages: int = 1
