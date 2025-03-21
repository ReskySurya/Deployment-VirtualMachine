import functools
import time
import inspect
import json
import enum
from typing import Callable, Dict, Any, Optional, Type, Union
from sqlalchemy.orm import Session


from app.history.models import EventType, EventStatus
from app.history.service import HistoryService

class HistoryTracker:
    """
    Decorator untuk mencatat history operasi secara otomatis.
    
    Decorator ini akan:
    1. Mencatat parameter input
    2. Mencatat hasil output
    3. Menangkap dan mencatat error jika terjadi
    4. Menghitung durasi operasi
    5. Mencatat status operasi
    
    Contoh penggunaan:
    
    @HistoryTracker(event_type=EventType.VM_CREATE)
    def create_vm(self, user_id: int, vm_data: Dict[str, Any]) -> VM:
        # Implementasi
        pass
    """
    
    def __init__(
        self, 
        event_type: EventType,
        get_user_id: Optional[Callable] = None,
        get_vm_id: Optional[Callable] = None,
        get_credential_id: Optional[Callable] = None,
        initial_status: EventStatus = EventStatus.PENDING,
        success_status: EventStatus = EventStatus.SUCCESS,
        error_status: EventStatus = EventStatus.FAILED,
        exclude_params: Optional[list] = None
    ):
        """
        Inisialisasi decorator HistoryTracker
        
        Args:
            event_type: Tipe event yang akan dicatat
            get_user_id: Fungsi untuk mendapatkan user_id dari parameter fungsi
            get_vm_id: Fungsi untuk mendapatkan vm_id dari parameter fungsi
            get_credential_id: Fungsi untuk mendapatkan credential_id dari parameter fungsi
            initial_status: Status awal event
            success_status: Status event jika operasi berhasil
            error_status: Status event jika operasi gagal
            exclude_params: Parameter yang tidak perlu dicatat (misalnya password)
        """
        self.event_type = event_type
        self.get_user_id = get_user_id
        self.get_vm_id = get_vm_id
        self.get_credential_id = get_credential_id
        self.initial_status = initial_status
        self.success_status = success_status
        self.error_status = error_status
        self.exclude_params = exclude_params or []
    
    def __call__(self, func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Dapatkan instance class (self) dari args
            instance = args[0] if args else None
            
            # Dapatkan db session dari instance
            db = getattr(instance, 'db', None)
            if not db or not isinstance(db, Session):
                # Jika tidak ada db session, jalankan fungsi tanpa tracking
                return func(*args, **kwargs)
            
            # Inisialisasi history service
            history_service = HistoryService(db)
            
            # Dapatkan parameter fungsi
            params = self._get_function_params(func, args, kwargs)
            
            # Filter parameter yang tidak perlu dicatat
            filtered_params = {k: v for k, v in params.items() if k not in self.exclude_params}
            
            # Dapatkan user_id, vm_id, dan credential_id
            user_id = self._get_param_value(self.get_user_id, params)
            vm_id = self._get_param_value(self.get_vm_id, params)
            credential_id = self._get_param_value(self.get_credential_id, params)
            
            # Buat event
            event = history_service.create_event(
                event_type=self.event_type,
                user_id=user_id,
                vm_id=vm_id,
                credential_id=credential_id,
                parameters=filtered_params,
                status=self.initial_status
            )
            
            # Catat waktu mulai
            start_time = time.time()
            
            try:
                # Jalankan fungsi asli
                result = func(*args, **kwargs)
                
                # Hitung durasi
                duration = time.time() - start_time
                
                # Perbarui event dengan status sukses
                result_data = self._prepare_result_data(result)
                history_service.update_event(
                    event_id=event.id,
                    status=self.success_status,
                    result=result_data,
                    duration=duration
                )
                
                return result
                
            except Exception as e:
                # Hitung durasi
                duration = time.time() - start_time
                
                # Perbarui event dengan status error
                history_service.update_event(
                    event_id=event.id,
                    status=self.error_status,
                    error_message=str(e),
                    duration=duration
                )
                
                # Re-raise exception
                raise
        
        return wrapper
    
    def _get_function_params(self, func, args, kwargs):
        """
        Mendapatkan parameter fungsi dari args dan kwargs
        """
        sig = inspect.signature(func)
        params = {}
        
        # Konversi args ke dict berdasarkan nama parameter
        param_names = list(sig.parameters.keys())
        for i, arg in enumerate(args):
            if i < len(param_names):
                param_name = param_names[i]
                # Skip parameter 'self'
                if param_name != 'self':
                    params[param_name] = self._serialize_param(arg)
        
        # Tambahkan kwargs
        for key, value in kwargs.items():
            params[key] = self._serialize_param(value)
        
        return params
    
    def _serialize_param(self, param):
        """
        Mengubah parameter menjadi format yang dapat di-serialize ke JSON
        """
        if hasattr(param, 'dict') and callable(getattr(param, 'dict')):
            # Handle Pydantic model
            return param.dict()
        elif hasattr(param, '__dict__'):
            # Handle object lain
            return {k: v for k, v in param.__dict__.items() if not k.startswith('_')}
        else:
            # Return parameter as is
            return param
    
    def _get_param_value(self, getter_func, params):
        """
        Mendapatkan nilai parameter menggunakan fungsi getter
        """
        if getter_func:
            return getter_func(params)
        return None
    
    def _prepare_result_data(self, result):
        """
        Menyiapkan data hasil untuk disimpan ke database
        """
        if result is None:
            return None
            
        if hasattr(result, 'dict') and callable(getattr(result, 'dict')):
            # Handle Pydantic model
            return self._handle_non_serializable(result.dict())
        elif hasattr(result, '__dict__'):
            # Handle object lain
            return self._handle_non_serializable({k: v for k, v in result.__dict__.items() if not k.startswith('_')})
        elif isinstance(result, dict):
            # Handle dict
            return self._handle_non_serializable(result)
        else:
            # Handle tipe data lain
            return {"result": str(result)}
            
    def _handle_non_serializable(self, obj):
        """
        Menangani objek yang tidak dapat di-serialize ke JSON
        """
        if isinstance(obj, dict):
            return {k: self._handle_non_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._handle_non_serializable(item) for item in obj]
        elif isinstance(obj, (set, tuple)):
            return [self._handle_non_serializable(item) for item in obj]
        elif hasattr(obj, 'isoformat') and callable(getattr(obj, 'isoformat')):
            # Konversi datetime ke string ISO format
            return obj.isoformat()
        elif isinstance(obj, enum.Enum):
            # Konversi Enum ke string
            return obj.value
        else:
            try:
                # Coba serialize ke JSON untuk cek apakah bisa
                json.dumps(obj)
                return obj
            except (TypeError, OverflowError):
                # Jika tidak bisa, konversi ke string
                return str(obj)

# Fungsi helper untuk mendapatkan parameter umum
def get_user_id(params):
    return params.get('user_id')

def get_vm_id(params):
    return params.get('vm_id')

def get_credential_id(params):
    return params.get('credential_id')

# Status tracking yang lebih detail
class TerraformStatus(str, enum.Enum):
    INITIATED = "initiated"
    PROVISIONING = "provisioning"
    COMPLETED = "completed"
    FAILED = "failed"

# Decorator khusus untuk operasi Terraform
class TerraformTracker(HistoryTracker):
    """
    Decorator khusus untuk mencatat operasi Terraform
    """
    
    def __init__(
        self, 
        event_type: EventType,
        get_user_id: Optional[Callable] = None,
        get_vm_id: Optional[Callable] = None,
        get_credential_id: Optional[Callable] = None,
        exclude_params: Optional[list] = None
    ):
        super().__init__(
            event_type=event_type,
            get_user_id=get_user_id,
            get_vm_id=get_vm_id,
            get_credential_id=get_credential_id,
            initial_status=EventStatus.PENDING,
            success_status=EventStatus.SUCCESS,
            error_status=EventStatus.FAILED,
            exclude_params=exclude_params
        )
    
    def __call__(self, func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Dapatkan instance class (self) dari args
            instance = args[0] if args else None
            
            # Dapatkan db session dari instance
            db = getattr(instance, 'db', None)
            if not db or not isinstance(db, Session):
                # Jika tidak ada db session, jalankan fungsi tanpa tracking
                return func(*args, **kwargs)
            
            # Inisialisasi history service
            history_service = HistoryService(db)
            
            # Dapatkan parameter fungsi
            params = self._get_function_params(func, args, kwargs)
            
            # Filter parameter yang tidak perlu dicatat
            filtered_params = {k: v for k, v in params.items() if k not in self.exclude_params}
            
            # Dapatkan user_id, vm_id, dan credential_id
            user_id = self._get_param_value(self.get_user_id, params)
            vm_id = self._get_param_value(self.get_vm_id, params)
            credential_id = self._get_param_value(self.get_credential_id, params)
            
            # Buat event
            event = history_service.create_event(
                event_type=self.event_type,
                user_id=user_id,
                vm_id=vm_id,
                credential_id=credential_id,
                parameters=filtered_params,
                status=self.initial_status
            )
            
            # Catat waktu mulai
            start_time = time.time()
            
            try:
                # Update status ke PROVISIONING
                history_service.update_event(
                    event_id=event.id,
                    status=TerraformStatus.PROVISIONING
                )
                
                # Jalankan fungsi asli
                result = func(*args, **kwargs)
                
                # Hitung durasi
                duration = time.time() - start_time
                
                # Perbarui event dengan status sukses
                result_data = self._prepare_result_data(result)
                history_service.update_event(
                    event_id=event.id,
                    status=self.success_status,
                    result=result_data,
                    duration=duration
                )
                
                return result
                
            except Exception as e:
                # Hitung durasi
                duration = time.time() - start_time
                
                # Perbarui event dengan status error
                history_service.update_event(
                    event_id=event.id,
                    status=self.error_status,
                    error_message=str(e),
                    duration=duration
                )
                
                # Re-raise exception
                raise
        
        return wrapper 