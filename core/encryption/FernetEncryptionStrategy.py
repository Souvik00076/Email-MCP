
from core.encryption import EncryptionStrategy
from cryptography.fernet import Fernet
from typing import Any
import json
import os

class FernetEncryption(EncryptionStrategy):
    def __init__(self, key: bytes | str | None = None):
        if key is None:
            key = os.getenv("FERNET_KEY")
            if key is None:
                raise ValueError("FERNET_KEY not found in environment")
        
        if isinstance(key, str):
            self._key = key.encode()
        else:
            self._key = key
        
        self._fernet = Fernet(self._key)

    @property
    def key(self) -> bytes:
        return self._key

    @classmethod
    def generate_key(cls) -> str:
        return Fernet.generate_key().decode()

    def encrypt(self, data: dict[str, Any]) -> str:
        json_bytes = json.dumps(data, separators=(',', ':')).encode('utf-8')
        encrypted_bytes = self._fernet.encrypt(json_bytes)
        return encrypted_bytes.decode('utf-8')

    def decrypt(self,encrypted_data:str)->dict[str,Any]:
        encrypted_bytes = encrypted_data.encode('utf-8')
        decrypted_bytes = self._fernet.decrypt(encrypted_bytes)
        return json.loads(decrypted_bytes.decode('utf-8'))

