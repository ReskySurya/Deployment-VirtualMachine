import time
from typing import Callable, Dict, Any
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import json
import logging

from app.database import get_db
from app.history.service import HistoryService
from app.history.models import EventType, EventStatus
from app.auth.jwt import get_current_user

logger = logging.getLogger(__name__)

class HistoryMiddleware(BaseHTTPMiddleware):
    """
    Middleware untuk mencatat history request API secara otomatis.
    
    Middleware ini akan:
    1. Mencatat endpoint yang diakses
    2. Mencatat method (GET, POST, PUT, DELETE)
    3. Mencatat parameter request
    4. Mencatat response
    5. Mencatat error jika terjadi
    6. Menghitung durasi request
    """
    
    def __init__(
        self, 
        app: ASGIApp,
        exclude_paths: list = None,
        exclude_methods: list = None
    ):
        """
        Inisialisasi middleware
        
        Args:
            app: Aplikasi ASGI
            exclude_paths: Path yang tidak perlu dicatat (misalnya /docs, /redoc)
            exclude_methods: Method yang tidak perlu dicatat (misalnya OPTIONS)
        """
        super().__init__(app)
        self.exclude_paths = exclude_paths or ["/docs", "/redoc", "/openapi.json"]
        self.exclude_methods = exclude_methods or ["OPTIONS"]
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip jika path atau method di-exclude
        if self._should_skip_logging(request):
            return await call_next(request)
        
        # Catat waktu mulai
        start_time = time.time()
        
        # Dapatkan user_id dari token (jika ada)
        user_id = await self._get_user_id(request)
        
        # Dapatkan event type berdasarkan path dan method
        event_type = self._get_event_type(request)
        
        # Dapatkan parameter request
        params = await self._get_request_params(request)
        
        # Dapatkan db session
        db = next(get_db())
        
        # Inisialisasi history service
        history_service = HistoryService(db)
        
        # Buat event
        event = None
        if user_id:
            try:
                event = history_service.create_event(
                    event_type=event_type,
                    user_id=user_id,
                    parameters=params,
                    status=EventStatus.IN_PROGRESS
                )
            except Exception as e:
                logger.error(f"Error creating history event: {str(e)}")
        
        try:
            # Jalankan request
            response = await call_next(request)
            
            # Hitung durasi
            duration = time.time() - start_time
            
            # Perbarui event dengan status sukses jika ada
            if event:
                try:
                    # Dapatkan response body
                    response_body = await self._get_response_body(response)
                    
                    history_service.update_event(
                        event_id=event.id,
                        status=EventStatus.SUCCESS,
                        result=response_body,
                        duration=duration
                    )
                except Exception as e:
                    logger.error(f"Error updating history event: {str(e)}")
            
            return response
            
        except Exception as e:
            # Hitung durasi
            duration = time.time() - start_time
            
            # Perbarui event dengan status error jika ada
            if event:
                try:
                    history_service.update_event(
                        event_id=event.id,
                        status=EventStatus.FAILED,
                        error_message=str(e),
                        duration=duration
                    )
                except Exception as e:
                    logger.error(f"Error updating history event: {str(e)}")
            
            # Re-raise exception
            raise
    
    def _should_skip_logging(self, request: Request) -> bool:
        """
        Memeriksa apakah request perlu di-skip
        """
        # Skip jika path di-exclude
        for path in self.exclude_paths:
            if request.url.path.startswith(path):
                return True
        
        # Skip jika method di-exclude
        if request.method in self.exclude_methods:
            return True
        
        return False
    
    async def _get_user_id(self, request: Request) -> int:
        """
        Mendapatkan user_id dari token
        """
        try:
            # Dapatkan token dari header Authorization
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                return None
            
            token = auth_header.replace("Bearer ", "")
            
            # Dapatkan user dari token
            user = await get_current_user (token)
            return user.id
        except Exception:
            return None
    
    def _get_event_type(self, request: Request) -> EventType:
        """
        Mendapatkan event type berdasarkan path dan method
        """
        path = request.url.path
        method = request.method
        
        # VM endpoints
        if path.startswith("/vms"):
            if method == "POST" and path == "/vms":
                return EventType.VM_CREATE
            elif method == "POST" and path.endswith("/start"):
                return EventType.VM_START
            elif method == "POST" and path.endswith("/stop"):
                return EventType.VM_STOP
            elif method == "DELETE":
                return EventType.VM_DELETE
            elif method == "GET" and len(path.split("/")) > 2:
                return EventType.VM_STATUS_UPDATE
        
        # Credential endpoints
        elif path.startswith("/credentials"):
            if method == "POST" and path == "/credentials":
                return EventType.CREDENTIAL_CREATE
            elif method == "PUT":
                return EventType.CREDENTIAL_UPDATE
            elif method == "DELETE":
                return EventType.CREDENTIAL_DELETE
            elif method == "GET" and path.endswith("/validate"):
                return EventType.CREDENTIAL_VALIDATE
        
        # Default: gunakan path dan method sebagai event type
        return f"{method.lower()}_{path.replace('/', '_')}"
    
    async def _get_request_params(self, request: Request) -> Dict[str, Any]:
        """
        Mendapatkan parameter request
        """
        params = {
            "path": request.url.path,
            "method": request.method,
            "query_params": dict(request.query_params)
        }
        
        # Tambahkan body jika ada
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.json()
                # Mask sensitive data
                if isinstance(body, dict):
                    body = self._mask_sensitive_data(body)
                params["body"] = body
            except Exception:
                # Jika body bukan JSON, skip
                pass
        
        return params
    
    def _mask_sensitive_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Menyembunyikan data sensitif seperti password, secret key, dll
        """
        sensitive_fields = [
            "password", "secret", "key", "token", "private_key", 
            "access_key", "secret_key", "aws_secret_access_key"
        ]
        
        result = {}
        for key, value in data.items():
            if isinstance(value, dict):
                result[key] = self._mask_sensitive_data(value)
            elif isinstance(value, str) and any(field in key.lower() for field in sensitive_fields):
                result[key] = "******"
            else:
                result[key] = value
        
        return result
    
    async def _get_response_body(self, response: Response) -> Dict[str, Any]:
        """
        Mendapatkan body dari response
        """
        try:
            # Dapatkan response body
            body = response.body.decode("utf-8")
            
            # Parse JSON jika ada
            if body:
                return json.loads(body)
            
            return {}
        except Exception:
            # Jika body bukan JSON atau kosong, return status code saja
            return {"status_code": response.status_code} 