import sqlite3
from pathlib import Path

import pytest

from gitlab_admin.browse import cache


@pytest.fixture
def tmp_cache(tmp_path: Path) -> Path:
    return tmp_path / "browse.sqlite"


@pytest.fixture
def initialized_conn(tmp_cache: Path) -> sqlite3.Connection:
    with cache.connect(tmp_cache) as conn:
        cache.init_schema(conn)
        yield conn


@pytest.fixture
def fixture_db() -> Path:
    return Path(__file__).parent / "fixtures" / "snapshot.sqlite"
