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


BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://43.205.124.78:8000").rstrip("/")
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


def _response_error_detail(response: requests.Response, fallback: str) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            detail = payload.get("detail") or payload.get("message") or payload.get("error")
            if isinstance(detail, str) and detail.strip():
                return detail.strip()
    except Exception:
        pass

    response_text = (response.text or "").strip()
    if response_text:
        return f"{fallback} ({response.status_code}): {response_text[:300]}"
    return f"{fallback} ({response.status_code})."


def _legacy_start_batch(payload: dict) -> tuple[int | None, str | None]:
    """
    Backward-compatible fallback for older backend builds that don't expose
    /api/production/hmi/start-batch yet.
    """
    create_response = requests.post(
        _backend_url("/api/production/hmi/batches"),
        json=payload,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if create_response.status_code >= 400:
        return None, _response_error_detail(create_response, "Unable to create batch")

    try:
        created = create_response.json()
    except Exception:
        created = {}

    batch_id = created.get("id") if isinstance(created, dict) else None
    if not batch_id:
        return None, "Unable to start batch: backend did not return created batch ID."

    machine_start_response = requests.post(
        _backend_url("/api/plc/machine/start"),
        json={"batch_id": int(batch_id)},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if machine_start_response.status_code >= 400:
        return None, _response_error_detail(
            machine_start_response,
            "Unable to start machine for this batch",
        )

    return int(batch_id), None


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
            "latest_batch": latest_batch,
            "suggested_batch_no": suggested_batch_no,
            "today": _today_ist_iso(),
            "url_for": _template_url_for,
            "get_flashed_messages": _template_get_flashed_messages,
        },
    )


@app.post("/batch/start", name="start_batch")
async def start_batch(request: Request):
    form = await request.form()
    try:
        batch_no = str(form.get("batch_no") or "").strip()

        batch_count = int(form.get("batch_count", ""))
        if batch_count <= 0:
            raise ValueError("Batch count must be greater than 0.")

        duration_seconds = float(form.get("duration_per_count_seconds", ""))
        if duration_seconds <= 0:
            raise ValueError("Duration per count must be greater than 0.")

        recipe_id = int(form.get("recipe_id", ""))
        if recipe_id <= 0:
            raise ValueError("Recipe ID is required.")

        payload = {
            "batch_no": batch_no,
            "batch_count": batch_count,
            "duration_per_count_seconds": duration_seconds,
            "recipe_id": recipe_id,
            "date": form.get("date"),
        }
    except ValueError as exc:
        _flash(request, str(exc), "error")
        return _redirect_to_index(request)

    try:
        response = requests.post(
            _backend_url("/api/production/hmi/start-batch"),
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code == 404:
            # Fallback path for legacy backend versions.
            batch_id, fallback_error = _legacy_start_batch(payload)
            if fallback_error:
                _flash(request, fallback_error, "error")
                return _redirect_to_index(request)
            _flash(request, f"Batch #{batch_id} started.", "success")
            return _redirect_to_index(request)

        if response.status_code >= 400:
            _flash(request, _response_error_detail(response, "Unable to start batch"), "error")
            return _redirect_to_index(request)

        try:
            batch_id = response.json().get("id")
        except Exception:
            batch_id = None
        _flash(request, f"Batch #{batch_id} started.", "success")
    except Exception:
        _flash(request, "Backend is unreachable. Batch was not started.", "error")

    return _redirect_to_index(request)


@app.post("/machine/start", name="start_machine")
def start_machine(request: Request):
    try:
        response = requests.post(
            _backend_url("/api/plc/machine/start"),
            json={},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", "Unable to turn ON process.")
            except Exception:
                detail = "Unable to turn ON process."
            _flash(request, detail, "error")
            return _redirect_to_index(request)
        _flash(request, "Process turned ON.", "success")
    except Exception:
        _flash(request, "Backend is unreachable. Process was not turned ON.", "error")

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
                detail = response.json().get("detail", "Unable to turn OFF process.")
            except Exception:
                detail = "Unable to turn OFF process."
            _flash(request, detail, "error")
            return _redirect_to_index(request)
        _flash(request, "Process turned OFF.", "success")
    except Exception:
        _flash(request, "Backend is unreachable. Process was not turned OFF.", "error")

    return _redirect_to_index(request)


@app.post("/batch/stop", name="stop_batch")
def stop_batch(request: Request):
    try:
        response = requests.post(
            _backend_url("/api/production/hmi/stop-active-batch"),
            json={},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", "Unable to stop active batch.")
            except Exception:
                detail = "Unable to stop active batch."
            _flash(request, detail, "error")
            return _redirect_to_index(request)
        _flash(request, "Active batch stopped.", "success")
    except Exception:
        _flash(request, "Backend is unreachable. Active batch was not stopped.", "error")

    return _redirect_to_index(request)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001, reload=True)
