from datetime import datetime, timedelta

from ..fastapi_compat import Blueprint, jsonify, request
from sqlalchemy import select

from ..common import DEFAULT_CLIENT_ID, db_session, dt, error, serialize_batch
from ...models.plc import PLCDataSnapshot
from ...models.production import ProductionBatch, ProductionBatchMaterial, ProductionReport
from ...services.plc_simulator import (
    ensure_plc_live_data,
    get_or_create_machine_state,
    set_machine_running,
)
from ...services.production_runtime import (
    RUN_STATUS_COMPLETED,
    RUN_STATUS_RUNNING,
    RUN_STATUS_STOPPED,
    normalize_batch_count,
    sync_active_batch_progress,
    try_post_batch_stock,
)

plc_bp = Blueprint("plc", __name__, url_prefix="/api/plc")


def _serialize_plc_row(row: PLCDataSnapshot | None, running_status: bool) -> dict:
    return {
        "id": row.id if row else None,
        "running_status": running_status,
        "ambient_temp": row.ambient_temp if row else None,
        "humidity": row.humidity if row else None,
        "pressure_before": row.pressure_before if row else None,
        "pressure_after": row.pressure_after if row else None,
        "conditioner_temp": row.conditioner_temp if row else None,
        "bagging_temp": row.bagging_temp if row else None,
        "motor_temp": row.motor_temp if row else None,
        "motor_rpm": row.motor_rpm if row else None,
        "pellet_feeder_speed": row.pellet_feeder_speed if row else None,
        "pellet_motor_load": row.pellet_motor_load if row else None,
        "recorded_at": dt(row.recorded_at) if row else None,
    }


def _active_batch_payload(db, machine_state) -> dict | None:
    if not machine_state.active_batch_id:
        return None

    batch = (
        db.execute(
            select(ProductionBatch).where(
                ProductionBatch.id == machine_state.active_batch_id,
                ProductionBatch.client_id == DEFAULT_CLIENT_ID,
            )
        )
        .scalars()
        .one_or_none()
    )
    if not batch:
        return None

    has_report = (
        db.execute(select(ProductionReport.id).where(ProductionReport.batch_id == batch.id))
        .scalars()
        .one_or_none()
        is not None
    )
    payload = serialize_batch(
        batch,
        has_report=has_report,
        is_active=bool(machine_state.is_running and machine_state.active_batch_id == batch.id),
    )
    payload["materials"] = [
        {"id": row.id, "rm_name": row.rm_name, "quantity": row.quantity}
        for row in db.execute(
            select(ProductionBatchMaterial)
            .where(ProductionBatchMaterial.batch_id == batch.id)
            .order_by(ProductionBatchMaterial.id.asc())
        )
        .scalars()
        .all()
    ]
    return payload


def _machine_status_payload(machine_state, latest_row: PLCDataSnapshot | None, active_batch: dict | None) -> dict:
    return {
        "is_running": bool(machine_state.is_running),
        "active_batch_id": machine_state.active_batch_id,
        "active_batch": active_batch,
        "updated_at": dt(machine_state.updated_at),
        "last_snapshot_at": dt(latest_row.recorded_at) if latest_row else None,
    }


@plc_bp.get("/latest")
def plc_latest():
    with db_session() as db:
        machine_state = get_or_create_machine_state(db)
        synced_batch = sync_active_batch_progress(db, machine_state=machine_state)
        if synced_batch:
            try_post_batch_stock(db, batch=synced_batch, client_id=DEFAULT_CLIENT_ID)
        ensure_plc_live_data(db, minutes=60)
        row = db.execute(
            select(PLCDataSnapshot).order_by(PLCDataSnapshot.recorded_at.desc()).limit(1)
        ).scalars().first()
        return jsonify(_serialize_plc_row(row=row, running_status=bool(machine_state.is_running)))


@plc_bp.get("/history")
def plc_history():
    try:
        minutes = int(request.args.get("minutes", 60))
    except ValueError:
        return error("minutes must be an integer")
    if minutes <= 0:
        return error("minutes must be greater than 0")

    since = datetime.utcnow() - timedelta(minutes=minutes)
    with db_session() as db:
        machine_state = get_or_create_machine_state(db)
        synced_batch = sync_active_batch_progress(db, machine_state=machine_state)
        if synced_batch:
            try_post_batch_stock(db, batch=synced_batch, client_id=DEFAULT_CLIENT_ID)
        ensure_plc_live_data(db, minutes=max(minutes, 60))
        rows = (
            db.execute(
                select(PLCDataSnapshot)
                .where(PLCDataSnapshot.recorded_at >= since)
                .order_by(PLCDataSnapshot.recorded_at.asc())
            )
            .scalars()
            .all()
        )

    if not rows:
        return jsonify([])

    return jsonify(
        [
            {
                "recorded_at": dt(row.recorded_at),
                "ambient_temp": row.ambient_temp,
                "humidity": row.humidity,
                "pressure_before": row.pressure_before,
                "pressure_after": row.pressure_after,
                "conditioner_temp": row.conditioner_temp,
                "bagging_temp": row.bagging_temp,
                "pellet_feeder_speed": row.pellet_feeder_speed,
                "pellet_motor_load": row.pellet_motor_load,
            }
            for row in rows
        ]
    )


@plc_bp.get("/machine/status")
def machine_status():
    with db_session() as db:
        machine_state = get_or_create_machine_state(db)
        synced_batch = sync_active_batch_progress(db, machine_state=machine_state)
        if synced_batch:
            try_post_batch_stock(db, batch=synced_batch, client_id=DEFAULT_CLIENT_ID)
        latest_row = db.execute(
            select(PLCDataSnapshot).order_by(PLCDataSnapshot.recorded_at.desc()).limit(1)
        ).scalars().one_or_none()
        active_batch = _active_batch_payload(db, machine_state)
        return jsonify(_machine_status_payload(machine_state, latest_row, active_batch))


@plc_bp.post("/machine/start")
def machine_start():
    payload = request.get_json(silent=True) or {}
    batch_id_raw = payload.get("batch_id")
    batch_id: int | None = None
    if batch_id_raw not in (None, ""):
        try:
            batch_id = int(batch_id_raw)
        except (TypeError, ValueError):
            return error("batch_id must be an integer")

    with db_session() as db:
        machine_state = get_or_create_machine_state(db)
        sync_active_batch_progress(db, machine_state=machine_state)

        if batch_id is not None:
            batch = (
                db.execute(
                    select(ProductionBatch).where(
                        ProductionBatch.id == batch_id,
                        ProductionBatch.client_id == DEFAULT_CLIENT_ID,
                    )
                )
                .scalars()
                .one_or_none()
            )
            if batch is None:
                return error("Batch not found", 404)

            if (batch.hmi_status or "").lower() == RUN_STATUS_COMPLETED:
                return error("Batch is already completed.")

            planned_count = normalize_batch_count(batch.batch_size)
            if planned_count <= 0:
                return error("Batch count is invalid for this batch.")

            duration = float(batch.hmi_duration_seconds or 0)
            if duration <= 0:
                return error("Duration per count is missing for this batch.")

            completed_count = max(0, int(batch.hmi_completed_count or 0))
            if completed_count >= planned_count:
                return error("Batch is already completed.")

            if completed_count > 0:
                batch.hmi_started_at = datetime.utcnow() - timedelta(
                    seconds=max(0.0, (completed_count - 1) * duration)
                )
            elif batch.hmi_started_at is None:
                batch.hmi_started_at = datetime.utcnow()
            batch.hmi_status = RUN_STATUS_RUNNING
            batch.hmi_completed_at = None
            batch.last_modified_at = datetime.utcnow()

        machine_state = set_machine_running(
            db,
            running=True,
            active_batch_id=batch_id if batch_id is not None else machine_state.active_batch_id,
        )
        synced_batch = sync_active_batch_progress(db, machine_state=machine_state)
        if synced_batch:
            try_post_batch_stock(db, batch=synced_batch, client_id=DEFAULT_CLIENT_ID)
        latest_row = db.execute(
            select(PLCDataSnapshot).order_by(PLCDataSnapshot.recorded_at.desc()).limit(1)
        ).scalars().one_or_none()
        active_batch = _active_batch_payload(db, machine_state)
        return jsonify(_machine_status_payload(machine_state, latest_row, active_batch))


@plc_bp.post("/machine/stop")
def machine_stop():
    with db_session() as db:
        machine_state = get_or_create_machine_state(db)
        sync_active_batch_progress(db, machine_state=machine_state)
        if machine_state.active_batch_id:
            active_batch = db.get(ProductionBatch, machine_state.active_batch_id)
            if active_batch and (active_batch.hmi_status or "").lower() != RUN_STATUS_COMPLETED:
                now = datetime.utcnow()
                if active_batch.hmi_started_at is None:
                    active_batch.hmi_started_at = now
                active_batch.hmi_status = RUN_STATUS_STOPPED
                active_batch.hmi_completed_at = now
                active_batch.last_modified_at = now

        machine_state = set_machine_running(db, running=False, active_batch_id=None)
        latest_row = db.execute(
            select(PLCDataSnapshot).order_by(PLCDataSnapshot.recorded_at.desc()).limit(1)
        ).scalars().one_or_none()
        return jsonify(_machine_status_payload(machine_state, latest_row, None))
