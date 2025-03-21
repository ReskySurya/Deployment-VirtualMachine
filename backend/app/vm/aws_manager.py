import boto3
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)

class AwsVmManager:
    def __init__(self, credentials: Dict[str, Any]):
        """
        Inisialisasi manager VM AWS
        
        Args:
            credentials: Dictionary berisi kredensial AWS
        """
        self.aws_access_key_id = credentials.get("aws_access_key_id")
        self.aws_secret_access_key = credentials.get("aws_secret_access_key")
        self.region = credentials.get("aws_region", "us-east-1")
        
        # Inisialisasi klien EC2
        self.ec2_client = boto3.client(
            'ec2',
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            region_name=self.region
        )
        
        self.ec2_resource = boto3.resource(
            'ec2',
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            region_name=self.region
        )
    
    def list_instances(self) -> List[Dict[str, Any]]:
        """
        Mendapatkan daftar instance EC2
        
        Returns:
            List of EC2 instances
        """
        try:
            response = self.ec2_client.describe_instances()
            instances = []
            
            for reservation in response.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    instances.append({
                        "instance_id": instance.get("InstanceId"),
                        "instance_type": instance.get("InstanceType"),
                        "state": instance.get("State", {}).get("Name"),
                        "public_ip": instance.get("PublicIpAddress"),
                        "private_ip": instance.get("PrivateIpAddress"),
                        "launch_time": instance.get("LaunchTime"),
                        "tags": instance.get("Tags", [])
                    })
            
            return instances
        except Exception as e:
            logger.error(f"Error listing AWS instances: {str(e)}")
            raise
    
    def get_instance(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """
        Mendapatkan detail instance EC2
        
        Args:
            instance_id: ID instance EC2
            
        Returns:
            Instance details or None if not found
        """
        try:
            response = self.ec2_client.describe_instances(InstanceIds=[instance_id])
            
            for reservation in response.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    return {
                        "instance_id": instance.get("InstanceId"),
                        "instance_type": instance.get("InstanceType"),
                        "state": instance.get("State", {}).get("Name"),
                        "public_ip": instance.get("PublicIpAddress"),
                        "private_ip": instance.get("PrivateIpAddress"),
                        "launch_time": instance.get("LaunchTime"),
                        "tags": instance.get("Tags", [])
                    }
            
            return None
        except Exception as e:
            logger.error(f"Error getting AWS instance {instance_id}: {str(e)}")
            raise
    
    def create_instance(
        self, 
        name: str,
        instance_type: str = "t2.micro",
        ami_id: str = "ami-0c55b159cbfafe1f0",  # Amazon Linux 2 AMI
        key_name: Optional[str] = None,
        security_group_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Membuat instance EC2 baru
        
        Args:
            name: Nama instance
            instance_type: Tipe instance EC2
            ami_id: ID AMI
            key_name: Nama key pair
            security_group_ids: List ID security group
            
        Returns:
            Created instance details
        """
        try:
            run_args = {
                "ImageId": ami_id,
                "InstanceType": instance_type,
                "MinCount": 1,
                "MaxCount": 1,
                "TagSpecifications": [
                    {
                        "ResourceType": "instance",
                        "Tags": [
                            {
                                "Key": "Name",
                                "Value": name
                            }
                        ]
                    }
                ]
            }
            
            if key_name:
                run_args["KeyName"] = key_name
                
            if security_group_ids:
                run_args["SecurityGroupIds"] = security_group_ids
            
            response = self.ec2_client.run_instances(**run_args)
            
            instance = response.get("Instances", [])[0]
            instance_id = instance.get("InstanceId")
            
            # Tunggu instance running
            waiter = self.ec2_client.get_waiter('instance_running')
            waiter.wait(InstanceIds=[instance_id])
            
            # Dapatkan detail instance terbaru
            return self.get_instance(instance_id)
        except Exception as e:
            logger.error(f"Error creating AWS instance: {str(e)}")
            raise
    
    def start_instance(self, instance_id: str) -> Dict[str, Any]:
        """
        Memulai instance EC2 yang dihentikan
        
        Args:
            instance_id: ID instance EC2
            
        Returns:
            Updated instance details
        """
        try:
            self.ec2_client.start_instances(InstanceIds=[instance_id])
            
            # Tunggu instance running
            waiter = self.ec2_client.get_waiter('instance_running')
            waiter.wait(InstanceIds=[instance_id])
            
            return self.get_instance(instance_id)
        except Exception as e:
            logger.error(f"Error starting AWS instance {instance_id}: {str(e)}")
            raise
    
    def stop_instance(self, instance_id: str) -> Dict[str, Any]:
        """
        Menghentikan instance EC2
        
        Args:
            instance_id: ID instance EC2
            
        Returns:
            Updated instance details
        """
        try:
            self.ec2_client.stop_instances(InstanceIds=[instance_id])
            
            # Tunggu instance stopped
            waiter = self.ec2_client.get_waiter('instance_stopped')
            waiter.wait(InstanceIds=[instance_id])
            
            return self.get_instance(instance_id)
        except Exception as e:
            logger.error(f"Error stopping AWS instance {instance_id}: {str(e)}")
            raise
    
    def terminate_instance(self, instance_id: str) -> Dict[str, Any]:
        """
        Menghapus instance EC2
        
        Args:
            instance_id: ID instance EC2
            
        Returns:
            Final instance details
        """
        try:
            # Dapatkan detail instance sebelum dihapus
            instance = self.get_instance(instance_id)
            
            self.ec2_client.terminate_instances(InstanceIds=[instance_id])
            
            # Tunggu instance terminated
            waiter = self.ec2_client.get_waiter('instance_terminated')
            waiter.wait(InstanceIds=[instance_id])
            
            return instance
        except Exception as e:
            logger.error(f"Error terminating AWS instance {instance_id}: {str(e)}")
            raise
