from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum
from app.database import Base
from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional, Dict, Any, List
import json
from datetime import datetime

# Import model VM
from app.vm.models import VM

class CredentialType(str, enum.Enum):
    AWS = "aws"
    GCP = "gcp"

class Credential(Base):
    __tablename__ = "credentials"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    type = Column(Enum(CredentialType))
    encrypted_data = Column(Text)  # Encrypted credentials
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationship
    user = relationship("User", back_populates="credentials")
    vms = relationship("VM", back_populates="credential")
    events = relationship("Event", back_populates="credential")

# Pydantic models for API
class CredentialBase(BaseModel):
    name: str
    type: CredentialType

class AWSCredentialCreate(CredentialBase):
    type: CredentialType = CredentialType.AWS
    access_key: str
    secret_key: str
    region: str
    

class GCPCredentialCreate(CredentialBase):
    type: CredentialType = CredentialType.GCP
    project_id: str
    private_key_id: str
    private_key: str
    client_email: str
    client_id: str
    auth_uri: str = "https://accounts.google.com/o/oauth2/auth"
    token_uri: str = "https://oauth2.googleapis.com/token"
    auth_provider_x509_cert_url: str = "https://www.googleapis.com/oauth2/v1/certs"
    client_x509_cert_url: Optional[str] = None

class CredentialCreate(BaseModel):
    name: str
    type: CredentialType
    aws_credentials: Optional[AWSCredentialCreate] = None
    gcp_credentials: Optional[GCPCredentialCreate] = None
    
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        json_schema_extra={
            "examples": [
                {
                    "name": "AWS Credential Saya",
                    "type": "aws",
                    "aws_credentials": {
                        "access_key": "AKIAIOSFODNN7EXAMPLE",
                        "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                        "region": "us-east-1"
                    }
                },
                {
                    "name": "GCP Credential Saya",
                    "type": "gcp",
                    "gcp_credentials": {
                        "project_id": "your-project-id",
                        "private_key_id": "key-id",
                        "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
                        "client_email": "service-account@project-id.iam.gserviceaccount.com",
                        "client_id": "client-id"
                    }
                }
            ]
        }
    )
    
    @field_validator('aws_credentials')
    def validate_aws_credentials(cls, v, info):
        values = info.data
        if 'type' in values and values['type'] == CredentialType.AWS and v is None:
            raise ValueError("AWS credentials required when type is 'aws'")
        if 'type' in values and values['type'] != CredentialType.AWS and v is not None:
            raise ValueError("AWS credentials should only be provided when type is 'aws'")
        return v
    
    @field_validator('gcp_credentials')
    def validate_gcp_credentials(cls, v, info):
        values = info.data
        if 'type' in values and values['type'] == CredentialType.GCP and v is None:
            raise ValueError("GCP credentials required when type is 'gcp'")
        if 'type' in values and values['type'] != CredentialType.GCP and v is not None:
            raise ValueError("GCP credentials should only be provided when type is 'gcp'")
        return v

class CredentialResponse(CredentialBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

class CredentialListResponse(BaseModel):
    credentials: List[CredentialResponse]
    total: int