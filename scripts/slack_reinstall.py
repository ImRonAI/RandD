"""One-shot Slack reinstall via OAuth v2 + PKCE (token rotation compatible).

The app's "Reinstall" button disappears once token rotation is enabled, so this
script drives the OAuth consent flow manually:

    python scripts/slack_reinstall.py <CLIENT_ID> [CLIENT_SECRET]

1. Prints the authorize URL (all bot scopes declared in the app manifest).
2. You open it, approve, and land on https://cato-labs.com/redirect?code=...
   (the page itself may 404 — that's fine, copy the full URL from the bar).
3. Paste that URL (or just the code) back here.
4. The script exchanges it (PKCE; secret optional but used when provided),
   prints the new grant's scopes, and writes SLACK_BOT_TOKEN /
   SLACK_BOT_REFRESH_TOKEN into .env.
"""

import base64
import hashlib
import json
import os
import pathlib
import secrets
import sys
import urllib.parse
import urllib.request

REDIRECT_URI = "https://cato-labs.com/redirect"
ENV_PATH = pathlib.Path(__file__).resolve().parent.parent / ".env"
SCOPES_CACHE = pathlib.Path("/tmp/slack_bot_scopes.txt")
FALLBACK_SCOPES = "chat:write,chat:write.public,files:write,files:read,channels:read,channels:join,commands,assistant:write,incoming-webhook"


def call(method: str, **params) -> dict:
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(f"https://slack.com/api/{method}", data=data)
    return json.load(urllib.request.urlopen(req))


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: python scripts/slack_reinstall.py <CLIENT_ID> [CLIENT_SECRET]")
    client_id = sys.argv[1].strip()
    client_secret = sys.argv[2].strip() if len(sys.argv) > 2 else None

    scopes = SCOPES_CACHE.read_text().strip() if SCOPES_CACHE.exists() else FALLBACK_SCOPES

    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    state = secrets.token_urlsafe(16)

    authorize = "https://slack.com/oauth/v2/authorize?" + urllib.parse.urlencode(
        {
            "client_id": client_id,
            "scope": scopes,
            "redirect_uri": REDIRECT_URI,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    print("\n1) Open and approve:\n")
    print(authorize)
    print("\n2) Paste the URL you were redirected to (or just the code= value):")
    raw = input("> ").strip()
    code = raw
    if "code=" in raw:
        code = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query)["code"][0]

    params = {
        "client_id": client_id,
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier,
    }
    if client_secret:
        params["client_secret"] = client_secret
    resp = call("oauth.v2.access", **params)
    if not resp.get("ok"):
        sys.exit(f"exchange failed: {resp.get('error')}")

    token = resp["access_token"]
    refresh = resp.get("refresh_token", "")
    print("\ngranted scopes:", resp.get("scope"))
    print("bot token:", token[:24] + "...")

    env = ENV_PATH.read_text().splitlines()
    out = []
    for line in env:
        if line.startswith("SLACK_BOT_TOKEN="):
            out.append(f"SLACK_BOT_TOKEN={token}")
        elif line.startswith("SLACK_BOT_REFRESH_TOKEN="):
            out.append(f"SLACK_BOT_REFRESH_TOKEN={refresh}")
        else:
            out.append(line)
    ENV_PATH.write_text("\n".join(out) + "\n")
    print(f"\n.env updated. Verify with: python scripts/slack_smoke_test.py")


if __name__ == "__main__":
    main()
