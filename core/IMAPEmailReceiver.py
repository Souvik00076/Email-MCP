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

    # Defaults kept for backward compatibility; pass imap_host/imap_port to
    # __init__ to target a different IMAP server (e.g. non-Gmail providers).
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

    def __init__(self, access_token: str, email_user: str, imap_host: str = IMAP_HOST, imap_port: int = IMAP_PORT):
        self.access_token = access_token
        self.email_user = email_user
        self.IMAP_HOST = imap_host
        self.IMAP_PORT = imap_port
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
            # imaplib does not auto-quote mailbox names; folders containing
            # spaces or special chars (e.g. "[Gmail]/Sent Mail") must be
            # wrapped in a quoted IMAP string or the server rejects the
            # SELECT/EXAMINE command with "Could not parse command".
            mailbox = folder
            if any(c in folder for c in (' ', '"', '\\')) and not (
                    folder.startswith('"') and folder.endswith('"')):
                escaped = folder.replace('\\', '\\\\').replace('"', '\\"')
                mailbox = f'"{escaped}"'
            status, data = self._imap_connection.select(
                mailbox, readonly=readonly)
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

    def _parse_fetch_response(self, msg_data: list) -> List[Tuple[bytes, bool, bytes]]:
        """Parse a `FETCH ... (FLAGS RFC822)` response — single or batched —
        into a list of (email_id, is_read, raw_email) tuples.

        A batched response repeats the (header, raw) tuple pattern once per
        message, with plain b')' entries interleaved as separators; those
        aren't tuples, so the isinstance check below skips them. A
        single-message response is just the degenerate case of one tuple.
        """
        parsed = []
        for part in msg_data:
            if not isinstance(part, tuple) or len(part) < 2:
                continue
            header, raw_email = part[0], part[1]
            if not isinstance(header, bytes) or not isinstance(raw_email, bytes):
                continue
            id_match = re.match(rb"(\d+)", header)
            if not id_match:
                continue
            parsed.append((id_match.group(1), b"\\Seen" in header, raw_email))
        return parsed

    def _extract_common_fields(self, msg: Message) -> Tuple[str, str, str, str, datetime]:
        """Extract the header fields shared by summary and detail views:
        (subject, from_name, from_address, to_address, date)."""
        subject = self._decode_header_value(
            msg.get("Subject", "(No Subject)"))
        from_name, from_address = self._parse_email_address(
            msg.get("From", ""))
        to_address = msg.get("To", "")
        date = self._parse_date(msg.get("Date", ""))
        return subject, from_name, from_address, to_address, date

    @staticmethod
    def _normalize_header(value: Optional[str]) -> Optional[str]:
        """Collapse a folded header into a single line.

        Long headers (notably References, which grows by one msg-id per hop)
        arrive wrapped across lines with leading whitespace. Angle brackets are
        kept — <...> is the form In-Reply-To/References use on the wire.
        """
        if not value:
            return None
        return " ".join(value.split()) or None

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

        if not fetch_slice:
            return summaries

        # (FLAGS RFC822) asks the server for two things together in one
        # round-trip: the message's flags (to know if it's read/unread) and
        # its full raw content.
        # Batch fetch: one FETCH call for all IDs (comma-separated message set)
        # instead of one round-trip per email. fetch_slice items are bytes
        # (e.g. b"20"), so decode each before joining — imaplib's fetch()
        # is typed to take a str message_set.
        message_set = ",".join(i.decode() for i in fetch_slice)
        status, msg_data = self._imap_connection.fetch(
            message_set, "(FLAGS RFC822)")
        if status != "OK" or not msg_data:
            return summaries

        parsed_messages = self._parse_fetch_response(msg_data)

        for email_id, is_read, raw_email in parsed_messages:
            try:
                msg = email.message_from_bytes(raw_email)
                subject, from_name, from_address, to_address, date = self._extract_common_fields(
                    msg)

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
                    message_id=self._normalize_header(msg.get("Message-ID")),
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
                email_id, "(FLAGS RFC822)"
            )
            if status != "OK" or not msg_data or not msg_data[0]:
                return None

            parsed = self._parse_fetch_response(msg_data)
            if not parsed:
                return None
            _, is_read, raw_email = parsed[0]
            msg = email.message_from_bytes(raw_email)

            subject, from_name, from_address, to_address, date = self._extract_common_fields(
                msg)
            cc = msg.get("Cc", "")

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
                folder=folder,
                message_id=self._normalize_header(msg.get("Message-ID")),
                in_reply_to=self._normalize_header(msg.get("In-Reply-To")),
                references=self._normalize_header(msg.get("References")),
                reply_to=self._normalize_header(msg.get("Reply-To")),
            )
        except Exception as e:
            raise Exception(f"Failed to fetch email: {str(e)}")

    async def mark_as_read(self, email_id: str, folder: str = "INBOX") -> bool:
        self._select_folder(folder, readonly=False)
        if not self._imap_connection:
            raise Exception("IMAP connection not established")
        try:
            status, _ = self._imap_connection.store(
                email_id, "+FLAGS", "\\Seen"
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
                email_id, "-FLAGS", "\\Seen"
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
                    # STATUS gets both counts in a single round-trip per
                    # folder (vs. SELECT + SEARCH = two), and — unlike
                    # SELECT — never changes the connection's currently
                    # selected mailbox, so no _current_folder reset needed.
                    st_status, st_data = self._imap_connection.status(
                        folder_path, "(MESSAGES UNSEEN)")
                    if st_status == "OK" and st_data and st_data[0]:
                        st_str = st_data[0].decode(
                            "utf-8", errors="replace") if isinstance(st_data[0], bytes) else str(st_data[0])
                        msg_match = re.search(r"MESSAGES\s+(\d+)", st_str)
                        unseen_match = re.search(r"UNSEEN\s+(\d+)", st_str)
                        if msg_match:
                            msg_count = int(msg_match.group(1))
                        if unseen_match:
                            unread_count = int(unseen_match.group(1))
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
