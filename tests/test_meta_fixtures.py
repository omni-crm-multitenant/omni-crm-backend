import json
from pathlib import Path

import pytest

from app.services.meta_fixtures import parse_fixture


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "meta"


@pytest.mark.parametrize("fixture_path", sorted(FIXTURE_DIR.glob("*.json")))
def test_meta_fixture_matches_expected_shape(fixture_path: Path) -> None:
    if fixture_path.name.endswith(".expected.json"):
        pytest.skip("expectation sibling")
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    expected_path = fixture_path.with_name(f"{fixture_path.stem}.expected.json")
    actual = parse_fixture(fixture["fixture_kind"], fixture["payload"])
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    assert actual == expected, f"fixture contract mismatch: {fixture_path.name}"
