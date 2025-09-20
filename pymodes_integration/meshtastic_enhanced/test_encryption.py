"""
Unit tests for EncryptionHandler

This module contains comprehensive tests for the encryption and decryption
functionality of the enhanced Meshtastic integration.
"""

import unittest
import base64
import secrets
from .encryption_handler import EncryptionHandler
from .exceptions import EncryptionError, MeshtasticValidationError


class TestEncryptionHandler(unittest.TestCase):
    """Test cases for EncryptionHandler class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.handler = EncryptionHandler()
        self.test_psk = EncryptionHandler.generate_psk(32)
        self.test_message = "Test aircraft alert: ICAO ABC123 at position 40.7128,-74.0060"
    
    def test_generate_psk(self):
        """Test PSK generation"""
        # Test default length
        psk = EncryptionHandler.generate_psk()
        self.assertTrue(EncryptionHandler.validate_psk(psk))
        
        # Test custom lengths
        for length in [1, 16, 32]:
            psk = EncryptionHandler.generate_psk(length)
            self.assertTrue(EncryptionHandler.validate_psk(psk))
            decoded = base64.b64decode(psk)
            self.assertEqual(len(decoded), length)
        
        # Test invalid lengths
        with self.assertRaises(MeshtasticValidationError):
            EncryptionHandler.generate_psk(0)
        
        with self.assertRaises(MeshtasticValidationError):
            EncryptionHandler.generate_psk(33)
    
    def test_validate_psk(self):
        """Test PSK validation"""
        # Valid PSKs
        valid_psks = [
            "AQ==",  # 1 byte
            "AQID",  # 3 bytes
            base64.b64encode(secrets.token_bytes(16)).decode(),  # 16 bytes
            base64.b64encode(secrets.token_bytes(32)).decode(),  # 32 bytes
        ]
        
        for psk in valid_psks:
            self.assertTrue(EncryptionHandler.validate_psk(psk))
        
        # Invalid PSKs
        invalid_psks = [
            "",  # Empty
            "invalid_base64!",  # Invalid base64
            base64.b64encode(b"").decode(),  # Empty key
            base64.b64encode(secrets.token_bytes(33)).decode(),  # Too long
            None,  # None value
        ]
        
        for psk in invalid_psks:
            self.assertFalse(EncryptionHandler.validate_psk(psk))
    
    def test_encode_decode_psk(self):
        """Test PSK encoding and decoding"""
        # Test various key lengths
        for length in [1, 8, 16, 24, 32]:
            key_bytes = secrets.token_bytes(length)
            
            # Encode to PSK
            psk = EncryptionHandler.encode_psk(key_bytes)
            self.assertTrue(EncryptionHandler.validate_psk(psk))
            
            # Decode back to bytes
            decoded_bytes = EncryptionHandler.decode_psk(psk)
            self.assertEqual(key_bytes, decoded_bytes)
        
        # Test invalid inputs
        with self.assertRaises(MeshtasticValidationError):
            EncryptionHandler.encode_psk(b"")  # Empty bytes
        
        with self.assertRaises(MeshtasticValidationError):
            EncryptionHandler.encode_psk(secrets.token_bytes(33))  # Too long
        
        with self.assertRaises(MeshtasticValidationError):
            EncryptionHandler.decode_psk("invalid_psk")  # Invalid PSK
    
    def test_encrypt_decrypt_roundtrip(self):
        """Test encryption/decryption roundtrip"""
        test_messages = [
            "Hello, World!",
            "Aircraft alert: Emergency squawk 7700",
            "Multi-line\nmessage\nwith\nspecial chars: !@#$%^&*()",
            "Unicode test: 🛩️ ✈️ 🚁",
            "A" * 200,  # Long message
            "x",  # Single character
        ]
        
        for message in test_messages:
            with self.subTest(message=message[:20] + "..."):
                # Encrypt the message
                encrypted = self.handler.encrypt_message(message, self.test_psk)
                self.assertIsInstance(encrypted, bytes)
                self.assertGreater(len(encrypted), 0)
                
                # Decrypt the message
                decrypted = self.handler.decrypt_message(encrypted, self.test_psk)
                self.assertEqual(decrypted, message)
    
    def test_encrypt_different_psks(self):
        """Test that different PSKs produce different encrypted data"""
        message = "Test message for PSK comparison"
        
        psk1 = EncryptionHandler.generate_psk()
        psk2 = EncryptionHandler.generate_psk()
        
        encrypted1 = self.handler.encrypt_message(message, psk1)
        encrypted2 = self.handler.encrypt_message(message, psk2)
        
        # Different PSKs should produce different encrypted data
        self.assertNotEqual(encrypted1, encrypted2)
        
        # Each should decrypt correctly with its own PSK
        decrypted1 = self.handler.decrypt_message(encrypted1, psk1)
        decrypted2 = self.handler.decrypt_message(encrypted2, psk2)
        
        self.assertEqual(decrypted1, message)
        self.assertEqual(decrypted2, message)
        
        # Cross-decryption should fail
        with self.assertRaises(EncryptionError):
            self.handler.decrypt_message(encrypted1, psk2)
        
        with self.assertRaises(EncryptionError):
            self.handler.decrypt_message(encrypted2, psk1)
    
    def test_encrypt_same_message_different_output(self):
        """Test that encrypting the same message twice produces different output"""
        message = "Same message encrypted twice"
        
        encrypted1 = self.handler.encrypt_message(message, self.test_psk)
        encrypted2 = self.handler.encrypt_message(message, self.test_psk)
        
        # Should be different due to random IV and salt
        self.assertNotEqual(encrypted1, encrypted2)
        
        # Both should decrypt to the same message
        decrypted1 = self.handler.decrypt_message(encrypted1, self.test_psk)
        decrypted2 = self.handler.decrypt_message(encrypted2, self.test_psk)
        
        self.assertEqual(decrypted1, message)
        self.assertEqual(decrypted2, message)
    
    def test_encrypt_invalid_inputs(self):
        """Test encryption with invalid inputs"""
        # Empty message
        with self.assertRaises(MeshtasticValidationError):
            self.handler.encrypt_message("", self.test_psk)
        
        # Empty PSK
        with self.assertRaises(MeshtasticValidationError):
            self.handler.encrypt_message("test", "")
        
        # Invalid PSK
        with self.assertRaises(EncryptionError):
            self.handler.encrypt_message("test", "invalid_psk")
    
    def test_decrypt_invalid_inputs(self):
        """Test decryption with invalid inputs"""
        # Empty encrypted data
        with self.assertRaises(MeshtasticValidationError):
            self.handler.decrypt_message(b"", self.test_psk)
        
        # Empty PSK
        with self.assertRaises(MeshtasticValidationError):
            self.handler.decrypt_message(b"some_data", "")
        
        # Too short encrypted data
        with self.assertRaises(MeshtasticValidationError):
            self.handler.decrypt_message(b"short", self.test_psk)
        
        # Invalid encrypted data
        with self.assertRaises(EncryptionError):
            invalid_data = secrets.token_bytes(64)  # Random bytes
            self.handler.decrypt_message(invalid_data, self.test_psk)
        
        # Invalid PSK
        with self.assertRaises(EncryptionError):
            encrypted = self.handler.encrypt_message("test", self.test_psk)
            self.handler.decrypt_message(encrypted, "invalid_psk")
    
    def test_get_encryption_info(self):
        """Test encryption information retrieval"""
        # Valid PSK
        info = self.handler.get_encryption_info(self.test_psk)
        self.assertTrue(info['is_valid'])
        self.assertEqual(info['algorithm'], 'AES-256-CBC')
        self.assertEqual(info['key_derivation'], 'PBKDF2-HMAC-SHA256')
        self.assertEqual(info['psk_length_bytes'], 32)
        self.assertEqual(info['psk_length_bits'], 256)
        
        # Invalid PSK
        info = self.handler.get_encryption_info("invalid_psk")
        self.assertFalse(info['is_valid'])
        self.assertIn('error', info)
    
    def test_encryption_roundtrip_test(self):
        """Test the built-in roundtrip test function"""
        # Valid roundtrip
        success, error = self.handler.test_encryption_roundtrip(
            self.test_message, self.test_psk
        )
        self.assertTrue(success)
        self.assertEqual(error, "")
        
        # Invalid PSK
        success, error = self.handler.test_encryption_roundtrip(
            self.test_message, "invalid_psk"
        )
        self.assertFalse(success)
        self.assertNotEqual(error, "")
    
    def test_encryption_constants(self):
        """Test encryption constants are correct"""
        self.assertEqual(EncryptionHandler.AES_BLOCK_SIZE, 16)
        self.assertEqual(EncryptionHandler.KEY_SIZE, 32)
        self.assertEqual(EncryptionHandler.IV_SIZE, 16)
        self.assertEqual(EncryptionHandler.SALT_SIZE, 16)
        self.assertGreater(EncryptionHandler.PBKDF2_ITERATIONS, 10000)
    
    def test_encrypted_data_structure(self):
        """Test the structure of encrypted data"""
        message = "Test message for structure validation"
        encrypted = self.handler.encrypt_message(message, self.test_psk)
        
        # Should contain salt + iv + encrypted_data
        min_expected_size = (
            EncryptionHandler.SALT_SIZE + 
            EncryptionHandler.IV_SIZE + 
            EncryptionHandler.AES_BLOCK_SIZE  # At least one block
        )
        self.assertGreaterEqual(len(encrypted), min_expected_size)
        
        # Extract components
        salt = encrypted[:EncryptionHandler.SALT_SIZE]
        iv = encrypted[EncryptionHandler.SALT_SIZE:EncryptionHandler.SALT_SIZE + EncryptionHandler.IV_SIZE]
        ciphertext = encrypted[EncryptionHandler.SALT_SIZE + EncryptionHandler.IV_SIZE:]
        
        # Verify sizes
        self.assertEqual(len(salt), EncryptionHandler.SALT_SIZE)
        self.assertEqual(len(iv), EncryptionHandler.IV_SIZE)
        self.assertGreater(len(ciphertext), 0)
        
        # Ciphertext should be multiple of block size (due to padding)
        self.assertEqual(len(ciphertext) % EncryptionHandler.AES_BLOCK_SIZE, 0)


if __name__ == '__main__':
    unittest.main()