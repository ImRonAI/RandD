"""Rotating Slack bot-token refresh (workspace has token rotation enabled).

The xoxe.xoxb bot token expires ~12h after issue. ``ensure_fresh_bot_token``
refreshes it through ``oauth.v2.access`` (grant_type=refresh_token) using the
client credentials, updates the process env, and rewrites .env so restarts
pick up the current pair. Call it at backend startup (and it's cheap enough
to call again before long-running sessions).
"""

import json
import logging
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

_ENV_PATHS = [
    Path(__file__).resolve().parent.parent / ".env",
    Path(__file__).resolve().parent.parent.parent / ".env",
]


def ensure_fresh_bot_token() -> bool:
    """Refresh SLACK_BOT_TOKEN via its refresh token. Returns True on success."""
    refresh = os.getenv("SLACK_BOT_REFRESH_TOKEN")
    client_id = os.getenv("SLACK_CLIENT_ID")
    client_secret = os.getenv("SLACK_CLIENT_SECRET")
    if not (refresh and client_id and client_secret):
        return False

    data = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh,
        }
    ).encode()
    try:
        resp = json.load(
            urllib.request.urlopen(
                urllib.request.Request("https://slack.com/api/oauth.v2.access", data=data),
                timeout=15,
            )
        )
    except Exception as exc:
        logger.warning("slack token refresh failed: %s", exc)
        return False
    if not resp.get("ok"):
        logger.warning("slack token refresh rejected: %s", resp.get("error"))
        return False

    new_token = resp["access_token"]
    new_refresh = resp.get("refresh_token", refresh)
    os.environ["SLACK_BOT_TOKEN"] = new_token
    os.environ["SLACK_BOT_REFRESH_TOKEN"] = new_refresh

    for env_path in _ENV_PATHS:
        if not env_path.exists():
            continue
        text = env_path.read_text()
        if "SLACK_BOT_TOKEN=" not in text:
            continue
        text = re.sub(r"(?m)^SLACK_BOT_TOKEN=.*$", f"SLACK_BOT_TOKEN={new_token}", text)
        text = re.sub(
            r"(?m)^SLACK_BOT_REFRESH_TOKEN=.*$",
            f"SLACK_BOT_REFRESH_TOKEN={new_refresh}",
            text,
        )
        env_path.write_text(text)
    logger.info("slack bot token refreshed (expires_in=%s)", resp.get("expires_in"))
    return True
