from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import create_app
from sheets_client import ConfigurationError, search_column_a_rows, search_rows, validate_phone_number

SAMPLE_ROWS = [
    ["ID", "Name", "City", "Phone (Original)", "Phone (Show)", "Notes"],
    ["1", "Alice", "Delhi", "8319754818", "9999999999", "First row"],
    ["2", "Bob", "Mumbai", "1111111111", "8319754818", "Matched in Show"],
    ["3", "Charlie", "Pune", "8319754818", "8319754818", "Matched in both"],
    ["4", "Diana", "Jaipur", "+918319754818", "08319754818", "Should not match strict 10-digit"],
    ["5", "Eve", "Bhopal", "831975481", "83197548180", "Wrong length"],
]


def test_validate_phone_number_accepts_10_digits():
    assert validate_phone_number("8319754818") == "8319754818"
    assert validate_phone_number("  8319754818 ") == "8319754818"


@pytest.mark.parametrize("bad_input", ["", "123", "12345678901", "+918319754818", "83197-54818", "831975481a"])
def test_validate_phone_number_rejects_invalid(bad_input: str):
    with pytest.raises(ValueError):
        validate_phone_number(bad_input)


def test_search_rows_returns_all_matching_rows_strictly():
    result = search_rows(SAMPLE_ROWS, "8319754818")

    assert result["query"] == "8319754818"
    assert result["total_rows_searched"] == 5
    assert result["headers"] == SAMPLE_ROWS[0]
    assert len(result["matches"]) == 3

    row_numbers = [m["row_number"] for m in result["matches"]]
    assert row_numbers == [2, 3, 4]

    assert result["matches"][0]["matched_columns"] == ["Phone (Original)"]
    assert result["matches"][1]["matched_columns"] == ["Phone (Show)"]
    assert result["matches"][2]["matched_columns"] == ["Phone (Original)", "Phone (Show)"]


def test_search_rows_handles_no_matches():
    result = search_rows(SAMPLE_ROWS, "7000000000")
    assert result["matches"] == []
    assert result["total_rows_searched"] == 5


def test_search_rows_pads_short_rows_and_falls_back_to_d_e():
    rows_no_matching_headers = [
        ["A", "B", "C", "Col D", "Col E"],
        ["1", "Test", "City", "8319754818"],
    ]
    result = search_rows(rows_no_matching_headers, "8319754818")
    assert len(result["matches"]) == 1
    assert result["matches"][0]["values"] == ["1", "Test", "City", "8319754818", ""]


class FakeSheetService:
    def search_phone(self, phone_number: str):
        return search_rows(SAMPLE_ROWS, phone_number)


class UnconfiguredSheetService:
    def search_phone(self, phone_number: str):
        raise ConfigurationError("Missing credentials")


def _auth_headers(client, password: str = "inhouse101") -> dict[str, str]:
    resp = client.post("/api/auth", json={"password": password})
    assert resp.status_code == 200
    return {"X-Auth-Token": resp.get_json()["token"]}


def test_api_auth_rejects_wrong_password(tmp_path: Path):
    app = create_app(sheet_service=FakeSheetService(), base_dir=tmp_path)
    client = app.test_client()

    resp = client.post("/api/auth", json={"password": "wrong"})
    assert resp.status_code == 401


def test_api_search_requires_auth(tmp_path: Path):
    app = create_app(sheet_service=FakeSheetService(), base_dir=tmp_path)
    client = app.test_client()

    assert client.get("/api/search?phone=8319754818").status_code == 401
    assert client.post("/api/refresh").status_code == 401


def test_api_search_full_password_returns_rows(tmp_path: Path):
    app = create_app(sheet_service=FakeSheetService(), base_dir=tmp_path)
    client = app.test_client()
    headers = _auth_headers(client, "inhouse101")

    resp = client.get("/api/search?phone=8319754818", headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["mode"] == "full"
    assert len(data["matches"]) == 3


def test_api_search_masked_password_hides_rows(tmp_path: Path):
    app = create_app(sheet_service=FakeSheetService(), base_dir=tmp_path)
    client = app.test_client()
    headers = _auth_headers(client, "cgm2026")

    dup_resp = client.get("/api/search?phone=8319754818", headers=headers)
    assert dup_resp.status_code == 200
    dup_data = dup_resp.get_json()
    assert dup_data == {"query": "8319754818", "mode": "masked", "is_duplicate": True}

    ok_resp = client.get("/api/search?phone=7000000000", headers=headers)
    assert ok_resp.status_code == 200
    ok_data = ok_resp.get_json()
    assert ok_data == {"query": "7000000000", "mode": "masked", "is_duplicate": False}


def test_api_search_invalid_number(tmp_path: Path):
    app = create_app(sheet_service=FakeSheetService(), base_dir=tmp_path)
    client = app.test_client()
    headers = _auth_headers(client, "inhouse101")

    resp = client.get("/api/search?phone=12345", headers=headers)
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_api_search_unconfigured_returns_503(tmp_path: Path):
    app = create_app(sheet_service=UnconfiguredSheetService(), base_dir=tmp_path)
    client = app.test_client()
    headers = _auth_headers(client, "inhouse101")

    resp = client.get("/api/search?phone=8319754818", headers=headers)
    assert resp.status_code == 503
    assert resp.get_json()["needs_setup"] is True


def test_api_status_reflects_config(tmp_path: Path):
    (tmp_path / "config.json").write_text(
        json.dumps({"spreadsheet_id": "abc123", "sheet_name": "Leads", "credentials_file": "credentials.json"}),
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
    data = resp.get_json()
    assert data["configured"] is True
    assert data["sheet_name"] == "Leads"
    assert data["service_account_email"] == "bot@example.iam.gserviceaccount.com"


def test_search_column_a_matches_leading_1_and_exact_10_digits():
    rows_with_header = [
        ["Phone", "Status"],
        ["19012409963", "Used"],
        ["9012409963", "Also Used"],
        ["+1 (901) 240-9963", "Formatted US"],
        ["29012409963", "Different prefix"],
    ]
    res = search_column_a_rows(rows_with_header, "9012409963")
    assert res["total_rows_searched"] == 4
    assert [m["row_number"] for m in res["matches"]] == [2, 3, 4]
    assert res["matches"][0]["matched_indices"] == [0]


def test_search_column_a_without_header_row():
    rows_no_header = [
        ["19012409963"],
        ["18005551234"],
    ]
    res = search_column_a_rows(rows_no_header, "9012409963")
    assert res["total_rows_searched"] == 2
    assert res["headers"] == ["Phone"]
    assert [m["row_number"] for m in res["matches"]] == [1]
