"""RandD Live FastAPI backend."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env first, then fall back to the repo-root .env (both
# gitignored) so provider credentials (GOOGLE_API_KEY, OPENAI_*, AWS_*) are
# set within the project without ever being committed.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

# botocore only resolves the default region from AWS_DEFAULT_REGION; bridge it
# from AWS_REGION so every boto3 client (Bedrock KB memory, Nova) gets a region.
if os.getenv("AWS_REGION") and not os.getenv("AWS_DEFAULT_REGION"):
    os.environ["AWS_DEFAULT_REGION"] = os.environ["AWS_REGION"]

# Slack uses rotating tokens (~12h expiry): refresh the bot token at startup so
# the slack tools always initialize with a live token.
from app.slack_token import ensure_fresh_bot_token  # noqa: E402

ensure_fresh_bot_token()
