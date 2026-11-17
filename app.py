from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request
from googleapiclient.errors import HttpError
from itsdangerous import BadSignature, URLSafeSerializer

from sheets_client import ConfigurationError, GoogleSheetService, get_setup_status

BASE_DIR = Path(__file__).resolve().parent


def _build_serializer() -> URLSafeSerializer:
    """Create a deterministic token serializer shared across Gunicorn workers."""
    seed = (
        os.environ.get("FLASK_SECRET_KEY")
        or os.environ.get("SPREADSHEET_ID")
        or "cgm-dupe-checker-secret"
    )
    key = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return URLSafeSerializer(key, salt="ts-auth")


def create_app(sheet_service: Any | None = None, base_dir: Path | None = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    root_dir = base_dir or BASE_DIR
    service = sheet_service or GoogleSheetService(root_dir)
    serializer = _build_serializer()

    full_pw = os.environ.get("FULL_ACCESS_PASSWORD", "inhouse101")
    masked_pw = os.environ.get("MASKED_ACCESS_PASSWORD", "cgm2026")
    password_modes = {
        full_pw: "full",
        masked_pw: "masked",
    }

    def _get_auth_mode() -> str | None:
        token = request.headers.get("X-Auth-Token", "").strip()
        if not token:
            return None
        try:
            payload = serializer.loads(token)
            mode = payload.get("mode") if isinstance(payload, dict) else None
            return mode if mode in ("full", "masked") else None
        except BadSignature:
            return None

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/api/status")
    def api_status():
        status = get_setup_status(root_dir)
        return jsonify(status)

    @app.post("/api/auth")
    def api_auth():
        data = request.get_json(silent=True) or {}
        password = str(data.get("password", ""))
        mode = password_modes.get(password)
        if not mode:
            return jsonify({"error": "Incorrect password."}), 401
        token = serializer.dumps({"mode": mode})
        return jsonify({"ok": True, "mode": mode, "token": token})

    @app.get("/api/search")
    def api_search():
        mode = _get_auth_mode()
        if not mode:
            return jsonify({"error": "Authentication required."}), 401

        phone = request.args.get("phone", "")
        force_refresh = request.args.get("refresh") == "1"
        try:
            if force_refresh:
                result = service.search_phone(phone, force_refresh=True)
            else:
                result = service.search_phone(phone)

            if mode == "masked":
                return jsonify(
                    {
                        "query": result["query"],
                        "mode": "masked",
                        "is_duplicate": len(result["matches"]) > 0,
                    }
                )

            result["mode"] = "full"
            return jsonify(result)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except ConfigurationError as exc:
            return jsonify({"error": str(exc), "needs_setup": True}), 503
        except HttpError as exc:
            status_code = getattr(exc.resp, "status", 502)
            if status_code == 403:
                msg = (
                    "Access denied by Google Sheets API. Make sure your Google Sheet is shared "
                    "with the service account email in credentials.json."
                )
            elif status_code == 404:
                msg = "Google Sheet not found. Check 'spreadsheet_id' in config.json."
            elif status_code == 400:
                msg = "Invalid sheet range. Check 'sheet_name' in config.json."
            else:
                msg = f"Google Sheets API error (HTTP {status_code})."
            return jsonify({"error": msg}), 502
        except Exception as exc:
            return jsonify({"error": f"Unexpected error: {exc}"}), 500

    @app.post("/api/refresh")
    def api_refresh():
        mode = _get_auth_mode()
        if not mode:
            return jsonify({"error": "Authentication required."}), 401

        try:
            rows, _ = service.fetch_rows(force_refresh=True)
            return jsonify({"refreshed": True, "total_rows": max(len(rows) - 1, 0)})
        except ConfigurationError as exc:
            return jsonify({"error": str(exc), "needs_setup": True}), 503
        except HttpError as exc:
            status_code = getattr(exc.resp, "status", 502)
            return jsonify({"error": f"Google Sheets API error (HTTP {status_code})."}), 502
        except Exception as exc:
            return jsonify({"error": f"Unexpected error: {exc}"}), 500

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    host = "0.0.0.0" if "PORT" in os.environ else "127.0.0.1"
    app.run(host=host, port=port, debug=False)
