"""
Encryption handler for enhanced Meshtastic integration

This module provides PSK-based message encryption and decryption
functionality for secure Meshtastic communication.
"""

import base64
import hashlib
import secrets
import logging
from typing import Optional, Tuple
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding, hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
from .exceptions import EncryptionError, MeshtasticValidationError


logger = logging.getLogger(__name__)


class EncryptionHandler:
    """
    Handles PSK-based message encryption and decryption for Meshtastic
    
    This class provides encryption/decryption functionality using AES-256-CBC
    with PBKDF2 key derivation, compatible with Meshtastic's encryption scheme.
    """
    
    # Constants for encryption
    AES_BLOCK_SIZE = 16  # AES block size in bytes
    KEY_SIZE = 32        # AES-256 key size in bytes
    IV_SIZE = 16         # Initialization vector size in bytes
    SALT_SIZE = 16       # Salt size for key derivation
    PBKDF2_ITERATIONS = 100000  # PBKDF2 iterations
    
    def __init__(self):
        """Initialize the encryption handler"""
        self._backend = default_backend()
        logger.debug("Initialized EncryptionHandler")
    
    def encrypt_message(self, message: str, psk: str) -> bytes:
        """
        Encrypt a message using PSK-based encryption
        
        Args:
            message: Plain text message to encrypt
            psk: Base64 encoded pre-shared key
            
        Returns:
            Encrypted message bytes (salt + iv + encrypted_data)
            
        Raises:
            EncryptionError: If encryption fails
            MeshtasticValidationError: If inputs are invalid
        """
        if not message:
            raise MeshtasticValidationError("Message cannot be empty")
        
        if not psk:
            raise MeshtasticValidationError("PSK cannot be empty")
        
        try:
            # Decode PSK from base64
            psk_bytes = base64.b64decode(psk, validate=True)
            
            # Generate random salt and IV
            salt = secrets.token_bytes(self.SALT_SIZE)
            iv = secrets.token_bytes(self.IV_SIZE)
            
            # Derive encryption key from PSK using PBKDF2
            key = self._derive_key(psk_bytes, salt)
            
            # Convert message to bytes
            message_bytes = message.encode('utf-8')
            
            # Pad message to AES block size
            padder = padding.PKCS7(self.AES_BLOCK_SIZE * 8).padder()
            padded_message = padder.update(message_bytes) + padder.finalize()
            
            # Create cipher and encrypt
            cipher = Cipher(
                algorithms.AES(key),
                modes.CBC(iv),
                backend=self._backend
            )
            encryptor = cipher.encryptor()
            encrypted_data = encryptor.update(padded_message) + encryptor.finalize()
            
            # Combine salt + iv + encrypted_data
            result = salt + iv + encrypted_data
            
            logger.debug(f"Encrypted message of {len(message)} characters to {len(result)} bytes")
            return result
            
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise EncryptionError(f"Failed to encrypt message: {e}")
    
    def decrypt_message(self, encrypted_data: bytes, psk: str) -> str:
        """
        Decrypt a message using PSK-based decryption
        
        Args:
            encrypted_data: Encrypted message bytes (salt + iv + encrypted_data)
            psk: Base64 encoded pre-shared key
            
        Returns:
            Decrypted plain text message
            
        Raises:
            EncryptionError: If decryption fails
            MeshtasticValidationError: If inputs are invalid
        """
        if not encrypted_data:
            raise MeshtasticValidationError("Encrypted data cannot be empty")
        
        if not psk:
            raise MeshtasticValidationError("PSK cannot be empty")
        
        # Minimum size check (salt + iv + at least one block)
        min_size = self.SALT_SIZE + self.IV_SIZE + self.AES_BLOCK_SIZE
        if len(encrypted_data) < min_size:
            raise MeshtasticValidationError(f"Encrypted data too short (minimum {min_size} bytes)")
        
        try:
            # Decode PSK from base64
            psk_bytes = base64.b64decode(psk, validate=True)
            
            # Extract salt, IV, and encrypted data
            salt = encrypted_data[:self.SALT_SIZE]
            iv = encrypted_data[self.SALT_SIZE:self.SALT_SIZE + self.IV_SIZE]
            ciphertext = encrypted_data[self.SALT_SIZE + self.IV_SIZE:]
            
            # Derive decryption key from PSK using PBKDF2
            key = self._derive_key(psk_bytes, salt)
            
            # Create cipher and decrypt
            cipher = Cipher(
                algorithms.AES(key),
                modes.CBC(iv),
                backend=self._backend
            )
            decryptor = cipher.decryptor()
            padded_message = decryptor.update(ciphertext) + decryptor.finalize()
            
            # Remove padding
            unpadder = padding.PKCS7(self.AES_BLOCK_SIZE * 8).unpadder()
            message_bytes = unpadder.update(padded_message) + unpadder.finalize()
            
            # Convert to string
            message = message_bytes.decode('utf-8')
            
            logger.debug(f"Decrypted {len(encrypted_data)} bytes to message of {len(message)} characters")
            return message
            
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise EncryptionError(f"Failed to decrypt message: {e}")
    
    def _derive_key(self, psk_bytes: bytes, salt: bytes) -> bytes:
        """
        Derive encryption key from PSK using PBKDF2
        
        Args:
            psk_bytes: Raw PSK bytes
            salt: Salt for key derivation
            
        Returns:
            Derived key bytes
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.KEY_SIZE,
            salt=salt,
            iterations=self.PBKDF2_ITERATIONS,
            backend=self._backend
        )
        return kdf.derive(psk_bytes)
    
    @staticmethod
    def generate_psk(length: int = 32) -> str:
        """
        Generate a new random PSK
        
        Args:
            length: Length of key in bytes (1-32)
            
        Returns:
            Base64 encoded PSK string
            
        Raises:
            MeshtasticValidationError: If length is invalid
        """
        if not (1 <= length <= 32):
            raise MeshtasticValidationError("PSK length must be between 1 and 32 bytes")
        
        # Generate random key bytes
        key_bytes = secrets.token_bytes(length)
        
        # Encode to base64
        psk = base64.b64encode(key_bytes).decode('ascii')
        
        logger.info(f"Generated new PSK of {length} bytes")
        return psk
    
    @staticmethod
    def validate_psk(psk: str) -> bool:
        """
        Validate a PSK (Pre-Shared Key)
        
        Args:
            psk: Base64 encoded PSK to validate
            
        Returns:
            True if PSK is valid, False otherwise
        """
        if not psk:
            return False
        
        try:
            # Decode base64 to validate format
            decoded = base64.b64decode(psk, validate=True)
            
            # PSK should be between 1 and 32 bytes
            if not (1 <= len(decoded) <= 32):
                return False
            
            return True
        except Exception:
            return False
    
    @staticmethod
    def encode_psk(key_bytes: bytes) -> str:
        """
        Encode raw key bytes to Base64 PSK format
        
        Args:
            key_bytes: Raw key bytes to encode
            
        Returns:
            Base64 encoded PSK string
            
        Raises:
            MeshtasticValidationError: If key bytes are invalid
        """
        if not key_bytes:
            raise MeshtasticValidationError("Key bytes cannot be empty")
        
        if len(key_bytes) > 32:
            raise MeshtasticValidationError("Key cannot exceed 32 bytes")
        
        return base64.b64encode(key_bytes).decode('ascii')
    
    @staticmethod
    def decode_psk(psk: str) -> bytes:
        """
        Decode Base64 PSK to raw key bytes
        
        Args:
            psk: Base64 encoded PSK string
            
        Returns:
            Raw key bytes
            
        Raises:
            MeshtasticValidationError: If PSK is invalid
        """
        if not EncryptionHandler.validate_psk(psk):
            raise MeshtasticValidationError("Invalid PSK format")
        
        try:
            return base64.b64decode(psk, validate=True)
        except Exception as e:
            raise MeshtasticValidationError(f"Failed to decode PSK: {e}")
    
    def get_encryption_info(self, psk: str) -> dict:
        """
        Get information about encryption parameters
        
        Args:
            psk: Base64 encoded PSK
            
        Returns:
            Dictionary with encryption information
        """
        try:
            psk_bytes = base64.b64decode(psk, validate=True)
            return {
                'algorithm': 'AES-256-CBC',
                'key_derivation': 'PBKDF2-HMAC-SHA256',
                'psk_length_bytes': len(psk_bytes),
                'psk_length_bits': len(psk_bytes) * 8,
                'block_size': self.AES_BLOCK_SIZE,
                'iv_size': self.IV_SIZE,
                'salt_size': self.SALT_SIZE,
                'pbkdf2_iterations': self.PBKDF2_ITERATIONS,
                'is_valid': True
            }
        except Exception:
            return {
                'is_valid': False,
                'error': 'Invalid PSK format'
            }
    
    def test_encryption_roundtrip(self, message: str, psk: str) -> Tuple[bool, str]:
        """
        Test encryption/decryption roundtrip for validation
        
        Args:
            message: Test message
            psk: PSK to test with
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Encrypt the message
            encrypted = self.encrypt_message(message, psk)
            
            # Decrypt it back
            decrypted = self.decrypt_message(encrypted, psk)
            
            # Check if roundtrip was successful
            if decrypted == message:
                return True, ""
            else:
                return False, "Decrypted message doesn't match original"
                
        except Exception as e:
            return False, str(e)