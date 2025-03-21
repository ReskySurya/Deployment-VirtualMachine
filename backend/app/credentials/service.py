from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import List, Optional, Dict, Any
import json
import time
from datetime import datetime

from app.credentials.models import Credential, CredentialType
from app.credentials.encryption import encrypt_credentials, decrypt_credentials
from app.history.service import HistoryService
from app.history.models import EventType, EventStatus
from app.history.decorators import HistoryTracker, get_user_id, get_credential_id

class CredentialService:
    def __init__(self, db: Session):
        self.db = db
        self.history_service = HistoryService(db)
    
    @HistoryTracker(
        event_type=EventType.CREDENTIAL_CREATE,
        get_user_id=get_user_id,
        exclude_params=["aws_credentials", "gcp_credentials"]
    )
    def create_credential(self, user_id: int, credential_data: Dict[str, Any]) -> Credential:
        """
        Membuat kredensial baru
        """
        try:
            # Enkripsi data kredensial
            if credential_data["type"] == CredentialType.AWS:
                data_to_encrypt = {
                    "access_key": credential_data["aws_credentials"]["access_key"],
                    "secret_key": credential_data["aws_credentials"]["secret_key"],
                    "region": credential_data["aws_credentials"]["region"]
                }
            elif credential_data["type"] == CredentialType.GCP:
                data_to_encrypt = {
                    "project_id": credential_data["gcp_credentials"]["project_id"],
                    "private_key_id": credential_data["gcp_credentials"]["private_key_id"],
                    "private_key": credential_data["gcp_credentials"]["private_key"],
                    "client_email": credential_data["gcp_credentials"]["client_email"],
                    "client_id": credential_data["gcp_credentials"]["client_id"],
                    "auth_uri": credential_data["gcp_credentials"].get("auth_uri", "https://accounts.google.com/o/oauth2/auth"),
                    "token_uri": credential_data["gcp_credentials"].get("token_uri", "https://oauth2.googleapis.com/token"),
                    "auth_provider_x509_cert_url": credential_data["gcp_credentials"].get("auth_provider_x509_cert_url", "https://www.googleapis.com/oauth2/v1/certs"),
                    "client_x509_cert_url": credential_data["gcp_credentials"].get("client_x509_cert_url")
                }
            else:
                raise ValueError(f"Tipe kredensial tidak didukung: {credential_data['type']}")
            
            encrypted_data = encrypt_credentials(data_to_encrypt)
            
            # Buat kredensial di database
            credential = Credential(
                name=credential_data["name"],
                type=credential_data["type"],
                encrypted_data=encrypted_data,
                user_id=user_id
            )
            
            self.db.add(credential)
            self.db.commit()
            self.db.refresh(credential)
            
            return credential
            
        except Exception as e:
            # Rollback transaksi database jika terjadi error
            self.db.rollback()
            
            # Re-raise exception untuk ditangani oleh router
            raise
    
    def get_credential(self, credential_id: int, user_id: int) -> Optional[Credential]:
        """
        Mendapatkan kredensial berdasarkan ID
        """
        return self.db.query(Credential).filter(
            Credential.id == credential_id,
            Credential.user_id == user_id
        ).first()
    
    def get_decrypted_credential(self, credential_id: int, user_id: int) -> Dict[str, Any]:
        """
        Mendapatkan dan mendekripsi kredensial
        """
        credential = self.get_credential(credential_id, user_id)
        if not credential:
            raise ValueError(f"Kredensial dengan ID {credential_id} tidak ditemukan")
        
        # Dekripsi kredensial
        decrypted_data = decrypt_credentials(credential.encrypted_data)
        
        return {
            "id": credential.id,
            "type": credential.type,
            **decrypted_data
        }
    
    def list_credentials(self, user_id: int, limit: int = 100, offset: int = 0) -> List[Credential]:
        """
        Mendapatkan daftar kredensial milik pengguna
        """
        return self.db.query(Credential).filter(
            Credential.user_id == user_id
        ).limit(limit).offset(offset).all()
    
    def count_credentials(self, user_id: int) -> int:
        """
        Menghitung jumlah kredensial milik pengguna
        """
        return self.db.query(Credential).filter(
            Credential.user_id == user_id
        ).count()
    
    @HistoryTracker(
        event_type=EventType.CREDENTIAL_DELETE,
        get_user_id=get_user_id,
        get_credential_id=get_credential_id
    )
    def delete_credential(self, credential_id: int, user_id: int) -> bool:
        """
        Menghapus kredensial
        """
        credential = self.get_credential(credential_id, user_id)
        if not credential:
            raise ValueError(f"Kredensial dengan ID {credential_id} tidak ditemukan")
        
        try:
            # Periksa apakah kredensial sedang digunakan oleh VM
            vm_count = self.db.query(Credential).join(
                Credential.vms
            ).filter(
                Credential.id == credential_id
            ).count()
            
            if vm_count > 0:
                raise ValueError(f"Kredensial sedang digunakan oleh {vm_count} VM. Hapus VM terlebih dahulu.")
            
            # Hapus kredensial dari database
            self.db.delete(credential)
            self.db.commit()
            
            return True
            
        except Exception as e:
            # Rollback transaksi database jika terjadi error
            self.db.rollback()
            
            # Re-raise exception untuk ditangani oleh router
            raise 