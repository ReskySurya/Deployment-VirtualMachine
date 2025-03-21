import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from typing import List, Any
import json
from pydantic import field_validator

# Load .env file
load_dotenv()

def parse_cors_origins(v: str) -> List[str]:
    """Parse a comma-separated string of origins into a list."""
    if not v:
        return ["http://localhost:3000", "http://localhost:8000"]
    return [origin.strip() for origin in v.split(",") if origin.strip()]

class Settings(BaseSettings):
    # Database settings
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "postgres")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "cloud_management")
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "debcb3128021bbb723876a32eef60b8691d5af196432d287984174b745c7fbe7")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    
    # Encryption key for credential storage
    CREDENTIALS_ENCRYPTION_KEY: str = os.getenv("CREDENTIALS_ENCRYPTION_KEY", "21260ca6f57ffe8fde0c6a92fb9e077732065788578ab609e3bfccad7218e0b5")
    
    # Terraform Settings
    TERRAFORM_PATH: str = os.getenv("TERRAFORM_PATH", os.path.join(os.path.dirname(os.path.dirname(__file__)), "terraform"))
    
    # App Settings
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "production")
    
    # API Settings
    API_PREFIX: str = os.getenv("API_PREFIX", "/api/v1")
    PROJECT_NAME: str = os.getenv("PROJECT_NAME", "Cloud VM Management API")
    PROJECT_VERSION: str = os.getenv("PROJECT_VERSION", "0.1.0")
    PROJECT_DESCRIPTION: str = os.getenv("PROJECT_DESCRIPTION", "API untuk mengelola virtual machine di berbagai cloud provider")
    
    # CORS Settings
    # Gunakan Any untuk menghindari validasi type saat runtime
    CORS_ORIGINS: Any = None
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "env_prefix": "",
        "extra": "allow",  # Mengizinkan atribut tambahan
    }
    
    # Database URL
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

# Buat instance Settings
settings = Settings()

# Set nilai CORS_ORIGINS
cors_origins_env = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8000")
settings.CORS_ORIGINS = parse_cors_origins(cors_origins_env)