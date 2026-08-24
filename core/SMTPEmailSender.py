import base64
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from .EmailSenderStrategy import EmailSenderStrategy, EmailMessage


class SMTPEmailSender(EmailSenderStrategy):

    # Defaults kept for backward compatibility; pass smtp_host/smtp_port to
    # __init__ to target a different SMTP server (e.g. non-Gmail providers).
    SMTP_HOST = "smtp.gmail.com"
    SMTP_PORT = 587

    def __init__(self, access_token: str, email_user: str, smtp_host: str = SMTP_HOST, smtp_port: int = SMTP_PORT):
        self.access_token = access_token
        self.email_user = email_user
        self.SMTP_HOST = smtp_host
        self.SMTP_PORT = smtp_port

    def _build_xoauth2_string(self) -> str:
        raw = f"user={self.email_user}\x01auth=Bearer {
            self.access_token}\x01\x01"
        return base64.b64encode(raw.encode()).decode()

    def _connect(self) -> smtplib.SMTP:
        """
        Open a fresh SMTP connection authenticated via OAuth2.
        Called once per send — no persistent connection needed (stateless).
        """
        try:
            conn = smtplib.SMTP(self.SMTP_HOST, self.SMTP_PORT, timeout=30)
            conn.starttls()
            conn.docmd("AUTH", f"XOAUTH2 {self._build_xoauth2_string()}")
            return conn
        except smtplib.SMTPAuthenticationError:
            raise Exception(
                "SMTP OAuth2 authentication failed. "
                "Access token may be expired — refresh and update Redis."
            )
        except Exception as e:
            raise Exception(f"Failed to connect to SMTP server: {str(e)}")

    async def send_email(self, email: EmailMessage) -> dict:
        """
        Send an email via OAuth2-authenticated SMTP.
        Opens and closes connection per call (stateless, safe for concurrent requests).

        Args:
            email: EmailMessage with to, subject, body, cc, bcc
        Returns:
            dict: success status, message, email_id
        Raises:
            Exception: on auth failure, SMTP error, or connection failure
        """
        if not self.validate_configuration():
            raise Exception(
                "SMTPEmailSender is missing access_token or email_user.")

        # Build message
        msg = MIMEMultipart()
        msg["From"] = self.email_user
        msg["To"] = email.to
        msg["Subject"] = email.subject

        if email.cc:
            msg["Cc"] = ", ".join(email.cc)

        msg.attach(MIMEText(email.body, "plain"))

        # BCC goes in recipient list only — never in headers
        recipients = [email.to]
        if email.cc:
            recipients.extend(email.cc)
        if email.bcc:
            recipients.extend(email.bcc)

        conn = self._connect()
        try:
            conn.sendmail(self.email_user, recipients, msg.as_string())
            return {
                "success": True,
                "message": "Email sent successfully via SMTP (OAuth2)",
                "email_id": f"smtp_{email.to}_{hash(email.subject)}"
            }
        except smtplib.SMTPException as e:
            raise Exception(f"SMTP error while sending: {str(e)}")
        finally:
            try:
                conn.quit()
            except Exception:
                pass

    def validate_configuration(self) -> bool:
        return bool(self.access_token and self.email_user)

    def get_provider_name(self) -> str:
        return "SMTP-OAuth2"

    def get_configuration_status(self) -> dict:
        return {
            "provider": self.get_provider_name(),
            "smtp_host": self.SMTP_HOST,
            "smtp_port": self.SMTP_PORT,
            "email_user": self.email_user,
            "access_token": "***" if self.access_token else "Not provided",
            "is_valid": self.validate_configuration()
        }
