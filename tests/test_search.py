from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import create_app
from sheets_client import AppError, check_column_a_duplicate, validate_phone_number

SAMPLE_ROWS = [
    ["Phone"],
    ["19012409963"],
    ["8319754818"],
    ["+1 (555) 123-4567"],
]


def test_validate_phone_number_accepts_10_digits():
    assert validate_phone_number("8319754818") == "8319754818"
    assert validate_phone_number("  9012409963 ") == "9012409963"


@pytest.mark.parametrize("bad_input", ["", "123", "12345678901", "+918319754818", "83197-54818", "831975481a"])
def test_validate_phone_number_rejects_invalid(bad_input: str):
    with pytest.raises(ValueError):
        validate_phone_number(bad_input)


def test_check_column_a_duplicate_matches_us_and_ten_digit_formats():
    assert check_column_a_duplicate(SAMPLE_ROWS, "9012409963") is True
    assert check_column_a_duplicate(SAMPLE_ROWS, "8319754818") is True
    assert check_column_a_duplicate(SAMPLE_ROWS, "5551234567") is True
    assert check_column_a_duplicate(SAMPLE_ROWS, "7000000000") is False


def test_check_column_a_duplicate_without_header_row():
    rows_no_header = [["19012409963"], ["18005551234"]]
    assert check_column_a_duplicate(rows_no_header, "9012409963") is True
    assert check_column_a_duplicate(rows_no_header, "8005551234") is True
    assert check_column_a_duplicate(rows_no_header, "9999999999") is False


class FakeSheetService:
    def check_phone(self, phone_number: str, force_refresh: bool = False):
        validated = validate_phone_number(phone_number)
        return {
            "query": validated,
            "is_duplicate": check_column_a_duplicate(SAMPLE_ROWS, validated),
        }

    def fetch_rows(self, force_refresh: bool = False):
        return SAMPLE_ROWS


class FailingSheetService:
    def check_phone(self, phone_number: str, force_refresh: bool = False):
        raise AppError("E103", "Access denied details hidden from user", 502)

    def fetch_rows(self, force_refresh: bool = False):
        raise AppError("E103", "Access denied details hidden from user", 502)


def test_api_search_returns_duplicate_and_clear(tmp_path: Path):
    app = create_app(sheet_service=FakeSheetService(), base_dir=tmp_path)
    client = app.test_client()

    dup_resp = client.get("/api/search?phone=9012409963")
    assert dup_resp.status_code == 200
    assert dup_resp.get_json() == {"query": "9012409963", "is_duplicate": True}

    ok_resp = client.get("/api/search?phone=7000000000")
    assert ok_resp.status_code == 200
    assert ok_resp.get_json() == {"query": "7000000000", "is_duplicate": False}


def test_api_search_invalid_number(tmp_path: Path):
    app = create_app(sheet_service=FakeSheetService(), base_dir=tmp_path)
    client = app.test_client()

    resp = client.get("/api/search?phone=12345")
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_api_search_hides_internal_error_details_with_code(tmp_path: Path):
    app = create_app(sheet_service=FailingSheetService(), base_dir=tmp_path)
    client = app.test_client()

    resp = client.get("/api/search?phone=9012409963")
    assert resp.status_code == 502
    data = resp.get_json()
    assert data["error_code"] == "E103"
    assert "E103" in data["error"]
    assert "Access denied" not in data["error"]


def test_api_status_minimal_configured(tmp_path: Path):
    (tmp_path / "config.json").write_text(
        json.dumps({"spreadsheet_id": "abc123", "credentials_file": "credentials.json"}),
        encoding="utf-8",
    )
    (tmp_path / "credentials.json").write_text(
        json.dumps({"client_email": "bot@example.iam.gserviceaccount.com"}),
        encoding="utf-8",
    )
    app = create_app(sheet_service=FakeSheetService(), base_dir=tmp_path)
    client = app.test_client()

    resp = client.get("/api/status")
    assert resp.status_code == 200
    assert resp.get_json() == {"configured": True}
