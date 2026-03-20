from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, EmailStr, ValidationError
from typing import Optional, List
import logging
from core import EmailSenderStrategy, SMTPEmailSender, EmailMessage
from dependencies import AuthDep

logger = logging.getLogger(__name__)

# Create router with prefix and tags
router = APIRouter(prefix="/send", tags=["Email Sending"])

# Initialize email sender singleton


# Pydantic Models for Send Operations
class EmailRequest(BaseModel):
    to: EmailStr = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Email subject")
    body: str = Field(..., description="Email body content")
    cc: Optional[List[EmailStr]] = Field(None, description="CC recipients")
    bcc: Optional[List[EmailStr]] = Field(None, description="BCC recipients")


class EmailResponse(BaseModel):
    success: bool
    message: str
    email_id: Optional[str] = None


email_user = "souvikfs06@gmail.com"

# Routes


@router.post("/email", response_model=EmailResponse)
async def send_email(email: EmailRequest, token=AuthDep):
    """
    Send an email via MCP server using SMTP.
    Supports CC and BCC recipients.
    """
    try:
        logger.info(f"Attempting to send email to: {email.to}")
        # Convert EmailRequest to EmailMessage
        email_message = EmailMessage(
            to=email.to,
            subject=email.subject,
            body=email.body,
            cc=email.cc,
            bcc=email.bcc
        )
        email_sender: EmailSenderStrategy = SMTPEmailSender(token, email_user)
        # Send email using singleton SMTP sender
        result = await email_sender.send_email(email_message)
        logger.info(f"Email sent successfully to: {email.to}")
        return EmailResponse(**result)
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Email validation failed: {str(e)}"
        )
    except Exception as e:
        error_message = str(e)
        logger.error(f"Failed to send email: {error_message}")
        # Determine appropriate status code based on error type
        if "authentication" in error_message.lower():
            status_code = status.HTTP_401_UNAUTHORIZED
            error_type = "Authentication Error"
        elif "configuration" in error_message.lower():
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            error_type = "Configuration Error"
        elif "connection" in error_message.lower() or "connect" in error_message.lower():
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            error_type = "Connection Error"
        else:
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            error_type = "Email Sending Error"
        raise HTTPException(
            status_code=status_code,
            detail={
                "success": False,
                "error": error_type,
                "detail": error_message
            }
        )


@router.get("/status")
async def get_send_status(token: AuthDep):

    try:
        email_sender: EmailSenderStrategy = SMTPEmailSender(token, email_user)
        config_status = email_sender.get_configuration_status()
        return {
            "success": True,
            "status": config_status
        }
    except Exception as e:
        logger.error(f"Failed to get email status: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }
