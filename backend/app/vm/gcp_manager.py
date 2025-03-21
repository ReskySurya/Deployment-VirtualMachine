from google.oauth2 import service_account
from google.cloud import compute_v1
from typing import Dict, Any, List, Optional
import logging
import time

logger = logging.getLogger(__name__)

class GcpVmManager:
    def __init__(self, credentials: Dict[str, Any]):
        """
        Inisialisasi manager VM GCP
        
        Args:
            credentials: Dictionary berisi kredensial GCP
        """
        self.project_id = credentials.get("gcp_project_id")
        self.service_account_info = credentials.get("gcp_service_account_json")
        
        # Buat kredensial dari service account info
        self.credentials = service_account.Credentials.from_service_account_info(
            self.service_account_info
        )
        
        # Inisialisasi klien Compute Engine
        self.instance_client = compute_v1.InstancesClient(credentials=self.credentials)
        self.zone_client = compute_v1.ZonesClient(credentials=self.credentials)
        self.region_client = compute_v1.RegionsClient(credentials=self.credentials)
        self.machine_type_client = compute_v1.MachineTypesClient(credentials=self.credentials)
        self.image_client = compute_v1.ImagesClient(credentials=self.credentials)
        self.operation_client = compute_v1.ZoneOperationsClient(credentials=self.credentials)
    
    def list_instances(self, zone: str = "us-central1-a") -> List[Dict[str, Any]]:
        """
        Mendapatkan daftar instance VM
        
        Args:
            zone: Zona GCP
            
        Returns:
            List of VM instances
        """
        try:
            request = compute_v1.ListInstancesRequest(
                project=self.project_id,
                zone=zone
            )
            
            instances = []
            for instance in self.instance_client.list(request=request):
                instances.append({
                    "id": instance.id,
                    "name": instance.name,
                    "machine_type": instance.machine_type.split("/")[-1],
                    "zone": instance.zone.split("/")[-1],
                    "status": instance.status,
                    "network_interfaces": [
                        {
                            "network": ni.network.split("/")[-1],
                            "external_ip": ni.access_configs[0].nat_i_p if ni.access_configs else None,
                            "internal_ip": ni.network_i_p
                        } for ni in instance.network_interfaces
                    ],
                    "creation_timestamp": instance.creation_timestamp
                })
            
            return instances
        except Exception as e:
            logger.error(f"Error listing GCP instances: {str(e)}")
            raise
    
    def get_instance(self, name: str, zone: str = "us-central1-a") -> Optional[Dict[str, Any]]:
        """
        Mendapatkan detail instance VM
        
        Args:
            name: Nama instance
            zone: Zona GCP
            
        Returns:
            Instance details or None if not found
        """
        try:
            request = compute_v1.GetInstanceRequest(
                project=self.project_id,
                zone=zone,
                instance=name
            )
            
            instance = self.instance_client.get(request=request)
            
            return {
                "id": instance.id,
                "name": instance.name,
                "machine_type": instance.machine_type.split("/")[-1],
                "zone": instance.zone.split("/")[-1],
                "status": instance.status,
                "network_interfaces": [
                    {
                        "network": ni.network.split("/")[-1],
                        "external_ip": ni.access_configs[0].nat_i_p if ni.access_configs else None,
                        "internal_ip": ni.network_i_p
                    } for ni in instance.network_interfaces
                ],
                "creation_timestamp": instance.creation_timestamp
            }
        except Exception as e:
            logger.error(f"Error getting GCP instance {name}: {str(e)}")
            return None
    
    def create_instance(
        self,
        name: str,
        machine_type: str = "e2-micro",
        zone: str = "us-central1-a",
        image_project: str = "debian-cloud",
        image_family: str = "debian-11"
    ) -> Dict[str, Any]:
        """
        Membuat instance VM baru
        
        Args:
            name: Nama instance
            machine_type: Tipe mesin
            zone: Zona GCP
            image_project: Proyek image
            image_family: Keluarga image
            
        Returns:
            Created instance details
        """
        try:
            # Dapatkan image terbaru
            image_request = compute_v1.GetFromFamilyImageRequest(
                project=image_project,
                family=image_family
            )
            image = self.image_client.get_from_family(request=image_request)
            
            # Buat instance
            instance = compute_v1.Instance()
            instance.name = name
            instance.machine_type = f"zones/{zone}/machineTypes/{machine_type}"
            
            # Disk boot
            disk = compute_v1.AttachedDisk()
            disk.boot = True
            disk.auto_delete = True
            disk.initialize_params = compute_v1.AttachedDiskInitializeParams()
            disk.initialize_params.source_image = image.self_link
            instance.disks = [disk]
            
            # Network interface
            network_interface = compute_v1.NetworkInterface()
            network_interface.name = "global/networks/default"
            
            access_config = compute_v1.AccessConfig()
            access_config.name = "External NAT"
            access_config.type_ = "ONE_TO_ONE_NAT"
            access_config.network_tier = "PREMIUM"
            network_interface.access_configs = [access_config]
            
            instance.network_interfaces = [network_interface]
            
            # Buat request
            request = compute_v1.InsertInstanceRequest(
                project=self.project_id,
                zone=zone,
                instance_resource=instance
            )
            
            # Kirim request
            operation = self.instance_client.insert(request=request)
            
            # Tunggu operasi selesai
            while operation.status != compute_v1.Operation.Status.DONE:
                operation_request = compute_v1.GetZoneOperationRequest(
                    project=self.project_id,
                    zone=zone,
                    operation=operation.name
                )
                operation = self.operation_client.get(request=operation_request)
                time.sleep(1)
            
            # Dapatkan detail instance
            return self.get_instance(name, zone)
        except Exception as e:
            logger.error(f"Error creating GCP instance: {str(e)}")
            raise
    
    def start_instance(self, name: str, zone: str = "us-central1-a") -> Dict[str, Any]:
        """
        Memulai instance VM yang dihentikan
        
        Args:
            name: Nama instance
            zone: Zona GCP
            
        Returns:
            Updated instance details
        """
        try:
            request = compute_v1.StartInstanceRequest(
                project=self.project_id,
                zone=zone,
                instance=name
            )
            
            operation = self.instance_client.start(request=request)
            
            # Tunggu operasi selesai
            while operation.status != compute_v1.Operation.Status.DONE:
                operation_request = compute_v1.GetZoneOperationRequest(
                    project=self.project_id,
                    zone=zone,
                    operation=operation.name
                )
                operation = self.operation_client.get(request=operation_request)
                time.sleep(1)
            
            # Dapatkan detail instance
            return self.get_instance(name, zone)
        except Exception as e:
            logger.error(f"Error starting GCP instance {name}: {str(e)}")
            raise
    
    def stop_instance(self, name: str, zone: str = "us-central1-a") -> Dict[str, Any]:
        """
        Menghentikan instance VM
        
        Args:
            name: Nama instance
            zone: Zona GCP
            
        Returns:
            Updated instance details
        """
        try:
            request = compute_v1.StopInstanceRequest(
                project=self.project_id,
                zone=zone,
                instance=name
            )
            
            operation = self.instance_client.stop(request=request)
            
            # Tunggu operasi selesai
            while operation.status != compute_v1.Operation.Status.DONE:
                operation_request = compute_v1.GetZoneOperationRequest(
                    project=self.project_id,
                    zone=zone,
                    operation=operation.name
                )
                operation = self.operation_client.get(request=operation_request)
                time.sleep(1)
            
            # Dapatkan detail instance
            return self.get_instance(name, zone)
        except Exception as e:
            logger.error(f"Error stopping GCP instance {name}: {str(e)}")
            raise
    
    def delete_instance(self, name: str, zone: str = "us-central1-a") -> Dict[str, Any]:
        """
        Menghapus instance VM
        
        Args:
            name: Nama instance
            zone: Zona GCP
            
        Returns:
            Final instance details
        """
        try:
            # Dapatkan detail instance sebelum dihapus
            instance = self.get_instance(name, zone)
            
            request = compute_v1.DeleteInstanceRequest(
                project=self.project_id,
                zone=zone,
                instance=name
            )
            
            operation = self.instance_client.delete(request=request)
            
            # Tunggu operasi selesai
            while operation.status != compute_v1.Operation.Status.DONE:
                operation_request = compute_v1.GetZoneOperationRequest(
                    project=self.project_id,
                    zone=zone,
                    operation=operation.name
                )
                operation = self.operation_client.get(request=operation_request)
                time.sleep(1)
            
            return instance
        except Exception as e:
            logger.error(f"Error deleting GCP instance {name}: {str(e)}")
            raise
