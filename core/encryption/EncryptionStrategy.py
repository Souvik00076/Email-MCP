from abc import ABC, abstractmethod
from typing import Any
class EncryptionStrategy(ABC):
    @abstractmethod
    def encrypt(self, data: dict[str, Any]) -> str:
        pass

    @abstractmethod
    def decrypt(self, encrypted_data: str) -> dict[str, Any]:
        pass

