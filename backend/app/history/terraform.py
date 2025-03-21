import json
import logging
import time
import subprocess
from typing import Dict, Any, Optional, List, Tuple
import os
import re

from app.history.models import EventType, EventStatus
from app.history.service import HistoryService
from app.history.decorators import TerraformStatus

logger = logging.getLogger(__name__)

class TerraformExecutor:
    """
    Kelas untuk mengeksekusi perintah Terraform dan mencatat hasilnya ke history
    """
    
    def __init__(self, db, user_id: int, vm_id: Optional[int] = None, credential_id: Optional[int] = None):
        """
        Inisialisasi TerraformExecutor
        
        Args:
            db: Session database
            user_id: ID pengguna
            vm_id: ID VM (opsional)
            credential_id: ID kredensial (opsional)
        """
        self.db = db
        self.user_id = user_id
        self.vm_id = vm_id
        self.credential_id = credential_id
        self.history_service = HistoryService(db)
    
    def execute(
        self, 
        command: str, 
        working_dir: str, 
        variables: Dict[str, Any] = None,
        event_type: EventType = EventType.VM_CREATE
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Mengeksekusi perintah Terraform dan mencatat hasilnya ke history
        
        Args:
            command: Perintah Terraform (apply, destroy, dll)
            working_dir: Direktori kerja Terraform
            variables: Variabel Terraform
            event_type: Tipe event
            
        Returns:
            Tuple berisi status sukses dan hasil eksekusi
        """
        # Buat event
        event = self.history_service.create_event(
            event_type=event_type,
            user_id=self.user_id,
            vm_id=self.vm_id,
            credential_id=self.credential_id,
            parameters={
                "command": command,
                "working_dir": working_dir,
                "variables": self._mask_sensitive_data(variables) if variables else None
            },
            status=TerraformStatus.INITIATED
        )
        
        # Catat waktu mulai
        start_time = time.time()
        
        try:
            # Update status ke PROVISIONING
            self.history_service.update_event(
                event_id=event.id,
                status=TerraformStatus.PROVISIONING
            )
            
            # Siapkan variabel Terraform
            env = os.environ.copy()
            if variables:
                for key, value in variables.items():
                    env[f"TF_VAR_{key}"] = str(value)
            
            # Siapkan perintah Terraform
            if command == "apply":
                cmd = ["terraform", "apply", "-auto-approve"]
            elif command == "destroy":
                cmd = ["terraform", "destroy", "-auto-approve"]
            elif command == "plan":
                cmd = ["terraform", "plan"]
            elif command == "init":
                cmd = ["terraform", "init"]
            else:
                cmd = ["terraform", command]
            
            # Eksekusi perintah Terraform
            process = subprocess.Popen(
                cmd,
                cwd=working_dir,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Baca output
            stdout, stderr = process.communicate()
            
            # Periksa status eksekusi
            success = process.returncode == 0
            
            # Parse output Terraform
            result = self._parse_terraform_output(stdout, stderr, command)
            
            # Hitung durasi
            duration = time.time() - start_time
            
            # Update event
            if success:
                self.history_service.update_event(
                    event_id=event.id,
                    status=TerraformStatus.COMPLETED,
                    result=result,
                    duration=duration
                )
            else:
                self.history_service.update_event(
                    event_id=event.id,
                    status=TerraformStatus.FAILED,
                    error_message=stderr,
                    result=result,
                    duration=duration
                )
            
            return success, result
            
        except Exception as e:
            # Hitung durasi
            duration = time.time() - start_time
            
            # Update event dengan status error
            self.history_service.update_event(
                event_id=event.id,
                status=TerraformStatus.FAILED,
                error_message=str(e),
                duration=duration
            )
            
            # Re-raise exception
            raise
    
    def _parse_terraform_output(self, stdout: str, stderr: str, command: str) -> Dict[str, Any]:
        """
        Parse output Terraform
        
        Args:
            stdout: Output standar
            stderr: Output error
            command: Perintah Terraform
            
        Returns:
            Dictionary berisi hasil parsing
        """
        result = {
            "stdout": stdout,
            "stderr": stderr,
            "resources": []
        }
        
        # Parse output untuk mendapatkan resource yang dibuat/dihapus
        if command == "apply":
            # Parse resource yang dibuat
            created_resources = re.findall(r'([\w\._-]+):\s+Creation complete', stdout)
            result["created_resources"] = created_resources
            
            # Parse output values
            output_values = self._parse_terraform_output_values(stdout)
            if output_values:
                result["output_values"] = output_values
                
            # Parse instance ID untuk VM
            instance_id = self._parse_instance_id(stdout)
            if instance_id:
                result["instance_id"] = instance_id
                
            # Parse IP address
            ip_address = self._parse_ip_address(stdout)
            if ip_address:
                result["ip_address"] = ip_address
        
        elif command == "destroy":
            # Parse resource yang dihapus
            destroyed_resources = re.findall(r'([\w\._-]+):\s+Destruction complete', stdout)
            result["destroyed_resources"] = destroyed_resources
        
        return result
    
    def _parse_terraform_output_values(self, stdout: str) -> Dict[str, Any]:
        """
        Parse output values dari Terraform
        
        Args:
            stdout: Output standar
            
        Returns:
            Dictionary berisi output values
        """
        output_values = {}
        
        # Cari bagian "Outputs:"
        outputs_section = re.search(r'Outputs:(.*?)(?=\n\n|\Z)', stdout, re.DOTALL)
        if outputs_section:
            outputs_text = outputs_section.group(1)
            
            # Parse setiap output
            output_pattern = r'(\w+)\s+=\s+(.*?)(?=\n\w+\s+=|\Z)'
            for match in re.finditer(output_pattern, outputs_text, re.DOTALL):
                key = match.group(1).strip()
                value = match.group(2).strip()
                output_values[key] = value
        
        return output_values
    
    def _parse_instance_id(self, stdout: str) -> Optional[str]:
        """
        Parse instance ID dari output Terraform
        
        Args:
            stdout: Output standar
            
        Returns:
            Instance ID jika ditemukan
        """
        # AWS instance ID
        aws_instance_id = re.search(r'instance_id\s+=\s+(i-[a-f0-9]+)', stdout)
        if aws_instance_id:
            return aws_instance_id.group(1)
        
        # GCP instance ID
        gcp_instance_id = re.search(r'instance_id\s+=\s+([a-z0-9-]+)', stdout)
        if gcp_instance_id:
            return gcp_instance_id.group(1)
        
        return None
    
    def _parse_ip_address(self, stdout: str) -> Dict[str, str]:
        """
        Parse IP address dari output Terraform
        
        Args:
            stdout: Output standar
            
        Returns:
            Dictionary berisi IP address
        """
        result = {}
        
        # Public IP
        public_ip = re.search(r'public_ip\s+=\s+(\d+\.\d+\.\d+\.\d+)', stdout)
        if public_ip:
            result["public_ip"] = public_ip.group(1)
        
        # Private IP
        private_ip = re.search(r'private_ip\s+=\s+(\d+\.\d+\.\d+\.\d+)', stdout)
        if private_ip:
            result["private_ip"] = private_ip.group(1)
        
        return result
    
    def _mask_sensitive_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Menyembunyikan data sensitif seperti password, secret key, dll
        
        Args:
            data: Data yang akan disembunyikan
            
        Returns:
            Data yang sudah disembunyikan
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