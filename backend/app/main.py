from fastapi import FastAPI, Request, status, Depends, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import os
from sqlalchemy.orm import Session
from datetime import datetime
from sqlalchemy import text

from app.auth.router import router as auth_router
from app.credentials.router import router as credentials_router
from app.vm.router import router as vm_router
from app.database import engine, Base, get_db
from app.users.router import router as users_router
from app.history.router import router as history_router
from app.history.middleware import HistoryMiddleware
from app.config import settings

# Import models for creating tables
from app.users.models import User
from app.credentials.models import Credential
from app.vm.models import VM
from app.history.models import Event

# Buat tabel database jika belum ada
Base.metadata.create_all(bind=engine)

# API router with global prefix
api_router = APIRouter(prefix="/api/v1")

# Tambahkan router ke API v1
api_router.include_router(auth_router)
api_router.include_router(credentials_router, prefix="/credentials", tags=["credentials"])
api_router.include_router(vm_router, prefix="/vms", tags=["vms"])
api_router.include_router(users_router)
api_router.include_router(history_router)

app = FastAPI(
    title=settings.PROJECT_NAME if hasattr(settings, 'PROJECT_NAME') else "Cloud VM Management API",
    description=settings.PROJECT_DESCRIPTION if hasattr(settings, 'PROJECT_DESCRIPTION') else "API untuk mengelola virtual machine di berbagai cloud provider",
    version=settings.PROJECT_VERSION if hasattr(settings, 'PROJECT_VERSION') else "0.1.0",
)

# Konfigurasi CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Tambahkan frontend URL secara eksplisit
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tambahkan middleware history
app.add_middleware(
    HistoryMiddleware,
    exclude_paths=["/docs", "/redoc", "/openapi.json", "/", "/health", "/api/v1/docs", "/api/v1/redoc", "/api/v1/openapi.json"],
    exclude_methods=["OPTIONS"]
)

# Include API router
app.include_router(api_router)

# Exception handler global
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors(), "body": exc.body},
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"Terjadi kesalahan internal: {str(exc)}"},
    )

# Health check endpoint
@app.get("/health", tags=["health"])
async def health_check(db: Session = Depends(get_db)):
    # Cek koneksi database
    try:
        # Eksekusi query sederhana dengan text() untuk SQLAlchemy yang lebih baru
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    return {
        "status": "healthy",
        "version": settings.PROJECT_VERSION,
        "timestamp": datetime.now().isoformat(),
        "database": db_status
    }

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "Selamat datang di Cloud VM Management API",
        "version": settings.PROJECT_VERSION,
        "docs": "/docs",
        "api": "/api/v1"
    }

# Kustomisasi dokumentasi OpenAPI
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
