from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from passlib.context import CryptContext
from app.database import Base

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    credentials = relationship("Credential", back_populates="user")
    vms = relationship("VM", back_populates="user")
    events = relationship("Event", back_populates="user")

    @staticmethod
    def verify_password(plain_password, hashed_password):
        try:
            # Coba verifikasi password dengan passlib
            result = pwd_context.verify(plain_password, hashed_password)
            print(f"Password verification result: {result}")
            return result
        except Exception as e:
            # Tangkap dan log error apa pun selama verifikasi
            print(f"Error during password verification: {str(e)}")
            # Return False jika terjadi error
            return False

    @staticmethod
    def get_password_hash(password):
        try:
            # Coba hash password dengan passlib
            result = pwd_context.hash(password)
            print(f"Password hashed successfully")
            return result
        except Exception as e:
            # Tangkap dan log error apa pun selama hashing
            print(f"Error during password hashing: {str(e)}")
            # Re-raise error karena ini tidak boleh gagal
            raise