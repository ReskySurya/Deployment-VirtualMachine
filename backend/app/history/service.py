from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, desc
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import json
import enum

from app.history.models import Event, EventType, EventStatus

class HistoryService:
    def __init__(self, db: Session):
        """
        Inisialisasi History Service
        
        Args:
            db: Session database
        """
        self.db = db
    
    def create_event(
        self,
        event_type: EventType,
        user_id: Optional[int] = None,
        vm_id: Optional[int] = None,
        credential_id: Optional[int] = None,
        parameters: Optional[Dict[str, Any]] = None,
        result: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        status: EventStatus = EventStatus.PENDING,
        duration: Optional[float] = None
    ) -> Event:
        """
        Membuat event baru
        
        Args:
            event_type: Tipe event
            user_id: ID pengguna
            vm_id: ID VM (opsional)
            credential_id: ID kredensial (opsional)
            parameters: Parameter input
            result: Hasil output
            error_message: Pesan error
            status: Status event
            duration: Durasi event dalam detik
            
        Returns:
            Event baru
        """
        # Konversi parameters dan result
        if parameters:
            parameters = self._ensure_json_serializable(parameters)
        
        if result:
            result = self._ensure_json_serializable(result)
        
        # Konversi status jika berupa enum
        if isinstance(status, enum.Enum):
            status_value = status.value
        else:
            status_value = status
        
        # Konversi event_type jika berupa enum
        if isinstance(event_type, enum.Enum):
            event_type_value = event_type.value
        else:
            event_type_value = event_type
        
        event = Event(
            event_type=event_type_value,
            status=status_value,
            user_id=user_id,
            vm_id=vm_id,
            credential_id=credential_id,
            parameters=parameters,
            result=result,
            error_message=error_message,
            duration=duration
        )
        
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        
        return event
    
    def update_event(
        self,
        event_id: int,
        result: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        status: Optional[EventStatus] = None,
        duration: Optional[float] = None
    ) -> Event:
        """
        Memperbarui event yang sudah ada
        
        Args:
            event_id: ID event
            result: Hasil output
            error_message: Pesan error
            status: Status event
            duration: Durasi event dalam detik
            
        Returns:
            Event yang diperbarui
        """
        event = self.db.query(Event).filter(Event.id == event_id).first()
        
        if not event:
            raise ValueError(f"Event dengan ID {event_id} tidak ditemukan")
        
        if result is not None:
            # Pastikan result dapat diubah menjadi JSON
            event.result = self._ensure_json_serializable(result)
        
        if error_message is not None:
            event.error_message = error_message
        
        if status is not None:
            # Jika status adalah enum, simpan nilainya
            if isinstance(status, enum.Enum):
                event.status = status.value
            else:
                event.status = status
        
        if duration is not None:
            event.duration = duration
        
        try:
            self.db.commit()
            self.db.refresh(event)
            return event
        except Exception as e:
            self.db.rollback()
            raise ValueError(f"Error updating event: {str(e)}")
    
    def _ensure_json_serializable(self, obj):
        """
        Memastikan objek dapat diubah menjadi JSON
        """
        if isinstance(obj, dict):
            return {k: self._ensure_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._ensure_json_serializable(item) for item in obj]
        elif isinstance(obj, (set, tuple)):
            return [self._ensure_json_serializable(item) for item in obj]
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
    
    def get_event(self, event_id: int) -> Optional[Event]:
        """
        Mendapatkan event berdasarkan ID
        
        Args:
            event_id: ID event
            
        Returns:
            Event jika ditemukan, None jika tidak
        """
        return self.db.query(Event).filter(Event.id == event_id).first()
    
    def list_events(
        self,
        user_id: Optional[int] = None,
        vm_id: Optional[int] = None,
        credential_id: Optional[int] = None,
        event_type: Optional[EventType] = None,
        status: Optional[EventStatus] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Event]:
        """
        Mendapatkan daftar event dengan filter opsional
        
        Args:
            user_id: Filter berdasarkan ID pengguna
            vm_id: Filter berdasarkan ID VM
            credential_id: Filter berdasarkan ID kredensial
            event_type: Filter berdasarkan tipe event
            status: Filter berdasarkan status event
            start_date: Filter berdasarkan tanggal mulai
            end_date: Filter berdasarkan tanggal akhir
            limit: Jumlah maksimum event yang dikembalikan
            offset: Jumlah event yang dilewati untuk paginasi
            
        Returns:
            Daftar event yang sesuai dengan filter
        """
        query = self.db.query(Event)
        
        if user_id is not None:
            query = query.filter(Event.user_id == user_id)
        
        if vm_id is not None:
            query = query.filter(Event.vm_id == vm_id)
        
        if credential_id is not None:
            query = query.filter(Event.credential_id == credential_id)
        
        if event_type is not None:
            query = query.filter(Event.event_type == event_type)
        
        if status is not None:
            query = query.filter(Event.status == status)
        
        if start_date is not None:
            query = query.filter(Event.timestamp >= start_date)
        
        if end_date is not None:
            query = query.filter(Event.timestamp <= end_date)
        
        return query.order_by(desc(Event.timestamp)).limit(limit).offset(offset).all()
    
    def count_events(
        self,
        user_id: Optional[int] = None,
        vm_id: Optional[int] = None,
        credential_id: Optional[int] = None,
        event_type: Optional[EventType] = None,
        status: Optional[EventStatus] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> int:
        """
        Menghitung jumlah event dengan filter opsional
        
        Args:
            user_id: Filter berdasarkan ID pengguna
            vm_id: Filter berdasarkan ID VM
            credential_id: Filter berdasarkan ID kredensial
            event_type: Filter berdasarkan tipe event
            status: Filter berdasarkan status event
            start_date: Filter berdasarkan tanggal mulai
            end_date: Filter berdasarkan tanggal akhir
            
        Returns:
            Jumlah event yang sesuai dengan filter
        """
        query = self.db.query(func.count(Event.id))
        
        if user_id is not None:
            query = query.filter(Event.user_id == user_id)
        
        if vm_id is not None:
            query = query.filter(Event.vm_id == vm_id)
        
        if credential_id is not None:
            query = query.filter(Event.credential_id == credential_id)
        
        if event_type is not None:
            query = query.filter(Event.event_type == event_type)
        
        if status is not None:
            query = query.filter(Event.status == status)
        
        if start_date is not None:
            query = query.filter(Event.timestamp >= start_date)
        
        if end_date is not None:
            query = query.filter(Event.timestamp <= end_date)
        
        return query.scalar()
    
    def get_event_counts_by_type(
        self,
        user_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, int]:
        """
        Mendapatkan jumlah event per tipe
        
        Args:
            user_id: Filter berdasarkan ID pengguna
            start_date: Filter berdasarkan tanggal mulai
            end_date: Filter berdasarkan tanggal akhir
            
        Returns:
            Dictionary dengan tipe event sebagai key dan jumlah sebagai value
        """
        query = self.db.query(Event.event_type, func.count(Event.id))
        
        if user_id is not None:
            query = query.filter(Event.user_id == user_id)
        
        if start_date is not None:
            query = query.filter(Event.timestamp >= start_date)
        
        if end_date is not None:
            query = query.filter(Event.timestamp <= end_date)
        
        result = query.group_by(Event.event_type).all()
        
        return {event_type: count for event_type, count in result}
    
    def get_success_ratio(
        self,
        user_id: Optional[int] = None,
        event_type: Optional[EventType] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Mendapatkan rasio keberhasilan/kegagalan event
        
        Args:
            user_id: Filter berdasarkan ID pengguna
            event_type: Filter berdasarkan tipe event
            start_date: Filter berdasarkan tanggal mulai
            end_date: Filter berdasarkan tanggal akhir
            
        Returns:
            Dictionary dengan rasio keberhasilan/kegagalan
        """
        query = self.db.query(Event.status, func.count(Event.id))
        
        if user_id is not None:
            query = query.filter(Event.user_id == user_id)
        
        if event_type is not None:
            query = query.filter(Event.event_type == event_type)
        
        if start_date is not None:
            query = query.filter(Event.timestamp >= start_date)
        
        if end_date is not None:
            query = query.filter(Event.timestamp <= end_date)
        
        result = query.group_by(Event.status).all()
        
        status_counts = {status: count for status, count in result}
        total = sum(status_counts.values())
        
        success_count = status_counts.get(EventStatus.SUCCESS, 0)
        failed_count = status_counts.get(EventStatus.FAILED, 0)
        pending_count = status_counts.get(EventStatus.PENDING, 0)
        in_progress_count = status_counts.get(EventStatus.IN_PROGRESS, 0)
        
        success_ratio = (success_count / total * 100) if total > 0 else 0
        failed_ratio = (failed_count / total * 100) if total > 0 else 0
        
        return {
            "total": total,
            "success": success_count,
            "failed": failed_count,
            "pending": pending_count,
            "in_progress": in_progress_count,
            "success_ratio": success_ratio,
            "failed_ratio": failed_ratio
        }
    
    def get_average_durations(
        self,
        user_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, float]:
        """
        Mendapatkan durasi rata-rata per tipe event
        
        Args:
            user_id: Filter berdasarkan ID pengguna
            start_date: Filter berdasarkan tanggal mulai
            end_date: Filter berdasarkan tanggal akhir
            
        Returns:
            Dictionary dengan tipe event sebagai key dan durasi rata-rata sebagai value
        """
        query = self.db.query(
            Event.event_type,
            func.avg(Event.duration).label("avg_duration")
        )
        
        if user_id is not None:
            query = query.filter(Event.user_id == user_id)
        
        if start_date is not None:
            query = query.filter(Event.timestamp >= start_date)
        
        if end_date is not None:
            query = query.filter(Event.timestamp <= end_date)
        
        # Hanya event yang berhasil dan memiliki durasi
        query = query.filter(
            Event.status == EventStatus.SUCCESS,
            Event.duration.isnot(None)
        )
        
        result = query.group_by(Event.event_type).all()
        
        return {event_type: float(avg_duration) for event_type, avg_duration in result}
    
    def get_daily_stats(
        self,
        user_id: Optional[int] = None,
        event_type: Optional[EventType] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Mendapatkan statistik harian
        
        Args:
            user_id: Filter berdasarkan ID pengguna
            event_type: Filter berdasarkan tipe event
            start_date: Filter berdasarkan tanggal mulai
            end_date: Filter berdasarkan tanggal akhir
            
        Returns:
            List dictionary dengan statistik harian
        """
        # Buat daftar tanggal
        dates = []
        current_date = start_date
        while current_date <= end_date:
            dates.append(current_date.date())
            current_date += timedelta(days=1)
        
        result = []
        
        for date in dates:
            # Tentukan tanggal mulai dan akhir untuk hari ini
            day_start = datetime.combine(date, datetime.min.time())
            day_end = datetime.combine(date, datetime.max.time())
            
            # Hitung jumlah event
            count_query = self.db.query(func.count(Event.id))
            
            if user_id is not None:
                count_query = count_query.filter(Event.user_id == user_id)
            
            if event_type is not None:
                count_query = count_query.filter(Event.event_type == event_type)
            
            count_query = count_query.filter(
                Event.timestamp >= day_start,
                Event.timestamp <= day_end
            )
            
            count = count_query.scalar()
            
            # Hitung rasio keberhasilan
            success_ratio = self.get_success_ratio(
                user_id=user_id,
                event_type=event_type,
                start_date=day_start,
                end_date=day_end
            )
            
            result.append({
                "date": date.isoformat(),
                "count": count,
                "success_ratio": success_ratio
            })
        
        return result
    
    def get_average_duration_by_event_type(
        self,
        event_type: EventType,
        user_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> float:
        """
        Mendapatkan durasi rata-rata untuk tipe event tertentu
        
        Args:
            event_type: Tipe event
            user_id: Filter berdasarkan ID pengguna
            start_date: Filter berdasarkan tanggal mulai
            end_date: Filter berdasarkan tanggal akhir
            
        Returns:
            Durasi rata-rata dalam detik
        """
        query = self.db.query(func.avg(Event.duration))
        
        query = query.filter(Event.event_type == event_type)
        
        if user_id is not None:
            query = query.filter(Event.user_id == user_id)
        
        if start_date is not None:
            query = query.filter(Event.timestamp >= start_date)
        
        if end_date is not None:
            query = query.filter(Event.timestamp <= end_date)
        
        # Hanya event yang berhasil dan memiliki durasi
        query = query.filter(
            Event.status == EventStatus.SUCCESS,
            Event.duration.isnot(None)
        )
        
        result = query.scalar()
        
        return float(result) if result is not None else 0.0 