from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
PHONE_PATTERN = re.compile(r"^\d{10}$")
PLACEHOLDER_SHEET_ID = "PASTE_YOUR_GOOGLE_SHEET_ID_HERE"


class ConfigurationError(Exception):
    """Raised when config.json or credentials.json is missing or incomplete."""


def validate_phone_number(raw_number: str) -> str:
    """Validate and return a strict 10-digit phone number string."""
    cleaned = (raw_number or "").strip()
    if not PHONE_PATTERN.fullmatch(cleaned):
        raise ValueError("Please enter a valid 10-digit phone number (e.g. 8319754818).")
    return cleaned


def load_config(config_path: Path) -> dict[str, Any]:
    """Load configuration from config.json."""
    if not config_path.exists():
        raise ConfigurationError(f"Missing configuration file: {config_path.name}")

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"Invalid JSON in {config_path.name}: {exc}") from exc

    return data


def _resolve_runtime_config(base_dir: Path) -> dict[str, Any]:
    """Merge config.json (if present) with environment variable overrides."""
    config_path = base_dir / "config.json"
    config: dict[str, Any] = {}
    if config_path.exists():
        config = load_config(config_path)

    env_sheet_id = os.environ.get("SPREADSHEET_ID", "").strip()
    env_sheet_name = os.environ.get("SHEET_NAME", "").strip()
    if env_sheet_id:
        config["spreadsheet_id"] = env_sheet_id
    if env_sheet_name:
        config["sheet_name"] = env_sheet_name
    return config


def get_setup_status(base_dir: Path) -> dict[str, Any]:
    """Return current configuration status without failing."""
    config_path = base_dir / "config.json"
    env_creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "").strip()

    status: dict[str, Any] = {
        "configured": False,
        "has_config": config_path.exists() or bool(os.environ.get("SPREADSHEET_ID", "").strip()),
        "has_credentials": False,
        "has_spreadsheet_id": False,
        "spreadsheet_id": "",
        "sheet_name": "Sheet1",
        "service_account_email": None,
        "message": "",
    }

    try:
        config = _resolve_runtime_config(base_dir)
    except ConfigurationError as exc:
        status["message"] = str(exc)
        return status

    spreadsheet_id = str(config.get("spreadsheet_id", "")).strip()
    sheet_name = str(config.get("sheet_name", "Sheet1")).strip() or "Sheet1"
    status["spreadsheet_id"] = spreadsheet_id
    status["sheet_name"] = sheet_name
    status["has_spreadsheet_id"] = bool(spreadsheet_id and spreadsheet_id != PLACEHOLDER_SHEET_ID)

    if env_creds_json:
        try:
            creds_data = json.loads(env_creds_json)
            status["has_credentials"] = True
            status["service_account_email"] = creds_data.get("client_email")
        except json.JSONDecodeError:
            status["has_credentials"] = False
    else:
        creds_rel = str(config.get("credentials_file", "credentials.json")).strip() or "credentials.json"
        creds_path = Path(creds_rel)
        if not creds_path.is_absolute():
            creds_path = base_dir / creds_path
        if creds_path.exists():
            try:
                creds_data = json.loads(creds_path.read_text(encoding="utf-8"))
                status["has_credentials"] = True
                status["service_account_email"] = creds_data.get("client_email")
            except (OSError, json.JSONDecodeError):
                status["has_credentials"] = False

    if not status["has_credentials"]:
        status["message"] = "Service account credentials not found or invalid."
    elif not status["has_spreadsheet_id"]:
        status["message"] = "Please set your Google Sheet ID."
    else:
        status["configured"] = True
        status["message"] = "Connected configuration ready."

    return status


def resolve_target_columns(
    headers: list[str],
    original_name: str = "Phone (Original)",
    show_name: str = "Phone (Show)",
) -> tuple[int, int, str, str]:
    """Find indices for Phone (Original) and Phone (Show), falling back to D (3) and E (4)."""
    normalized = [h.strip() for h in headers]

    orig_idx = normalized.index(original_name) if original_name in normalized else 3
    show_idx = normalized.index(show_name) if show_name in normalized else 4

    orig_label = headers[orig_idx].strip() if orig_idx < len(headers) and headers[orig_idx].strip() else original_name
    show_label = headers[show_idx].strip() if show_idx < len(headers) and headers[show_idx].strip() else show_name

    return orig_idx, show_idx, orig_label, show_label


def search_rows(
    rows: list[list[Any]],
    phone_number: str,
    original_col_name: str = "Phone (Original)",
    show_col_name: str = "Phone (Show)",
) -> dict[str, Any]:
    """Search sheet rows for an exact 10-digit match in Phone (Original) or Phone (Show)."""
    target = validate_phone_number(phone_number)

    if not rows:
        return {
            "query": target,
            "headers": [],
            "matches": [],
            "total_rows_searched": 0,
            "target_columns": [original_col_name, show_col_name],
        }

    raw_headers = [str(cell) for cell in rows[0]]
    max_width = max(len(raw_headers), *(len(r) for r in rows[1:])) if len(rows) > 1 else len(raw_headers)

    headers = list(raw_headers)
    for col_idx in range(len(headers), max_width):
        headers.append(f"Column {col_idx + 1}")

    orig_idx, show_idx, orig_label, show_label = resolve_target_columns(
        headers, original_col_name, show_col_name
    )

    matches: list[dict[str, Any]] = []
    data_rows = rows[1:]

    for offset, row in enumerate(data_rows):
        sheet_row_number = offset + 2
        row_values = [str(cell) if cell is not None else "" for cell in row]
        if len(row_values) < max_width:
            row_values.extend([""] * (max_width - len(row_values)))

        matched_columns: list[str] = []
        matched_indices: list[int] = []

        for col_idx, col_label in ((orig_idx, orig_label), (show_idx, show_label)):
            if col_idx < len(row_values) and col_idx not in matched_indices and row_values[col_idx].strip() == target:
                matched_columns.append(col_label)
                matched_indices.append(col_idx)

        if matched_columns:
            matches.append(
                {
                    "row_number": sheet_row_number,
                    "matched_columns": matched_columns,
                    "matched_indices": matched_indices,
                    "values": row_values,
                }
            )

    return {
        "query": target,
        "headers": headers,
        "matches": matches,
        "total_rows_searched": len(data_rows),
        "target_columns": [orig_label, show_label],
    }


class GoogleSheetService:
    """Client for fetching rows from a private Google Sheet via Service Account."""

    def __init__(self, base_dir: Path, cache_ttl_seconds: float = 20.0) -> None:
        self.base_dir = base_dir
        self.cache_ttl_seconds = cache_ttl_seconds
        self._lock = threading.Lock()
        self._cached_rows: list[list[Any]] | None = None
        self._cached_config: dict[str, Any] | None = None
        self._cache_time: float = 0.0

    def _get_config_and_credentials(self) -> tuple[dict[str, Any], Credentials]:
        config = _resolve_runtime_config(self.base_dir)
        spreadsheet_id = str(config.get("spreadsheet_id", "")).strip()
        if not spreadsheet_id or spreadsheet_id == PLACEHOLDER_SHEET_ID:
            raise ConfigurationError("Please set a valid 'spreadsheet_id' in config.json or SPREADSHEET_ID env var.")

        env_creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "").strip()
        if env_creds_json:
            try:
                info = json.loads(env_creds_json)
            except json.JSONDecodeError as exc:
                raise ConfigurationError(f"Invalid JSON in GOOGLE_CREDENTIALS_JSON: {exc}") from exc
            creds = Credentials.from_service_account_info(info, scopes=SCOPES)
            return config, creds

        creds_rel = str(config.get("credentials_file", "credentials.json")).strip() or "credentials.json"
        creds_path = Path(creds_rel)
        if not creds_path.is_absolute():
            creds_path = self.base_dir / creds_path

        if not creds_path.exists():
            raise ConfigurationError(
                f"Credentials file '{creds_path.name}' not found. Place your Google Service Account JSON in {self.base_dir} or set GOOGLE_CREDENTIALS_JSON."
            )

        creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
        return config, creds

    def fetch_rows(self, force_refresh: bool = False) -> tuple[list[list[Any]], dict[str, Any]]:
        """Fetch all rows from the configured sheet tab, using a short-lived cache."""
        with self._lock:
            now = time.monotonic()
            if (
                not force_refresh
                and self._cached_rows is not None
                and self._cached_config is not None
                and (now - self._cache_time) < self.cache_ttl_seconds
            ):
                return self._cached_rows, self._cached_config

        config, creds = self._get_config_and_credentials()
        spreadsheet_id = str(config["spreadsheet_id"]).strip()
        sheet_name = str(config.get("sheet_name", "Sheet1")).strip() or "Sheet1"

        service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        range_name = f"'{sheet_name}'"
        result = (
            service.spreadsheets()
            .values()
            .get(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueRenderOption="FORMATTED_VALUE",
            )
            .execute()
        )
        rows = result.get("values", [])

        with self._lock:
            self._cached_rows = rows
            self._cached_config = config
            self._cache_time = time.monotonic()

        return rows, config

    def search_phone(self, phone_number: str, force_refresh: bool = False) -> dict[str, Any]:
        """Validate phone_number, fetch sheet rows, and return matching rows."""
        validated = validate_phone_number(phone_number)
        rows, config = self.fetch_rows(force_refresh=force_refresh)
        columns_cfg = config.get("columns", {})
        orig_name = str(columns_cfg.get("original", "Phone (Original)")).strip() or "Phone (Original)"
        show_name = str(columns_cfg.get("show", "Phone (Show)")).strip() or "Phone (Show)"
        return search_rows(rows, validated, original_col_name=orig_name, show_col_name=show_name)
