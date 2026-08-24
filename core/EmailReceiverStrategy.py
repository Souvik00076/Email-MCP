from abc import ABC, abstractmethod
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, EmailStr


class EmailSummary(BaseModel):
    """Summary model for email list responses"""
    email_id: str
    subject: str
    from_address: str
    from_name: Optional[str] = None
    to_address: str
    date: datetime
    preview: str  # First 200 chars of plain text body
    is_read: bool
    has_attachments: bool
    folder: str
    # RFC 5322 identity of this message, e.g. "<abc@mail.gmail.com>". Carried on
    # summaries so a reply can be composed straight off a list result without a
    # second fetch.
    message_id: Optional[str] = None


class EmailDetail(BaseModel):
    """Full email details model"""
    email_id: str
    subject: str
    from_address: str
    from_name: Optional[str] = None
    to_address: str
    cc: Optional[List[str]] = None
    date: datetime
    body_plain: Optional[str] = None
    body_html: Optional[str] = None
    is_read: bool
    has_attachments: bool
    attachment_names: Optional[List[str]] = None
    folder: str
    # Threading headers (RFC 5322 §3.6.4). message_id identifies this message;
    # in_reply_to/references point back at its ancestors. To reply to this
    # message, send with in_reply_to=message_id and
    # references=(references or in_reply_to) + " " + message_id.
    message_id: Optional[str] = None
    in_reply_to: Optional[str] = None
    references: Optional[str] = None
    # When present, overrides From as the intended destination for replies.
    reply_to: Optional[str] = None


class FolderInfo(BaseModel):
    """Folder/mailbox information"""
    name: str
    full_path: str
    message_count: Optional[int] = None
    unread_count: Optional[int] = None


class EmailReceiverStrategy(ABC):
    """
    Abstract base class for email receiving strategies.
    Implement this class to create different email receiving providers
    (e.g., IMAP, Gmail API, Microsoft Graph, etc.)
    """

    @abstractmethod
    async def fetch_recent_emails(
        self,
        folder: str = "INBOX",
        limit: int = 20,
        offset: int = 0,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None
    ) -> List[EmailSummary]:
        """
        Fetch recent emails from a folder with pagination.

        Args:
            folder: Folder name to fetch from (default: INBOX)
            limit: Maximum number of emails to return
            offset: Number of emails to skip
            from_date: Optional start date filter
            to_date: Optional end date filter

        Returns:
            List[EmailSummary]: List of email summaries
        """
        pass

    @abstractmethod
    async def fetch_unread_emails(
        self,
        folder: str = "INBOX",
        limit: int = 20,
        offset: int = 0,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None
    ) -> List[EmailSummary]:
        """
        Fetch unread emails from a folder with pagination.

        Args:
            folder: Folder name to fetch from (default: INBOX)
            limit: Maximum number of emails to return
            offset: Number of emails to skip
            from_date: Optional start date filter
            to_date: Optional end date filter

        Returns:
            List[EmailSummary]: List of unread email summaries
        """
        pass

    @abstractmethod
    async def search_emails_by_sender(
        self,
        sender_query: str,
        folder: str = "INBOX",
        limit: int = 20,
        offset: int = 0,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None
    ) -> List[EmailSummary]:
        """
        Search emails by sender with fuzzy matching.

        Args:
            sender_query: Search query for sender (email or name)
            folder: Folder name to search in (default: INBOX)
            limit: Maximum number of emails to return
            offset: Number of emails to skip
            from_date: Optional start date filter
            to_date: Optional end date filter

        Returns:
            List[EmailSummary]: List of matching email summaries
        """
        pass

    @abstractmethod
    async def fetch_spam_emails(
        self,
        limit: int = 20,
        offset: int = 0,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None
    ) -> List[EmailSummary]:
        """
        Fetch emails from spam/junk folder with pagination.

        Args:
            limit: Maximum number of emails to return
            offset: Number of emails to skip
            from_date: Optional start date filter
            to_date: Optional end date filter

        Returns:
            List[EmailSummary]: List of spam email summaries
        """
        pass

    @abstractmethod
    async def get_email_by_id(
        self,
        email_id: str,
        folder: str = "INBOX"
    ) -> Optional[EmailDetail]:
        """
        Get full email details by ID.

        Args:
            email_id: Unique email identifier
            folder: Folder where the email is located

        Returns:
            EmailDetail: Full email details or None if not found
        """
        pass

    @abstractmethod
    async def mark_as_read(
        self,
        email_id: str,
        folder: str = "INBOX"
    ) -> bool:
        """
        Mark an email as read.

        Args:
            email_id: Unique email identifier
            folder: Folder where the email is located

        Returns:
            bool: True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def mark_as_unread(
        self,
        email_id: str,
        folder: str = "INBOX"
    ) -> bool:
        """
        Mark an email as unread.

        Args:
            email_id: Unique email identifier
            folder: Folder where the email is located

        Returns:
            bool: True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def list_folders(self) -> List[FolderInfo]:
        """
        List all available folders/mailboxes.

        Returns:
            List[FolderInfo]: List of folder information
        """
        pass

    @abstractmethod
    async def get_folder_emails(
        self,
        folder: str,
        limit: int = 20,
        offset: int = 0,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None
    ) -> List[EmailSummary]:
        """
        Get emails from a specific folder with pagination.

        Args:
            folder: Folder name/path
            limit: Maximum number of emails to return
            offset: Number of emails to skip
            from_date: Optional start date filter
            to_date: Optional end date filter

        Returns:
            List[EmailSummary]: List of email summaries
        """
        pass

    @abstractmethod
    def validate_configuration(self) -> bool:
        """
        Validate that the email receiver is properly configured.

        Returns:
            bool: True if configuration is valid, False otherwise
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """
        Get the name of the email provider.

        Returns:
            str: Provider name (e.g., "IMAP", "Gmail API", "Microsoft Graph")
        """
        pass
