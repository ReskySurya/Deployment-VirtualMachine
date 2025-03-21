# Modul History

Modul ini menyediakan fungsionalitas untuk mencatat aktivitas dan operasi dalam aplikasi Cloud VM Management.

## Komponen Utama

### 1. Models

- `Event`: Model untuk menyimpan data event
- `EventType`: Enum untuk tipe event (VM_CREATE, VM_START, dll)
- `EventStatus`: Enum untuk status event (SUCCESS, FAILED, PENDING, IN_PROGRESS)
- `TerraformStatus`: Enum untuk status Terraform (INITIATED, PROVISIONING, COMPLETED, FAILED)

### 2. Service

- `HistoryService`: Service untuk operasi CRUD pada event

### 3. Decorators

- `HistoryTracker`: Decorator untuk mencatat operasi secara otomatis
- `TerraformTracker`: Decorator khusus untuk operasi Terraform

### 4. Middleware

- `HistoryMiddleware`: Middleware untuk mencatat request API

### 5. Terraform Integration

- `TerraformExecutor`: Kelas untuk mengeksekusi dan mencatat operasi Terraform

## Cara Penggunaan

### Menggunakan Decorator

```python
from app.history.decorators import HistoryTracker
from app.history.models import EventType

class MyService:
    def __init__(self, db):
        self.db = db
    
    @HistoryTracker(
        event_type=EventType.VM_CREATE,
        get_user_id=lambda params: params.get("user_id"),
        get_vm_id=lambda params: params.get("vm_id")
    )
    def create_something(self, user_id, vm_id, data):
        # Implementasi
        pass
```

### Menggunakan TerraformExecutor

```python
from app.history.terraform import TerraformExecutor
from app.history.models import EventType

# Inisialisasi executor
executor = TerraformExecutor(db, user_id, vm_id)

# Eksekusi perintah Terraform
success, result = executor.execute(
    command="apply",
    working_dir="/path/to/terraform",
    variables={"key": "value"},
    event_type=EventType.VM_CREATE
)
```

### Menggunakan Middleware

Middleware sudah terdaftar di `main.py` dan akan otomatis mencatat request API.

## Fitur

1. **Mencatat Parameter Input**: Semua parameter input dicatat secara otomatis
2. **Mencatat Hasil Output**: Hasil operasi dicatat secara otomatis
3. **Menangkap dan Mencatat Error**: Error dicatat dengan pesan error dan stack trace
4. **Menghitung Durasi Operasi**: Durasi operasi dicatat dalam detik
5. **Status Tracking**: Status operasi dicatat (PENDING, IN_PROGRESS, SUCCESS, FAILED)
6. **Fault Tolerance**: Penanganan error di semua level
7. **Integrasi dengan Terraform**: Mencatat output dan error dari eksekusi Terraform

## Contoh Data Event

```json
{
  "id": 1,
  "event_type": "vm_create",
  "status": "success",
  "timestamp": "2023-06-01T12:00:00Z",
  "user_id": 1,
  "vm_id": 2,
  "credential_id": 3,
  "parameters": {
    "name": "my-vm",
    "provider": "aws",
    "instance_type": "t2.micro",
    "region": "us-east-1"
  },
  "result": {
    "instance_id": "i-1234567890abcdef0",
    "public_ip": "1.2.3.4",
    "private_ip": "10.0.0.1"
  },
  "duration": 5.67
}
``` 