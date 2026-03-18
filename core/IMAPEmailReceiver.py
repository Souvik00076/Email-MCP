import os
import re
import html
import imaplib
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime, parseaddr
from typing import Optional, List, Tuple
from datetime import datetime
from dotenv import load_dotenv
from .EmailReceiverStrategy import (
    EmailReceiverStrategy,
    EmailSummary,
    EmailDetail,
    FolderInfo
)

# Load environment variables
load_dotenv()


class IMAPEmailReceiver(EmailReceiverStrategy):
    """
    IMAP Email Receiver Strategy.
    Uses IMAP protocol to read emails from configured mail server.
    Maintains a persistent connection to avoid re-authentication on every request.
    Implements Singleton pattern to persist across API requests.
    """
    _instance: Optional['IMAPEmailReceiver'] = None
    _initialized = False

    def __new__(cls):
        """Singleton pattern - only one instance exists"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize IMAP receiver with environment variables (only once)"""
        if self._initialized:
            return
        
        self.imap_host: Optional[str] = os.getenv("IMAP_HOST")
        imap_port_str = os.getenv("IMAP_PORT", "993")
        self.imap_port: int = int(imap_port_str) if imap_port_str else 993
        self.email_user: Optional[str] = os.getenv("EMAIL_USER")
        self.email_password: Optional[str] = os.getenv("EMAIL_PASSWORD")
        use_ssl_str = os.getenv("IMAP_USE_SSL", "True")
        self.use_ssl: bool = use_ssl_str.lower() == "true" if use_ssl_str else True
        
        self._imap_connection: Optional[imaplib.IMAP4_SSL | imaplib.IMAP4] = None
        self._is_connected: bool = False
        self._current_folder: Optional[str] = None
        self._initialized = True
        
        # Common spam folder names to try
        self._spam_folder_names = [
            "[Gmail]/Spam",
            "Spam",
            "Junk",
            "Junk E-mail",
            "Bulk Mail",
            "[Gmail]/Junk"
        ]

    def _connect(self):
        """
        Establish and authenticate IMAP connection.
        Reuses existing connection if already established.
        """
        if self._is_connected and self._imap_connection:
            try:
                # Test if connection is still alive
                self._imap_connection.noop()
                return
            except:
                # Connection is dead, reconnect
                self._is_connected = False
                self._imap_connection = None
                self._current_folder = None

        # Validate required fields
        if not self.imap_host or not self.email_user or not self.email_password:
            raise Exception("IMAP configuration incomplete. Check your .env file.")

        try:
            # Create new connection
            if self.use_ssl:
                self._imap_connection = imaplib.IMAP4_SSL(
                    self.imap_host, 
                    self.imap_port,
                    timeout=30
                )
            else:
                self._imap_connection = imaplib.IMAP4(
                    self.imap_host, 
                    self.imap_port,
                    timeout=30
                )
            
            # Login
            self._imap_connection.login(self.email_user, self.email_password)
            self._is_connected = True
            
        except imaplib.IMAP4.error as e:
            raise Exception(f"IMAP authentication failed: {str(e)}")
        except Exception as e:
            raise Exception(f"Failed to connect to IMAP server: {str(e)}")

    def _select_folder(self, folder: str, readonly: bool = True):
        """Select a folder/mailbox for operations"""
        if self._current_folder != folder:
            self._connect()
            if not self._imap_connection:
                raise Exception("IMAP connection not established")
            
            status, data = self._imap_connection.select(folder, readonly=readonly)
            if status != "OK":
                raise Exception(f"Failed to select folder '{folder}': {data}")
            self._current_folder = folder

    def disconnect(self):
        """Close the IMAP connection"""
        if self._imap_connection:
            try:
                self._imap_connection.close()
                self._imap_connection.logout()
            except:
                pass
            finally:
                self._imap_connection = None
                self._is_connected = False
                self._current_folder = None

    def _decode_header_value(self, value: str) -> str:
        """Decode email header value (handles encoded headers)"""
        if not value:
            return ""
        
        decoded_parts = []
        for part, encoding in decode_header(value):
            if isinstance(part, bytes):
                try:
                    decoded_parts.append(part.decode(encoding or 'utf-8', errors='replace'))
                except:
                    decoded_parts.append(part.decode('utf-8', errors='replace'))
            else:
                decoded_parts.append(part)
        
        return ''.join(decoded_parts)

    def _parse_email_address(self, raw_from: str) -> Tuple[str, str]:
        """Parse email address and extract name and email"""
        decoded = self._decode_header_value(raw_from)
        name, address = parseaddr(decoded)
        return name, address

    def _get_plain_text_body(self, msg: email.message.Message) -> str:
        """Extract plain text body from email message"""
        body = ""
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))
                
                # Skip attachments
                if "attachment" in content_disposition:
                    continue
                
                if content_type == "text/plain":
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or 'utf-8'
                            body = payload.decode(charset, errors='replace')
                            break
                    except:
                        continue
        else:
            content_type = msg.get_content_type()
            if content_type == "text/plain":
                try:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        charset = msg.get_content_charset() or 'utf-8'
                        body = payload.decode(charset, errors='replace')
                except:
                    pass
        
        return body.strip()

    def _get_html_body(self, msg: email.message.Message) -> str:
        """Extract HTML body from email message"""
        body = ""
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))
                
                if "attachment" in content_disposition:
                    continue
                
                if content_type == "text/html":
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or 'utf-8'
                            body = payload.decode(charset, errors='replace')
                            break
                    except:
                        continue
        else:
            content_type = msg.get_content_type()
            if content_type == "text/html":
                try:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        charset = msg.get_content_charset() or 'utf-8'
                        body = payload.decode(charset, errors='replace')
                except:
                    pass
        
        return body.strip()

    def _has_attachments(self, msg: email.message.Message) -> bool:
        """Check if email has attachments"""
        if msg.is_multipart():
            for part in msg.walk():
                content_disposition = str(part.get("Content-Disposition", ""))
                if "attachment" in content_disposition:
                    return True
        return False

    def _get_attachment_names(self, msg: email.message.Message) -> List[str]:
        """Get list of attachment filenames"""
        attachments = []
        
        if msg.is_multipart():
            for part in msg.walk():
                content_disposition = str(part.get("Content-Disposition", ""))
                if "attachment" in content_disposition:
                    filename = part.get_filename()
                    if filename:
                        attachments.append(self._decode_header_value(filename))
        
        return attachments

    def _parse_date(self, date_str: str) -> datetime:
        """Parse email date string to datetime"""
        try:
            return parsedate_to_datetime(date_str)
        except:
            return datetime.now()

    def _build_search_criteria(
        self,
        unread_only: bool = False,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        sender: Optional[str] = None
    ) -> str:
        """Build IMAP search criteria string"""
        criteria = []
        
        if unread_only:
            criteria.append("UNSEEN")
        
        if from_date:
            date_str = from_date.strftime("%d-%b-%Y")
            criteria.append(f'SINCE {date_str}')
        
        if to_date:
            date_str = to_date.strftime("%d-%b-%Y")
            criteria.append(f'BEFORE {date_str}')
        
        # Note: IMAP FROM search is exact, fuzzy search done in Python
        if sender:
            criteria.append(f'FROM "{sender}"')
        
        if not criteria:
            criteria.append("ALL")
        
        return ' '.join(criteria)

    def _fetch_email_summaries(
        self,
        folder: str,
        search_criteria: str,
        limit: int,
        offset: int,
        sender_filter: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None
    ) -> List[EmailSummary]:
        """Core method to fetch email summaries with pagination"""
        self._select_folder(folder)
        
        if not self._imap_connection:
            raise Exception("IMAP connection not established")
        
        # Search for emails
        status, data = self._imap_connection.search(None, search_criteria)
        if status != "OK":
            raise Exception(f"IMAP search failed: {data}")
        
        email_ids = data[0].split()
        
        # Reverse to get most recent first
        email_ids = list(reversed(email_ids))
        
        # For sender fuzzy search, we need to fetch more emails and filter
        if sender_filter:
            # Fetch more to account for filtering
            fetch_limit = min(len(email_ids), (offset + limit) * 3)
            email_ids_to_fetch = email_ids[:fetch_limit]
        else:
            # Apply pagination directly
            email_ids_to_fetch = email_ids[offset:offset + limit]
        
        summaries = []
        
        for email_id in email_ids_to_fetch:
            try:
                # Fetch complete email with flags
                status, msg_data = self._imap_connection.fetch(
                    email_id, 
                    "(FLAGS RFC822)"
                )
                
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue
                
                # Parse flags and email from response
                # Response format: [(b'id (FLAGS (...) RFC822 {size}', b'raw_email'), b')']
                is_read = False
                raw_email = None
                
                for part in msg_data:
                    if isinstance(part, tuple):
                        # First element contains flags info
                        if isinstance(part[0], bytes):
                            is_read = b"\\Seen" in part[0]
                        # Second element is the raw email
                        if len(part) > 1 and isinstance(part[1], bytes):
                            raw_email = part[1]
                            break
                
                if not raw_email:
                    continue
                
                msg = email.message_from_bytes(raw_email)
                
                # Extract headers
                subject = self._decode_header_value(msg.get("Subject", "(No Subject)"))
                from_name, from_address = self._parse_email_address(msg.get("From", ""))
                to_address = msg.get("To", "")
                date = self._parse_date(msg.get("Date", ""))
                
                # Apply date filters (IMAP date search is day-level, we need finer control)
                if from_date and date < from_date:
                    continue
                if to_date and date > to_date:
                    continue
                
                # Apply sender fuzzy filter
                if sender_filter:
                    query_lower = sender_filter.lower()
                    if not (query_lower in from_address.lower() or 
                            query_lower in from_name.lower()):
                        continue
                
                # Get plain text preview (fallback to HTML if no plain text)
                body = self._get_plain_text_body(msg)
                if not body:
                    # Try to extract text from HTML
                    html_body = self._get_html_body(msg)
                    if html_body:
                        # Strip HTML tags for preview
                        body = re.sub(r'<style[^>]*>.*?</style>', '', html_body, flags=re.DOTALL | re.IGNORECASE)
                        body = re.sub(r'<script[^>]*>.*?</script>', '', body, flags=re.DOTALL | re.IGNORECASE)
                        body = re.sub(r'<[^>]+>', ' ', body)
                        body = re.sub(r'\s+', ' ', body).strip()
                        # Decode HTML entities
                        body = html.unescape(body)
                preview = body[:200] + "..." if len(body) > 200 else body
                
                summary = EmailSummary(
                    email_id=email_id.decode() if isinstance(email_id, bytes) else str(email_id),
                    subject=subject,
                    from_address=from_address,
                    from_name=from_name if from_name else None,
                    to_address=to_address,
                    date=date,
                    preview=preview,
                    is_read=is_read,
                    has_attachments=self._has_attachments(msg),
                    folder=folder
                )
                summaries.append(summary)
                
            except Exception as e:
                # Skip problematic emails
                continue
        
        # Apply pagination after fuzzy filtering
        if sender_filter:
            summaries = summaries[offset:offset + limit]
        
        return summaries

    async def fetch_recent_emails(
        self,
        folder: str = "INBOX",
        limit: int = 20,
        offset: int = 0,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None
    ) -> List[EmailSummary]:
        """Fetch recent emails from a folder with pagination"""
        search_criteria = self._build_search_criteria(
            from_date=from_date,
            to_date=to_date
        )
        return self._fetch_email_summaries(
            folder=folder,
            search_criteria=search_criteria,
            limit=limit,
            offset=offset,
            from_date=from_date,
            to_date=to_date
        )

    async def fetch_unread_emails(
        self,
        folder: str = "INBOX",
        limit: int = 20,
        offset: int = 0,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None
    ) -> List[EmailSummary]:
        """Fetch unread emails from a folder with pagination"""
        search_criteria = self._build_search_criteria(
            unread_only=True,
            from_date=from_date,
            to_date=to_date
        )
        return self._fetch_email_summaries(
            folder=folder,
            search_criteria=search_criteria,
            limit=limit,
            offset=offset,
            from_date=from_date,
            to_date=to_date
        )

    async def search_emails_by_sender(
        self,
        sender_query: str,
        folder: str = "INBOX",
        limit: int = 20,
        offset: int = 0,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None
    ) -> List[EmailSummary]:
        """Search emails by sender with fuzzy matching"""
        # Use ALL criteria and filter in Python for fuzzy matching
        search_criteria = self._build_search_criteria(
            from_date=from_date,
            to_date=to_date
        )
        return self._fetch_email_summaries(
            folder=folder,
            search_criteria=search_criteria,
            limit=limit,
            offset=offset,
            sender_filter=sender_query,
            from_date=from_date,
            to_date=to_date
        )

    async def fetch_spam_emails(
        self,
        limit: int = 20,
        offset: int = 0,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None
    ) -> List[EmailSummary]:
        """Fetch emails from spam/junk folder with pagination"""
        # Try to find spam folder
        spam_folder = await self._find_spam_folder()
        if not spam_folder:
            raise Exception("Spam folder not found. Available folders: " + 
                          ", ".join([f.name for f in await self.list_folders()]))
        
        search_criteria = self._build_search_criteria(
            from_date=from_date,
            to_date=to_date
        )
        return self._fetch_email_summaries(
            folder=spam_folder,
            search_criteria=search_criteria,
            limit=limit,
            offset=offset,
            from_date=from_date,
            to_date=to_date
        )

    async def _find_spam_folder(self) -> Optional[str]:
        """Find the spam folder name for the current mail server"""
        folders = await self.list_folders()
        folder_names = {f.full_path.lower(): f.full_path for f in folders}
        
        for spam_name in self._spam_folder_names:
            if spam_name.lower() in folder_names:
                return folder_names[spam_name.lower()]
        
        # Try partial match
        for folder_path, original_name in folder_names.items():
            if "spam" in folder_path or "junk" in folder_path:
                return original_name
        
        return None

    async def get_email_by_id(
        self,
        email_id: str,
        folder: str = "INBOX"
    ) -> Optional[EmailDetail]:
        """Get full email details by ID"""
        self._select_folder(folder)
        
        if not self._imap_connection:
            raise Exception("IMAP connection not established")
        
        try:
            status, msg_data = self._imap_connection.fetch(
                email_id.encode() if isinstance(email_id, str) else email_id,
                "(FLAGS RFC822)"
            )
            
            if status != "OK" or not msg_data or not msg_data[0]:
                return None
            
            # Parse flags
            flags_data = msg_data[0][0] if isinstance(msg_data[0], tuple) else b""
            is_read = b"\\Seen" in flags_data
            
            # Parse email
            raw_email = msg_data[0][1] if isinstance(msg_data[0], tuple) else msg_data[0]
            msg = email.message_from_bytes(raw_email)
            
            # Extract headers
            subject = self._decode_header_value(msg.get("Subject", "(No Subject)"))
            from_name, from_address = self._parse_email_address(msg.get("From", ""))
            to_address = msg.get("To", "")
            cc = msg.get("Cc", "")
            date = self._parse_date(msg.get("Date", ""))
            
            return EmailDetail(
                email_id=email_id,
                subject=subject,
                from_address=from_address,
                from_name=from_name if from_name else None,
                to_address=to_address,
                cc=cc.split(",") if cc else None,
                date=date,
                body_plain=self._get_plain_text_body(msg),
                body_html=self._get_html_body(msg),
                is_read=is_read,
                has_attachments=self._has_attachments(msg),
                attachment_names=self._get_attachment_names(msg) or None,
                folder=folder
            )
            
        except Exception as e:
            raise Exception(f"Failed to fetch email: {str(e)}")

    async def mark_as_read(
        self,
        email_id: str,
        folder: str = "INBOX"
    ) -> bool:
        """Mark an email as read"""
        self._select_folder(folder, readonly=False)
        
        if not self._imap_connection:
            raise Exception("IMAP connection not established")
        
        try:
            status, _ = self._imap_connection.store(
                email_id.encode() if isinstance(email_id, str) else email_id,
                '+FLAGS',
                '\\Seen'
            )
            return status == "OK"
        except Exception as e:
            raise Exception(f"Failed to mark email as read: {str(e)}")

    async def mark_as_unread(
        self,
        email_id: str,
        folder: str = "INBOX"
    ) -> bool:
        """Mark an email as unread"""
        self._select_folder(folder, readonly=False)
        
        if not self._imap_connection:
            raise Exception("IMAP connection not established")
        
        try:
            status, _ = self._imap_connection.store(
                email_id.encode() if isinstance(email_id, str) else email_id,
                '-FLAGS',
                '\\Seen'
            )
            return status == "OK"
        except Exception as e:
            raise Exception(f"Failed to mark email as unread: {str(e)}")

    async def list_folders(self) -> List[FolderInfo]:
        """List all available folders/mailboxes"""
        self._connect()
        
        if not self._imap_connection:
            raise Exception("IMAP connection not established")
        
        status, folder_list = self._imap_connection.list()
        if status != "OK":
            raise Exception("Failed to list folders")
        
        folders = []
        for folder_data in folder_list:
            if folder_data:
                # Parse folder info: (flags) delimiter "folder_name"
                try:
                    if isinstance(folder_data, bytes):
                        folder_data = folder_data.decode('utf-8', errors='replace')
                    
                    # Extract folder name (last quoted string or last part)
                    parts = folder_data.split('"')
                    if len(parts) >= 2:
                        folder_path = parts[-2]
                    else:
                        folder_path = folder_data.split()[-1]
                    
                    # Get folder name (last part of path)
                    folder_name = folder_path.split('/')[-1]
                    
                    # Try to get message count
                    msg_count = None
                    unread_count = None
                    try:
                        status, data = self._imap_connection.select(folder_path, readonly=True)
                        if status == "OK":
                            msg_count = int(data[0])
                            # Get unread count
                            status, unread_data = self._imap_connection.search(None, "UNSEEN")
                            if status == "OK" and unread_data[0]:
                                unread_count = len(unread_data[0].split())
                    except:
                        pass
                    
                    folders.append(FolderInfo(
                        name=folder_name,
                        full_path=folder_path,
                        message_count=msg_count,
                        unread_count=unread_count
                    ))
                    
                except Exception:
                    continue
        
        self._current_folder = None  # Reset since we selected multiple folders
        return folders

    async def get_folder_emails(
        self,
        folder: str,
        limit: int = 20,
        offset: int = 0,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None
    ) -> List[EmailSummary]:
        """Get emails from a specific folder with pagination"""
        search_criteria = self._build_search_criteria(
            from_date=from_date,
            to_date=to_date
        )
        return self._fetch_email_summaries(
            folder=folder,
            search_criteria=search_criteria,
            limit=limit,
            offset=offset,
            from_date=from_date,
            to_date=to_date
        )

    def validate_configuration(self) -> bool:
        """Validate that the IMAP receiver is properly configured"""
        required_configs = [
            self.imap_host,
            self.imap_port,
            self.email_user,
            self.email_password
        ]
        return all(config is not None for config in required_configs)

    def get_provider_name(self) -> str:
        """Get the name of the email provider"""
        return "IMAP"

    def get_configuration_status(self) -> dict:
        """Get current configuration status for debugging"""
        return {
            "provider": self.get_provider_name(),
            "imap_host": self.imap_host or "Not configured",
            "imap_port": self.imap_port,
            "email_user": self.email_user or "Not configured",
            "email_password": "***" if self.email_password else "Not configured",
            "use_ssl": self.use_ssl,
            "is_connected": self._is_connected,
            "current_folder": self._current_folder,
            "is_valid": self.validate_configuration()
        }

    def __del__(self):
        """Cleanup connection on object destruction"""
        self.disconnect()
