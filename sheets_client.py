from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
PHONE_PATTERN = re.compile(r"^\d{10}$")
PLACEHOLDER_SHEET_ID = "PASTE_YOUR_GOOGLE_SHEET_ID_HERE"


class AppError(Exception):
    """Error carrying an opaque public error code without leaking details."""

    def __init__(self, code: str, detail: str, status_code: int = 502) -> None:
        super().__init__(detail)
        self.code = code
        self.status_code = status_code


def validate_phone_number(raw_number: str) -> str:
    """Validate and return a strict 10-digit phone number string."""
    cleaned = (raw_number or "").strip()
    if not PHONE_PATTERN.fullmatch(cleaned):
        raise ValueError("Please enter a valid 10-digit phone number.")
    return cleaned


def load_config(config_path: Path) -> dict[str, Any]:
    """Load configuration from config.json."""
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AppError("E101", f"Invalid JSON in {config_path.name}: {exc}", 503) from exc


def _parse_credentials_env(raw: str) -> dict[str, Any]:
    """Parse GOOGLE_CREDENTIALS_JSON from raw JSON, quoted JSON, or base64-encoded JSON."""
    cleaned = raw.lstrip("\ufeff").strip()
    if (cleaned.startswith("'") and cleaned.endswith("'")) or (
        cleaned.startswith('"') and cleaned.endswith('"')
    ):
        inner = cleaned[1:-1].strip()
        if inner.startswith("{"):
            cleaned = inner

    if not cleaned.startswith("{"):
        try:
            decoded = base64.b64decode(cleaned, validate=True).decode("utf-8").strip()
            if decoded.startswith("{"):
                cleaned = decoded
        except Exception:
            pass

    return json.loads(cleaned)


def _extract_spreadsheet_id(raw: str) -> str:
    """Extract spreadsheet ID from a raw ID or full Google Sheets URL."""
    cleaned = raw.strip()
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", cleaned)
    return match.group(1) if match else cleaned


def _resolve_sheet_target(base_dir: Path) -> tuple[str, str, dict[str, Any]]:
    """Resolve the active Google Sheet ID and tab name (preferring SECOND_SPREADSHEET_ID)."""
    config = load_config(base_dir / "config.json")

    second_cfg = config.get("second_sheet") or {}
    env_second_id = os.environ.get("SECOND_SPREADSHEET_ID", "").strip()
    env_second_name = os.environ.get("SECOND_SHEET_NAME", "").strip()

    if env_second_id:
        return _extract_spreadsheet_id(env_second_id), env_second_name, config

    if second_cfg.get("spreadsheet_id"):
        return (
            _extract_spreadsheet_id(str(second_cfg["spreadsheet_id"])),
            env_second_name or str(second_cfg.get("sheet_name", "")).strip(),
            config,
        )

    env_id = os.environ.get("SPREADSHEET_ID", "").strip()
    env_name = os.environ.get("SHEET_NAME", "").strip()
    sheet_id = _extract_spreadsheet_id(env_id or str(config.get("spreadsheet_id", "")))
    sheet_name = env_name or str(config.get("sheet_name", "")).strip()
    return sheet_id, sheet_name, config


def get_setup_status(base_dir: Path) -> dict[str, Any]:
    """Return minimal configuration status without exposing sheet internals."""
    try:
        sheet_id, _, config = _resolve_sheet_target(base_dir)
    except AppError:
        return {"configured": False}

    has_sheet_id = bool(sheet_id and sheet_id != PLACEHOLDER_SHEET_ID)

    has_credentials = False
    env_creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "").strip()
    if env_creds_json:
        try:
            _parse_credentials_env(env_creds_json)
            has_credentials = True
        except Exception:
            has_credentials = False
    else:
        creds_rel = str(config.get("credentials_file", "credentials.json")).strip() or "credentials.json"
        creds_path = Path(creds_rel)
        if not creds_path.is_absolute():
            creds_path = base_dir / creds_path
        if creds_path.exists():
            try:
                json.loads(creds_path.read_text(encoding="utf-8"))
                has_credentials = True
            except (OSError, json.JSONDecodeError):
                has_credentials = False

    return {"configured": has_sheet_id and has_credentials}


def _matches_us_or_ten_digit(cell_value: str, target: str) -> bool:
    """Match 10-digit target or 11-digit '1' + target, ignoring formatting like +1, spaces, or dashes."""
    digits = re.sub(r"\D", "", cell_value)
    if digits == target:
        return True
    return len(digits) == 11 and digits.startswith("1") and digits[1:] == target


def check_column_a_duplicate(rows: list[list[Any]], phone_number: str) -> bool:
    """Return True if phone_number exists in Column A (10-digit or '1' + 10-digit)."""
    target = validate_phone_number(phone_number)
    if not rows:
        return False

    first_col_cell = str(rows[0][0]).strip() if rows[0] else ""
    first_row_is_data = bool(re.fullmatch(r"\d{10,11}", re.sub(r"\D", "", first_col_cell)))
    data_rows = rows if first_row_is_data else rows[1:]

    for row in data_rows:
        if row and _matches_us_or_ten_digit(str(row[0] or ""), target):
            return True
    return False


class GoogleSheetService:
    """Client for checking phone numbers against a private Google Sheet."""

    def __init__(self, base_dir: Path, cache_ttl_seconds: float = 20.0) -> None:
        self.base_dir = base_dir
        self.cache_ttl_seconds = cache_ttl_seconds
        self._lock = threading.Lock()
        self._cached_rows: list[list[Any]] | None = None
        self._cache_time: float = 0.0

    def _get_target_and_credentials(self) -> tuple[str, str, Credentials]:
        sheet_id, sheet_name, config = _resolve_sheet_target(self.base_dir)
        if not sheet_id or sheet_id == PLACEHOLDER_SHEET_ID:
            raise AppError("E101", "Missing or placeholder spreadsheet ID.", 503)

        env_creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "").strip()
        if env_creds_json:
            try:
                info = _parse_credentials_env(env_creds_json)
                creds = Credentials.from_service_account_info(info, scopes=SCOPES)
                return sheet_id, sheet_name, creds
            except Exception as exc:
                raise AppError("E102", f"Invalid GOOGLE_CREDENTIALS_JSON: {exc}", 503) from exc

        creds_rel = str(config.get("credentials_file", "credentials.json")).strip() or "credentials.json"
        creds_path = Path(creds_rel)
        if not creds_path.is_absolute():
            creds_path = self.base_dir / creds_path

        if not creds_path.exists():
            raise AppError("E102", f"Credentials file not found: {creds_path}", 503)

        try:
            creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
        except Exception as exc:
            raise AppError("E102", f"Invalid credentials file: {exc}", 503) from exc
        return sheet_id, sheet_name, creds

    def fetch_rows(self, force_refresh: bool = False) -> list[list[Any]]:
        """Fetch Column A values from the configured Google Sheet using a short-lived cache."""
        with self._lock:
            now = time.monotonic()
            if (
                not force_refresh
                and self._cached_rows is not None
                and (now - self._cache_time) < self.cache_ttl_seconds
            ):
                return self._cached_rows

        sheet_id, sheet_name, creds = self._get_target_and_credentials()
        service = build("sheets", "v4", credentials=creds, cache_discovery=False)

        try:
            target_tab = sheet_name.strip()
            if not target_tab:
                meta = (
                    service.spreadsheets()
                    .get(spreadsheetId=sheet_id, fields="sheets(properties(title))")
                    .execute()
                )
                sheets = meta.get("sheets", [])
                if not sheets:
                    rows: list[list[Any]] = []
                    with self._lock:
                        self._cached_rows = rows
                        self._cache_time = time.monotonic()
                    return rows
                target_tab = sheets[0]["properties"]["title"]

            result = (
                service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=sheet_id,
                    range=f"'{target_tab}'!A:A",
                    valueRenderOption="FORMATTED_VALUE",
                )
                .execute()
            )
            rows = result.get("values", [])
        except HttpError as exc:
            code = getattr(exc.resp, "status", 502)
            if code == 403:
                raise AppError("E103", "Google Sheets access denied (403).", 502) from exc
            if code == 404:
                raise AppError("E104", "Google Sheet not found (404).", 502) from exc
            if code == 400:
                raise AppError("E105", "Invalid sheet tab/range (400).", 502) from exc
            raise AppError("E106", f"Google Sheets API error ({code}).", 502) from exc

        with self._lock:
            self._cached_rows = rows
            self._cache_time = time.monotonic()

        return rows

    def check_phone(self, phone_number: str, force_refresh: bool = False) -> dict[str, Any]:
        """Validate phone_number and return whether it is a duplicate."""
        validated = validate_phone_number(phone_number)
        rows = self.fetch_rows(force_refresh=force_refresh)
        return {
            "query": validated,
            "is_duplicate": check_column_a_duplicate(rows, validated),
        }
