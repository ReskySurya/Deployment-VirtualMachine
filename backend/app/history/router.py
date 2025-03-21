from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from app.database import get_db
from app.auth.jwt import get_current_user
from app.users.models import User
from app.history.models import Event, EventType, EventStatus, EventResponse, EventListResponse
from app.history.service import HistoryService
from app.vm.service import VMService

router = APIRouter(
    prefix="/history",
    tags=["history"],
    responses={404: {"description": "Not found"}},
)

@router.get("/", response_model=EventListResponse)
def list_events(
    event_type: Optional[EventType] = None,
    status: Optional[EventStatus] = None,
    vm_id: Optional[int] = Query(None, description="Filter berdasarkan VM ID"),
    credential_id: Optional[int] = Query(None, description="Filter berdasarkan Credential ID"),
    user_id: Optional[int] = Query(None, description="Filter berdasarkan User ID (hanya untuk admin)"),
    start_date: Optional[datetime] = Query(None, description="Filter berdasarkan tanggal mulai (format: YYYY-MM-DD)"),
    end_date: Optional[datetime] = Query(None, description="Filter berdasarkan tanggal akhir (format: YYYY-MM-DD)"),
    limit: int = Query(100, ge=1, le=1000, description="Jumlah maksimum event yang dikembalikan"),
    offset: int = Query(0, ge=0, description="Jumlah event yang dilewati untuk paginasi"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Mendapatkan daftar event dengan filter opsional.
    Admin dapat melihat semua event, sementara pengguna biasa hanya dapat melihat event mereka sendiri.
    
    Filter yang tersedia:
    - event_type: Tipe event (VM_CREATE, VM_START, dll)
    - status: Status event (SUCCESS, FAILED, PENDING, IN_PROGRESS)
    - vm_id: ID VM
    - credential_id: ID kredensial
    - user_id: ID pengguna (hanya untuk admin)
    - start_date: Tanggal mulai (format: YYYY-MM-DD)
    - end_date: Tanggal akhir (format: YYYY-MM-DD)
    """
    history_service = HistoryService(db)
    
    # Jika bukan admin, batasi hanya untuk event pengguna saat ini
    if not current_user.is_admin:
        user_id = current_user.id
    elif user_id is None:
        # Jika admin dan tidak ada filter user_id, tampilkan semua event
        user_id = None
    
    # Jika end_date diberikan tanpa waktu, tambahkan 23:59:59 untuk mencakup seluruh hari
    if end_date and end_date.hour == 0 and end_date.minute == 0 and end_date.second == 0:
        end_date = end_date.replace(hour=23, minute=59, second=59)
    
    events = history_service.list_events(
        user_id=user_id,
        vm_id=vm_id,
        credential_id=credential_id,
        event_type=event_type,
        status=status,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset
    )
    
    total = history_service.count_events(
        user_id=user_id,
        vm_id=vm_id,
        credential_id=credential_id,
        event_type=event_type,
        status=status,
        start_date=start_date,
        end_date=end_date
    )
    
    return EventListResponse(events=events, total=total)

@router.get("/{event_id}", response_model=EventResponse)
def get_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Mendapatkan detail event berdasarkan ID.
    Admin dapat melihat semua event, sementara pengguna biasa hanya dapat melihat event mereka sendiri.
    """
    history_service = HistoryService(db)
    event = history_service.get_event(event_id)
    
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event dengan ID {event_id} tidak ditemukan"
        )
    
    # Periksa apakah pengguna memiliki akses ke event ini
    if not current_user.is_admin and event.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Anda tidak memiliki izin untuk melihat event ini"
        )
    
    return event

@router.get("/stats/summary", response_model=Dict[str, Any])
def get_history_summary(
    period: str = Query("week", description="Periode statistik: day, week, month, year"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Mendapatkan ringkasan statistik history.
    
    Statistik yang tersedia:
    - Jumlah event per tipe
    - Rasio keberhasilan/kegagalan
    - Waktu rata-rata untuk setiap tipe event
    - Jumlah VM yang aktif vs. total
    
    Periode yang tersedia:
    - day: Hari ini
    - week: 7 hari terakhir
    - month: 30 hari terakhir
    - year: 365 hari terakhir
    """
    history_service = HistoryService(db)
    vm_service = VMService(db)
    
    # Tentukan tanggal mulai berdasarkan periode
    now = datetime.now()
    if period == "day":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start_date = now - timedelta(days=7)
    elif period == "month":
        start_date = now - timedelta(days=30)
    elif period == "year":
        start_date = now - timedelta(days=365)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Periode tidak valid: {period}. Gunakan day, week, month, atau year."
        )
    
    # Jika bukan admin, batasi hanya untuk event pengguna saat ini
    user_id = None if current_user.is_admin else current_user.id
    
    # Dapatkan statistik
    event_counts = history_service.get_event_counts_by_type(user_id=user_id, start_date=start_date)
    success_ratio = history_service.get_success_ratio(user_id=user_id, start_date=start_date)
    avg_durations = history_service.get_average_durations(user_id=user_id, start_date=start_date)
    
    # Dapatkan jumlah VM aktif vs. total
    active_vms = vm_service.count_vms_by_status(user_id=user_id, status="RUNNING")
    total_vms = vm_service.count_vms(user_id=user_id)
    
    return {
        "period": period,
        "start_date": start_date,
        "end_date": now,
        "event_counts": event_counts,
        "success_ratio": success_ratio,
        "avg_durations": avg_durations,
        "vm_stats": {
            "active": active_vms,
            "total": total_vms,
            "active_percentage": (active_vms / total_vms * 100) if total_vms > 0 else 0
        }
    }

@router.get("/stats/daily", response_model=List[Dict[str, Any]])
def get_daily_stats(
    days: int = Query(30, ge=1, le=365, description="Jumlah hari yang akan ditampilkan"),
    event_type: Optional[EventType] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Mendapatkan statistik harian untuk jumlah deployment dan rasio keberhasilan.
    
    Statistik yang tersedia:
    - Jumlah event per hari
    - Rasio keberhasilan per hari
    """
    history_service = HistoryService(db)
    
    # Tentukan tanggal mulai
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # Jika bukan admin, batasi hanya untuk event pengguna saat ini
    user_id = None if current_user.is_admin else current_user.id
    
    # Dapatkan statistik harian
    daily_stats = history_service.get_daily_stats(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        event_type=event_type
    )
    
    return daily_stats

@router.get("/stats/deployment-times", response_model=Dict[str, Any])
def get_deployment_times(
    period: str = Query("month", description="Periode statistik: week, month, year"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Mendapatkan statistik waktu deployment untuk VM dan kredensial.
    
    Statistik yang tersedia:
    - Waktu rata-rata untuk membuat VM
    - Waktu rata-rata untuk membuat kredensial
    - Waktu rata-rata untuk menghapus VM
    - Waktu rata-rata untuk menghapus kredensial
    """
    history_service = HistoryService(db)
    
    # Tentukan tanggal mulai berdasarkan periode
    now = datetime.now()
    if period == "week":
        start_date = now - timedelta(days=7)
    elif period == "month":
        start_date = now - timedelta(days=30)
    elif period == "year":
        start_date = now - timedelta(days=365)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Periode tidak valid: {period}. Gunakan week, month, atau year."
        )
    
    # Jika bukan admin, batasi hanya untuk event pengguna saat ini
    user_id = None if current_user.is_admin else current_user.id
    
    # Dapatkan statistik waktu deployment
    vm_create_time = history_service.get_average_duration_by_event_type(
        event_type=EventType.VM_CREATE,
        user_id=user_id,
        start_date=start_date
    )
    
    vm_delete_time = history_service.get_average_duration_by_event_type(
        event_type=EventType.VM_DELETE,
        user_id=user_id,
        start_date=start_date
    )
    
    credential_create_time = history_service.get_average_duration_by_event_type(
        event_type=EventType.CREDENTIAL_CREATE,
        user_id=user_id,
        start_date=start_date
    )
    
    credential_delete_time = history_service.get_average_duration_by_event_type(
        event_type=EventType.CREDENTIAL_DELETE,
        user_id=user_id,
        start_date=start_date
    )
    
    return {
        "period": period,
        "start_date": start_date,
        "end_date": now,
        "vm_create_time": vm_create_time,
        "vm_delete_time": vm_delete_time,
        "credential_create_time": credential_create_time,
        "credential_delete_time": credential_delete_time
    }
