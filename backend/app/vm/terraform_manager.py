import os
import json
import tempfile
import subprocess
import logging
import shutil
from typing import Dict, Any, Optional

from app.history.terraform import TerraformExecutor
from app.history.models import EventType

logger = logging.getLogger(__name__)

class TerraformManager:
    def __init__(self, terraform_dir: str):
        """
        Inisialisasi Terraform Manager
        
        Args:
            terraform_dir: Direktori tempat file Terraform berada
        """
        self.terraform_dir = terraform_dir
    
    def _create_vars_file(self, vars_data: Dict[str, Any], provider: str) -> str:
        """
        Membuat file terraform.tfvars.json
        
        Args:
            vars_data: Data variabel Terraform
            provider: Provider cloud (aws/gcp)
            
        Returns:
            Path ke direktori kerja
        """
        # Buat direktori kerja
        work_dir = os.path.join(tempfile.gettempdir(), f"terraform_{provider}_{os.urandom(8).hex()}")
        os.makedirs(work_dir, exist_ok=True)
        
        # Salin file Terraform ke direktori kerja
        provider_dir = os.path.join(self.terraform_dir, provider)
        for filename in os.listdir(provider_dir):
            if filename.endswith('.tf'):
                src_path = os.path.join(provider_dir, filename)
                dst_path = os.path.join(work_dir, filename)
                with open(src_path, 'r') as src, open(dst_path, 'w') as dst:
                    dst.write(src.read())
        
        # Buat file tfvars
        tfvars_path = os.path.join(work_dir, "terraform.tfvars.json")
        with open(tfvars_path, 'w') as f:
            json.dump(vars_data, f)
        
        return work_dir
    
    def apply_aws(self, workspace_name: str, variables: Dict[str, Any], db=None, user_id: Optional[int] = None, vm_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Menerapkan konfigurasi Terraform untuk AWS
        
        Args:
            workspace_name: Nama workspace Terraform
            variables: Variabel Terraform
            db: Session database (opsional)
            user_id: ID pengguna (opsional)
            vm_id: ID VM (opsional)
            
        Returns:
            Detail instance yang dibuat
        """
        # Siapkan variabel Terraform
        vars_data = {
            "access_key": variables.get("aws_access_key"),
            "secret_key": variables.get("aws_secret_key"),
            "region": variables.get("region", "us-east-1"),
            "name": variables.get("name"),
            "instance_type": variables.get("instance_type", "t2.micro"),
            "ami_id": variables.get("ami_id", "ami-0c55b159cbfafe1f0"),
            "key_name": variables.get("key_name"),
            "security_group_ids": variables.get("security_group_ids", [])
        }
        
        # Buat direktori kerja dan file tfvars
        work_dir = self._create_vars_file(vars_data, "aws")
        
        try:
            if db and user_id:
                # Gunakan TerraformExecutor untuk mencatat history
                executor = TerraformExecutor(db, user_id, vm_id)
                success, result = executor.execute(
                    command="apply",
                    working_dir=work_dir,
                    variables=vars_data,
                    event_type=EventType.VM_CREATE
                )
                
                if not success:
                    raise Exception(f"Terraform apply gagal: {result.get('stderr')}")
                
                # Format hasil
                return {
                    "instance_id": result.get("instance_id"),
                    "public_ip": result.get("ip_address", {}).get("public_ip"),
                    "private_ip": result.get("ip_address", {}).get("private_ip"),
                    "status": "running"
                }
            else:
                # Jalankan Terraform tanpa mencatat history
                # Inisialisasi Terraform
                init_process = subprocess.run(
                    ["terraform", "init"],
                    cwd=work_dir,
                    capture_output=True,
                    text=True,
                    check=True
                )
                logger.info(f"Terraform init output: {init_process.stdout}")
                
                # Jalankan Terraform apply
                process = subprocess.run(
                    ["terraform", "apply", "-auto-approve"],
                    cwd=work_dir,
                    capture_output=True,
                    text=True,
                    check=True
                )
                logger.info(f"Terraform apply output: {process.stdout}")
                
                # Dapatkan output Terraform
                output_process = subprocess.run(
                    ["terraform", "output", "-json"],
                    cwd=work_dir,
                    capture_output=True,
                    text=True,
                    check=True
                )
                
                # Parse output JSON
                output = json.loads(output_process.stdout)
                
                # Konversi output ke format yang lebih sederhana
                result = {}
                for key, value in output.items():
                    result[key] = value.get("value")
                
                # Format hasil
                return {
                    "instance_id": result.get("instance_id"),
                    "public_ip": result.get("public_ip"),
                    "private_ip": result.get("private_ip"),
                    "status": "running"
                }
        finally:
            # Bersihkan direktori kerja jika diperlukan
            # shutil.rmtree(work_dir)
            pass
    
    def destroy_aws(self, workspace_name: str, db=None, user_id: Optional[int] = None, vm_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Menghapus instance AWS menggunakan Terraform
        
        Args:
            workspace_name: Nama workspace Terraform
            db: Session database (opsional)
            user_id: ID pengguna (opsional)
            vm_id: ID VM (opsional)
            
        Returns:
            Status penghapusan
        """
        # Dapatkan direktori workspace
        workspace_dir = os.path.join(self.terraform_dir, "workspaces", workspace_name)
        
        if not os.path.exists(workspace_dir):
            raise Exception(f"Workspace {workspace_name} tidak ditemukan")
        
        try:
            if db and user_id:
                # Gunakan TerraformExecutor untuk mencatat history
                executor = TerraformExecutor(db, user_id, vm_id)
                success, result = executor.execute(
                    command="destroy",
                    working_dir=workspace_dir,
                    event_type=EventType.VM_DELETE
                )
                
                if not success:
                    raise Exception(f"Terraform destroy gagal: {result.get('stderr')}")
                
                return {"status": "destroyed"}
            else:
                # Jalankan Terraform tanpa mencatat history
                # Inisialisasi Terraform
                init_process = subprocess.run(
                    ["terraform", "init"],
                    cwd=workspace_dir,
                    capture_output=True,
                    text=True,
                    check=True
                )
                logger.info(f"Terraform init output: {init_process.stdout}")
                
                # Jalankan Terraform destroy
                process = subprocess.run(
                    ["terraform", "destroy", "-auto-approve"],
                    cwd=workspace_dir,
                    capture_output=True,
                    text=True,
                    check=True
                )
                logger.info(f"Terraform destroy output: {process.stdout}")
                
                return {"status": "destroyed"}
        finally:
            # Bersihkan direktori workspace jika diperlukan
            # shutil.rmtree(workspace_dir)
            pass
    
    def apply_gcp(self, workspace_name: str, variables: Dict[str, Any], db=None, user_id: Optional[int] = None, vm_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Menerapkan konfigurasi Terraform untuk GCP
        
        Args:
            workspace_name: Nama workspace Terraform
            variables: Variabel Terraform
            db: Session database (opsional)
            user_id: ID pengguna (opsional)
            vm_id: ID VM (opsional)
            
        Returns:
            Detail instance yang dibuat
        """
        # Siapkan variabel Terraform
        vars_data = {
            "credentials_json": variables.get("gcp_credentials_json"),
            "project_id": variables.get("gcp_project_id"),
            "region": variables.get("region", "us-central1"),
            "zone": variables.get("zone", "us-central1-a"),
            "name": variables.get("name"),
            "machine_type": variables.get("instance_type", "e2-micro"),
            "image": variables.get("image", "debian-cloud/debian-11")
        }
        
        # Buat direktori kerja dan file tfvars
        work_dir = self._create_vars_file(vars_data, "gcp")
        
        try:
            if db and user_id:
                # Gunakan TerraformExecutor untuk mencatat history
                executor = TerraformExecutor(db, user_id, vm_id)
                success, result = executor.execute(
                    command="apply",
                    working_dir=work_dir,
                    variables=vars_data,
                    event_type=EventType.VM_CREATE
                )
                
                if not success:
                    raise Exception(f"Terraform apply gagal: {result.get('stderr')}")
                
                # Format hasil
                return {
                    "instance_id": result.get("instance_id"),
                    "external_ip": result.get("ip_address", {}).get("public_ip"),
                    "internal_ip": result.get("ip_address", {}).get("private_ip"),
                    "status": "RUNNING"
                }
            else:
                # Jalankan Terraform tanpa mencatat history
                # Inisialisasi Terraform
                init_process = subprocess.run(
                    ["terraform", "init"],
                    cwd=work_dir,
                    capture_output=True,
                    text=True,
                    check=True
                )
                logger.info(f"Terraform init output: {init_process.stdout}")
                
                # Jalankan Terraform apply
                process = subprocess.run(
                    ["terraform", "apply", "-auto-approve"],
                    cwd=work_dir,
                    capture_output=True,
                    text=True,
                    check=True
                )
                logger.info(f"Terraform apply output: {process.stdout}")
                
                # Dapatkan output Terraform
                output_process = subprocess.run(
                    ["terraform", "output", "-json"],
                    cwd=work_dir,
                    capture_output=True,
                    text=True,
                    check=True
                )
                
                # Parse output JSON
                output = json.loads(output_process.stdout)
                
                # Konversi output ke format yang lebih sederhana
                result = {}
                for key, value in output.items():
                    result[key] = value.get("value")
                
                # Format hasil
                return {
                    "instance_id": result.get("instance_id"),
                    "external_ip": result.get("external_ip"),
                    "internal_ip": result.get("internal_ip"),
                    "status": "RUNNING"
                }
        finally:
            # Bersihkan direktori kerja jika diperlukan
            # shutil.rmtree(work_dir)
            pass
    
    def destroy_gcp(self, workspace_name: str, db=None, user_id: Optional[int] = None, vm_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Menghapus instance GCP menggunakan Terraform
        
        Args:
            workspace_name: Nama workspace Terraform
            db: Session database (opsional)
            user_id: ID pengguna (opsional)
            vm_id: ID VM (opsional)
            
        Returns:
            Status penghapusan
        """
        # Dapatkan direktori workspace
        workspace_dir = os.path.join(self.terraform_dir, "workspaces", workspace_name)
        
        if not os.path.exists(workspace_dir):
            raise Exception(f"Workspace {workspace_name} tidak ditemukan")
        
        try:
            if db and user_id:
                # Gunakan TerraformExecutor untuk mencatat history
                executor = TerraformExecutor(db, user_id, vm_id)
                success, result = executor.execute(
                    command="destroy",
                    working_dir=workspace_dir,
                    event_type=EventType.VM_DELETE
                )
                
                if not success:
                    raise Exception(f"Terraform destroy gagal: {result.get('stderr')}")
                
                return {"status": "destroyed"}
            else:
                # Jalankan Terraform tanpa mencatat history
                # Inisialisasi Terraform
                init_process = subprocess.run(
                    ["terraform", "init"],
                    cwd=workspace_dir,
                    capture_output=True,
                    text=True,
                    check=True
                )
                logger.info(f"Terraform init output: {init_process.stdout}")
                
                # Jalankan Terraform destroy
                process = subprocess.run(
                    ["terraform", "destroy", "-auto-approve"],
                    cwd=workspace_dir,
                    capture_output=True,
                    text=True,
                    check=True
                )
                logger.info(f"Terraform destroy output: {process.stdout}")
                
                return {"status": "destroyed"}
        finally:
            # Bersihkan direktori workspace jika diperlukan
            # shutil.rmtree(workspace_dir)
            pass 