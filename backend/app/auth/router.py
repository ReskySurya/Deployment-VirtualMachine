from datetime import timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.users.models import User
from app.auth.jwt import create_access_token, get_current_active_user
from app.config import settings
from pydantic import BaseModel, EmailStr, Field, ConfigDict

router = APIRouter(prefix="/auth", tags=["authentication"])

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    
    model_config = ConfigDict(arbitrary_types_allowed=True)

class Token(BaseModel):
    access_token: str
    token_type: str
    user: Optional[dict] = None
    
    model_config = ConfigDict(arbitrary_types_allowed=True)

@router.post("/register", response_model=Token)
def register(user_data: UserCreate, db: Session = Depends(get_db)) -> Any:
    """
    Mendaftarkan pengguna baru
    """
    # Cek apakah username sudah ada
    user_by_username = db.query(User).filter(User.username == user_data.username).first()
    if user_by_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username sudah digunakan"
        )
    
    # Cek apakah email sudah ada
    user_by_email = db.query(User).filter(User.email == user_data.email).first()
    if user_by_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email sudah terdaftar"
        )
    
    # Buat user baru
    hashed_password = User.get_password_hash(user_data.password)
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_password
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Buat token akses
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": new_user.email}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
) -> Any:
    """
    Login untuk mendapatkan token akses
    
    - **username**: Gunakan email Anda di field ini
    - **password**: Password Anda
    """
    user = db.query(User).filter(User.email == form_data.username).first()
    
    if not user or not User.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email atau password salah",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Akun tidak aktif"
        )
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

class LoginRequest(BaseModel):
    username: str  # Email pengguna
    password: str
    
    model_config = ConfigDict(arbitrary_types_allowed=True)

@router.post("/login-json", response_model=Token)
def login_json(
    login_data: LoginRequest,
    db: Session = Depends(get_db)
) -> Any:
    """
    Login dengan JSON body untuk mendapatkan token akses
    
    - **username**: Gunakan email Anda
    - **password**: Password Anda
    """
    print(f"Login request received: {login_data.username}")
    
    # Coba cari user baik dengan email atau username
    user = db.query(User).filter(User.email == login_data.username).first()
    
    # Jika tidak ditemukan dengan email, coba dengan username
    if not user:
        user = db.query(User).filter(User.username == login_data.username).first()
        print(f"Searching by username: {user is not None}")
    else:
        print(f"Found user by email: {user.username}")
    
    # Verifikasi password jika user ditemukan
    if not user or not User.verify_password(login_data.password, user.hashed_password):
        print("Invalid credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email/username atau password salah",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        print("User account not active")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Akun tidak aktif"
        )
    
    print(f"Login successful for user: {user.username}")
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token, 
        "token_type": "bearer", 
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_active": user.is_active,
            "is_admin": user.is_admin
        }
    }

class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    is_active: bool
    is_admin: bool
    
    model_config = ConfigDict(arbitrary_types_allowed=True)

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """
    Mendapatkan informasi pengguna yang terautentikasi
    """
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "is_active": current_user.is_active,
        "is_admin": current_user.is_admin
    }