#!/usr/bin/env python3
"""DAH-127 SQLite-to-PostgreSQL import command.

Configuration is environment-only so credentials and tenant mappings never
appear in shell history. See docs/development/DAH_127_IMPORT_RUNBOOK.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.vantage.importer import ImportContractError, run_from_environment


def main() -> int:
    try:
        result = run_from_environment()
    except ImportContractError as error:
        print(json.dumps({"status": "rejected", "error": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    except Exception as error:  # the run ledger contains the durable detail
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps({"status": "ok", **result}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
