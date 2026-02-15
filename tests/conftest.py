"""テスト共通 fixture"""

from __future__ import annotations

from pathlib import Path

import pytest

# プロジェクトルート
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# パス定数
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"
RULES_DIR = PROJECT_ROOT / "src" / "rules"
LEDGER_MAPPING_YML = RULES_DIR / "ledger_mapping.yml"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def rules_dir() -> Path:
    return RULES_DIR


@pytest.fixture
def ledger_mapping_yml() -> Path:
    return LEDGER_MAPPING_YML
