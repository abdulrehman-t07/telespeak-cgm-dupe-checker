from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request

from sheets_client import AppError, GoogleSheetService, get_setup_status

BASE_DIR = Path(__file__).resolve().parent


def _public_error_response(code: str, status_code: int):
    return (
        jsonify(
            {
                "error": f"Something went wrong. Please try again later. (Error Code: {code})",
                "error_code": code,
            }
        ),
        status_code,
    )


def create_app(sheet_service: Any | None = None, base_dir: Path | None = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    root_dir = base_dir or BASE_DIR
    service = sheet_service or GoogleSheetService(root_dir)

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/api/status")
    def api_status():
        return jsonify(get_setup_status(root_dir))

    @app.get("/api/search")
    def api_search():
        phone = request.args.get("phone", "")
        force_refresh = request.args.get("refresh") == "1"
        try:
            if force_refresh:
                result = service.check_phone(phone, force_refresh=True)
            else:
                result = service.check_phone(phone)
            return jsonify(result)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except AppError as exc:
            return _public_error_response(exc.code, exc.status_code)
        except Exception:
            return _public_error_response("E107", 500)

    @app.post("/api/refresh")
    def api_refresh():
        try:
            service.fetch_rows(force_refresh=True)
            return jsonify({"refreshed": True})
        except AppError as exc:
            return _public_error_response(exc.code, exc.status_code)
        except Exception:
            return _public_error_response("E107", 500)

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    host = "0.0.0.0" if "PORT" in os.environ else "127.0.0.1"
    app.run(host=host, port=port, debug=False)
