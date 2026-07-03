"""RandD Live FastAPI backend."""

from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env (gitignored) so AWS/Google credentials are set within the
# project without ever being committed.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
