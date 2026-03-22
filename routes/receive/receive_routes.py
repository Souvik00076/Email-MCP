from fastapi import APIRouter, HTTPException, status, Query
from httpx import Auth
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import logging
from core import EmailReceiverStrategy, IMAPEmailReceiver, EmailSummary, EmailDetail, FolderInfo
from dependencies import AuthDep

logger = logging.getLogger(__name__)

# Create router with prefix and tags
router = APIRouter(prefix="/receive", tags=["Email Receiving"])

# Initialize email receiver singleton


# Pydantic Models for Receive Operations
class EmailListResponse(BaseModel):
    success: bool
    emails: List[EmailSummary]
    total: int
    limit: int
    offset: int


class FolderListResponse(BaseModel):
    success: bool
    folders: List[FolderInfo]
    total: int


class EmailDetailResponse(BaseModel):
    success: bool
    email: EmailDetail


# Helper function for error handling


def handle_error(error_message: str, context: str):
    """Common error handling logic for receive routes"""
    logger.error(f"{context}: {error_message}")
    if "configuration" in error_message.lower():
        return status.HTTP_503_SERVICE_UNAVAILABLE, "Configuration Error"
    elif "authentication" in error_message.lower():
        return status.HTTP_401_UNAUTHORIZED, "Authentication Error"
    elif "connection" in error_message.lower() or "connect" in error_message.lower():
        return status.HTTP_503_SERVICE_UNAVAILABLE, "Connection Error"
    elif "spam folder not found" in error_message.lower():
        return status.HTTP_404_NOT_FOUND, "Folder Not Found"
    elif "failed to select folder" in error_message.lower():
        return status.HTTP_404_NOT_FOUND, "Folder Not Found"
    else:
        return status.HTTP_500_INTERNAL_SERVER_ERROR, "Email Fetch Error"


# Routes
@router.get("/recent", response_model=EmailListResponse)
async def get_recent_emails(
    user_info: AuthDep,
    limit: int = Query(default=20, ge=1, le=100,
                       description="Maximum number of emails to return"),
    offset: int = Query(
        default=0, ge=0, description="Number of emails to skip"),
    from_date: Optional[datetime] = Query(
        default=None, description="Filter emails from this date (ISO format)"),
    to_date: Optional[datetime] = Query(
        default=None, description="Filter emails until this date (ISO format)"),
    folder: str = Query(
        default="INBOX", description="Folder to fetch emails from")
):
    """
    Get recent emails with pagination and optional date filtering.
    Returns emails sorted by date (most recent first).
    """
    try:
        logger.info(f"Fetching recent emails from {
                    folder}, limit={limit}, offset={offset}")
        logger.info(f"[DEBUG] token (first 20 chars): {
                    str(user_info.token)[:20]}...")

        email_receiver: EmailReceiverStrategy = IMAPEmailReceiver(
            str(user_info.token), user_info.email)
        emails = await email_receiver.fetch_recent_emails(
            folder=folder,
            limit=limit,
            offset=offset,
            from_date=from_date,
            to_date=to_date
        )

        logger.info(f"Successfully fetched {len(emails)} emails")

        return EmailListResponse(
            success=True,
            emails=emails,
            total=len(emails),
            limit=limit,
            offset=offset
        )
    except Exception as e:
        error_message = str(e)
        status_code, error_type = handle_error(
            error_message, "Failed to fetch recent emails")
        raise HTTPException(
            status_code=status_code,
            detail={"success": False, "error": error_type,
                    "detail": error_message}
        )


@router.get("/unread", response_model=EmailListResponse)
async def get_unread_emails(
    user_info: AuthDep,
    limit: int = Query(default=20, ge=1, le=100,
                       description="Maximum number of emails to return"),
    offset: int = Query(
        default=0, ge=0, description="Number of emails to skip"),
    from_date: Optional[datetime] = Query(
        default=None, description="Filter emails from this date (ISO format)"),
    to_date: Optional[datetime] = Query(
        default=None, description="Filter emails until this date (ISO format)"),
    folder: str = Query(
        default="INBOX", description="Folder to fetch emails from")
):
    """
    Get unread emails with pagination and optional date filtering.
    Returns only emails that have not been read (UNSEEN flag).
    """
    try:
        logger.info(f"Fetching unread emails from {
                    folder}, limit={limit}, offset={offset}")
        email_receiver: EmailReceiverStrategy = IMAPEmailReceiver(
            user_info.token, user_info.email)
        emails = await email_receiver.fetch_unread_emails(
            folder=folder,
            limit=limit,
            offset=offset,
            from_date=from_date,
            to_date=to_date
        )

        logger.info(f"Successfully fetched {len(emails)} unread emails")

        return EmailListResponse(
            success=True,
            emails=emails,
            total=len(emails),
            limit=limit,
            offset=offset
        )
    except Exception as e:
        error_message = str(e)
        status_code, error_type = handle_error(
            error_message, "Failed to fetch unread emails")
        raise HTTPException(
            status_code=status_code,
            detail={"success": False, "error": error_type,
                    "detail": error_message}
        )


@router.get("/search", response_model=EmailListResponse)
async def search_emails_by_sender(
    user_info: AuthDep,
    sender: str = Query(..., min_length=1,
                        description="Search query for sender (email or name) - case-insensitive partial match"),
    limit: int = Query(default=20, ge=1, le=100,
                       description="Maximum number of emails to return"),
    offset: int = Query(
        default=0, ge=0, description="Number of emails to skip"),
    from_date: Optional[datetime] = Query(
        default=None, description="Filter emails from this date (ISO format)"),
    to_date: Optional[datetime] = Query(
        default=None, description="Filter emails until this date (ISO format)"),
    folder: str = Query(default="INBOX", description="Folder to search in")
):
    """
    Search emails by sender with fuzzy matching.
    Performs case-insensitive partial match on sender email address and name.
    For example, searching 'john' will match 'john@example.com' and 'John Doe <johnd@test.com>'.
    """
    try:
        logger.info(f"Searching emails from sender '{sender}' in {
                    folder}, limit={limit}, offset={offset}")
        email_receiver: EmailReceiverStrategy = IMAPEmailReceiver(
            user_info.token, user_info.email)
        emails = await email_receiver.search_emails_by_sender(
            sender_query=sender,
            folder=folder,
            limit=limit,
            offset=offset,
            from_date=from_date,
            to_date=to_date
        )

        logger.info(f"Found {len(emails)} emails matching sender '{sender}'")

        return EmailListResponse(
            success=True,
            emails=emails,
            total=len(emails),
            limit=limit,
            offset=offset
        )
    except Exception as e:
        error_message = str(e)
        status_code, error_type = handle_error(
            error_message, "Failed to search emails")
        raise HTTPException(
            status_code=status_code,
            detail={"success": False, "error": error_type,
                    "detail": error_message}
        )


@router.get("/spam", response_model=EmailListResponse)
async def get_spam_emails(
    user_info: AuthDep,
    limit: int = Query(default=20, ge=1, le=100,
                       description="Maximum number of emails to return"),
    offset: int = Query(
        default=0, ge=0, description="Number of emails to skip"),
    from_date: Optional[datetime] = Query(
        default=None, description="Filter emails from this date (ISO format)"),
    to_date: Optional[datetime] = Query(
        default=None, description="Filter emails until this date (ISO format)")
):
    """
    Get emails from spam/junk folder with pagination.
    Automatically detects the spam folder name (e.g., '[Gmail]/Spam', 'Junk', etc.).
    """
    try:
        logger.info(f"Fetching spam emails, limit={limit}, offset={offset}")
        email_receiver: EmailReceiverStrategy = IMAPEmailReceiver(
            user_info.token, user_info.email)
        emails = await email_receiver.fetch_spam_emails(
            limit=limit,
            offset=offset,
            from_date=from_date,
            to_date=to_date
        )

        logger.info(f"Successfully fetched {len(emails)} spam emails")

        return EmailListResponse(
            success=True,
            emails=emails,
            total=len(emails),
            limit=limit,
            offset=offset
        )
    except Exception as e:
        error_message = str(e)
        status_code, error_type = handle_error(
            error_message, "Failed to fetch spam emails")
        raise HTTPException(
            status_code=status_code,
            detail={"success": False, "error": error_type,
                    "detail": error_message}
        )


@router.get("/folders", response_model=FolderListResponse)
async def list_email_folders(
    user_info: AuthDep
):
    """
    List all available email folders/mailboxes.
    Returns folder names, full paths, message counts, and unread counts.
    """
    try:
        logger.info("Fetching email folders")
        email_receiver: EmailReceiverStrategy = IMAPEmailReceiver(
            user_info.token, user_info.email)
        folders = await email_receiver.list_folders()

        logger.info(f"Successfully fetched {len(folders)} folders")

        return FolderListResponse(
            success=True,
            folders=folders,
            total=len(folders)
        )
    except Exception as e:
        error_message = str(e)
        status_code, error_type = handle_error(
            error_message, "Failed to fetch folders")
        raise HTTPException(
            status_code=status_code,
            detail={"success": False, "error": error_type,
                    "detail": error_message}
        )


@router.get("/folder/{folder_path:path}", response_model=EmailListResponse)
async def get_folder_emails(
    user_info: AuthDep,
    folder_path: str,
    limit: int = Query(default=20, ge=1, le=100,
                       description="Maximum number of emails to return"),
    offset: int = Query(
        default=0, ge=0, description="Number of emails to skip"),
    from_date: Optional[datetime] = Query(
        default=None, description="Filter emails from this date (ISO format)"),
    to_date: Optional[datetime] = Query(
        default=None, description="Filter emails until this date (ISO format)")
):
    """
    Get emails from a specific folder with pagination.
    Use the full_path from /receive/folders endpoint (e.g., '[Gmail]/Sent Mail', 'INBOX', 'Drafts').
    """
    try:
        logger.info(f"Fetching emails from folder '{
                    folder_path}', limit={limit}, offset={offset}")
        email_receiver: EmailReceiverStrategy = IMAPEmailReceiver(
            user_info.token, user_info.email)
        emails = await email_receiver.get_folder_emails(
            folder=folder_path,
            limit=limit,
            offset=offset,
            from_date=from_date,
            to_date=to_date
        )

        logger.info(f"Successfully fetched {
                    len(emails)} emails from folder '{folder_path}'")

        return EmailListResponse(
            success=True,
            emails=emails,
            total=len(emails),
            limit=limit,
            offset=offset
        )
    except Exception as e:
        error_message = str(e)
        status_code, error_type = handle_error(
            error_message, f"Failed to fetch emails from folder '{folder_path}'")
        raise HTTPException(
            status_code=status_code,
            detail={"success": False, "error": error_type,
                    "detail": error_message}
        )


@router.get("/email/{email_id}", response_model=EmailDetailResponse)
async def get_email_by_id(
    user_info: AuthDep,
    email_id: str,
    folder: str = Query(
        default="INBOX", description="Folder where the email is located")
):
    """
    Get full details of a single email by its ID.
    Returns complete email including body (plain text and HTML), attachments info, etc.
    """
    try:
        logger.info(f"Fetching email {email_id} from folder '{folder}'")
        email_receiver: EmailReceiverStrategy = IMAPEmailReceiver(
            user_info.token, user_info.email)
        email_detail = await email_receiver.get_email_by_id(
            email_id=email_id,
            folder=folder
        )

        if not email_detail:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "success": False,
                    "error": "Email Not Found",
                    "detail": f"Email with ID '{email_id}' not found in folder '{folder}'"
                }
            )

        logger.info(f"Successfully fetched email {email_id}")

        return EmailDetailResponse(
            success=True,
            email=email_detail
        )
    except HTTPException:
        raise
    except Exception as e:
        error_message = str(e)
        status_code, error_type = handle_error(
            error_message, f"Failed to fetch email {email_id}")
        raise HTTPException(
            status_code=status_code,
            detail={"success": False, "error": error_type,
                    "detail": error_message}
        )


@router.post("/email/{email_id}/mark-read")
async def mark_email_as_read(
    user_info: AuthDep,
    email_id: str,
    folder: str = Query(
        default="INBOX", description="Folder where the email is located")
):
    """
    Mark an email as read by setting the SEEN flag.
    """
    try:
        logger.info(f"Marking email {email_id} as read in folder '{folder}'")
        email_receiver: EmailReceiverStrategy = IMAPEmailReceiver(
            user_info.token, user_info.email)
        success = await email_receiver.mark_as_read(
            email_id=email_id,
            folder=folder
        )

        if success:
            logger.info(f"Successfully marked email {email_id} as read")
            return {
                "success": True,
                "message": f"Email {email_id} marked as read"
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "success": False,
                    "error": "Mark Read Failed",
                    "detail": f"Failed to mark email {email_id} as read"
                }
            )
    except HTTPException:
        raise
    except Exception as e:
        error_message = str(e)
        status_code, error_type = handle_error(
            error_message, f"Failed to mark email {email_id} as read")
        raise HTTPException(
            status_code=status_code,
            detail={"success": False, "error": error_type,
                    "detail": error_message}
        )


@router.post("/email/{email_id}/mark-unread")
async def mark_email_as_unread(
    user_info: AuthDep,
    email_id: str,
    folder: str = Query(
        default="INBOX", description="Folder where the email is located")
):
    """
    Mark an email as unread by removing the SEEN flag.
    """
    try:
        logger.info(f"Marking email {email_id} as unread in folder '{folder}'")
        email_receiver: EmailReceiverStrategy = IMAPEmailReceiver(
            user_info.token, user_info.email)
        success = await email_receiver.mark_as_unread(
            email_id=email_id,
            folder=folder
        )

        if success:
            logger.info(f"Successfully marked email {email_id} as unread")
            return {
                "success": True,
                "message": f"Email {email_id} marked as unread"
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "success": False,
                    "error": "Mark Unread Failed",
                    "detail": f"Failed to mark email {email_id} as unread"
                }
            )
    except HTTPException:
        raise
    except Exception as e:
        error_message = str(e)
        status_code, error_type = handle_error(
            error_message, f"Failed to mark email {email_id} as unread")
        raise HTTPException(
            status_code=status_code,
            detail={"success": False, "error": error_type,
                    "detail": error_message}
        )


@router.get("/status")
async def get_receive_status(
    user_info: AuthDep
):
    """
    Get the current status of the email receiver (IMAP) configuration.
    """
    try:
        email_receiver: EmailReceiverStrategy = IMAPEmailReceiver(
            user_info.token, user_info.email)
        config_status = email_receiver.get_configuration_status()
        return {
            "success": True,
            "status": config_status
        }
    except Exception as e:
        logger.error(f"Failed to get IMAP status: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }
