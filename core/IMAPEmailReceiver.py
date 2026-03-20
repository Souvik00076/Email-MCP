import re
import html
import imaplib
import email
from email.message import Message
from email.header import decode_header
from email.utils import parsedate_to_datetime, parseaddr
from typing import Optional, List, Tuple
from datetime import datetime
from .EmailReceiverStrategy import (
    EmailReceiverStrategy,
    EmailSummary,
    EmailDetail,
    FolderInfo
)


class IMAPEmailReceiver(EmailReceiverStrategy):

    IMAP_HOST = "imap.gmail.com"
    IMAP_PORT = 993

    # Common spam folder names to try
    SPAM_FOLDER_NAMES = [
        "[Gmail]/Spam",
        "Spam",
        "Junk",
        "Junk E-mail",
        "Bulk Mail",
        "[Gmail]/Junk"
    ]

    def __init__(self, access_token: str, email_user: str):
        self.access_token = access_token
        self.email_user = email_user
        self._imap_connection: Optional[imaplib.IMAP4_SSL] = None
        self._is_connected: bool = False
        self._current_folder: Optional[str] = None

    def _build_xoauth2_string(self) -> bytes:
        raw = f"user={self.email_user}\x01auth=Bearer {self.access_token}\x01\x01"
        return raw.encode()

    def _connect(self):
        if self._is_connected and self._imap_connection:
            try:
                self._imap_connection.noop()
                return
            except:
                self._is_connected = False
                self._imap_connection = None
                self._current_folder = None

        if not self.validate_configuration():
            raise Exception(
                "IMAPEmailReceiver is missing access_token or email_user.")

        try:
            self._imap_connection = imaplib.IMAP4_SSL(
                self.IMAP_HOST, self.IMAP_PORT)
            self._imap_connection.authenticate(
                "XOAUTH2", lambda x: self._build_xoauth2_string()
            )
            self._is_connected = True
        except imaplib.IMAP4.error as e:
            import logging
            logging.getLogger(__name__).error(f"IMAP XOAUTH2 auth failed: {repr(e)}")
            raise Exception(
                f"IMAP OAuth2 authentication failed. Detail: {repr(e)}"
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"IMAP connection error: {repr(e)}")
            raise Exception(f"Failed to connect to IMAP server: {repr(e)}")

    def _select_folder(self, folder: str, readonly: bool = True):
        if self._current_folder != folder:
            self._connect()
            if not self._imap_connection:
                raise Exception("IMAP connection not established")
            status, data = self._imap_connection.select(
                folder, readonly=readonly)
            if status != "OK":
                raise Exception(f"Failed to select folder '{folder}': {data}")
            self._current_folder = folder

    def disconnect(self):
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
        if not value:
            return ""
        decoded_parts = []
        for part, encoding in decode_header(value):
            if isinstance(part, bytes):
                try:
                    decoded_parts.append(part.decode(
                        encoding or "utf-8", errors="replace"))
                except:
                    decoded_parts.append(
                        part.decode("utf-8", errors="replace"))
            else:
                decoded_parts.append(part)
        return "".join(decoded_parts)

    def _parse_email_address(self, raw_from: str) -> Tuple[str, str]:
        decoded = self._decode_header_value(raw_from)
        name, address = parseaddr(decoded)
        return name, address

    def _get_plain_text_body(self, msg: Message) -> str:
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if "attachment" in str(part.get("Content-Disposition", "")):
                    continue
                if part.get_content_type() == "text/plain":
                    try:
                        payload = part.get_payload(decode=True)
                        if isinstance(payload, bytes):
                            charset = msg.get_content_charset() or "utf-8"
                            body = payload.decode(charset, errors="replace")
                            break
                    except:
                        continue
        else:
            if msg.get_content_type() == "text/plain":
                try:
                    payload = msg.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        charset = msg.get_content_charset() or "utf-8"
                        body = payload.decode(charset, errors="replace")
                except:
                    pass
        return body.strip()

    def _get_html_body(self, msg: Message) -> str:
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if "attachment" in str(part.get("Content-Disposition", "")):
                    continue
                if part.get_content_type() == "text/html":
                    try:
                        payload = part.get_payload(decode=True)
                        if isinstance(payload, bytes):
                            charset = part.get_content_charset() or "utf-8"
                            body = payload.decode(charset, errors="replace")
                            break
                    except:
                        continue
        else:
            if msg.get_content_type() == "text/html":
                try:
                    payload = msg.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        charset = msg.get_content_charset() or "utf-8"
                        body = payload.decode(charset, errors="replace")
                except:
                    pass
        return body.strip()

    def _has_attachments(self, msg: Message) -> bool:
        if msg.is_multipart():
            for part in msg.walk():
                if "attachment" in str(part.get("Content-Disposition", "")):
                    return True
        return False

    def _get_attachment_names(self, msg: Message) -> List[str]:
        attachments = []
        if msg.is_multipart():
            for part in msg.walk():
                if "attachment" in str(part.get("Content-Disposition", "")):
                    filename = part.get_filename()
                    if filename:
                        attachments.append(self._decode_header_value(filename))
        return attachments

    def _parse_date(self, date_str: str) -> datetime:
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
        criteria = []
        if unread_only:
            criteria.append("UNSEEN")
        if from_date:
            criteria.append(f"SINCE {from_date.strftime('%d-%b-%Y')}")
        if to_date:
            criteria.append(f"BEFORE {to_date.strftime('%d-%b-%Y')}")
        if sender:
            criteria.append(f'FROM "{sender}"')
        return " ".join(criteria) if criteria else "ALL"

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
        self._select_folder(folder)

        if not self._imap_connection:
            raise Exception("IMAP connection not established")

        status, data = self._imap_connection.search(None, search_criteria)
        if status != "OK":
            raise Exception(f"IMAP search failed: {data}")

        email_ids = list(reversed(data[0].split()))

        # Fetch extra when fuzzy filtering sender — we'll paginate after filtering
        if sender_filter:
            fetch_slice = email_ids[: (offset + limit) * 3]
        else:
            fetch_slice = email_ids[offset: offset + limit]

        summaries = []

        for email_id in fetch_slice:
            try:
                status, msg_data = self._imap_connection.fetch(
                    email_id, "(FLAGS RFC822)")
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue

                is_read = False
                raw_email = None
                for part in msg_data:
                    if isinstance(part, tuple):
                        if isinstance(part[0], bytes):
                            is_read = b"\\Seen" in part[0]
                        if len(part) > 1 and isinstance(part[1], bytes):
                            raw_email = part[1]
                            break

                if not raw_email:
                    continue

                msg = email.message_from_bytes(raw_email)
                subject = self._decode_header_value(
                    msg.get("Subject", "(No Subject)"))
                from_name, from_address = self._parse_email_address(
                    msg.get("From", ""))
                to_address = msg.get("To", "")
                date = self._parse_date(msg.get("Date", ""))

                if from_date and date < from_date:
                    continue
                if to_date and date > to_date:
                    continue

                if sender_filter:
                    q = sender_filter.lower()
                    if not (q in from_address.lower() or q in from_name.lower()):
                        continue

                body = self._get_plain_text_body(msg)
                if not body:
                    html_body = self._get_html_body(msg)
                    if html_body:
                        body = re.sub(
                            r"<style[^>]*>.*?</style>", "", html_body, flags=re.DOTALL | re.IGNORECASE)
                        body = re.sub(
                            r"<script[^>]*>.*?</script>", "", body, flags=re.DOTALL | re.IGNORECASE)
                        body = re.sub(r"<[^>]+>", " ", body)
                        body = html.unescape(re.sub(r"\s+", " ", body).strip())

                preview = body[:200] + "..." if len(body) > 200 else body

                summaries.append(EmailSummary(
                    email_id=email_id.decode() if isinstance(email_id, bytes) else str(email_id),
                    subject=subject,
                    from_address=from_address,
                    from_name=from_name or None,
                    to_address=to_address,
                    date=date,
                    preview=preview,
                    is_read=is_read,
                    has_attachments=self._has_attachments(msg),
                    folder=folder
                ))
            except Exception:
                continue

        if sender_filter:
            summaries = summaries[offset: offset + limit]

        return summaries

    async def fetch_recent_emails(self, folder: str = "INBOX", limit: int = 20, offset: int = 0, from_date: Optional[datetime] = None, to_date: Optional[datetime] = None) -> List[EmailSummary]:
        return self._fetch_email_summaries(folder, self._build_search_criteria(from_date=from_date, to_date=to_date), limit, offset, from_date=from_date, to_date=to_date)

    async def fetch_unread_emails(self, folder: str = "INBOX", limit: int = 20, offset: int = 0, from_date: Optional[datetime] = None, to_date: Optional[datetime] = None) -> List[EmailSummary]:
        return self._fetch_email_summaries(folder, self._build_search_criteria(unread_only=True, from_date=from_date, to_date=to_date), limit, offset, from_date=from_date, to_date=to_date)

    async def search_emails_by_sender(self, sender_query: str, folder: str = "INBOX", limit: int = 20, offset: int = 0, from_date: Optional[datetime] = None, to_date: Optional[datetime] = None) -> List[EmailSummary]:
        return self._fetch_email_summaries(folder, self._build_search_criteria(from_date=from_date, to_date=to_date), limit, offset, sender_filter=sender_query, from_date=from_date, to_date=to_date)

    async def fetch_spam_emails(self, limit: int = 20, offset: int = 0, from_date: Optional[datetime] = None, to_date: Optional[datetime] = None) -> List[EmailSummary]:
        spam_folder = await self._find_spam_folder()
        if not spam_folder:
            folders = await self.list_folders()
            raise Exception("Spam folder not found. Available folders: " +
                            ", ".join([f.name for f in folders]))
        return self._fetch_email_summaries(spam_folder, self._build_search_criteria(from_date=from_date, to_date=to_date), limit, offset, from_date=from_date, to_date=to_date)

    async def _find_spam_folder(self) -> Optional[str]:
        folders = await self.list_folders()
        folder_names = {f.full_path.lower(): f.full_path for f in folders}
        for spam_name in self.SPAM_FOLDER_NAMES:
            if spam_name.lower() in folder_names:
                return folder_names[spam_name.lower()]
        for folder_path, original_name in folder_names.items():
            if "spam" in folder_path or "junk" in folder_path:
                return original_name
        return None

    async def get_email_by_id(self, email_id: str, folder: str = "INBOX") -> Optional[EmailDetail]:
        self._select_folder(folder)
        if not self._imap_connection:
            raise Exception("IMAP connection not established")
        try:
            status, msg_data = self._imap_connection.fetch(
                email_id if isinstance(email_id, str) else email_id,
                "(FLAGS RFC822)"
            )
            if status != "OK" or not msg_data or not msg_data[0]:
                return None

            flags_data = msg_data[0][0] if isinstance(
                msg_data[0], tuple) else b""
            is_read = b"\\Seen" in flags_data
            raw_email = msg_data[0][1] if isinstance(
                msg_data[0], tuple) else msg_data[0]
            msg = email.message_from_bytes(raw_email)

            subject = self._decode_header_value(
                msg.get("Subject", "(No Subject)"))
            from_name, from_address = self._parse_email_address(
                msg.get("From", ""))
            to_address = msg.get("To", "")
            cc = msg.get("Cc", "")
            date = self._parse_date(msg.get("Date", ""))

            return EmailDetail(
                email_id=email_id,
                subject=subject,
                from_address=from_address,
                from_name=from_name or None,
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

    async def mark_as_read(self, email_id: str, folder: str = "INBOX") -> bool:
        self._select_folder(folder, readonly=False)
        if not self._imap_connection:
            raise Exception("IMAP connection not established")
        try:
            status, _ = self._imap_connection.store(
                email_id if isinstance(email_id, str) else email_id,
                "+FLAGS", "\\Seen"
            )
            return status == "OK"
        except Exception as e:
            raise Exception(f"Failed to mark email as read: {str(e)}")

    async def mark_as_unread(self, email_id: str, folder: str = "INBOX") -> bool:
        self._select_folder(folder, readonly=False)
        if not self._imap_connection:
            raise Exception("IMAP connection not established")
        try:
            status, _ = self._imap_connection.store(
                email_id if isinstance(email_id, str) else email_id,
                "-FLAGS", "\\Seen"
            )
            return status == "OK"
        except Exception as e:
            raise Exception(f"Failed to mark email as unread: {str(e)}")

    async def list_folders(self) -> List[FolderInfo]:
        self._connect()
        if not self._imap_connection:
            raise Exception("IMAP connection not established")

        status, folder_list = self._imap_connection.list()
        if status != "OK":
            raise Exception("Failed to list folders")

        folders = []
        for folder_data in folder_list:
            if not folder_data:
                continue
            try:
                # folder_data can be tuple[bytes, bytes] or bytes — normalize to str
                if isinstance(folder_data, tuple):
                    raw = folder_data[-1]
                    folder_str = raw.decode(
                        "utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
                elif isinstance(folder_data, bytes):
                    folder_str = folder_data.decode("utf-8", errors="replace")
                else:
                    folder_str = str(folder_data)

                parts = folder_str.split('"')
                folder_path = parts[-2] if len(
                    parts) >= 2 else folder_str.split()[-1]
                folder_name = folder_path.split("/")[-1]

                msg_count: Optional[int] = None
                unread_count: Optional[int] = None
                try:
                    sel_status, sel_data = self._imap_connection.select(
                        folder_path, readonly=True)
                    if sel_status == "OK" and sel_data and sel_data[0] is not None:
                        msg_count = int(sel_data[0].decode() if isinstance(
                            sel_data[0], bytes) else sel_data[0])
                        srch_status, srch_data = self._imap_connection.search(
                            None, "UNSEEN")
                    if srch_status == "OK" and srch_data and srch_data[0]:
                        unread_count = len(srch_data[0].split())
                except Exception:
                    pass

                folders.append(FolderInfo(
                    name=folder_name,
                    full_path=folder_path,
                    message_count=msg_count,
                    unread_count=unread_count
                ))
            except Exception:
                continue

            self._current_folder = None
        return folders

    async def get_folder_emails(self, folder: str, limit: int = 20, offset: int = 0, from_date: Optional[datetime] = None, to_date: Optional[datetime] = None) -> List[EmailSummary]:
        return self._fetch_email_summaries(folder, self._build_search_criteria(from_date=from_date, to_date=to_date), limit, offset, from_date=from_date, to_date=to_date)

    def validate_configuration(self) -> bool:
        return bool(self.access_token and self.email_user)

    def get_provider_name(self) -> str:
        return "IMAP-OAuth2"

    def get_configuration_status(self) -> dict:
        return {
            "provider": self.get_provider_name(),
            "imap_host": self.IMAP_HOST,
            "imap_port": self.IMAP_PORT,
            "email_user": self.email_user,
            "access_token": "***" if self.access_token else "Not provided",
            "is_connected": self._is_connected,
            "current_folder": self._current_folder,
            "is_valid": self.validate_configuration()
        }
