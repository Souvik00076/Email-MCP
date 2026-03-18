from abc import ABC, abstractmethod
from typing import Optional, List
from pydantic import BaseModel, EmailStr


class EmailMessage(BaseModel):
    """Email message data model"""
    to: EmailStr
    subject: str
    body: str
    cc: Optional[List[EmailStr]] = None
    bcc: Optional[List[EmailStr]] = None


class EmailSenderStrategy(ABC):
    """
    Abstract base class for email sending strategies.
    Implement this class to create different email sending providers
    (e.g., SMTP, SendGrid, AWS SES, etc.)
    """
    
    @abstractmethod
    async def send_email(self, email: EmailMessage) -> dict:
        """
        Send an email using the specific strategy implementation.
        
        Args:
            email: EmailMessage object containing all email details
            
        Returns:
            dict: Response containing success status, message, and email_id
            
        Raises:
            Exception: If email sending fails
        """
        pass
    
    @abstractmethod
    def validate_configuration(self) -> bool:
        """
        Validate that the email sender is properly configured.
        
        Returns:
            bool: True if configuration is valid, False otherwise
        """
        pass
    
    @abstractmethod
    def get_provider_name(self) -> str:
        """
        Get the name of the email provider.
        
        Returns:
            str: Provider name (e.g., "SMTP", "SendGrid", "AWS SES")
        """
        pass
