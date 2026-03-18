# Email MCP Server

A FastAPI-based MCP (Model Context Protocol) server for email operations. Supports both sending emails via SMTP and reading emails via IMAP.

## Features

- **Send Emails** - Send emails with CC/BCC support via SMTP
- **Read Emails** - Fetch recent, unread, or search emails via IMAP
- **Folder Management** - List and read from any email folder
- **Spam Detection** - Auto-detect and read from spam folder
- **Fuzzy Search** - Search emails by sender (case-insensitive partial match)
- **Date Filtering** - Filter emails by date range
- **Pagination** - Limit and offset support for all list endpoints
- **MCP Integration** - Full MCP protocol support via FastAPI-MCP

## Setup

### 1. Create virtual environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure environment
```bash
cp .env.example .env
```

Edit `.env` with your email credentials:
```bash
# Email credentials (shared for SMTP and IMAP)
EMAIL_USER=your-email@gmail.com
EMAIL_PASSWORD=your-app-password

# SMTP Configuration (sending)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=True

# IMAP Configuration (reading)
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USE_SSL=True
```

> **Note for Gmail users:** You need to use an [App Password](https://support.google.com/accounts/answer/185833) instead of your regular password. Enable 2FA first, then generate an app password.

### 4. Run the server
```bash
python main.py
```

Or using uvicorn directly:
```bash
uvicorn main:app --reload
```

## API Endpoints

### Health & Status

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Root endpoint with health status |
| `/health` | GET | Health check endpoint |
| `/email/status` | GET | Email sender configuration status |

### Sending Emails

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/send-email` | POST | Send an email with optional CC/BCC |

**Example:**
```bash
curl -X POST http://localhost:8000/send-email \
  -H "Content-Type: application/json" \
  -d '{
    "to": "recipient@example.com",
    "subject": "Hello",
    "body": "This is a test email",
    "cc": ["cc@example.com"],
    "bcc": ["bcc@example.com"]
  }'
```

### Reading Emails

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/emails/recent` | GET | Get recent emails (most recent first) |
| `/emails/unread` | GET | Get unread emails only |
| `/emails/search` | GET | Search emails by sender (fuzzy match) |
| `/emails/spam` | GET | Get emails from spam folder |
| `/emails/folders` | GET | List all available folders |
| `/emails/folder/{path}` | GET | Get emails from a specific folder |
| `/emails/{id}` | GET | Get full details of a single email |

**Common Query Parameters:**
- `limit` (default: 20, max: 100) - Number of emails to return
- `offset` (default: 0) - Number of emails to skip (pagination)
- `from_date` - Filter emails from this date (ISO format)
- `to_date` - Filter emails until this date (ISO format)
- `folder` - Folder to fetch from (default: INBOX)

**Examples:**
```bash
# Get 10 most recent emails
curl "http://localhost:8000/emails/recent?limit=10"

# Get unread emails from last week
curl "http://localhost:8000/emails/unread?from_date=2024-03-11T00:00:00"

# Search for emails from "john" (fuzzy match)
curl "http://localhost:8000/emails/search?sender=john"

# Get spam emails
curl "http://localhost:8000/emails/spam?limit=10"

# List all folders
curl "http://localhost:8000/emails/folders"

# Get emails from Sent folder
curl "http://localhost:8000/emails/folder/[Gmail]/Sent%20Mail"

# Get full email details
curl "http://localhost:8000/emails/12345?folder=INBOX"
```

### Managing Emails

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/emails/{id}/mark-read` | POST | Mark an email as read |
| `/emails/{id}/mark-unread` | POST | Mark an email as unread |

**Examples:**
```bash
# Mark email as read
curl -X POST "http://localhost:8000/emails/12345/mark-read?folder=INBOX"

# Mark email as unread
curl -X POST "http://localhost:8000/emails/12345/mark-unread?folder=INBOX"
```

## Response Models

### EmailSummary (list endpoints)
```json
{
  "email_id": "12345",
  "subject": "Hello World",
  "from_address": "sender@example.com",
  "from_name": "John Doe",
  "to_address": "you@example.com",
  "date": "2024-03-18T10:30:00",
  "preview": "This is the first 200 characters of the email...",
  "is_read": false,
  "has_attachments": true,
  "folder": "INBOX"
}
```

### EmailDetail (single email endpoint)
```json
{
  "email_id": "12345",
  "subject": "Hello World",
  "from_address": "sender@example.com",
  "from_name": "John Doe",
  "to_address": "you@example.com",
  "cc": ["cc@example.com"],
  "date": "2024-03-18T10:30:00",
  "body_plain": "Plain text content...",
  "body_html": "<html>HTML content...</html>",
  "is_read": false,
  "has_attachments": true,
  "attachment_names": ["document.pdf", "image.png"],
  "folder": "INBOX"
}
```

### FolderInfo (folders endpoint)
```json
{
  "name": "Sent Mail",
  "full_path": "[Gmail]/Sent Mail",
  "message_count": 150,
  "unread_count": 0
}
```

## Architecture

```
email-mcp/
├── main.py                    # FastAPI app with all endpoints
├── sender/
│   ├── __init__.py
│   ├── EmailSenderStrategy.py # Abstract base for sending
│   ├── SMTPEmailSender.py     # SMTP implementation
│   ├── EmailReceiverStrategy.py # Abstract base for reading
│   └── IMAPEmailReceiver.py   # IMAP implementation
├── requirements.txt
├── .env.example
└── README.md
```

## API Documentation

Once running, visit:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

## Common IMAP Folder Names

| Provider | Inbox | Sent | Spam | Drafts | Trash |
|----------|-------|------|------|--------|-------|
| Gmail | INBOX | [Gmail]/Sent Mail | [Gmail]/Spam | [Gmail]/Drafts | [Gmail]/Trash |
| Outlook | INBOX | Sent | Junk | Drafts | Deleted |
| Yahoo | INBOX | Sent | Bulk Mail | Draft | Trash |

Use `/emails/folders` endpoint to discover the exact folder names for your provider.

## Security Notes

- Never commit your `.env` file with real credentials
- Use app-specific passwords instead of your main password
- For production, consider implementing OAuth2 authentication
- The server uses persistent connections (singleton pattern) for efficiency
