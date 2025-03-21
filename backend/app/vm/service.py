import os
import json
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
import logging
import time
from datetime import datetime

from app.vm.models import VM, VMStatus, VMProvider
from app.credentials.models import Credential, CredentialType
from app.credentials.encryption import decrypt_credentials
from app.vm.aws_manager import AwsVmManager
from app.vm.gcp_manager import GcpVmManager
from app.vm.terraform_manager import TerraformManager
from app.config import settings
from app.credentials.service import CredentialService
from app.history.service import HistoryService
from app.history.models import EventType, EventStatus
from app.history.decorators import HistoryTracker, get_user_id, get_vm_id, get_credential_id

logger = logging.getLogger(__name__)

class VMService:
    def __init__(self, db: Session):
        """
        Inisialisasi VM Service
        
        Args:
            db: Session database
        """
        self.db = db
        self.aws_manager = None
        self.gcp_manager = None
        self.terraform_manager = TerraformManager(os.path.join(settings.TERRAFORM_PATH))
        self.credential_service = CredentialService(db)
        self.history_service = HistoryService(db)
    
    def _get_credential(self, credential_id: int, user_id: int) -> Dict[str, Any]:
        """
        Mendapatkan dan mendekripsi kredensial dari database
        """
        return self.credential_service.get_decrypted_credential(credential_id, user_id)
    
    def _get_aws_manager(self, credentials: Dict[str, Any]) -> AwsVmManager:
        """
        Mendapatkan AWS Manager
        
        Args:
            credentials: Kredensial AWS
            
        Returns:
            Instance AWS Manager
        """
        return AwsVmManager(credentials)
    
    def _get_gcp_manager(self, credentials: Dict[str, Any]) -> GcpVmManager:
        """
        Mendapatkan GCP Manager
        
        Args:
            credentials: Kredensial GCP
            
        Returns:
            Instance GCP Manager
        """
        return GcpVmManager(credentials)
    
    @HistoryTracker(
        event_type=EventType.VM_CREATE,
        get_user_id=get_user_id,
        get_credential_id=lambda params: params.get("vm_data", {}).get("credential_id")
    )
    def create_vm(self, user_id: int, vm_data: Dict[str, Any]) -> VM:
        """
        Membuat VM baru berdasarkan input pengguna dan kredensial cloud provider
        """
        try:
            # Buat VM di database dengan status CREATING
            vm = VM(
                name=vm_data["name"],
                provider=vm_data["provider"],
                instance_type=vm_data["instance_type"],
                region=vm_data["region"],
                user_id=user_id,
                credential_id=vm_data["credential_id"],
                status=VMStatus.CREATING
            )
            
            self.db.add(vm)
            self.db.commit()
            self.db.refresh(vm)
            
            # Dapatkan kredensial yang didekripsi
            credentials = self._get_credential(vm_data["credential_id"], user_id)
            
            # Siapkan parameter tambahan berdasarkan provider
            tf_vars = {
                "name": vm_data["name"],
                "instance_type": vm_data["instance_type"],
                "region": vm_data["region"]
            }
            
            if vm.provider == VMProvider.AWS:
                tf_vars.update({
                    "aws_access_key": credentials["access_key"],
                    "aws_secret_key": credentials["secret_key"],
                    "ami_id": vm_data.get("ami_id", "ami-0c55b159cbfafe1f0"),  # Default Amazon Linux 2 AMI
                    "key_name": vm_data.get("key_name"),
                    "security_group_ids": vm_data.get("security_group_ids", [])
                })
                
                # Buat VM di AWS menggunakan Terraform
                result = self.terraform_manager.apply_aws(
                    workspace_name=f"vm-{vm.id}",
                    variables=tf_vars,
                    db=self.db,
                    user_id=user_id,
                    vm_id=vm.id
                )
                
                # Update VM dengan instance ID dan status
                vm.instance_id = result.get("instance_id")
                vm.status = VMStatus.RUNNING if result.get("status") == "running" else VMStatus.FAILED
                
            elif vm.provider == VMProvider.GCP:
                tf_vars.update({
                    "gcp_credentials_json": json.dumps(credentials),
                    "gcp_project_id": credentials["project_id"],
                    "image": vm_data.get("image", "debian-cloud/debian-10"),
                    "zone": vm_data.get("zone", f"{vm_data['region']}-a")
                })
                
                # Buat VM di GCP menggunakan Terraform
                result = self.terraform_manager.apply_gcp(
                    workspace_name=f"vm-{vm.id}",
                    variables=tf_vars,
                    db=self.db,
                    user_id=user_id,
                    vm_id=vm.id
                )
                
                # Update VM dengan instance ID dan status
                vm.instance_id = result.get("instance_id")
                vm.status = VMStatus.RUNNING if result.get("status") == "RUNNING" else VMStatus.FAILED
            
            # Simpan perubahan ke database
            self.db.commit()
            self.db.refresh(vm)
            
            return vm
            
        except Exception as e:
            # Rollback transaksi database jika terjadi error
            self.db.rollback()
            
            # Re-raise exception untuk ditangani oleh router
            raise
    
    @HistoryTracker(
        event_type=EventType.VM_STATUS_UPDATE,
        get_user_id=get_user_id,
        get_vm_id=get_vm_id
    )
    def get_vm(self, vm_id: int, user_id: int) -> Optional[VM]:
        """
        Mendapatkan detail VM dan memperbarui statusnya dari cloud jika VM sedang berjalan
        """
        vm = self.db.query(VM).filter(VM.id == vm_id, VM.user_id == user_id).first()
        
        if not vm:
            return None
        
        # Jika VM sedang berjalan, refresh status dari cloud
        if vm.status == VMStatus.RUNNING:
            try:
                # Dapatkan kredensial yang didekripsi
                credentials = self._get_credential(vm.credential_id, user_id)
                
                # Periksa status VM di cloud berdasarkan provider
                if vm.provider == VMProvider.AWS:
                    # Implementasi pengecekan status AWS
                    pass
                elif vm.provider == VMProvider.GCP:
                    # Implementasi pengecekan status GCP
                    pass
                
            except Exception as e:
                logger.error(f"Error saat memeriksa status VM: {str(e)}")
        
        return vm
    
    def list_vms(self, user_id: int, limit: int = 100, offset: int = 0) -> List[VM]:
        """
        Mendapatkan daftar VM yang dimiliki oleh pengguna
        """
        return self.db.query(VM).filter(VM.user_id == user_id).limit(limit).offset(offset).all()
    
    def count_vms(self, user_id: Optional[int] = None) -> int:
        """
        Menghitung jumlah VM yang dimiliki oleh pengguna
        
        Args:
            user_id: ID pengguna (opsional, jika None maka hitung semua VM)
            
        Returns:
            Jumlah VM
        """
        query = self.db.query(VM)
        
        if user_id is not None:
            query = query.filter(VM.user_id == user_id)
        
        return query.count()
    
    def count_vms_by_status(self, status: str, user_id: Optional[int] = None) -> int:
        """
        Menghitung jumlah VM berdasarkan status
        
        Args:
            status: Status VM (RUNNING, STOPPED, CREATING, FAILED)
            user_id: ID pengguna (opsional, jika None maka hitung semua VM)
            
        Returns:
            Jumlah VM dengan status tertentu
        """
        query = self.db.query(VM).filter(VM.status == status)
        
        if user_id is not None:
            query = query.filter(VM.user_id == user_id)
        
        return query.count()
    
    @HistoryTracker(
        event_type=EventType.VM_START,
        get_user_id=get_user_id,
        get_vm_id=get_vm_id
    )
    def start_vm(self, vm_id: int, user_id: int) -> VM:
        """
        Memulai VM yang sedang berhenti
        """
        vm = self.db.query(VM).filter(VM.id == vm_id, VM.user_id == user_id).first()
        
        if not vm:
            raise ValueError(f"VM dengan ID {vm_id} tidak ditemukan")
        
        if vm.status != VMStatus.STOPPED:
            raise ValueError(f"VM harus dalam status STOPPED untuk dapat dimulai, status saat ini: {vm.status}")
        
        try:
            # Dapatkan kredensial yang didekripsi
            credentials = self._get_credential(vm.credential_id, user_id)
            
            # Mulai VM berdasarkan provider
            if vm.provider == VMProvider.AWS:
                # Implementasi start VM AWS
                pass
            elif vm.provider == VMProvider.GCP:
                # Implementasi start VM GCP
                pass
            
            # Update status VM
            vm.status = VMStatus.RUNNING
            self.db.commit()
            self.db.refresh(vm)
            
            return vm
            
        except Exception as e:
            # Rollback transaksi database jika terjadi error
            self.db.rollback()
            
            # Re-raise exception untuk ditangani oleh router
            raise
    
    @HistoryTracker(
        event_type=EventType.VM_STOP,
        get_user_id=get_user_id,
        get_vm_id=get_vm_id
    )
    def stop_vm(self, vm_id: int, user_id: int) -> VM:
        """
        Menghentikan VM yang sedang berjalan
        """
        vm = self.db.query(VM).filter(VM.id == vm_id, VM.user_id == user_id).first()
        
        if not vm:
            raise ValueError(f"VM dengan ID {vm_id} tidak ditemukan")
        
        if vm.status != VMStatus.RUNNING:
            raise ValueError(f"VM harus dalam status RUNNING untuk dapat dihentikan, status saat ini: {vm.status}")
        
        try:
            # Dapatkan kredensial yang didekripsi
            credentials = self._get_credential(vm.credential_id, user_id)
            
            # Hentikan VM berdasarkan provider
            if vm.provider == VMProvider.AWS:
                # Implementasi stop VM AWS
                pass
            elif vm.provider == VMProvider.GCP:
                # Implementasi stop VM GCP
                pass
            
            # Update status VM
            vm.status = VMStatus.STOPPED
            self.db.commit()
            self.db.refresh(vm)
            
            return vm
            
        except Exception as e:
            # Rollback transaksi database jika terjadi error
            self.db.rollback()
            
            # Re-raise exception untuk ditangani oleh router
            raise
    
    @HistoryTracker(
        event_type=EventType.VM_DELETE,
        get_user_id=get_user_id,
        get_vm_id=get_vm_id
    )
    def delete_vm(self, vm_id: int, user_id: int) -> bool:
        """
        Menghapus VM dari cloud dan database
        """
        vm = self.db.query(VM).filter(VM.id == vm_id, VM.user_id == user_id).first()
        
        if not vm:
            raise ValueError(f"VM dengan ID {vm_id} tidak ditemukan")
        
        try:
            # Dapatkan kredensial yang didekripsi
            credentials = self._get_credential(vm.credential_id, user_id)
            
            # Hapus VM dari cloud berdasarkan provider
            if vm.provider == VMProvider.AWS:
                # Implementasi delete VM AWS menggunakan Terraform destroy
                self.terraform_manager.destroy_aws(
                    workspace_name=f"vm-{vm.id}",
                    db=self.db,
                    user_id=user_id,
                    vm_id=vm.id
                )
            elif vm.provider == VMProvider.GCP:
                # Implementasi delete VM GCP menggunakan Terraform destroy
                self.terraform_manager.destroy_gcp(
                    workspace_name=f"vm-{vm.id}",
                    db=self.db,
                    user_id=user_id,
                    vm_id=vm.id
                )
            
            # Hapus VM dari database
            self.db.delete(vm)
            self.db.commit()
            
            return True
            
        except Exception as e:
            # Rollback transaksi database jika terjadi error
            self.db.rollback()
            
            # Re-raise exception untuk ditangani oleh router
            raise 