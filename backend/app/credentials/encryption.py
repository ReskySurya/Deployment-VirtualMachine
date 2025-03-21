from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad
import base64
import json
from app.config import settings
import hashlib
import os
import logging

logger = logging.getLogger(__name__)

def get_encryption_key():
    """
    Derive an encryption key from the settings
    """
    if not settings.CREDENTIALS_ENCRYPTION_KEY:
        raise ValueError("CREDENTIALS_ENCRYPTION_KEY not set in environment variables")
    
    # Use a hash of the settings key to ensure proper length
    return hashlib.sha256(settings.CREDENTIALS_ENCRYPTION_KEY.encode()).digest()

def encrypt_credentials(credentials_data):
    """
    Encrypt credentials data before storing in database
    
    Args:
        credentials_data (dict): Dictionary of credential data
        
    Returns:
        str: Base64 encoded encrypted data with IV prepended
    """
    try:
        # Convert dict to JSON string
        data = json.dumps(credentials_data).encode('utf-8')
        
        # Create cipher with random IV
        key = get_encryption_key()
        iv = get_random_bytes(16)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        
        # Pad and encrypt
        padded_data = pad(data, AES.block_size)
        encrypted_data = cipher.encrypt(padded_data)
        
        # Combine IV and encrypted data and encode as base64
        result = base64.b64encode(iv + encrypted_data).decode('utf-8')
        return result
    except Exception as e:
        logger.error(f"Error encrypting credentials: {str(e)}")
        raise ValueError(f"Failed to encrypt credentials: {str(e)}")

def decrypt_credentials(encrypted_data):
    """
    Decrypt credentials data retrieved from database
    
    Args:
        encrypted_data (str): Base64 encoded encrypted data with IV prepended
        
    Returns:
        dict: Dictionary of credential data
    """
    try:
        # Decode from base64
        raw_data = base64.b64decode(encrypted_data.encode('utf-8'))
        
        # Extract IV and encrypted data
        iv = raw_data[:16]
        encrypted_credentials = raw_data[16:]
        
        # Create cipher with extracted IV
        key = get_encryption_key()
        cipher = AES.new(key, AES.MODE_CBC, iv)
        
        # Decrypt and unpad
        decrypted_data = unpad(cipher.decrypt(encrypted_credentials), AES.block_size)
        
        # Convert JSON string back to dict
        return json.loads(decrypted_data.decode('utf-8'))
    except ValueError as e:
        logger.error(f"Error decrypting credentials (value error): {str(e)}")
        raise ValueError(f"Failed to decrypt credentials: {str(e)}")
    except Exception as e:
        logger.error(f"Error decrypting credentials: {str(e)}")
        raise ValueError("Failed to decrypt credentials")

def mask_sensitive_data(data, mask_char="*", show_chars=4):
    """
    Mask sensitive data for logging or display
    
    Args:
        data (dict): Dictionary containing sensitive data
        mask_char (str): Character to use for masking
        show_chars (int): Number of characters to show at the end
        
    Returns:
        dict: Dictionary with sensitive data masked
    """
    if not isinstance(data, dict):
        return data
    
    masked_data = data.copy()
    
    sensitive_keys = [
        "aws_secret_access_key", 
        "private_key", 
        "password", 
        "secret", 
        "token"
    ]
    
    for key, value in masked_data.items():
        if isinstance(value, dict):
            masked_data[key] = mask_sensitive_data(value, mask_char, show_chars)
        elif isinstance(value, str) and any(sensitive_key in key.lower() for sensitive_key in sensitive_keys):
            if len(value) <= show_chars:
                masked_data[key] = mask_char * len(value)
            else:
                masked_data[key] = mask_char * (len(value) - show_chars) + value[-show_chars:]
    
    return masked_data