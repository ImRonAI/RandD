"""Text console harness for the STR QC agent.

Usage:
    python -m strqc_agent.console

Requires GOOGLE_API_KEY; without it, prints a notice and exits 0 so dev
tooling (``make agent``) never crashes.
"""

from __future__ import annotations

import asyncio
import sys

from dotenv import load_dotenv
from strqc_shared.config import get_settings

from .assemble import build_agent
from .context import AgentRunContext


def main() -> int:
    # Settings reads .env itself, but tool deps (strands_google, boto3, openai
    # fallbacks) read os.environ — so load .env into the process env too.
    load_dotenv()
    settings = get_settings()
    if not settings.google_api_key:
        print(
            "GOOGLE_API_KEY is not set — skipping live agent session.\n"
            "Add it to your .env to talk to the Keeper (text mode)."
        )
        return 0

    from strands.experimental.bidi import BidiTextIO

    ctx = AgentRunContext(db_path=settings.strqc_db_path, photo_dir=settings.strqc_photo_dir)
    agent = build_agent(ctx, provider_config={"inference": {"response_modalities": ["TEXT"]}})
    text_io = BidiTextIO(input_prompt="you> ")

    print("the Keeper is listening — Ctrl+C to leave.")
    try:
        asyncio.run(agent.run(inputs=[text_io.input()], outputs=[text_io.output()]))
    except KeyboardInterrupt:
        print("\nsession closed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
