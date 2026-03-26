from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..models.plc import MachineState
from ..models.production import ProductionBatch
from .stock import add_feed_produced


RUN_STATUS_PENDING = "pending"
RUN_STATUS_RUNNING = "running"
RUN_STATUS_STOPPED = "stopped"
RUN_STATUS_COMPLETED = "completed"


def normalize_batch_count(value: float | int | None) -> int:
    try:
        count = int(float(value or 0))
    except (TypeError, ValueError):
        return 0
    return max(0, count)


def _duration_seconds(batch: ProductionBatch) -> float:
    try:
        seconds = float(batch.hmi_duration_seconds or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, seconds)


def _is_batch_ready_for_stock(batch: ProductionBatch) -> bool:
    if bool(batch.stock_posted):
        return False
    if (batch.hmi_status or "").lower() != RUN_STATUS_COMPLETED:
        return False

    product_name = (batch.product_name or "").strip()
    if not product_name:
        return False

    try:
        num_bags = float(batch.num_bags or 0)
        weight_per_bag = float(batch.weight_per_bag or 0)
        output = float(batch.output or 0)
    except (TypeError, ValueError):
        return False

    return num_bags > 0 and weight_per_bag > 0 and output > 0


def try_post_batch_stock(db: Session, *, batch: ProductionBatch, client_id: int) -> bool:
    """Post feed stock once the batch is complete and all required details are available."""
    if not _is_batch_ready_for_stock(batch):
        return False

    add_feed_produced(
        db=db,
        client_id=client_id,
        feed_type=(batch.product_name or "").strip(),
        quantity=float(batch.output),
        date=batch.date,
        weight_per_bag=batch.weight_per_bag,
    )
    batch.stock_posted = True
    batch.last_modified_at = datetime.utcnow()
    return True


def sync_active_batch_progress(db: Session, *, machine_state: MachineState) -> ProductionBatch | None:
    """
    Update the active batch counter according to elapsed duration.
    Auto-completes and stops machine when planned count is reached.
    """
    if not machine_state.is_running or not machine_state.active_batch_id:
        return None

    batch = db.get(ProductionBatch, machine_state.active_batch_id)
    if not batch:
        machine_state.is_running = False
        machine_state.active_batch_id = None
        machine_state.updated_at = datetime.utcnow()
        return None

    total_count = normalize_batch_count(batch.batch_size)
    duration = _duration_seconds(batch)

    if total_count <= 0:
        batch.hmi_status = RUN_STATUS_RUNNING
        if batch.hmi_started_at is None:
            batch.hmi_started_at = datetime.utcnow()
        batch.last_modified_at = datetime.utcnow()
        return batch

    if batch.hmi_started_at is None:
        completed = max(0, int(batch.hmi_completed_count or 0))
        if duration > 0 and completed > 0:
            batch.hmi_started_at = datetime.utcnow() - timedelta(
                seconds=(completed - 1) * duration
            )
        else:
            batch.hmi_started_at = datetime.utcnow()

    now = datetime.utcnow()
    elapsed_seconds = max(0.0, (now - batch.hmi_started_at).total_seconds())

    if duration > 0:
        display_count = min(total_count, max(1, int(elapsed_seconds // duration) + 1))
    else:
        display_count = total_count

    batch.hmi_completed_count = display_count
    batch.hmi_status = RUN_STATUS_RUNNING
    batch.last_modified_at = now

    is_finished = duration <= 0 or elapsed_seconds >= (total_count * duration)
    if is_finished:
        batch.hmi_completed_count = total_count
        batch.hmi_status = RUN_STATUS_COMPLETED
        batch.hmi_completed_at = now
        machine_state.is_running = False
        machine_state.active_batch_id = None
        machine_state.updated_at = now

    return batch
