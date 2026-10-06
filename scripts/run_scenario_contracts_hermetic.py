#!/usr/bin/env python3
"""Compatibility wrapper for the canonical scenario-contract gate.

The release has one implementation: ``run_scenario_contract_gate.py``.  This
entry point is retained only so older local commands fail over to that same
implementation instead of maintaining a second release sequence.
"""
from __future__ import annotations

import sys

from run_scenario_contract_gate import main


def translated_argv(argv: list[str]) -> list[str]:
    result = list(argv)
    for index, value in enumerate(result):
        if value == "--keep-workspace":
            result[index] = "--keep-sandbox"
    if "--mode" not in result:
        result.extend(["--mode", "check"])
    return result


if __name__ == "__main__":
    sys.argv = translated_argv(sys.argv)
    raise SystemExit(main())
