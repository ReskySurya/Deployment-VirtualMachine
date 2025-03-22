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
    
    # Menyiapkan log untuk debug
    logger.debug(f"Validating credential type: {credential.type}")
    logger.debug(f"Decrypted data keys: {decrypted_data.keys()}")
    
    # Validate with cloud provider
    try:
        if credential.type == CredentialType.AWS:
            # Code to validate AWS credentials
            import boto3
            from botocore.exceptions import ClientError, NoCredentialsError
            
            try:
                # Cek kunci yang ada di data terenkripsi
                aws_access_key = decrypted_data.get('access_key') or decrypted_data.get('aws_access_key_id')
                aws_secret_key = decrypted_data.get('secret_key') or decrypted_data.get('aws_secret_access_key') 
                aws_region = decrypted_data.get('region') or decrypted_data.get('aws_region')
                
                if not aws_access_key:
                    return {"valid": False, "message": "Validation failed: 'aws_access_key_id'"}
                    
                if not aws_secret_key:
                    return {"valid": False, "message": "Validation failed: 'aws_secret_access_key'"}
                    
                if not aws_region:
                    return {"valid": False, "message": "Validation failed: 'aws_region'"}
                
                logger.debug(f"Using AWS credentials with region: {aws_region}")
                
                # Buat sesi dengan kredensial
                session = boto3.Session(
                    aws_access_key_id=aws_access_key,
                    aws_secret_access_key=aws_secret_key,
                    region_name=aws_region
                )
                
                # Coba akses layanan EC2 untuk validasi
                ec2 = session.client('ec2')
                ec2.describe_regions()  # Ini akan gagal jika kredensial tidak valid
                
                return {"valid": True, "message": "Kredensial AWS berhasil divalidasi"}
                
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                error_message = e.response.get('Error', {}).get('Message', str(e))
                logger.error(f"AWS validation error: {error_code} - {error_message}")
                return {
                    "valid": False, 
                    "message": f"Validasi AWS gagal: {error_code} - {error_message}"
                }
            except NoCredentialsError:
                logger.error("AWS validation error: No credentials provided")
                return {
                    "valid": False,
                    "message": "Validasi AWS gagal: Kredensial tidak ditemukan"
                }
            except Exception as e:
                logger.error(f"Unexpected AWS validation error: {str(e)}")
                return {
                    "valid": False,
                    "message": f"Validasi AWS gagal: {str(e)}"
                }
            
        elif credential.type == CredentialType.GCP:
            # Code to validate GCP credentials
            from google.oauth2 import service_account
            from google.cloud import storage
            import json
            
            try:
                # Cek format kredensial GCP
                if 'gcp_service_account_json' in decrypted_data:
                    # Format lengkap dari file JSON
                    service_account_info = decrypted_data['gcp_service_account_json']
                else:
                    # Format dari input manual
                    service_account_info = {
                        "type": "service_account",
                        "project_id": decrypted_data.get('project_id'),
                        "private_key_id": decrypted_data.get('private_key_id'),
                        "private_key": decrypted_data.get('private_key'),
                        "client_email": decrypted_data.get('client_email'),
                        "client_id": decrypted_data.get('client_id'),
                        "auth_uri": decrypted_data.get('auth_uri', "https://accounts.google.com/o/oauth2/auth"),
                        "token_uri": decrypted_data.get('token_uri', "https://oauth2.googleapis.com/token"),
                        "auth_provider_x509_cert_url": decrypted_data.get('auth_provider_x509_cert_url', 
                                                        "https://www.googleapis.com/oauth2/v1/certs"),
                        "client_x509_cert_url": decrypted_data.get('client_x509_cert_url', "")
                    }
                
                # Validasi field-field penting
                for field in ['project_id', 'private_key', 'client_email']:
                    if not service_account_info.get(field):
                        return {"valid": False, "message": f"Validation failed: '{field}'"}
                
                # Buat kredensial dari informasi service account
                credentials = service_account.Credentials.from_service_account_info(service_account_info)
                
                # Validasi dengan mencoba mengakses layanan Storage
                storage_client = storage.Client(credentials=credentials, project=service_account_info['project_id'])
                # Coba list buckets (hanya mengecek koneksi)
                storage_client.list_buckets(max_results=1)
                
                return {"valid": True, "message": "Kredensial GCP berhasil divalidasi"}
                
            except Exception as e:
                logger.error(f"GCP validation error: {str(e)}")
                return {
                    "valid": False,
                    "message": f"Validasi GCP gagal: {str(e)}"
                }
        else:
            return {
                "valid": False,
                "message": f"Tipe kredensial tidak didukung: {credential.type}"
            }
    except Exception as e:
        logger.error(f"Unexpected error in credential validation: {str(e)}")
        return {
            "valid": False,
            "message": f"Validasi gagal: {str(e)}"
        }

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