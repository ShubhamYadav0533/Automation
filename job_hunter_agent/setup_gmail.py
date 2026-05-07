"""
Run this once to authorize Gmail access.
It will open a browser — log in with shubhamyadav0533@gmail.com and allow access.
The token will be saved to credentials/gmail_token.pickle
"""
import os
import pickle
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

CREDS_FILE = Path("credentials/gmail_credentials.json")
TOKEN_FILE = Path("credentials/gmail_token.pickle")

def setup():
    creds = None
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    print("\n✅ Gmail authorized successfully!")
    print(f"   Token saved to: {TOKEN_FILE}")
    print("\nYou can now run: python agent.py")

if __name__ == "__main__":
    setup()
