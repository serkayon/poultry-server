from datetime import datetime

from ..fastapi_compat import Blueprint, Response, jsonify, request
from sqlalchemy import func, or_, select

from ..common import (
    DEFAULT_CLIENT_ID,
    db_session,
    error,
    json_body,
    parse_datetime,
    parse_float,
    required,
    dt,
    serialize_raw_entry,
)
from ...models.config import RecipeMaterial
from ...models.production import ProductionBatchMaterial
from ...models.raw_material import RawMaterialEntry, RawMaterialLabReport, RawMaterialType
from ...models.stock import RMStockLedger
from ...services.stock import rebuild_rm_stock_ledger
from ...utils.export import (
    export_multi_table_to_excel,
    export_multi_table_to_pdf,
    export_table_to_csv,
    export_table_to_excel,
    export_table_to_pdf,
)

raw_material_bp = Blueprint("raw_material", __name__, url_prefix="/api/raw-material")


def _serialize_lab_report(report: RawMaterialLabReport) -> dict:
    return {
        "id": report.id,
        "entry_id": report.entry_id,
        "protein": report.protein,
        "fat": report.fat,
        "nitrogen": report.nitrogen,
        "fiber": report.fiber,
        "ash": report.ash,
        "calcium": report.calcium,
        "phosphorus": report.phosphorus,
        "salt": report.salt,
        "moisture": report.moisture,
        "fungus": report.fungus,
        "broke": report.broke,
        "water_damage": report.water_damage,
        "small": report.small,
        "dunkey": report.dunkey,
        "fm": report.fm,
        "maize_count": report.maize_count,
        "colour": report.colour,
        "smell": report.smell,
        "created_at": dt(report.created_at),
    }


@raw_material_bp.get("/types")
def list_rm_types():
    with db_session() as db:
        rows = (
            db.execute(select(RawMaterialType).order_by(RawMaterialType.name.asc()))
            .scalars()
            .all()
        )
    return jsonify(
        [
            {
                "id": row.id,
                "name": row.name,
                "created_at": dt(row.created_at),
                "last_modified_at": dt(row.last_modified_at or row.created_at),
            }
            for row in rows
        ]
    )


@raw_material_bp.post("/types")
def add_rm_type():
    name = request.args.get("name", "").strip()
    if not name:
        return error("RM type name is required")

    with db_session() as db:
        existing = (
            db.execute(
                select(RawMaterialType).where(func.lower(RawMaterialType.name) == name.lower())
            )
            .scalars()
            .one_or_none()
        )
        if existing:
            return error("RM type already exists")

        row = RawMaterialType(name=name, last_modified_at=datetime.utcnow())
        db.add(row)
        db.flush()
        return jsonify(
            {
                "id": row.id,
                "name": row.name,
                "created_at": dt(row.created_at),
                "last_modified_at": dt(row.last_modified_at or row.created_at),
            }
        )


@raw_material_bp.put("/types/<int:type_id>")
def update_rm_type(type_id: int):
    name = request.args.get("name", "").strip()
    if not name:
        return error("RM type name is required")

    with db_session() as db:
        row = db.get(RawMaterialType, type_id)
        if not row:
            return error("RM type not found", 404)

        existing = (
            db.execute(
                select(RawMaterialType).where(
                    func.lower(RawMaterialType.name) == name.lower(),
                    RawMaterialType.id != type_id,
                )
            )
            .scalars()
            .one_or_none()
        )
        if existing:
            return error("RM type already exists")

        old_name = row.name
        row.name = name
        row.last_modified_at = datetime.utcnow()

        recipe_rows = (
            db.execute(select(RecipeMaterial).where(func.lower(RecipeMaterial.rm_name) == old_name.lower()))
            .scalars()
            .all()
        )
        for item in recipe_rows:
            item.rm_name = name

        entry_rows = (
            db.execute(select(RawMaterialEntry).where(func.lower(RawMaterialEntry.rm_type) == old_name.lower()))
            .scalars()
            .all()
        )
        for item in entry_rows:
            item.rm_type = name

        batch_material_rows = (
            db.execute(
                select(ProductionBatchMaterial).where(
                    func.lower(ProductionBatchMaterial.rm_name) == old_name.lower()
                )
            )
            .scalars()
            .all()
        )
        for item in batch_material_rows:
            item.rm_name = name

        stock_rows = (
            db.execute(select(RMStockLedger).where(func.lower(RMStockLedger.rm_name) == old_name.lower()))
            .scalars()
            .all()
        )
        for item in stock_rows:
            item.rm_name = name

        db.flush()
        return jsonify(
            {
                "id": row.id,
                "name": row.name,
                "created_at": dt(row.created_at),
                "last_modified_at": dt(row.last_modified_at or row.created_at),
            }
        )


@raw_material_bp.delete("/types/<int:type_id>")
def delete_rm_type(type_id: int):
    with db_session() as db:
        row = db.get(RawMaterialType, type_id)
        if not row:
            return error("RM type not found", 404)

        in_use_recipe = (
            db.execute(select(RecipeMaterial).where(func.lower(RecipeMaterial.rm_name) == row.name.lower()))
            .scalars()
            .first()
            is not None
        )
        if in_use_recipe:
            return error("Cannot delete RM type because it is used in recipes. Edit recipes first.")

        db.delete(row)
        db.flush()
        return jsonify({"id": type_id, "deleted": True})


@raw_material_bp.get("")
def list_raw_material_entries():
    try:
        from_date = parse_datetime(request.args.get("from_date"), "from_date")
        to_date = parse_datetime(request.args.get("to_date"), "to_date")
    except ValueError as exc:
        return error(str(exc))
    rm_type = request.args.get("rm_type")

    with db_session() as db:
        query = select(RawMaterialEntry).where(RawMaterialEntry.client_id == DEFAULT_CLIENT_ID)
        if from_date:
            query = query.where(RawMaterialEntry.date >= from_date)
        if to_date:
            query = query.where(RawMaterialEntry.date <= to_date)
        if rm_type:
            query = query.where(RawMaterialEntry.rm_type == rm_type)
        query = query.order_by(RawMaterialEntry.date.desc())

        entries = db.execute(query).scalars().all()
        out = []
        for entry in entries:
            has_lab = (
                db.execute(
                    select(RawMaterialLabReport).where(RawMaterialLabReport.entry_id == entry.id)
                )
                .scalars()
                .one_or_none()
                is not None
            )
            out.append(serialize_raw_entry(entry, has_lab))
    return jsonify(out)


@raw_material_bp.post("")
def create_raw_material_entry():
    try:
        payload = json_body()
        date = parse_datetime(required(payload, "date"), "date")
        if date is None:
            raise ValueError("date is required")
        total_weight = parse_float(payload, "total_weight", required_field=True)
        if total_weight is None or total_weight <= 0:
            raise ValueError("total_weight must be greater than 0")
        entry = RawMaterialEntry(
            client_id=DEFAULT_CLIENT_ID,
            date=date,
            rm_type=required(payload, "rm_type"),
            supplier=required(payload, "supplier"),
            challan_no=required(payload, "challan_no"),
            vehicle_no=required(payload, "vehicle_no"),
            total_weight=total_weight,
            remarks=payload.get("remarks"),
        )
    except ValueError as exc:
        return error(str(exc))

    try:
        with db_session() as db:
            db.add(entry)
            db.flush()
            db.refresh(entry)
            rebuild_rm_stock_ledger(db=db, client_id=DEFAULT_CLIENT_ID)
            return jsonify(serialize_raw_entry(entry, has_lab=False))
    except ValueError as exc:
        return error(str(exc))


@raw_material_bp.put("/<int:entry_id>")
def update_raw_material_entry(entry_id: int):
    try:
        payload = json_body()
        date = parse_datetime(required(payload, "date"), "date")
        if date is None:
            raise ValueError("date is required")
        rm_type = required(payload, "rm_type")
        supplier = required(payload, "supplier")
        challan_no = required(payload, "challan_no")
        vehicle_no = required(payload, "vehicle_no")
        total_weight = parse_float(payload, "total_weight", required_field=True)
        if total_weight is None or total_weight <= 0:
            raise ValueError("total_weight must be greater than 0")
    except ValueError as exc:
        return error(str(exc))

    try:
        with db_session() as db:
            entry = db.get(RawMaterialEntry, entry_id)
            if not entry or entry.client_id != DEFAULT_CLIENT_ID:
                return error("Entry not found", 404)

            entry.date = date
            entry.rm_type = rm_type
            entry.supplier = supplier
            entry.challan_no = challan_no
            entry.vehicle_no = vehicle_no
            entry.total_weight = total_weight
            entry.remarks = payload.get("remarks")
            entry.last_modified_at = datetime.utcnow()
            db.flush()

            rebuild_rm_stock_ledger(db=db, client_id=DEFAULT_CLIENT_ID)

            has_lab = (
                db.execute(select(RawMaterialLabReport).where(RawMaterialLabReport.entry_id == entry.id))
                .scalars()
                .one_or_none()
                is not None
            )
            return jsonify(serialize_raw_entry(entry, has_lab=has_lab))
    except ValueError as exc:
        return error(str(exc))


@raw_material_bp.post("/lab-report")
def submit_raw_material_lab_report():
    try:
        payload = json_body()
        entry_id = int(required(payload, "entry_id"))
    except (ValueError, TypeError) as exc:
        return error(str(exc))

    with db_session() as db:
        entry = db.get(RawMaterialEntry, entry_id)
        if not entry:
            return error("Entry not found", 404)

        report = (
            db.execute(select(RawMaterialLabReport).where(RawMaterialLabReport.entry_id == entry_id))
            .scalars()
            .one_or_none()
        )
        if not report:
            report = RawMaterialLabReport(entry_id=entry_id)
            db.add(report)

        report.protein = parse_float(payload, "protein")
        report.fat = parse_float(payload, "fat")
        report.nitrogen = parse_float(payload, "nitrogen")
        report.fiber = parse_float(payload, "fiber")
        report.ash = parse_float(payload, "ash")
        report.calcium = parse_float(payload, "calcium")
        report.phosphorus = parse_float(payload, "phosphorus")
        report.salt = parse_float(payload, "salt")
        report.moisture = parse_float(payload, "moisture")
        report.fungus = payload.get("fungus")
        report.broke = payload.get("broke")
        report.water_damage = payload.get("water_damage")
        report.small = payload.get("small")
        report.dunkey = payload.get("dunkey")
        report.fm = payload.get("fm")
        report.maize_count = payload.get("maize_count")
        report.colour = payload.get("colour")
        report.smell = payload.get("smell")
        db.flush()
        return jsonify({"id": report.id, "entry_id": entry_id})


@raw_material_bp.get("/lab-report/<int:entry_id>")
def get_raw_material_lab_report(entry_id: int):
    with db_session() as db:
        entry = db.get(RawMaterialEntry, entry_id)
        if not entry or entry.client_id != DEFAULT_CLIENT_ID:
            return error("Entry not found", 404)

        report = (
            db.execute(select(RawMaterialLabReport).where(RawMaterialLabReport.entry_id == entry_id))
            .scalars()
            .one_or_none()
        )
        if not report:
            return jsonify({"entry_id": entry_id, "report": None})
        return jsonify({"entry_id": entry_id, "report": _serialize_lab_report(report)})


@raw_material_bp.get("/download")
def download_raw_material():
    try:
        from_date = parse_datetime(request.args.get("from_date"), "from_date")
        to_date = parse_datetime(request.args.get("to_date"), "to_date")
    except ValueError as exc:
        return error(str(exc))
    rm_type = str(request.args.get("rm_type") or "").strip()
    query_text = str(request.args.get("q") or "").strip()

    file_format = request.args.get("format", "pdf").lower()

    with db_session() as db:
        query = select(RawMaterialEntry).where(RawMaterialEntry.client_id == DEFAULT_CLIENT_ID)
        if from_date:
            query = query.where(RawMaterialEntry.date >= from_date)
        if to_date:
            query = query.where(RawMaterialEntry.date <= to_date)
        if rm_type:
            query = query.where(func.lower(RawMaterialEntry.rm_type) == rm_type.lower())
        if query_text:
            pattern = f"%{query_text}%"
            query = query.where(
                or_(
                    RawMaterialEntry.rm_type.ilike(pattern),
                    RawMaterialEntry.supplier.ilike(pattern),
                    RawMaterialEntry.vehicle_no.ilike(pattern),
                    RawMaterialEntry.challan_no.ilike(pattern),
                )
            )
        query = query.order_by(RawMaterialEntry.date.desc())
        entries = db.execute(query).scalars().all()

    headers = ["Date", "RM Type", "Supplier", "Challan No", "Vehicle No", "Total Weight", "Remarks"]
    rows = [
        (
            row.date.strftime("%Y-%m-%d"),
            row.rm_type,
            row.supplier,
            row.challan_no,
            row.vehicle_no,
            row.total_weight,
            row.remarks or "",
        )
        for row in entries
    ]

    if file_format == "csv":
        return Response(
            export_table_to_csv(headers, rows),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=raw_material_report.csv"},
        )
    if file_format in ("excel", "xlsx"):
        return Response(
            export_table_to_excel("Raw Material Report", headers, rows),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=raw_material_report.xlsx"},
        )
    return Response(
        export_table_to_pdf("Raw Material Report", headers, rows),
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=raw_material_report.pdf"},
    )


@raw_material_bp.get("/<int:entry_id>/download")
def download_raw_material_entry(entry_id: int):
    file_format = request.args.get("format", "pdf").lower()
    if file_format not in ("pdf", "excel", "xlsx"):
        return error("format must be one of: pdf, excel, xlsx")

    with db_session() as db:
        entry = (
            db.execute(
                select(RawMaterialEntry).where(
                    RawMaterialEntry.id == entry_id,
                    RawMaterialEntry.client_id == DEFAULT_CLIENT_ID,
                )
            )
            .scalars()
            .one_or_none()
        )
        if not entry:
            return error("Entry not found", 404)

        report = (
            db.execute(select(RawMaterialLabReport).where(RawMaterialLabReport.entry_id == entry_id))
            .scalars()
            .one_or_none()
        )

    details_headers = ["Field", "Value"]
    details_rows = [
        ("Entry ID", entry.id),
        ("Date", entry.date.strftime("%Y-%m-%d")),
        ("RM Type", entry.rm_type),
        ("Supplier", entry.supplier),
        ("Challan No", entry.challan_no),
        ("Vehicle No", entry.vehicle_no),
        ("Total Weight", entry.total_weight),
        ("Remarks", entry.remarks or ""),
        ("Created At", dt(entry.created_at) or ""),
        ("Last Modified At", dt(entry.last_modified_at) or ""),
    ]

    is_maize_entry = str(entry.rm_type or "").strip().lower() == "maize"
    if report:
        basic_lab_rows = [
            ("Protein", report.protein if report.protein is not None else ""),
            ("Fat", report.fat if report.fat is not None else ""),
            ("Fiber", report.fiber if report.fiber is not None else ""),
            ("Ash", report.ash if report.ash is not None else ""),
            ("Calcium", report.calcium if report.calcium is not None else ""),
            ("Phosphorus", report.phosphorus if report.phosphorus is not None else ""),
            ("Salt", report.salt if report.salt is not None else ""),
            ("Moisture", report.moisture if report.moisture is not None else ""),
        ]
        maize_only_lab_rows = [
            ("Fungus", report.fungus or ""),
            ("Broke", report.broke or ""),
            ("Water Damage", report.water_damage or ""),
            ("Small", report.small or ""),
            ("Dunkey", report.dunkey or ""),
            ("FM", report.fm or ""),
            ("Maize Count", report.maize_count or ""),
            ("Colour", report.colour or ""),
            ("Smell", report.smell or ""),
        ]
        lab_rows = basic_lab_rows + (maize_only_lab_rows if is_maize_entry else [])
    else:
        lab_rows = [("Lab Report", "Not available")]

    sections = [
        {
            "title": "Raw Material Entry Details",
            "headers": details_headers,
            "rows": details_rows,
            "sheet_name": "Entry Details",
        },
        {
            "title": "Lab Report",
            "headers": ["Parameter", "Value"],
            "rows": lab_rows,
            "sheet_name": "Lab Report",
        },
    ]

    filename = f"raw_material_entry_{entry_id}_report"
    if file_format in ("excel", "xlsx"):
        excel_rows = details_rows + [("", "")] + [("Lab Report", "")] + lab_rows
        return Response(
            export_table_to_excel(
                "Raw Material Entry Report",
                ["Field / Parameter", "Value"],
                excel_rows,
                sheet_name="Entry Report",
            ),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}.xlsx"},
        )
    return Response(
        export_multi_table_to_pdf("Raw Material Entry Report", sections),
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}.pdf"},
    )
