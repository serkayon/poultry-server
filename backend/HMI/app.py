from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware


BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://localhost:8000").rstrip("/")
REQUEST_TIMEOUT_SECONDS = 10
HMI_SECRET_KEY = os.getenv("HMI_SECRET_KEY", "hmi-local-dev-secret")

try:
    IST_TIMEZONE = ZoneInfo("Asia/Kolkata")
except ZoneInfoNotFoundError:
    IST_TIMEZONE = timezone(timedelta(hours=5, minutes=30), name="IST")

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Mill HMI Dashboard")
app.add_middleware(SessionMiddleware, secret_key=HMI_SECRET_KEY)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _today_ist_iso() -> str:
    return datetime.now(IST_TIMEZONE).date().isoformat()


def _backend_url(path: str) -> str:
    return f"{BACKEND_BASE_URL}{path}"


def _safe_get_json(path: str, fallback):
    try:
        response = requests.get(_backend_url(path), timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except Exception:
        return fallback


def _suggest_batch_no_from_batches(batches: list[dict]) -> str:
    pattern = re.compile(r"^BATCH(\d+)$", re.IGNORECASE)
    max_sequence = 0
    for item in batches:
        batch_no = str(item.get("batch_no") or "").strip()
        match = pattern.match(batch_no)
        if not match:
            continue
        try:
            sequence = int(match.group(1))
        except ValueError:
            continue
        if sequence > max_sequence:
            max_sequence = sequence
    return f"BATCH{max_sequence + 1:05d}"


def _flash(request: Request, message: str, category: str = "message") -> None:
    flashes = list(request.session.get("_flashes", []))
    flashes.append({"category": category, "message": message})
    request.session["_flashes"] = flashes


def _pop_flashes(request: Request) -> list[tuple[str, str]]:
    raw_messages = request.session.pop("_flashes", [])
    out: list[tuple[str, str]] = []
    for item in raw_messages:
        if isinstance(item, dict):
            out.append((str(item.get("category") or "message"), str(item.get("message") or "")))
    return out


def _redirect_to_index(request: Request) -> RedirectResponse:
    return RedirectResponse(url=request.url_for("index"), status_code=303)


@app.get("/", response_class=HTMLResponse, name="index")
def index(request: Request):
    machine_status = _safe_get_json(
        "/api/plc/machine/status",
        {
            "is_running": False,
            "active_batch_id": None,
            "active_batch": None,
            "updated_at": None,
            "last_snapshot_at": None,
        },
    )
    batches = _safe_get_json("/api/production/batches", [])
    safe_batches = batches if isinstance(batches, list) else []
    pending_batches = [
        item
        for item in safe_batches
        if isinstance(item, dict) and (item.get("run_status") or "").lower() != "completed"
    ]
    latest_batch = safe_batches[0] if safe_batches else None
    suggested_batch_no = _suggest_batch_no_from_batches(safe_batches)
    messages = _pop_flashes(request)

    def _template_url_for(name: str, **params) -> str:
        if "filename" in params and "path" not in params:
            params["path"] = params.pop("filename")
        return str(request.url_for(name, **params))

    def _template_get_flashed_messages(with_categories: bool = False):
        if with_categories:
            return messages
        return [message for _, message in messages]

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "machine_status": machine_status,
            "batches": safe_batches,
            "pending_batches": pending_batches,
            "latest_batch": latest_batch,
            "suggested_batch_no": suggested_batch_no,
            "today": _today_ist_iso(),
            "url_for": _template_url_for,
            "get_flashed_messages": _template_get_flashed_messages,
        },
    )


@app.post("/batch/add", name="add_batch")
async def add_batch(request: Request):
    form = await request.form()
    try:
        batch_no = str(form.get("batch_no") or "").strip()

        batch_count = int(form.get("batch_count", ""))
        if batch_count <= 0:
            raise ValueError("Batch count must be greater than 0.")

        duration_seconds = float(form.get("duration_per_count_seconds", ""))
        if duration_seconds <= 0:
            raise ValueError("Duration per count must be greater than 0.")

        payload = {
            "batch_no": batch_no,
            "batch_count": batch_count,
            "duration_per_count_seconds": duration_seconds,
            "date": form.get("date"),
        }
    except ValueError as exc:
        _flash(request, str(exc), "error")
        return _redirect_to_index(request)

    try:
        response = requests.post(
            _backend_url("/api/production/hmi/batches"),
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", "Unable to add batch.")
            except Exception:
                detail = "Unable to add batch."
            _flash(request, detail, "error")
            return _redirect_to_index(request)
        batch_id = response.json().get("id")
        _flash(request, f"Batch #{batch_id} created. Use Start to run.", "success")
    except Exception:
        _flash(request, "Backend is unreachable. Batch was not created.", "error")

    return _redirect_to_index(request)


@app.post("/machine/start", name="start_machine")
async def start_machine(request: Request):
    form = await request.form()
    body = {}
    batch_id = str(form.get("batch_id") or "").strip()
    if not batch_id:
        _flash(request, "Select a batch to start.", "error")
        return _redirect_to_index(request)
    try:
        body["batch_id"] = int(batch_id)
    except ValueError:
        _flash(request, "batch_id must be a valid integer.", "error")
        return _redirect_to_index(request)

    try:
        response = requests.post(
            _backend_url("/api/plc/machine/start"),
            json=body,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", "Unable to start machine.")
            except Exception:
                detail = "Unable to start machine."
            _flash(request, detail, "error")
            return _redirect_to_index(request)
        _flash(request, "Machine started.", "success")
    except Exception:
        _flash(request, "Backend is unreachable. Machine was not started.", "error")

    return _redirect_to_index(request)


@app.post("/machine/stop", name="stop_machine")
def stop_machine(request: Request):
    try:
        response = requests.post(
            _backend_url("/api/plc/machine/stop"),
            json={},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", "Unable to stop machine.")
            except Exception:
                detail = "Unable to stop machine."
            _flash(request, detail, "error")
            return _redirect_to_index(request)
        _flash(request, "Machine stopped.", "success")
    except Exception:
        _flash(request, "Backend is unreachable. Machine was not stopped.", "error")

    return _redirect_to_index(request)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8010, reload=True)
