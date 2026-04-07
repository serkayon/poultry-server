from datetime import datetime, timedelta
from math import floor
from typing import Mapping, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.dispatch import DispatchEntry, DispatchProduct
from ..models.production import ProductionBatch, ProductionBatchMaterial
from ..models.raw_material import RawMaterialEntry
from ..models.stock import FeedStock, RMStockLedger

IST_OFFSET = timedelta(hours=5, minutes=30)


def _start_of_day(dt: datetime) -> datetime:
    # Persist one ledger row per type, per day.
    return dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)


def _normalize_bag_weight_grams(weight_per_bag: float | int | None) -> int | None:
    if weight_per_bag in (None, ""):
        return None
    try:
        parsed = float(weight_per_bag)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return int(round(parsed * 1000))


def _bag_weight_label(bag_weight_grams: int | None) -> str:
    if bag_weight_grams in (None, 0):
        return ""
    kg = bag_weight_grams / 1000.0
    return f"{kg:g}kg/bag"


def _feed_variant_label(feed_type: str, bag_weight_grams: int | None) -> str:
    label = _bag_weight_label(bag_weight_grams)
    if not label:
        return feed_type
    return f"{feed_type} ({label})"


def _normalize_feed_type(feed_type: str | None) -> str:
    return str(feed_type or "").strip()


def _normalize_batch_run_count(value: float | int | None) -> float:
    try:
        count = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, count)


def calculate_rm_consumption_quantity(
    per_batch_quantity: float | int | None,
    batch_run_count: float | int | None,
) -> float:
    try:
        quantity = float(per_batch_quantity or 0)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, quantity) * _normalize_batch_run_count(batch_run_count)


def resolve_effective_batch_run_count(
    *,
    batch_size: float | int | None,
    hmi_completed_count: float | int | None,
    hmi_status: str | None,
    rm_shortage_flag: bool | None = None,
) -> float:
    """
    Return actual utilized batch count for RM consumption calculations.
    Priority:
    1) hmi_completed_count when present (>0) for completed batches
    2) legacy fallback: if status is completed and completed_count is 0, use planned batch_size
    3) otherwise 0
    """
    if bool(rm_shortage_flag):
        return 0.0

    status = str(hmi_status or "").strip().lower()
    if status != "completed":
        return 0.0

    planned_count = _normalize_batch_run_count(batch_size)
    completed_count = _normalize_batch_run_count(hmi_completed_count)
    if completed_count > 0:
        if planned_count > 0:
            return min(completed_count, planned_count)
        return completed_count

    # Legacy fallback for older completed rows that do not have completed_count populated.
    return planned_count


def get_rm_available_stock(
    db: Session,
    *,
    client_id: int,
    rm_name: str,
    date: datetime,
) -> float:
    day = _start_of_day(date)
    row = db.execute(
        select(RMStockLedger).where(
            RMStockLedger.client_id == client_id,
            RMStockLedger.rm_name == rm_name,
            RMStockLedger.date == day,
        )
    ).scalars().one_or_none()

    if row:
        return (
            float(row.opening_stock or 0)
            + float(row.received or 0)
            - float(row.consumption or 0)
        )

    return _latest_rm_closing(db=db, client_id=client_id, rm_name=rm_name, day=day)


def collect_rm_shortages(
    db: Session,
    *,
    client_id: int,
    date: datetime,
    materials: Sequence[Mapping[str, object]],
    batch_run_count: float | int | None,
) -> list[dict]:
    required_by_rm: dict[str, float] = {}

    for material in materials:
        rm_name = str(material.get("rm_name") or "").strip()
        if not rm_name:
            continue
        required_quantity = calculate_rm_consumption_quantity(
            per_batch_quantity=material.get("quantity"),
            batch_run_count=batch_run_count,
        )
        if required_quantity <= 0:
            continue
        required_by_rm[rm_name] = required_by_rm.get(rm_name, 0.0) + float(required_quantity)

    shortages: list[dict] = []
    for rm_name in sorted(required_by_rm):
        required_quantity = required_by_rm[rm_name]
        available_quantity = get_rm_available_stock(
            db=db,
            client_id=client_id,
            rm_name=rm_name,
            date=date,
        )
        if required_quantity <= available_quantity:
            continue
        shortages.append(
            {
                "rm_name": rm_name,
                "required_quantity": required_quantity,
                "available_quantity": available_quantity,
                "shortage_quantity": required_quantity - available_quantity,
            }
        )
    return shortages


def calculate_max_supported_batch_count(
    db: Session,
    *,
    client_id: int,
    date: datetime,
    materials: Sequence[Mapping[str, object]],
    requested_batch_count: float | int | None,
) -> int:
    try:
        requested = max(0.0, float(requested_batch_count or 0))
    except (TypeError, ValueError):
        return 0

    if requested <= 0:
        return 0

    per_batch_by_rm: dict[str, float] = {}
    for material in materials:
        rm_name = str(material.get("rm_name") or "").strip()
        if not rm_name:
            continue
        try:
            qty = float(material.get("quantity") or 0)
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue
        per_batch_by_rm[rm_name] = per_batch_by_rm.get(rm_name, 0.0) + qty

    if not per_batch_by_rm:
        return int(floor(requested))

    supported = requested
    for rm_name, per_batch_qty in per_batch_by_rm.items():
        available = get_rm_available_stock(
            db=db,
            client_id=client_id,
            rm_name=rm_name,
            date=date,
        )
        if per_batch_qty <= 0:
            continue
        supported = min(supported, max(0.0, available / per_batch_qty))

    return max(0, int(floor(supported + 1e-9)))


def format_rm_shortage_message(
    shortages: Sequence[Mapping[str, object]],
    *,
    heading: str = "Insufficient raw material stock",
) -> str:
    if not shortages:
        return heading

    lines = [f"{heading}:"]
    for item in shortages:
        rm_name = str(item.get("rm_name") or "").strip() or "Unknown RM"
        try:
            required_quantity = float(item.get("required_quantity") or 0)
        except (TypeError, ValueError):
            required_quantity = 0.0
        try:
            available_quantity = float(item.get("available_quantity") or 0)
        except (TypeError, ValueError):
            available_quantity = 0.0
        try:
            shortage_quantity = float(item.get("shortage_quantity") or 0)
        except (TypeError, ValueError):
            shortage_quantity = 0.0

        lines.append(
            (
                f"- {rm_name} "
                f"(required: {required_quantity:.3f} kg, "
                f"available: {available_quantity:.3f} kg, "
                f"shortage: {shortage_quantity:.3f} kg)"
            )
        )
    return "\n".join(lines)


def _latest_rm_closing(
    db: Session,
    client_id: int,
    rm_name: str,
    day: datetime,
) -> float:
    latest = db.execute(
        select(RMStockLedger)
        .where(
            RMStockLedger.client_id == client_id,
            RMStockLedger.rm_name == rm_name,
            RMStockLedger.date < day,
        )
        .order_by(RMStockLedger.date.desc())
        .limit(1)
    ).scalars().one_or_none()
    return float(latest.closing_stock if latest else 0)


def _latest_feed_closing(
    db: Session,
    client_id: int,
    feed_type: str,
    day: datetime,
    bag_weight_grams: int | None = None,
) -> float:
    normalized_feed_type = _normalize_feed_type(feed_type)
    if not normalized_feed_type:
        return 0.0
    query = select(FeedStock).where(
        FeedStock.client_id == client_id,
        func.lower(func.trim(FeedStock.feed_type)) == normalized_feed_type.lower(),
        FeedStock.date < day,
    )
    if bag_weight_grams is None:
        query = query.where(FeedStock.bag_weight_grams.is_(None))
    else:
        query = query.where(FeedStock.bag_weight_grams == bag_weight_grams)
    latest = (
        db.execute(query.order_by(FeedStock.date.desc(), FeedStock.id.desc()).limit(1))
        .scalars()
        .one_or_none()
    )
    return float(latest.closing_stock if latest else 0)


def _get_or_create_rm_row(
    db: Session,
    client_id: int,
    rm_name: str,
    date: datetime,
) -> RMStockLedger:
    day = _start_of_day(date)
    row = db.execute(
        select(RMStockLedger).where(
            RMStockLedger.client_id == client_id,
            RMStockLedger.rm_name == rm_name,
            RMStockLedger.date == day,
        )
    ).scalars().one_or_none()
    if row:
        return row

    opening = _latest_rm_closing(db=db, client_id=client_id, rm_name=rm_name, day=day)
    row = RMStockLedger(
        client_id=client_id,
        date=day,
        rm_name=rm_name,
        opening_stock=opening,
        received=0,
        consumption=0,
        closing_stock=opening,
    )
    db.add(row)
    db.flush()
    return row


def _get_or_create_feed_row(
    db: Session,
    client_id: int,
    feed_type: str,
    date: datetime,
    bag_weight_grams: int | None = None,
) -> FeedStock:
    normalized_feed_type = _normalize_feed_type(feed_type)
    if not normalized_feed_type:
        raise ValueError("feed_type is required")

    day = _start_of_day(date)
    query = select(FeedStock).where(
        FeedStock.client_id == client_id,
        func.lower(func.trim(FeedStock.feed_type)) == normalized_feed_type.lower(),
        FeedStock.date == day,
    )
    if bag_weight_grams is None:
        query = query.where(FeedStock.bag_weight_grams.is_(None))
    else:
        query = query.where(FeedStock.bag_weight_grams == bag_weight_grams)

    row = db.execute(query.order_by(FeedStock.id.desc()).limit(1)).scalars().one_or_none()
    if row:
        return row

    opening = _latest_feed_closing(
        db=db,
        client_id=client_id,
        feed_type=normalized_feed_type,
        day=day,
        bag_weight_grams=bag_weight_grams,
    )
    row = FeedStock(
        client_id=client_id,
        date=day,
        feed_type=normalized_feed_type,
        bag_weight_grams=bag_weight_grams,
        opening_stock=opening,
        produced=0,
        dispatched=0,
        closing_stock=opening,
    )
    db.add(row)
    db.flush()
    return row


def add_rm_received(
    db: Session,
    client_id: int,
    rm_name: str,
    quantity: float,
    date: datetime,
) -> None:
    row = _get_or_create_rm_row(
        db=db,
        client_id=client_id,
        rm_name=rm_name,
        date=date,
    )
    row.received = float(row.received or 0) + float(quantity)
    row.closing_stock = (
        float(row.opening_stock or 0)
        + float(row.received or 0)
        - float(row.consumption or 0)
    )


def add_rm_consumption(
    db: Session,
    client_id: int,
    rm_name: str,
    quantity: float,
    date: datetime,
) -> None:
    qty = float(quantity)
    if qty <= 0:
        raise ValueError(f"Consumption quantity for {rm_name} must be greater than 0")

    row = _get_or_create_rm_row(
        db=db,
        client_id=client_id,
        rm_name=rm_name,
        date=date,
    )
    available = (
        float(row.opening_stock or 0)
        + float(row.received or 0)
        - float(row.consumption or 0)
    )
    if qty > available:
        raise ValueError(
            f"Insufficient raw material stock for {rm_name}. Available: {available}"
        )

    row.consumption = float(row.consumption or 0) + qty
    row.closing_stock = (
        float(row.opening_stock or 0)
        + float(row.received or 0)
        - float(row.consumption or 0)
    )


def add_feed_produced(
    db: Session,
    client_id: int,
    feed_type: str,
    quantity: float,
    date: datetime,
    weight_per_bag: float | int | None = None,
) -> None:
    normalized_feed_type = _normalize_feed_type(feed_type)
    if not normalized_feed_type:
        raise ValueError("feed_type is required")
    bag_weight_grams = _normalize_bag_weight_grams(weight_per_bag)
    row = _get_or_create_feed_row(
        db=db,
        client_id=client_id,
        feed_type=normalized_feed_type,
        date=date,
        bag_weight_grams=bag_weight_grams,
    )
    row.produced = float(row.produced or 0) + float(quantity)
    row.closing_stock = (
        float(row.opening_stock or 0)
        + float(row.produced or 0)
        - float(row.dispatched or 0)
    )


def add_feed_dispatched(
    db: Session,
    client_id: int,
    feed_type: str,
    quantity: float,
    date: datetime,
    weight_per_bag: float | int | None = None,
) -> None:
    qty = float(quantity)
    normalized_feed_type = _normalize_feed_type(feed_type)
    if not normalized_feed_type:
        raise ValueError("feed_type is required")
    bag_weight_grams = _normalize_bag_weight_grams(weight_per_bag)
    variant_label = _feed_variant_label(normalized_feed_type, bag_weight_grams)
    if qty <= 0:
        raise ValueError(f"Dispatch quantity for {variant_label} must be greater than 0")

    row = _get_or_create_feed_row(
        db=db,
        client_id=client_id,
        feed_type=normalized_feed_type,
        date=date,
        bag_weight_grams=bag_weight_grams,
    )
    available = (
        float(row.opening_stock or 0)
        + float(row.produced or 0)
        - float(row.dispatched or 0)
    )
    if qty > available:
        raise ValueError(
            f"Insufficient stock for {variant_label}. Available: {available}"
        )

    row.dispatched = float(row.dispatched or 0) + qty
    row.closing_stock = (
        float(row.opening_stock or 0)
        + float(row.produced or 0)
        - float(row.dispatched or 0)
    )


def rebuild_rm_stock_ledger(db: Session, client_id: int) -> None:
    # Rebuild complete RM ledger from RM inward entries + production consumption.
    existing_rows = (
        db.execute(select(RMStockLedger).where(RMStockLedger.client_id == client_id))
        .scalars()
        .all()
    )
    for row in existing_rows:
        db.delete(row)
    db.flush()

    rm_entries = (
        db.execute(
            select(
                RawMaterialEntry.date,
                RawMaterialEntry.rm_type,
                RawMaterialEntry.total_weight,
            )
            .where(RawMaterialEntry.client_id == client_id)
            .order_by(RawMaterialEntry.date.asc(), RawMaterialEntry.id.asc())
        )
        .all()
    )
    for date, rm_type, total_weight in rm_entries:
        add_rm_received(
            db=db,
            client_id=client_id,
            rm_name=rm_type,
            quantity=float(total_weight),
            date=date,
        )

    consumption_rows = (
        db.execute(
            select(
                ProductionBatch.date,
                ProductionBatchMaterial.rm_name,
                ProductionBatchMaterial.quantity,
                ProductionBatch.batch_size,
                ProductionBatch.hmi_completed_count,
                ProductionBatch.hmi_status,
                ProductionBatch.rm_shortage_flag,
            )
            .join(ProductionBatch, ProductionBatch.id == ProductionBatchMaterial.batch_id)
            .where(ProductionBatch.client_id == client_id)
            .order_by(
                ProductionBatch.date.asc(),
                ProductionBatch.id.asc(),
                ProductionBatchMaterial.id.asc(),
            )
        )
        .all()
    )
    for (
        date,
        rm_name,
        quantity,
        batch_size,
        hmi_completed_count,
        hmi_status,
        rm_shortage_flag,
    ) in consumption_rows:
        effective_count = resolve_effective_batch_run_count(
            batch_size=batch_size,
            hmi_completed_count=hmi_completed_count,
            hmi_status=hmi_status,
            rm_shortage_flag=rm_shortage_flag,
        )
        consumption_quantity = calculate_rm_consumption_quantity(
            per_batch_quantity=quantity,
            batch_run_count=effective_count,
        )
        if consumption_quantity <= 0:
            continue
        add_rm_consumption(
            db=db,
            client_id=client_id,
            rm_name=rm_name,
            quantity=consumption_quantity,
            date=date,
        )


def rebuild_feed_stock_ledger(db: Session, client_id: int) -> None:
    # Rebuild complete feed ledger from production output + dispatch entries.
    existing_rows = (
        db.execute(select(FeedStock).where(FeedStock.client_id == client_id))
        .scalars()
        .all()
    )
    for row in existing_rows:
        db.delete(row)
    db.flush()

    produced_rows = (
        db.execute(
            select(
                ProductionBatch.date,
                ProductionBatch.product_name,
                ProductionBatch.weight_per_bag,
                ProductionBatch.output,
            )
            .where(
                ProductionBatch.client_id == client_id,
                ProductionBatch.stock_posted.is_(True),
            )
            .order_by(ProductionBatch.date.asc(), ProductionBatch.id.asc())
        )
        .all()
    )
    for date, product_name, weight_per_bag, output in produced_rows:
        add_feed_produced(
            db=db,
            client_id=client_id,
            feed_type=product_name,
            quantity=float(output),
            date=date,
            weight_per_bag=weight_per_bag,
        )

    dispatch_rows = (
        db.execute(
            select(
                DispatchEntry.date,
                DispatchProduct.product_type,
                DispatchProduct.weight_per_bag,
                DispatchProduct.total_weight,
            )
            .join(DispatchProduct, DispatchProduct.dispatch_id == DispatchEntry.id)
            .where(DispatchEntry.client_id == client_id)
            .order_by(DispatchEntry.date.asc(), DispatchEntry.id.asc())
        )
        .all()
    )
    for date, product_type, weight_per_bag, total_weight in dispatch_rows:
        # Dispatch entries are stored in UTC-naive form after API parsing.
        # Shift to IST wall clock before daily ledger bucketing.
        ledger_date = date + IST_OFFSET
        add_feed_dispatched(
            db=db,
            client_id=client_id,
            feed_type=product_type,
            quantity=float(total_weight),
            date=ledger_date,
            weight_per_bag=weight_per_bag,
        )
