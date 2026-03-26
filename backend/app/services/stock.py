from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.dispatch import DispatchEntry, DispatchProduct
from ..models.production import ProductionBatch, ProductionBatchMaterial
from ..models.raw_material import RawMaterialEntry
from ..models.stock import FeedStock, RMStockLedger


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
    query = select(FeedStock).where(
        FeedStock.client_id == client_id,
        FeedStock.feed_type == feed_type,
        FeedStock.date < day,
    )
    if bag_weight_grams is None:
        query = query.where(FeedStock.bag_weight_grams.is_(None))
    else:
        query = query.where(FeedStock.bag_weight_grams == bag_weight_grams)
    latest = db.execute(query.order_by(FeedStock.date.desc()).limit(1)).scalars().one_or_none()
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
    day = _start_of_day(date)
    query = select(FeedStock).where(
        FeedStock.client_id == client_id,
        FeedStock.feed_type == feed_type,
        FeedStock.date == day,
    )
    if bag_weight_grams is None:
        query = query.where(FeedStock.bag_weight_grams.is_(None))
    else:
        query = query.where(FeedStock.bag_weight_grams == bag_weight_grams)

    row = db.execute(query).scalars().one_or_none()
    if row:
        return row

    opening = _latest_feed_closing(
        db=db,
        client_id=client_id,
        feed_type=feed_type,
        day=day,
        bag_weight_grams=bag_weight_grams,
    )
    row = FeedStock(
        client_id=client_id,
        date=day,
        feed_type=feed_type,
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
    bag_weight_grams = _normalize_bag_weight_grams(weight_per_bag)
    row = _get_or_create_feed_row(
        db=db,
        client_id=client_id,
        feed_type=feed_type,
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
    bag_weight_grams = _normalize_bag_weight_grams(weight_per_bag)
    variant_label = _feed_variant_label(feed_type, bag_weight_grams)
    if qty <= 0:
        raise ValueError(f"Dispatch quantity for {variant_label} must be greater than 0")

    row = _get_or_create_feed_row(
        db=db,
        client_id=client_id,
        feed_type=feed_type,
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
    for date, rm_name, quantity in consumption_rows:
        add_rm_consumption(
            db=db,
            client_id=client_id,
            rm_name=rm_name,
            quantity=float(quantity),
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
        add_feed_dispatched(
            db=db,
            client_id=client_id,
            feed_type=product_type,
            quantity=float(total_weight),
            date=date,
            weight_per_bag=weight_per_bag,
        )
