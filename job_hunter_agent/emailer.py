"""
job_hunter_agent/emailer.py
============================
Handles all Gmail operations:
  - Send outreach emails to leads (via SMTP App Password — no OAuth needed)
  - Read incoming replies (via Gmail API if token exists, else IMAP)
  - Send AI-generated follow-up replies
  - Track email threads per lead

Setup: Add GMAIL_APP_PASSWORD to .env
  1. Go to myaccount.google.com/apppasswords
  2. Create app password for "JobHunterAgent"
  3. Add to .env: GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
"""

import os
import base64
import pickle
import logging
import json
import smtplib
import imaplib
import email as email_lib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List, Optional
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)
logger = logging.getLogger(__name__)

SENDER_EMAIL = os.getenv("GMAIL_SENDER_EMAIL", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
CREDENTIALS_FILE = os.getenv("GMAIL_CREDENTIALS_FILE", "credentials/gmail_credentials.json")
TOKEN_FILE = os.getenv("GMAIL_TOKEN_FILE", "credentials/gmail_token.pickle")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]


def _smtp_available() -> bool:
    return bool(SENDER_EMAIL and GMAIL_APP_PASSWORD and not GMAIL_APP_PASSWORD.startswith("your_"))


def _get_gmail_service():
    """Authenticate and return Gmail API service (OAuth token)."""
    import pickle
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if Path(TOKEN_FILE).exists():
        with open(TOKEN_FILE, "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path(CREDENTIALS_FILE).exists():
                raise FileNotFoundError(
                    f"Gmail credentials not found at {CREDENTIALS_FILE}"
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        Path(TOKEN_FILE).parent.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_FILE, "wb") as token:
            pickle.dump(creds, token)

    return build("gmail", "v1", credentials=creds)


# ─────────────────────────────────────────────
#  SEND outreach email to a lead
# ─────────────────────────────────────────────
def send_outreach_email(
    to_email: str,
    subject: str,
    body: str,
    lead_id: str,
) -> Optional[Dict]:
    """
    Send an outreach email via SMTP (App Password) or Gmail API.
    Returns dict with message_id on success, None on failure.
    """
    # --- Primary: SMTP App Password (no OAuth needed) ---
    if _smtp_available():
        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = SENDER_EMAIL
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))
            html_body = body.replace("\n", "<br>")
            msg.attach(MIMEText(f"<html><body><p>{html_body}</p></body></html>", "html"))

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(SENDER_EMAIL, GMAIL_APP_PASSWORD.replace(" ", ""))
                server.sendmail(SENDER_EMAIL, to_email, msg.as_string())

            fake_id = f"smtp_{lead_id}_{int(__import__('time').time())}"
            logger.info(f"✉️  Email sent via SMTP to {to_email}")
            return {"message_id": fake_id, "thread_id": fake_id}
        except Exception as e:
            logger.error(f"SMTP send error: {e}")
            return None

    # --- Fallback: Gmail API (OAuth token) ---
    if Path(TOKEN_FILE).exists():
        try:
            from googleapiclient.errors import HttpError
            service = _get_gmail_service()
            msg = MIMEMultipart("alternative")
            msg["to"] = to_email
            msg["from"] = SENDER_EMAIL
            msg["subject"] = subject
            msg.attach(MIMEText(body, "plain"))
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
            logger.info(f"✉️  Email sent via Gmail API to {to_email}")
            return {"message_id": sent["id"], "thread_id": sent["threadId"]}
        except Exception as e:
            logger.error(f"Gmail API send error: {e}")
            return None

    logger.warning("⚠️  No email method available. Add GMAIL_APP_PASSWORD to .env")
    return None


# ─────────────────────────────────────────────
#  READ replies from inbox
# ─────────────────────────────────────────────
def get_new_replies(after_timestamp: Optional[str] = None) -> List[Dict]:
    """
    Fetch new unread replies via IMAP (App Password) or Gmail API.
    """
    # --- Primary: IMAP with App Password ---
    if _smtp_available():
        try:
            replies = []
            with imaplib.IMAP4_SSL("imap.gmail.com") as imap:
                imap.login(SENDER_EMAIL, GMAIL_APP_PASSWORD.replace(" ", ""))
                imap.select("INBOX")
                _, msg_nums = imap.search(None, "UNSEEN")
                for num in msg_nums[0].split()[:20]:
                    _, data = imap.fetch(num, "(RFC822)")
                    raw = data[0][1]
                    msg = email_lib.message_from_bytes(raw)
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                                break
                    else:
                        body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

                    replies.append({
                        "message_id": num.decode(),
                        "thread_id": num.decode(),
                        "from_email": msg.get("From", ""),
                        "subject": msg.get("Subject", ""),
                        "date": msg.get("Date", ""),
                        "body": body,
                        "snippet": body[:200],
                    })
                    # Mark as read
                    imap.store(num, "+FLAGS", "\\Seen")
            logger.info(f"📬 Found {len(replies)} new replies via IMAP")
            return replies
        except Exception as e:
            logger.error(f"IMAP read error: {e}")
            return []

    # --- Fallback: Gmail API ---
    if Path(TOKEN_FILE).exists():
        try:
            from googleapiclient.errors import HttpError
            service = _get_gmail_service()
            query = "in:inbox is:unread"
            results = service.users().messages().list(userId="me", q=query, maxResults=50).execute()
            messages = results.get("messages", [])
            replies = []
            for msg_ref in messages:
                msg = service.users().messages().get(userId="me", id=msg_ref["id"], format="full").execute()
                headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
                body = _extract_email_body(msg.get("payload", {}))
                replies.append({
                    "message_id": msg["id"],
                    "thread_id": msg.get("threadId"),
                    "from_email": headers.get("from", ""),
                    "subject": headers.get("subject", ""),
                    "date": headers.get("date", ""),
                    "body": body,
                    "snippet": msg.get("snippet", ""),
                })
                service.users().messages().modify(userId="me", id=msg_ref["id"], body={"removeLabelIds": ["UNREAD"]}).execute()
            logger.info(f"📬 Found {len(replies)} new replies via Gmail API")
            return replies
        except Exception as e:
            logger.error(f"Gmail API read error: {e}")
            return []

    raise FileNotFoundError(
        "Gmail credentials not found at credentials/gmail_credentials.json\n"
        "Please add GMAIL_APP_PASSWORD to .env or run setup_gmail.py"
    )


def _extract_email_body(payload: Dict) -> str:
    if payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
    return ""


# ─────────────────────────────────────────────
#  SEND a reply in an existing thread
# ─────────────────────────────────────────────
def send_reply(
    to_email: str,
    subject: str,
    body: str,
    thread_id: str,
    original_message_id: str,
) -> Optional[Dict]:
    """Send a reply email."""
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    return send_outreach_email(to_email, subject, body, lead_id=thread_id)


# ─────────────────────────────────────────────
#  FIND contact email for a lead
# ─────────────────────────────────────────────
def find_contact_email(lead: Dict) -> Optional[str]:
    import requests
    hunter_key = os.getenv("HUNTERIO_API_KEY")
    website = lead.get("website", "") or lead.get("url", "")
    if not hunter_key or not website:
        return None
    try:
        from urllib.parse import urlparse
        domain = urlparse(website).netloc.replace("www.", "")
        if not domain:
            return None
        resp = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "api_key": hunter_key},
            timeout=10,
        )
        data = resp.json()
        emails = data.get("data", {}).get("emails", [])
        if emails:
            priority_roles = ["ceo", "cto", "founder", "owner", "manager", "director", "hr"]
            for role in priority_roles:
                for entry in emails:
                    if role in entry.get("position", "").lower():
                        return entry.get("value")
            return emails[0].get("value")
    except Exception as e:
        logger.error(f"Hunter.io error: {e}")
    return None


import os
import base64
import pickle
import logging
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List, Optional
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

CREDENTIALS_FILE = os.getenv("GMAIL_CREDENTIALS_FILE", "credentials/gmail_credentials.json")
TOKEN_FILE = os.getenv("GMAIL_TOKEN_FILE", "credentials/gmail_token.pickle")
SENDER_EMAIL = os.getenv("GMAIL_SENDER_EMAIL", "")


def _get_gmail_service():
    """Authenticate and return Gmail API service."""
    creds = None

    # Load existing token
    if Path(TOKEN_FILE).exists():
        with open(TOKEN_FILE, "rb") as token:
            creds = pickle.load(token)

    # Refresh or re-authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path(CREDENTIALS_FILE).exists():
                raise FileNotFoundError(
                    f"Gmail credentials not found at {CREDENTIALS_FILE}\n"
                    "Please follow the setup guide in README.md to create Gmail API credentials."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save token for next run
        Path(TOKEN_FILE).parent.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_FILE, "wb") as token:
            pickle.dump(creds, token)

    return build("gmail", "v1", credentials=creds)


def _create_email_message(
    to_email: str,
    subject: str,
    body: str,
    reply_to_thread_id: Optional[str] = None,
    reply_to_message_id: Optional[str] = None,
) -> Dict:
    """Create a Gmail API message object."""
    message = MIMEMultipart("alternative")
    message["to"] = to_email
    message["from"] = SENDER_EMAIL
    message["subject"] = subject

    if reply_to_message_id:
        message["In-Reply-To"] = reply_to_message_id
        message["References"] = reply_to_message_id

    # Plain text version
    text_part = MIMEText(body, "plain")
    message.attach(text_part)

    # HTML version (nicer formatting)
    html_body = body.replace("\n", "<br>")
    html_part = MIMEText(f"<html><body><p>{html_body}</p></body></html>", "html")
    message.attach(html_part)

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    msg_dict = {"raw": raw}
    if reply_to_thread_id:
        msg_dict["threadId"] = reply_to_thread_id
    return msg_dict


# ─────────────────────────────────────────────
#  SEND outreach email to a lead
# ─────────────────────────────────────────────
def send_outreach_email(
    to_email: str,
    subject: str,
    body: str,
    lead_id: str,
) -> Optional[str]:
    """
    Send an outreach email and return the message ID (for tracking replies).
    Returns message_id on success, None on failure.
    """
    try:
        service = _get_gmail_service()
        message = _create_email_message(to_email, subject, body)
        sent = service.users().messages().send(userId="me", body=message).execute()

        message_id = sent.get("id")
        thread_id = sent.get("threadId")

        logger.info(f"✉️  Email sent to {to_email} | Message ID: {message_id}")
        return {"message_id": message_id, "thread_id": thread_id}

    except HttpError as e:
        logger.error(f"Gmail send error: {e}")
        return None


# ─────────────────────────────────────────────
#  READ replies from inbox
# ─────────────────────────────────────────────
def get_new_replies(after_timestamp: Optional[str] = None) -> List[Dict]:
    """
    Fetch new email replies from Gmail inbox.
    Returns list of reply dicts with: from, subject, body, thread_id, message_id
    """
    try:
        service = _get_gmail_service()

        # Build search query
        query = "in:inbox is:unread"
        if after_timestamp:
            query += f" after:{after_timestamp}"

        results = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=50
        ).execute()

        messages = results.get("messages", [])
        replies = []

        for msg_ref in messages:
            msg = service.users().messages().get(
                userId="me",
                id=msg_ref["id"],
                format="full"
            ).execute()

            headers = msg.get("payload", {}).get("headers", [])
            header_dict = {h["name"].lower(): h["value"] for h in headers}

            # Extract email body
            body = _extract_email_body(msg.get("payload", {}))

            reply = {
                "message_id": msg["id"],
                "thread_id": msg.get("threadId"),
                "from_email": header_dict.get("from", ""),
                "subject": header_dict.get("subject", ""),
                "date": header_dict.get("date", ""),
                "body": body,
                "snippet": msg.get("snippet", ""),
            }
            replies.append(reply)

            # Mark as read
            service.users().messages().modify(
                userId="me",
                id=msg_ref["id"],
                body={"removeLabelIds": ["UNREAD"]}
            ).execute()

        logger.info(f"📬 Found {len(replies)} new replies")
        return replies

    except HttpError as e:
        logger.error(f"Gmail read error: {e}")
        return []


def _extract_email_body(payload: Dict) -> str:
    """Extract plain text body from Gmail message payload."""
    if payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")

    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

    # Try HTML if no plain text
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/html":
            data = part.get("body", {}).get("data", "")
            if data:
                from bs4 import BeautifulSoup
                html = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                return BeautifulSoup(html, "html.parser").get_text()

    return ""


# ─────────────────────────────────────────────
#  SEND a reply in an existing thread
# ─────────────────────────────────────────────
def send_reply(
    to_email: str,
    subject: str,
    body: str,
    thread_id: str,
    original_message_id: str,
) -> Optional[Dict]:
    """Send a reply within an existing email thread."""
    try:
        service = _get_gmail_service()

        # Add "Re:" prefix if not present
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        message = _create_email_message(
            to_email=to_email,
            subject=subject,
            body=body,
            reply_to_thread_id=thread_id,
            reply_to_message_id=original_message_id,
        )

        sent = service.users().messages().send(userId="me", body=message).execute()
        logger.info(f"↩️  Reply sent to {to_email} in thread {thread_id}")
        return {"message_id": sent["id"], "thread_id": sent["threadId"]}

    except HttpError as e:
        logger.error(f"Gmail reply error: {e}")
        return None


# ─────────────────────────────────────────────
#  EXTRACT email address from a lead
# ─────────────────────────────────────────────
def find_contact_email(lead: Dict) -> Optional[str]:
    """
    Try to find a contact email for a lead.
    Uses Hunter.io API if available, otherwise returns None.
    """
    import requests
    hunter_key = os.getenv("HUNTERIO_API_KEY")
    website = lead.get("website", "") or lead.get("url", "")

    if not hunter_key or not website:
        return None

    # Extract domain from URL
    try:
        from urllib.parse import urlparse
        domain = urlparse(website).netloc.replace("www.", "")
        if not domain:
            return None

        resp = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "api_key": hunter_key},
            timeout=10,
        )
        data = resp.json()
        emails = data.get("data", {}).get("emails", [])
        if emails:
            # Prefer decision-maker roles
            priority_roles = ["ceo", "cto", "founder", "owner", "manager", "director", "hr"]
            for role in priority_roles:
                for email_entry in emails:
                    position = email_entry.get("position", "").lower()
                    if role in position:
                        email = email_entry.get("value")
                        logger.info(f"Found email via Hunter.io: {email} ({position})")
                        return email
            # Fall back to first email
            return emails[0].get("value")

    except Exception as e:
        logger.error(f"Hunter.io error: {e}")

    return None
