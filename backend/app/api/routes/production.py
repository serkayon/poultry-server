import re
from datetime import datetime, timedelta

from ..fastapi_compat import Blueprint, Response, jsonify, request
from sqlalchemy import select

from ..common import (
    DEFAULT_CLIENT_ID,
    db_session,
    error,
    json_body,
    parse_datetime,
    parse_float,
    required,
    serialize_batch,
    serialize_batch_material,
    serialize_report,
)
from ...models.config import ProductType, Recipe
from ...models.plc import PLCDataSnapshot
from ...models.production import ProductionBatch, ProductionBatchMaterial, ProductionReport
from ...services.plc_simulator import ensure_plc_live_data, get_or_create_machine_state
from ...services.production_runtime import (
    RUN_STATUS_COMPLETED,
    RUN_STATUS_PENDING,
    RUN_STATUS_STOPPED,
    normalize_batch_count,
    sync_active_batch_progress,
    try_post_batch_stock,
)
from ...services.stock import (
    add_feed_produced,
    add_rm_consumption,
    rebuild_rm_stock_ledger,
    _latest_rm_closing,
    _start_of_day,
)
from ...utils.export import (
    export_batch_report_pdf,
    export_table_to_csv,
    export_table_to_excel,
    export_table_to_pdf,
)

production_bp = Blueprint("production", __name__, url_prefix="/api/production")


def _get_rm_available_stock(db, client_id, rm_name, quantity, date):
    """Get available raw material stock. Returns tuple (available_qty, is_insufficient)."""
    from ...models.stock import RMStockLedger
    from sqlalchemy import select
    
    day = _start_of_day(date)
    row = db.execute(
        select(RMStockLedger).where(
            RMStockLedger.client_id == client_id,
            RMStockLedger.rm_name == rm_name,
            RMStockLedger.date == day,
        )
    ).scalars().one_or_none()
    
    if row:
        available = (
            float(row.opening_stock or 0)
            + float(row.received or 0)
            - float(row.consumption or 0)
        )
    else:
        available = _latest_rm_closing(db=db, client_id=client_id, rm_name=rm_name, day=day)
    
    required = float(quantity)
    is_insufficient = required > available
    return available, is_insufficient


def _parse_batch_no(raw_value: object, fallback: str | None = None) -> str:
    if raw_value in (None, ""):
        return fallback or ""
    value = str(raw_value).strip()
    if not value:
        return fallback or ""
    if len(value) > 64:
        raise ValueError("batch_no must be 64 characters or fewer")
    return value


def _display_batch_no(batch: ProductionBatch) -> str:
    return _parse_batch_no(batch.batch_no, fallback=str(batch.id))


def _resolve_batch_plc_window(batch: ProductionBatch) -> tuple[datetime, datetime]:
    start = batch.hmi_started_at or batch.date or batch.created_at or datetime.utcnow()
    status = (batch.hmi_status or "").strip().lower()

    if batch.hmi_completed_at is not None:
        end = batch.hmi_completed_at
    elif status in (RUN_STATUS_COMPLETED, RUN_STATUS_STOPPED):
        end = batch.last_modified_at or start
    else:
        end = datetime.utcnow()

    if end < start:
        end = start
    return start, end


def _parse_materials(raw_materials: object) -> list[dict]:
    if not isinstance(raw_materials, list) or len(raw_materials) == 0:
        raise ValueError("materials is required and must be a non-empty list")

    parsed: list[dict] = []
    for index, item in enumerate(raw_materials, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"materials[{index}] must be an object")

        rm_name = str(item.get("rm_name") or "").strip()
        if not rm_name:
            raise ValueError(f"materials[{index}].rm_name is required")

        try:
            quantity = float(item.get("quantity"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"materials[{index}].quantity must be a number") from exc
        if quantity <= 0:
            raise ValueError(f"materials[{index}].quantity must be greater than 0")

        parsed.append({"rm_name": rm_name, "quantity": quantity})
    return parsed


def _parse_bag_output_fields(payload: dict, *, required_fields: bool) -> tuple[float, float, float]:
    num_bags = parse_float(payload, "num_bags", required_field=required_fields)
    weight_per_bag = parse_float(payload, "weight_per_bag", required_field=required_fields)

    if num_bags is None or weight_per_bag is None:
        raise ValueError("num_bags and weight_per_bag are required")
    if num_bags <= 0:
        raise ValueError("num_bags must be greater than 0")
    if weight_per_bag <= 0:
        raise ValueError("weight_per_bag must be greater than 0")

    output_value = num_bags * weight_per_bag
    if output_value <= 0:
        raise ValueError("output must be greater than 0")
    return num_bags, weight_per_bag, output_value


def _parse_hmi_batch_count(raw_value: object) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError("batch_count must be an integer") from exc
    if value <= 0:
        raise ValueError("batch_count must be greater than 0")
    return value


def _parse_hmi_duration(raw_value: object) -> float:
    try:
        value = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError("duration_per_count_seconds must be a number") from exc
    if value <= 0:
        raise ValueError("duration_per_count_seconds must be greater than 0")
    return value


def _batch_no_exists(
    db,
    batch_no: str,
    *,
    exclude_batch_id: int | None = None,
) -> bool:
    normalized = str(batch_no or "").strip()
    if not normalized:
        return False

    query = select(ProductionBatch.id).where(
        ProductionBatch.client_id == DEFAULT_CLIENT_ID,
        ProductionBatch.batch_no.is_not(None),
        ProductionBatch.batch_no.ilike(normalized),
    )
    if exclude_batch_id is not None:
        query = query.where(ProductionBatch.id != exclude_batch_id)
    return db.execute(query.limit(1)).first() is not None


def _suggest_next_hmi_batch_no(db) -> str:
    pattern = re.compile(r"^BATCH(\d+)$", re.IGNORECASE)
    rows = db.execute(
        select(ProductionBatch.batch_no).where(
            ProductionBatch.client_id == DEFAULT_CLIENT_ID,
            ProductionBatch.batch_no.is_not(None),
        )
    ).all()

    max_sequence = 0
    for (batch_no,) in rows:
        if not isinstance(batch_no, str):
            continue
        match = pattern.match(batch_no.strip())
        if not match:
            continue
        try:
            seq = int(match.group(1))
        except ValueError:
            continue
        if seq > max_sequence:
            max_sequence = seq
    return f"BATCH{max_sequence + 1:05d}"


@production_bp.get("/hmi/batch-no/suggest")
def suggest_hmi_batch_no():
    with db_session() as db:
        return jsonify({"batch_no": _suggest_next_hmi_batch_no(db)})


@production_bp.get("/batches")
def list_batches():
    try:
        date = parse_datetime(request.args.get("date"), "date")
        from_date = parse_datetime(request.args.get("from_date"), "from_date")
        to_date = parse_datetime(request.args.get("to_date"), "to_date")
    except ValueError as exc:
        return error(str(exc))
    product_name = request.args.get("product_name")

    with db_session() as db:
        machine_state = get_or_create_machine_state(db)
        synced_batch = sync_active_batch_progress(db, machine_state=machine_state)
        if synced_batch:
            try_post_batch_stock(db, batch=synced_batch, client_id=DEFAULT_CLIENT_ID)
        active_batch_id = machine_state.active_batch_id

        query = select(ProductionBatch).where(ProductionBatch.client_id == DEFAULT_CLIENT_ID)
        if date:
            start = date.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
            query = query.where(ProductionBatch.date >= start, ProductionBatch.date < end)
        if from_date:
            query = query.where(ProductionBatch.date >= from_date)
        if to_date:
            query = query.where(ProductionBatch.date <= to_date)
        if product_name:
            query = query.where(ProductionBatch.product_name == product_name)
        query = query.order_by(ProductionBatch.date.desc())

        batches = db.execute(query).scalars().all()
        out = []
        for batch in batches:
            has_report = (
                db.execute(select(ProductionReport).where(ProductionReport.batch_id == batch.id))
                .scalars()
                .one_or_none()
                is not None
            )
            out.append(
                serialize_batch(
                    batch,
                    has_report=has_report,
                    is_active=batch.id == active_batch_id,
                )
            )
    return jsonify(out)


@production_bp.post("/batches")
def create_batch():
    try:
        payload = json_body()
        date = parse_datetime(required(payload, "date"), "date")
        if date is None:
            raise ValueError("date is required")
        product_name = required(payload, "product_name")
        recipe_id_raw = payload.get("recipe_id")
        recipe_id = int(recipe_id_raw) if recipe_id_raw not in (None, "") else None
        batch_no_value = _parse_batch_no(payload.get("batch_no"))
        num_bags_value, weight_per_bag_value, output_value = _parse_bag_output_fields(
            payload,
            required_fields=True,
        )
    except (ValueError, TypeError) as exc:
        return error(str(exc))

    with db_session() as db:
        if batch_no_value and _batch_no_exists(db, batch_no_value):
            return error("batch_no already exists. Use a unique batch number.")

        recipe = None
        if recipe_id is not None:
            recipe = db.get(Recipe, recipe_id)
            if not recipe:
                return error("Recipe not found")
            # Keep canonical recipe naming in production/stock ledgers.
            product_name = recipe.name
        else:
            recipe = (
                db.execute(select(Recipe).where(Recipe.name.ilike(product_name)))
                .scalars()
                .one_or_none()
            )
            if not recipe:
                return error("Invalid product type. Select a valid recipe.")
            recipe_id = recipe.id
            product_name = recipe.name

        try:
            raw_materials_payload = payload.get("materials")
            if isinstance(raw_materials_payload, list) and len(raw_materials_payload) > 0:
                materials = _parse_materials(raw_materials_payload)
            elif recipe and recipe.materials:
                materials = [
                    {
                        "rm_name": item.rm_name,
                        "quantity": float(item.quantity),
                    }
                    for item in recipe.materials
                ]
            else:
                raise ValueError("materials is required and must be a non-empty list")
        except ValueError as exc:
            return error(str(exc))

        # Validate stock availability BEFORE creating batch
        insufficient_materials = []
        for material in materials:
            available, is_insufficient = _get_rm_available_stock(
                db=db,
                client_id=DEFAULT_CLIENT_ID,
                rm_name=material["rm_name"],
                quantity=material["quantity"],
                date=date,
            )
            if is_insufficient:
                insufficient_materials.append(
                    f"{material['rm_name']} (required: {material['quantity']}, available: {available})"
                )
        
        if insufficient_materials:
            error_msg = "Insufficient raw material stock:\n" + "\n".join(
                f"- {item}" for item in insufficient_materials
            )
            return error(error_msg)

        try:
            now = datetime.utcnow()
            batch = ProductionBatch(
                client_id=DEFAULT_CLIENT_ID,
                batch_no=batch_no_value or None,
                date=date,
                product_name=product_name,
                batch_size=parse_float(payload, "batch_size", required_field=True),
                mop=parse_float(payload, "mop"),
                water=parse_float(payload, "water"),
                num_bags=num_bags_value,
                weight_per_bag=weight_per_bag_value,
                output=output_value,
                recipe_id=recipe_id,
                hmi_duration_seconds=None,
                hmi_completed_count=normalize_batch_count(parse_float(payload, "batch_size") or 0),
                hmi_status=RUN_STATUS_COMPLETED,
                hmi_started_at=now,
                hmi_completed_at=now,
                stock_posted=False,
                last_modified_at=now,
            )
        except ValueError as exc:
            return error(str(exc))

        try:
            db.add(batch)
            db.flush()
            if not batch.batch_no:
                batch.batch_no = str(batch.id)
            db.refresh(batch)

            material_rows: list[ProductionBatchMaterial] = []
            for material in materials:
                row = ProductionBatchMaterial(
                    batch_id=batch.id,
                    rm_name=material["rm_name"],
                    quantity=material["quantity"],
                )
                db.add(row)
                material_rows.append(row)
                add_rm_consumption(
                    db=db,
                    client_id=DEFAULT_CLIENT_ID,
                    rm_name=material["rm_name"],
                    quantity=material["quantity"],
                    date=batch.date,
                )
            db.flush()

            add_feed_produced(
                db=db,
                client_id=DEFAULT_CLIENT_ID,
                feed_type=batch.product_name,
                quantity=batch.output,
                date=batch.date,
                weight_per_bag=batch.weight_per_bag,
            )
            batch.stock_posted = True

            response = serialize_batch(batch, has_report=False, is_active=False)
            response["materials"] = [serialize_batch_material(row) for row in material_rows]
            return jsonify(response)
        except ValueError as exc:
            return error(str(exc))


@production_bp.post("/hmi/batches")
def create_hmi_batch():
    try:
        payload = json_body()
        batch_no_input = _parse_batch_no(payload.get("batch_no"))
        batch_count = _parse_hmi_batch_count(required(payload, "batch_count"))
        duration_seconds = _parse_hmi_duration(required(payload, "duration_per_count_seconds"))
        date = parse_datetime(payload.get("date"), "date") or datetime.utcnow()
    except (ValueError, TypeError) as exc:
        return error(str(exc))

    with db_session() as db:
        batch_no = batch_no_input or _suggest_next_hmi_batch_no(db)
        if _batch_no_exists(db, batch_no):
            return error(
                f"batch_no already exists. Try {_suggest_next_hmi_batch_no(db)}."
            )
        batch = ProductionBatch(
            client_id=DEFAULT_CLIENT_ID,
            batch_no=batch_no,
            date=date,
            product_name="",
            batch_size=float(batch_count),
            mop=None,
            water=None,
            num_bags=None,
            weight_per_bag=None,
            output=0,
            recipe_id=None,
            hmi_duration_seconds=duration_seconds,
            hmi_completed_count=0,
            hmi_status=RUN_STATUS_PENDING,
            hmi_started_at=None,
            hmi_completed_at=None,
            stock_posted=False,
            last_modified_at=datetime.utcnow(),
        )
        db.add(batch)
        db.flush()
        return jsonify(serialize_batch(batch, has_report=False, is_active=False))


@production_bp.get("/batches/<int:batch_id>")
def get_batch(batch_id: int):
    with db_session() as db:
        machine_state = get_or_create_machine_state(db)
        synced_batch = sync_active_batch_progress(db, machine_state=machine_state)
        if synced_batch:
            try_post_batch_stock(db, batch=synced_batch, client_id=DEFAULT_CLIENT_ID)
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
        if not batch:
            return error("Batch not found", 404)

        report = (
            db.execute(select(ProductionReport).where(ProductionReport.batch_id == batch_id))
            .scalars()
            .one_or_none()
        )
        return jsonify(
            {
                "batch": serialize_batch(
                    batch,
                    has_report=report is not None,
                    is_active=batch.id == machine_state.active_batch_id,
                ),
                "report": serialize_report(report),
                "materials": [
                    serialize_batch_material(row)
                    for row in db.execute(
                        select(ProductionBatchMaterial)
                        .where(ProductionBatchMaterial.batch_id == batch_id)
                        .order_by(ProductionBatchMaterial.id.asc())
                    )
                    .scalars()
                    .all()
                ],
            }
        )


@production_bp.put("/batches/<int:batch_id>/details")
def update_batch_details(batch_id: int):
    try:
        payload = json_body()
    except ValueError as exc:
        return error(str(exc))

    try:
        with db_session() as db:
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
            if not batch:
                return error("Batch not found", 404)

            batch_updated = False

            if "date" in payload:
                try:
                    parsed_date = parse_datetime(payload.get("date"), "date")
                except ValueError as exc:
                    return error(str(exc))
                if parsed_date is None:
                    return error("date is required")
                batch.date = parsed_date
                batch_updated = True

            if "batch_no" in payload:
                try:
                    parsed_batch_no = _parse_batch_no(payload.get("batch_no"), fallback=str(batch.id))
                except ValueError as exc:
                    return error(str(exc))
                if _batch_no_exists(db, parsed_batch_no, exclude_batch_id=batch.id):
                    return error("batch_no already exists. Use a unique batch number.")
                batch.batch_no = parsed_batch_no
                batch_updated = True

            selected_recipe_materials: list[dict] | None = None
            if "product_name" in payload:
                product_name = str(payload.get("product_name") or "").strip()
                if product_name:
                    product_type_exists = (
                        db.execute(select(ProductType).where(ProductType.name.ilike(product_name)))
                        .scalars()
                        .one_or_none()
                    )
                    if not product_type_exists:
                        return error("Invalid product_name. Select a valid product type.")
                    selected_recipe = (
                        db.execute(select(Recipe).where(Recipe.name.ilike(product_name)))
                        .scalars()
                        .one_or_none()
                    )
                    if not selected_recipe:
                        return error("Recipe not found for selected product.")
                    batch.recipe_id = selected_recipe.id
                    selected_recipe_materials = [
                        {
                            "rm_name": item.rm_name,
                            "quantity": float(item.quantity),
                        }
                        for item in selected_recipe.materials
                    ]
                else:
                    batch.recipe_id = None
                batch.product_name = product_name
                batch_updated = True

            parsed_materials: list[dict] | None = None
            if "materials" in payload:
                try:
                    parsed_materials = _parse_materials(payload.get("materials"))
                except ValueError as exc:
                    return error(str(exc))
            elif selected_recipe_materials is not None:
                parsed_materials = selected_recipe_materials

            if "batch_size" in payload:
                try:
                    batch_size_value = parse_float(payload, "batch_size")
                except ValueError as exc:
                    return error(str(exc))
                if batch_size_value is None or batch_size_value <= 0:
                    return error("batch_size must be greater than 0")
                batch.batch_size = batch_size_value
                batch_updated = True

            if "mop" in payload:
                try:
                    batch.mop = parse_float(payload, "mop")
                except ValueError as exc:
                    return error(str(exc))
                batch_updated = True

            if "water" in payload:
                try:
                    batch.water = parse_float(payload, "water")
                except ValueError as exc:
                    return error(str(exc))
                batch_updated = True

            if "num_bags" in payload or "weight_per_bag" in payload:
                if normalize_batch_count(batch.batch_size) > 0 and (batch.hmi_status or "").lower() != RUN_STATUS_COMPLETED:
                    return error("Bag details can be entered only after batch count is completed.")
                candidate_num_bags = (
                    parse_float(payload, "num_bags")
                    if "num_bags" in payload
                    else float(batch.num_bags or 0)
                )
                candidate_weight_per_bag = (
                    parse_float(payload, "weight_per_bag")
                    if "weight_per_bag" in payload
                    else float(batch.weight_per_bag or 0)
                )
                if candidate_num_bags is None or candidate_num_bags <= 0:
                    return error("num_bags must be greater than 0")
                if candidate_weight_per_bag is None or candidate_weight_per_bag <= 0:
                    return error("weight_per_bag must be greater than 0")
                batch.num_bags = candidate_num_bags
                batch.weight_per_bag = candidate_weight_per_bag
                batch.output = candidate_num_bags * candidate_weight_per_bag
                batch_updated = True

            if "output" in payload:
                if "num_bags" not in payload and "weight_per_bag" not in payload:
                    try:
                        output_value = parse_float(payload, "output")
                    except ValueError as exc:
                        return error(str(exc))
                    if output_value is None or output_value <= 0:
                        return error("output must be greater than 0")
                    batch.output = output_value
                    batch_updated = True

            if parsed_materials is not None:
                existing_rows = (
                    db.execute(select(ProductionBatchMaterial).where(ProductionBatchMaterial.batch_id == batch.id))
                    .scalars()
                    .all()
                )
                for row in existing_rows:
                    db.delete(row)
                db.flush()
                for item in parsed_materials:
                    db.add(
                        ProductionBatchMaterial(
                            batch_id=batch.id,
                            rm_name=item["rm_name"],
                            quantity=item["quantity"],
                        )
                    )
                db.flush()
                rebuild_rm_stock_ledger(db=db, client_id=DEFAULT_CLIENT_ID)
                batch_updated = True

            if batch_updated:
                batch.last_modified_at = datetime.utcnow()

            try_post_batch_stock(db, batch=batch, client_id=DEFAULT_CLIENT_ID)
            machine_state = get_or_create_machine_state(db)
            has_report = (
                db.execute(select(ProductionReport).where(ProductionReport.batch_id == batch.id))
                .scalars()
                .one_or_none()
                is not None
            )
            db.flush()
            return jsonify(
                {
                    "batch": serialize_batch(
                        batch,
                        has_report=has_report,
                        is_active=batch.id == machine_state.active_batch_id,
                    ),
                    "materials": [
                        serialize_batch_material(row)
                        for row in db.execute(
                            select(ProductionBatchMaterial)
                            .where(ProductionBatchMaterial.batch_id == batch.id)
                            .order_by(ProductionBatchMaterial.id.asc())
                        )
                        .scalars()
                        .all()
                    ],
                    "stock_posted": bool(batch.stock_posted),
                }
            )
    except ValueError as exc:
        return error(str(exc))


@production_bp.post("/report")
def submit_production_report():
    try:
        payload = json_body()
        batch_id = int(required(payload, "batch_id"))
    except (ValueError, TypeError) as exc:
        return error(str(exc))

    try:
        with db_session() as db:
            batch = db.get(ProductionBatch, batch_id)
            if not batch:
                return error("Batch not found", 404)

            report = (
                db.execute(select(ProductionReport).where(ProductionReport.batch_id == batch_id))
                .scalars()
                .one_or_none()
            )
            if not report:
                report = ProductionReport(batch_id=batch_id)
                db.add(report)

            report_fields = [
                "protein",
                "fat",
                "fiber",
                "ash",
                "calcium",
                "phosphorus",
                "salt",
                "hm_retention",
                "mixer_moisture",
                "conditioner_moisture",
                "moisture_addition",
                "final_feed_moisture",
                "water_activity",
                "hardness",
                "pellet_diameter",
                "fines",
            ]
            for field in report_fields:
                if field in payload:
                    setattr(report, field, parse_float(payload, field))

            db.flush()
            return jsonify({"id": report.id, "batch_id": batch_id, "stock_posted": bool(batch.stock_posted)})
    except ValueError as exc:
        return error(str(exc))


@production_bp.get("/consumption")
def consumption_report():
    try:
        from_date = parse_datetime(request.args.get("from_date"), "from_date")
        to_date = parse_datetime(request.args.get("to_date"), "to_date")
    except ValueError as exc:
        return error(str(exc))

    with db_session() as db:
        query = (
            select(ProductionBatch)
            .where(ProductionBatch.client_id == DEFAULT_CLIENT_ID)
            .order_by(ProductionBatch.date.desc(), ProductionBatch.id.desc())
        )
        if from_date:
            query = query.where(ProductionBatch.date >= from_date)
        if to_date:
            query = query.where(ProductionBatch.date <= to_date)
        batches = db.execute(query).scalars().all()

        rows: list[dict] = []
        for batch in batches:
            total_batch = float(batch.batch_size or 0)
            batch_rows = (
                db.execute(
                    select(ProductionBatchMaterial)
                    .where(ProductionBatchMaterial.batch_id == batch.id)
                    .order_by(ProductionBatchMaterial.id.asc())
                )
                .scalars()
                .all()
            )

            batch_weight_per_run = 0.0
            batch_total_weight = 0.0
            for material in batch_rows:
                weight_per_batch = float(material.quantity or 0)
                total_weight = weight_per_batch * total_batch
                batch_weight_per_run += weight_per_batch
                batch_total_weight += total_weight
                rows.append(
                    {
                        "batch_id": batch.id,
                        "batch_no": _display_batch_no(batch),
                        "date": batch.date.strftime("%Y-%m-%d"),
                        "product_name": batch.product_name,
                        "rm_name": material.rm_name,
                        "weight_per_batch": weight_per_batch,
                        "total_batch": total_batch,
                        "total_weight": total_weight,
                        "is_total": False,
                    }
                )

            rows.append(
                {
                    "batch_id": batch.id,
                    "batch_no": _display_batch_no(batch),
                    "date": batch.date.strftime("%Y-%m-%d"),
                    "product_name": batch.product_name,
                    "rm_name": "TOTAL",
                    "weight_per_batch": batch_weight_per_run,
                    "total_batch": total_batch,
                    "total_weight": batch_total_weight,
                    "is_total": True,
                }
            )

    return jsonify(rows)


@production_bp.get("/download")
def download_production():
    try:
        from_date = parse_datetime(request.args.get("from_date"), "from_date")
        to_date = parse_datetime(request.args.get("to_date"), "to_date")
    except ValueError as exc:
        return error(str(exc))
    file_format = request.args.get("format", "pdf").lower()

    with db_session() as db:
        query = (
            select(ProductionBatch, ProductionReport)
            .outerjoin(ProductionReport, ProductionBatch.id == ProductionReport.batch_id)
            .where(ProductionBatch.client_id == DEFAULT_CLIENT_ID)
            .order_by(ProductionBatch.date.desc())
        )
        if from_date:
            query = query.where(ProductionBatch.date >= from_date)
        if to_date:
            query = query.where(ProductionBatch.date <= to_date)
        rows = db.execute(query).all()

    headers = [
        "Date",
        "Batch No",
        "Product",
        "Batch Size",
        "MOP",
        "Water",
        "No. of Bags",
        "Weight/Bag",
        "Output",
        "Protein",
        "Fat",
        "Fiber",
        "Ash",
        "Ca",
        "P",
        "Salt",
        "Hardness",
        "Fines",
    ]
    data_rows = [
        (
            batch.date.strftime("%Y-%m-%d"),
            _display_batch_no(batch),
            batch.product_name,
            batch.batch_size,
            batch.mop or "",
            batch.water or "",
            batch.num_bags or "",
            batch.weight_per_bag or "",
            batch.output,
            report.protein if report else "",
            report.fat if report else "",
            report.fiber if report else "",
            report.ash if report else "",
            report.calcium if report else "",
            report.phosphorus if report else "",
            report.salt if report else "",
            report.hardness if report else "",
            report.fines if report else "",
        )
        for batch, report in rows
    ]

    if file_format == "csv":
        return Response(
            export_table_to_csv(headers, data_rows),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=production_report.csv"},
        )
    if file_format in ("excel", "xlsx"):
        return Response(
            export_table_to_excel("Production Report", headers, data_rows),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=production_report.xlsx"},
        )
    return Response(
        export_table_to_pdf("Production Report", headers, data_rows),
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=production_report.pdf"},
    )
# 🔥 DOWNLOAD SINGLE BATCH REPORT
@production_bp.get("/<int:batch_id>/download")
def download_single_batch(batch_id: int):
    file_format = request.args.get("format", "pdf").lower()

    with db_session() as db:
        row = (
            db.execute(
                select(ProductionBatch, ProductionReport)
                .outerjoin(
                    ProductionReport,
                    ProductionBatch.id == ProductionReport.batch_id,
                )
                .where(
                    ProductionBatch.id == batch_id,
                    ProductionBatch.client_id == DEFAULT_CLIENT_ID,
                )
            )
            .first()
        )

        if not row:
            return error("Batch not found", 404)

        batch, report = row
        batch_start, batch_end = _resolve_batch_plc_window(batch)
        window_seconds = max(1, int((batch_end - batch_start).total_seconds()))
        window_minutes = max(1, int((window_seconds + 59) // 60))
        ensure_plc_live_data(db, minutes=max(60, window_minutes))

        if not report:
            return error("Report not available for this batch", 404)

        materials = (
            db.execute(
                select(ProductionBatchMaterial)
                .where(ProductionBatchMaterial.batch_id == batch_id)
                .order_by(ProductionBatchMaterial.id.asc())
            )
            .scalars()
            .all()
        )
        plc_rows = (
            db.execute(
                select(PLCDataSnapshot)
                .where(
                    PLCDataSnapshot.recorded_at >= batch_start,
                    PLCDataSnapshot.recorded_at <= batch_end,
                )
                .order_by(PLCDataSnapshot.recorded_at.asc())
            )
            .scalars()
            .all()
        )

    headers = [
        "Date",
        "Batch No",
        "Product",
        "Batch Size",
        "MOP",
        "Water",
        "No. of Bags",
        "Weight/Bag",
        "Output",
        "Protein",
        "Fat",
        "Fiber",
        "Ash",
        "Calcium",
        "Phosphorus",
        "Salt",
        "Hardness",
        "Fines",
    ]

    data_rows = [(
        batch.date.strftime("%Y-%m-%d"),
        _display_batch_no(batch),
        batch.product_name,
        batch.batch_size,
        batch.mop or "",
        batch.water or "",
        batch.num_bags or "",
        batch.weight_per_bag or "",
        batch.output,
        report.protein or "",
        report.fat or "",
        report.fiber or "",
        report.ash or "",
        report.calcium or "",
        report.phosphorus or "",
        report.salt or "",
        report.hardness or "",
        report.fines or "",
    )]

    filename = f"batch_{batch_id}_report"

    if file_format == "csv":
        return Response(
            export_table_to_csv(headers, data_rows),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}.csv"},
        )

    if file_format in ("excel", "xlsx"):
        return Response(
            export_table_to_excel("Batch Report", headers, data_rows),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}.xlsx"},
        )

    return Response(
        export_batch_report_pdf(
            batch,
            report,
            materials,
            plc_rows=plc_rows,
            plc_start=batch_start,
            plc_end=batch_end,
        ),
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}.pdf"},
    )
