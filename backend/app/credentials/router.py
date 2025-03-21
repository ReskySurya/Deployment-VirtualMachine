from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import logging
import json
from app.database import get_db
from app.users.models import User
from app.auth.jwt import get_current_user
from app.credentials.models import (
    Credential, 
    CredentialType, 
    CredentialCreate, 
    CredentialResponse,
    CredentialListResponse,
    AWSCredentialCreate,
    GCPCredentialCreate
)
from app.credentials.encryption import encrypt_credentials, decrypt_credentials, mask_sensitive_data
from app.credentials.service import CredentialService

router = APIRouter(
    prefix="/credentials",
    tags=["credentials"],
    responses={404: {"description": "Not found"}},
)
logger = logging.getLogger(__name__)

@router.post("/", response_model=CredentialResponse)
def create_credential(
    credential: CredentialCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Membuat kredensial baru untuk cloud provider
    """
    credential_service = CredentialService(db)
    
    try:
        new_credential = credential_service.create_credential(
            user_id=current_user.id,
            credential_data=credential.dict()
        )
        return new_credential
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Terjadi kesalahan saat membuat kredensial: {str(e)}"
        )

@router.get("/", response_model=CredentialListResponse)
def list_credentials(
    limit: int = Query(100, ge=1, le=1000, description="Jumlah maksimum kredensial yang dikembalikan"),
    offset: int = Query(0, ge=0, description="Jumlah kredensial yang dilewati untuk paginasi"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Mendapatkan daftar kredensial milik pengguna
    """
    credential_service = CredentialService(db)
    
    credentials = credential_service.list_credentials(
        user_id=current_user.id,
        limit=limit,
        offset=offset
    )
    
    total = credential_service.count_credentials(current_user.id)
    
    return CredentialListResponse(credentials=credentials, total=total)

@router.get("/{credential_id}", response_model=CredentialResponse)
def get_credential(
    credential_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Mendapatkan detail kredensial berdasarkan ID
    """
    credential_service = CredentialService(db)
    
    credential = credential_service.get_credential(
        credential_id=credential_id,
        user_id=current_user.id
    )
    
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Kredensial dengan ID {credential_id} tidak ditemukan"
        )
    
    return credential

@router.delete("/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_credential(
    credential_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Menghapus kredensial berdasarkan ID
    """
    credential_service = CredentialService(db)
    
    try:
        credential_service.delete_credential(
            credential_id=credential_id,
            user_id=current_user.id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Terjadi kesalahan saat menghapus kredensial: {str(e)}"
        )

@router.put("/{credential_id}", response_model=CredentialResponse)
async def update_credential(
    credential_id: int,
    credential_data: CredentialCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update a credential
    """
    credential_service = CredentialService(db)
    
    credential = credential_service.get_credential(
        credential_id=credential_id,
        user_id=current_user.id
    )
    
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential not found"
        )
    
    # Validate credential type matches existing
    if credential_data.type != credential.type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change credential type"
        )
    
    # Encrypt new credentials
    if credential.type == CredentialType.AWS:
        if not credential_data.aws_credentials:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="AWS credentials required"
            )
        credentials_to_encrypt = {
            "aws_access_key_id": credential_data.aws_credentials.aws_access_key_id,
            "aws_secret_access_key": credential_data.aws_credentials.aws_secret_access_key,
            "aws_region": credential_data.aws_credentials.aws_region
        }
    elif credential.type == CredentialType.GCP:
        if not credential_data.gcp_credentials:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GCP credentials required"
            )
        credentials_to_encrypt = {
            "gcp_service_account_json": credential_data.gcp_credentials.gcp_service_account_json,
            "gcp_project_id": credential_data.gcp_credentials.gcp_project_id
        }
    
    encrypted_data = encrypt_credentials(credentials_to_encrypt)
    
    # Update credential
    credential.name = credential_data.name
    credential.encrypted_data = encrypted_data
    
    credential_service.update_credential(credential)
    
    return credential

@router.get("/{credential_id}/validate", response_model=dict)
async def validate_credential(
    credential_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Validate that a credential works with the cloud provider
    """
    credential_service = CredentialService(db)
    
    credential = credential_service.get_credential(
        credential_id=credential_id,
        user_id=current_user.id
    )
    
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential not found"
        )
    
    # Decrypt credentials
    try:
        decrypted_data = decrypt_credentials(credential.encrypted_data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error decrypting credentials: {str(e)}"
        )
    
    # Validate with cloud provider
    try:
        if credential.type == CredentialType.AWS:
            # Code to validate AWS credentials would go here
            # For example, using boto3 to list regions
            import boto3
            from botocore.exceptions import ClientError
            
            try:
                session = boto3.Session(
                    aws_access_key_id=decrypted_data["aws_access_key_id"],
                    aws_secret_access_key=decrypted_data["aws_secret_access_key"],
                    region_name=decrypted_data["aws_region"]
                )
                ec2 = session.client('ec2')
                ec2.describe_regions()  # This will fail if credentials are invalid
                
                return {"valid": True, "message": "AWS credentials validated successfully"}
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                error_message = e.response.get('Error', {}).get('Message', str(e))
                return {
                    "valid": False, 
                    "message": f"AWS validation failed: {error_code} - {error_message}"
                }
            
        elif credential.type == CredentialType.GCP:
            # Code to validate GCP credentials would go here
            # For example, using google-auth and google-cloud-compute
            from google.oauth2 import service_account
            from google.cloud import compute_v1
            from google.api_core.exceptions import GoogleAPIError
            
            try:
                credentials = service_account.Credentials.from_service_account_info(
                    decrypted_data["gcp_service_account_json"]
                )
                
                # Test listing zones in the project
                client = compute_v1.ZonesClient(credentials=credentials)
                client.list(project=decrypted_data["gcp_project_id"], max_results=1)
                
                return {"valid": True, "message": "GCP credentials validated successfully"}
            except GoogleAPIError as e:
                return {
                    "valid": False, 
                    "message": f"GCP validation failed: {str(e)}"
                }
            except ValueError as e:
                return {
                    "valid": False, 
                    "message": f"Invalid GCP service account JSON: {str(e)}"
                }
        
        else:
            return {
                "valid": False, 
                "message": f"Unsupported credential type: {credential.type}"
            }
            
    except ImportError as e:
        # Handle case where required libraries are not installed
        return {
            "valid": False, 
            "message": f"Required library not installed: {str(e)}"
        }
    except Exception as e:
        return {"valid": False, "message": f"Validation failed: {str(e)}"}

@router.get("/{credential_id}/details", response_model=Dict[str, Any])
async def get_credential_details(
    credential_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get decrypted credential details for editing
    """
    credential_service = CredentialService(db)
    
    credential = credential_service.get_credential(
        credential_id=credential_id,
        user_id=current_user.id
    )
    
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential not found"
        )
    
    # Decrypt credentials
    try:
        decrypted_data = decrypt_credentials(credential.encrypted_data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error decrypting credentials: {str(e)}"
        )
    
    # Prepare response based on credential type
    response = {
        "id": credential.id,
        "name": credential.name,
        "type": credential.type,
        "created_at": credential.created_at,
        "updated_at": credential.updated_at
    }
    
    if credential.type == CredentialType.AWS:
        response["aws_credentials"] = {
            "aws_access_key_id": decrypted_data.get("aws_access_key_id", ""),
            "aws_secret_access_key": decrypted_data.get("aws_secret_access_key", ""),
            "aws_region": decrypted_data.get("aws_region", "us-east-1")
        }
    elif credential.type == CredentialType.GCP:
        response["gcp_credentials"] = {
            "gcp_project_id": decrypted_data.get("gcp_project_id", ""),
            "gcp_service_account_json": decrypted_data.get("gcp_service_account_json", {})
        }
    
    return response

@router.post("/upload-gcp-json", response_model=Dict[str, Any])
async def upload_gcp_json(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """
    Upload file JSON kredensial GCP
    
    Endpoint ini menerima file JSON kredensial GCP dan mengembalikan data yang dapat digunakan
    untuk membuat kredensial GCP melalui endpoint /credentials/
    
    Langkah-langkah penggunaan:
    1. Upload file JSON kredensial GCP melalui endpoint ini
    2. Gunakan data yang dikembalikan untuk membuat kredensial GCP melalui endpoint /credentials/
    
    Contoh penggunaan hasil endpoint ini:
    ```json
    {
      "name": "GCP Credential Saya",
      "type": "gcp",
      "gcp_credentials": {
        "gcp_service_account_json": { ... }, // Data dari respons endpoint ini
        "gcp_project_id": "your-project-id" // Data dari respons endpoint ini
      }
    }
    ```
    """
    if not file.filename.endswith('.json'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File harus berformat JSON"
        )
    
    try:
        # Baca konten file
        contents = await file.read()
        gcp_json = json.loads(contents)
        
        # Validasi format JSON
        required_fields = [
            "type", "project_id", "private_key_id", "private_key",
            "client_email", "client_id", "auth_uri", "token_uri"
        ]
        
        for field in required_fields:
            if field not in gcp_json:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File JSON tidak valid: field '{field}' tidak ditemukan"
                )
        
        if gcp_json.get("type") != "service_account":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File JSON bukan service account"
            )
        
        # Log dengan masking data sensitif
        masked_json = mask_sensitive_data(gcp_json)
        logger.info(f"GCP JSON berhasil diunggah oleh user {current_user.id}: {masked_json}")
        
        # Kembalikan data yang diperlukan untuk membuat kredensial
        return {
            "success": True,
            "message": "File JSON berhasil diunggah",
            "data": {
                "gcp_service_account_json": gcp_json,
                "gcp_project_id": gcp_json.get("project_id")
            }
        }
        
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File bukan JSON yang valid"
        )
    except Exception as e:
        logger.error(f"Error saat mengunggah file GCP JSON: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gagal memproses file: {str(e)}"
        )