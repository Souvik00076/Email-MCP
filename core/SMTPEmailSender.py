import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from dotenv import load_dotenv
from .EmailSenderStrategy import EmailSenderStrategy, EmailMessage

# Load environment variables
load_dotenv()


class SMTPEmailSender(EmailSenderStrategy):
    """
    SMTP Email Sender Strategy (Python equivalent of Nodemailer)
    Uses SMTP protocol to send emails via configured mail server.
    Maintains a persistent connection to avoid re-authentication on every send.
    Implements Singleton pattern to persist across API requests.
    """
    _instance: Optional['SMTPEmailSender'] = None
    _initialized = False
    def __new__(cls):
        """Singleton pattern - only one instance exists"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize SMTP sender with environment variables (only once)"""
        # Prevent re-initialization
        if self._initialized:
            return
        self.smtp_host: Optional[str] = os.getenv("SMTP_HOST")
        smtp_port_str = os.getenv("SMTP_PORT", "587")
        self.smtp_port: int = int(smtp_port_str) if smtp_port_str else 587
        self.email_user: Optional[str] = os.getenv("EMAIL_USER")
        self.email_password: Optional[str] = os.getenv("EMAIL_PASSWORD")
        use_tls_str = os.getenv("SMTP_USE_TLS", "True")
        self.use_tls: bool = use_tls_str.lower() == "true" if use_tls_str else True
        self._smtp_connection: Optional[smtplib.SMTP] = None
        self._is_connected: bool = False
        self._initialized = True

    def _connect(self):
        """
        Establish and authenticate SMTP connection.
        Reuses existing connection if already established.
        """
        if self._is_connected and self._smtp_connection:
            try:
                # Test if connection is still alive
                self._smtp_connection.noop()
                return
            except:
                # Connection is dead, reconnect
                self._is_connected = False
                self._smtp_connection = None
        # Validate required fields are not None
        if not self.smtp_host or not self.email_user or not self.email_password:
            raise Exception("SMTP configuration incomplete. Check your .env file.")
        try:
            # Create new connection
            self._smtp_connection = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30)
            if self.use_tls:
                self._smtp_connection.starttls()
            # Login once and reuse
            self._smtp_connection.login(self.email_user, self.email_password)
            self._is_connected = True
        except smtplib.SMTPAuthenticationError:
            raise Exception("SMTP authentication failed. Check your Gmail app password.")
        except Exception as e:
            raise Exception(f"Failed to connect to SMTP server: {str(e)}")

    def disconnect(self):
        """Close the SMTP connection"""
        if self._smtp_connection:
            try:
                self._smtp_connection.quit()
            except:
                pass
            finally:
                self._smtp_connection = None
                self._is_connected = False

    async def send_email(self, email: EmailMessage) -> dict:
        """
        Send an email using SMTP protocol.
        Reuses existing connection to avoid re-authentication.
        Args:
            email: EmailMessage object containing all email details
        Returns:
            dict: Response containing success status, message, and email_id
        Raises:
            Exception: If email sending fails
        """
        # Validate configuration before sending
        if not self.validate_configuration():
            raise Exception("SMTP configuration is invalid or incomplete")
        # Ensure we have an active connection
        self._connect()
        # Create message (define outside try block to avoid unbound variable)
        msg = MIMEMultipart()
        msg['From'] = self.email_user or ""
        msg['To'] = email.to
        msg['Subject'] = email.subject
        # Add CC recipients
        if email.cc:
            msg['Cc'] = ', '.join(email.cc)
        # Add BCC recipients (not shown in headers)
        # BCC is handled in the recipient list, not in headers
        # Attach body
        msg.attach(MIMEText(email.body, 'plain'))
        # Prepare recipient list
        recipients = [email.to]
        if email.cc:
            recipients.extend(email.cc)
        if email.bcc:
            recipients.extend(email.bcc)
        try:
            # Send email using persistent connection
            if not self._smtp_connection:
                raise Exception("SMTP connection not established")
            self._smtp_connection.sendmail(self.email_user or "", recipients, msg.as_string())
            return {
                "success": True,
                "message": "Email sent successfully via SMTP",
                "email_id": f"smtp_{email.to}_{hash(email.subject)}"
            }
        except smtplib.SMTPServerDisconnected:
            # Connection lost, retry once
            self._is_connected = False
            self._connect()
            if not self._smtp_connection:
                raise Exception("Failed to reconnect to SMTP server")
            self._smtp_connection.sendmail(self.email_user or "", recipients, msg.as_string())
            return {
                "success": True,
                "message": "Email sent successfully via SMTP (reconnected)",
                "email_id": f"smtp_{email.to}_{hash(email.subject)}"
            }
        except smtplib.SMTPException as e:
            raise Exception(f"SMTP error occurred: {str(e)}")
        except Exception as e:
            raise Exception(f"Failed to send email: {str(e)}")

    def validate_configuration(self) -> bool:
        """
        Validate that the SMTP sender is properly configured.
        Returns:
            bool: True if configuration is valid, False otherwise
        """
        required_configs = [
            self.smtp_host,
            self.smtp_port,
            self.email_user,
            self.email_password
        ]
        return all(config is not None for config in required_configs)

    def get_provider_name(self) -> str:
        """
        Get the name of the email provider.
        Returns:
            str: Provider name
        """
        return "SMTP"

    def get_configuration_status(self) -> dict:
        """
        Get current configuration status for debugging.
        Returns:
            dict: Configuration details (passwords masked)
        """
        return {
            "provider": self.get_provider_name(),
            "smtp_host": self.smtp_host or "Not configured",
            "smtp_port": self.smtp_port,
            "email_user": self.email_user or "Not configured",
            "email_password": "***" if self.email_password else "Not configured",
            "use_tls": self.use_tls,
            "is_connected": self._is_connected,
            "is_valid": self.validate_configuration()
        }
    def __del__(self):
        """Cleanup connection on object destruction"""
        self.disconnect()
