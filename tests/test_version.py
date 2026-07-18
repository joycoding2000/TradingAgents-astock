"""Application version consistency tests."""

from pathlib import Path
import re

from tradingagents.version import __version__


def test_application_version_matches_pyproject() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    content = pyproject.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)

    assert match is not None
    assert __version__ == match.group(1)
