from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Enum as SQLEnum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from enum import Enum
from app.database import Base
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime

class VMStatus(str, Enum):
    CREATING = "creating"
    RUNNING = "running"
    STOPPED = "stopped"
    TERMINATED = "terminated"
    FAILED = "failed"

class VMProvider(str, Enum):
    AWS = "aws"
    GCP = "gcp"

class VM(Base):
    __tablename__ = "vms"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    provider = Column(SQLEnum(VMProvider))
    status = Column(SQLEnum(VMStatus), default=VMStatus.CREATING)
    instance_id = Column(String, nullable=True)  # Cloud provider instance ID
    instance_type = Column(String)  # e.g., t2.micro for AWS
    region = Column(String)  # e.g., us-east-1
    public_ip = Column(String, nullable=True)
    private_ip = Column(String, nullable=True)
    
    # Foreign keys
    credential_id = Column(Integer, ForeignKey("credentials.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    credential = relationship("Credential", back_populates="vms")
    user = relationship("User", back_populates="vms")
    events = relationship("Event", back_populates="vm")

# Pydantic models for API
class VMBase(BaseModel):
    name: str
    provider: VMProvider
    instance_type: str
    region: str
    credential_id: int
    
    model_config = ConfigDict(arbitrary_types_allowed=True)

class VMCreate(VMBase):
    pass

class VMResponse(VMBase):
    id: int
    status: VMStatus
    instance_id: Optional[str] = None
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

class VMListResponse(BaseModel):
    vms: List[VMResponse]
    total: int
    
    model_config = ConfigDict(arbitrary_types_allowed=True)
