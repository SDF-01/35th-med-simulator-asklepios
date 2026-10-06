#!/usr/bin/env python3
"""Compact, content-addressed, cross-platform test workspace helpers."""
from __future__ import annotations

import hashlib
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

WORKSPACE_PROFILE = 'CONTENT_ADDRESSED_COMPACT_TEST_WORKSPACE_V1'
WINDOWS_PATH_BUDGET = 240


def compact_case_name(case_id: str, prefix: str = 'c') -> str:
    digest = hashlib.sha256(case_id.encode('utf-8')).hexdigest()[:16]
    return f'{prefix}-{digest}'


def preferred_temp_root() -> Path | None:
    value = os.environ.get('RUNNER_TEMP')
    if not value:
        return None
    path = Path(value)
    return path if path.is_dir() else None


def assert_path_budget(root: Path, relative_suffix: str, budget: int = WINDOWS_PATH_BUDGET) -> None:
    modeled = str(root / relative_suffix)
    if len(modeled) > budget:
        raise RuntimeError(f'test workspace path budget exceeded:{len(modeled)}:{budget}')


@contextmanager
def temporary_workspace(prefix: str = 'ask-') -> Iterator[Path]:
    base = preferred_temp_root()
    with tempfile.TemporaryDirectory(prefix=prefix, dir=str(base) if base else None) as temporary:
        root = Path(temporary)
        assert_path_budget(root, 'c-0123456789abcdef/repo/public/data/scenario_library/stakeholder-dashboard.json')
        yield root
