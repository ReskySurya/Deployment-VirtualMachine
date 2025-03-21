from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any

from app.database import get_db
from app.auth.jwt import get_current_user
from app.users.models import User
from app.vm.models import VM, VMCreate, VMResponse, VMListResponse, VMStatus, VMProvider
from app.vm.service import VMService

router = APIRouter(
    prefix="/vms",
    tags=["vms"],
    responses={404: {"description": "Not found"}},
)

class VMCreateExtended(VMCreate):
    # AWS specific
    ami_id: Optional[str] = None
    key_name: Optional[str] = None
    security_group_ids: Optional[List[str]] = None
    
    # GCP specific
    image: Optional[str] = None
    zone: Optional[str] = None

class VMActionResponse(BaseModel):
    status: str
    message: str

@router.get("/", response_model=VMListResponse)
def list_vms(
    limit: int = Query(100, ge=1, le=1000, description="Jumlah maksimum VM yang dikembalikan"),
    offset: int = Query(0, ge=0, description="Jumlah VM yang dilewati untuk paginasi"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Mendapatkan daftar VM milik pengguna
    """
    vm_service = VMService(db)
    
    vms = vm_service.list_vms(
        user_id=current_user.id,
        limit=limit,
        offset=offset
    )
    
    total = vm_service.count_vms(current_user.id)
    
    return VMListResponse(vms=vms, total=total)

@router.get("/{vm_id}", response_model=VMResponse)
def get_vm(
    vm_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Mendapatkan detail VM berdasarkan ID
    """
    vm_service = VMService(db)
    
    vm = vm_service.get_vm(
        vm_id=vm_id,
        user_id=current_user.id
    )
    
    if not vm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"VM dengan ID {vm_id} tidak ditemukan"
        )
    
    return vm

@router.post("/", response_model=VMResponse)
def create_vm(
    vm_data: VMCreateExtended,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Membuat VM baru
    """
    vm_service = VMService(db)
    
    try:
        vm = vm_service.create_vm(
            user_id=current_user.id,
            vm_data=vm_data.dict()
        )
        return vm
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Terjadi kesalahan saat membuat VM: {str(e)}"
        )

@router.post("/{vm_id}/start", response_model=VMResponse)
def start_vm(
    vm_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Memulai VM yang sedang berhenti
    """
    vm_service = VMService(db)
    
    try:
        vm = vm_service.start_vm(
            vm_id=vm_id,
            user_id=current_user.id
        )
        return vm
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Terjadi kesalahan saat memulai VM: {str(e)}"
        )

@router.post("/{vm_id}/stop", response_model=VMResponse)
def stop_vm(
    vm_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Menghentikan VM yang sedang berjalan
    """
    vm_service = VMService(db)
    
    try:
        vm = vm_service.stop_vm(
            vm_id=vm_id,
            user_id=current_user.id
        )
        return vm
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Terjadi kesalahan saat menghentikan VM: {str(e)}"
        )

@router.delete("/{vm_id}", response_model=VMActionResponse)
def delete_vm(
    vm_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Menghapus VM
    """
    vm_service = VMService(db)
    
    try:
        vm_service.delete_vm(
            vm_id=vm_id,
            user_id=current_user.id
        )
        return {"status": "success", "message": f"VM dengan ID {vm_id} berhasil dihapus"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Terjadi kesalahan saat menghapus VM: {str(e)}"
        )
