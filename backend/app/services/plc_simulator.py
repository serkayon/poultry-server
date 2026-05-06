# PLC data generator used to mimic live ingestion into DB.

from __future__ import annotations

import logging
import random
import threading
import time
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.plc import MachineState, PLCDataSnapshot
from .production_runtime import sync_active_batch_progress

MACHINE_STATE_ID = 1

BASE_STATE = {
    "running_status": False,
    "process_status": 0,
    "ambient_temp": 28.0,
    "humidity": 65.0,
    "pressure_before": 4.2,
    "pressure_after": 2.8,
    "conditioner_temp": 85.0,
    "bagging_temp": 32.0,
    "motor_temp": 45.0,
    "motor_rpm": 1250.0,
    "pellet_feeder_speed": 120.0,
    "pellet_motor_load": 62.0,
}

_writer_lock = threading.Lock()
_writer_thread: threading.Thread | None = None
_ensure_lock = threading.Lock()
logger = logging.getLogger(__name__)

# Handle next val.

def _next_val(prev: float, low: float, high: float, step: float) -> float:
    delta = (random.random() - 0.5) * 2 * step
    return max(low, min(high, prev + delta))

# Handle interval floor.

def _interval_floor(dt: datetime, interval_seconds: int) -> datetime:
    safe_interval = max(1, int(interval_seconds))
    floored_second = (dt.second // safe_interval) * safe_interval
    return dt.replace(second=floored_second, microsecond=0, tzinfo=None)

# Handle state from row.

def _state_from_row(row: PLCDataSnapshot | None) -> dict:
    if not row:
        return dict(BASE_STATE)
    return {
        "running_status": bool(row.running_status),
        "process_status": int(row.process_status or (100 if row.running_status else 0)),
        "ambient_temp": float(row.ambient_temp or BASE_STATE["ambient_temp"]),
        "humidity": float(row.humidity or BASE_STATE["humidity"]),
        "pressure_before": float(row.pressure_before or BASE_STATE["pressure_before"]),
        "pressure_after": float(row.pressure_after or BASE_STATE["pressure_after"]),
        "conditioner_temp": float(row.conditioner_temp or BASE_STATE["conditioner_temp"]),
        "bagging_temp": float(row.bagging_temp or BASE_STATE["bagging_temp"]),
        "motor_temp": float(row.motor_temp or BASE_STATE["motor_temp"]),
        "motor_rpm": float(row.motor_rpm or BASE_STATE["motor_rpm"]),
        "pellet_feeder_speed": float(
            row.pellet_feeder_speed or BASE_STATE["pellet_feeder_speed"]
        ),
        "pellet_motor_load": float(
            row.pellet_motor_load or BASE_STATE["pellet_motor_load"]
        ),
    }

# Handle advance state.

def _advance_state(state: dict) -> dict:
    nxt = dict(state)
    nxt["ambient_temp"] = _next_val(nxt["ambient_temp"], 24, 34, 0.8)
    nxt["humidity"] = _next_val(nxt["humidity"], 50, 78, 2.0)
    nxt["pressure_before"] = _next_val(nxt["pressure_before"], 3.5, 4.8, 0.12)
    nxt["pressure_after"] = _next_val(nxt["pressure_after"], 2.2, 3.4, 0.12)
    nxt["conditioner_temp"] = _next_val(nxt["conditioner_temp"], 80, 90, 1.0)
    nxt["bagging_temp"] = _next_val(nxt["bagging_temp"], 26, 40, 1.0)
    nxt["motor_temp"] = _next_val(nxt["motor_temp"], 40, 55, 1.0)
    nxt["motor_rpm"] = _next_val(nxt["motor_rpm"], 1100, 1400, 20.0)
    nxt["pellet_feeder_speed"] = _next_val(nxt["pellet_feeder_speed"], 95, 145, 3.0)
    nxt["pellet_motor_load"] = _next_val(nxt["pellet_motor_load"], 35, 95, 2.0)
    return nxt

# Handle insert snapshot.

def _insert_snapshot(
    db: Session,
    state: dict,
    recorded_at: datetime) -> None:
    db.add(
        PLCDataSnapshot(
            running_status=bool(state.get("running_status", False)),
            process_status=int(state.get("process_status", 100 if state.get("running_status", False) else 0)),
            ambient_temp=round(float(state["ambient_temp"]), 1),
            humidity=round(float(state["humidity"]), 1),
            pressure_before=round(float(state["pressure_before"]), 2),
            pressure_after=round(float(state["pressure_after"]), 2),
            conditioner_temp=round(float(state["conditioner_temp"]), 1),
            bagging_temp=round(float(state["bagging_temp"]), 1),
            motor_temp=round(float(state["motor_temp"]), 1),
            motor_rpm=round(float(state["motor_rpm"]), 1),
            pellet_feeder_speed=round(float(state["pellet_feeder_speed"]), 1),
            pellet_motor_load=round(float(state["pellet_motor_load"]), 1),
            recorded_at=recorded_at)
    )

# Get or create machine state.

def get_or_create_machine_state(db: Session) -> MachineState:
    machine_state = db.get(MachineState, MACHINE_STATE_ID)
    if machine_state is not None:
        return machine_state

    machine_state = MachineState(id=MACHINE_STATE_ID, is_running=False, active_batch_id=None)
    db.add(machine_state)
    db.flush()
    return machine_state

# Set machine running.

def set_machine_running(
    db: Session,
    *,
    running: bool,
    active_batch_id: int | None = None) -> MachineState:
    machine_state = get_or_create_machine_state(db)
    was_running = bool(machine_state.is_running)
    machine_state.is_running = running
    machine_state.updated_at = datetime.utcnow()
    machine_state.active_batch_id = active_batch_id if running else None

    if was_running != bool(running):
        latest_row = db.execute(
            select(PLCDataSnapshot).order_by(PLCDataSnapshot.recorded_at.desc()).limit(1)
        ).scalars().one_or_none()
        state = _state_from_row(latest_row)
        state["running_status"] = running
        state["process_status"] = 100 if running else 0
        _insert_snapshot(db=db, state=state, recorded_at=datetime.utcnow())
    return machine_state

# Ensure DB has PLC rows up to now with a fixed time interval.

def ensure_plc_live_data(
    db: Session,
    minutes: int = 60,
    interval_seconds: int = 5) -> None:
    with _ensure_lock:
        machine_state = get_or_create_machine_state(db)
        if not machine_state.is_running:
            return

        lookback_minutes = max(1, int(minutes))
        step_seconds = max(1, int(interval_seconds))
        lookback_slots = max(1, int((lookback_minutes * 60 + step_seconds - 1) // step_seconds))
        now_slot = _interval_floor(datetime.utcnow(), step_seconds)
        window_start = now_slot - timedelta(seconds=(lookback_slots - 1) * step_seconds)

        query = select(PLCDataSnapshot)
        latest_row = db.execute(
            query.order_by(PLCDataSnapshot.recorded_at.desc()).limit(1)
        ).scalars().one_or_none()

        state = _state_from_row(latest_row)
        state["running_status"] = True
        state["process_status"] = 100
        fill_start = window_start
        if latest_row:
            last_slot = _interval_floor(latest_row.recorded_at, step_seconds)
            # Prevent huge backfills if the latest row is very old.
            if last_slot < window_start - timedelta(minutes=240):
                fill_start = window_start
            else:
                fill_start = max(
                    last_slot + timedelta(seconds=step_seconds),
                    window_start)

        cursor = fill_start
        step = timedelta(seconds=step_seconds)
        while cursor <= now_slot:
            state = _advance_state(state)
            state["running_status"] = True
            state["process_status"] = 100
            _insert_snapshot(db=db, state=state, recorded_at=cursor)
            cursor += step

# Optional continuous writer for manual runs.

def run_plc_simulation(interval_seconds: int = 5):
    state = dict(BASE_STATE)
    while True:
        try:
            with SessionLocal() as session:
                machine_state = get_or_create_machine_state(session)
                if machine_state.is_running:
                    state = _advance_state(state)
                    state["running_status"] = True
                    state["process_status"] = 100
                    _insert_snapshot(session, state=state, recorded_at=datetime.utcnow())
                session.commit()
        except Exception:
            logger.exception("PLC simulation loop failed")
        time.sleep(max(1, interval_seconds))

# Handle background writer loop.

def _background_writer_loop(interval_seconds: int, lookback_minutes: int) -> None:
    while True:
        try:
            with SessionLocal() as session:
                machine_state = get_or_create_machine_state(session)
                sync_active_batch_progress(session, machine_state=machine_state)
                ensure_plc_live_data(session, minutes=lookback_minutes)
                session.commit()
        except Exception:
            logger.exception("PLC background writer loop failed")
        time.sleep(max(1, interval_seconds))

# Start one daemon writer thread per process.

def start_plc_background_writer(interval_seconds: int = 5, lookback_minutes: int = 60) -> None:
    global _writer_thread
    with _writer_lock:
        if _writer_thread and _writer_thread.is_alive():
            return
        _writer_thread = threading.Thread(
            target=_background_writer_loop,
            args=(interval_seconds, lookback_minutes),
            daemon=True,
            name="plc-background-writer")
        _writer_thread.start()

