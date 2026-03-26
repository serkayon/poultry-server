from ..fastapi_compat import Blueprint, Response, jsonify, request
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import datetime

from ..common import (
    DEFAULT_CLIENT_ID,
    db_session,
    error,
    json_body,
    parse_datetime,
    parse_float,
    required,
    dt,
)
from ...models.config import ProductType
from ...models.dispatch import DispatchEntry, DispatchProduct
from ...services.stock import add_feed_dispatched, rebuild_feed_stock_ledger
from ...utils.export import export_table_to_csv, export_table_to_excel, export_table_to_pdf
from ...utils.invoice import generate_invoice_pdf

dispatch_bp = Blueprint("dispatch", __name__, url_prefix="/api/dispatch")


def _serialize_dispatch(entry: DispatchEntry) -> dict:
    """Serialize a dispatch entry with its products."""
    return {
        "id": entry.id,
        "date": dt(entry.date),
        "party_name": entry.party_name,
        "party_phone": entry.party_phone or "",
        "party_address": entry.party_address or "",
        "pincode": entry.pincode or "",
        "vehicle_no": entry.vehicle_no,
        "price": entry.price,
        "created_at": dt(entry.created_at),
        "last_modified_at": dt(entry.last_modified_at or entry.created_at),
        "products": [
            {
                "id": p.id,
                "product_type": p.product_type,
                "num_bags": p.num_bags,
                "weight_per_bag": p.weight_per_bag,
                "total_weight": p.total_weight,
            }
            for p in entry.products
        ],
        "total_bags": sum(p.num_bags for p in entry.products),
        "total_weight": sum(p.total_weight for p in entry.products),
    }


@dispatch_bp.get("")
def list_dispatch_entries():
    try:
        from_date = parse_datetime(request.args.get("from_date"), "from_date")
        to_date = parse_datetime(request.args.get("to_date"), "to_date")
    except ValueError as exc:
        return error(str(exc))
    product_type = request.args.get("product_type")
    party_name = request.args.get("party_name")

    with db_session() as db:
        query = select(DispatchEntry).options(selectinload(DispatchEntry.products)).where(DispatchEntry.client_id == DEFAULT_CLIENT_ID)
        if from_date:
            query = query.where(DispatchEntry.date >= from_date)
        if to_date:
            query = query.where(DispatchEntry.date <= to_date)
        if product_type:
            # Filter by any product in the entry
            query = query.join(DispatchProduct).where(DispatchProduct.product_type == product_type)
        if party_name:
            query = query.where(DispatchEntry.party_name.ilike(f"%{party_name}%"))
        query = query.order_by(DispatchEntry.date.desc())
        rows = db.execute(query).scalars().all()
    return jsonify([_serialize_dispatch(row) for row in rows])


def _parse_dispatch_products(products: object) -> list[dict]:
    """Parse and validate dispatch products."""
    if not isinstance(products, list) or len(products) == 0:
        raise ValueError("products is required and must be a non-empty list")

    parsed: list[dict] = []
    for index, item in enumerate(products, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"products[{index}] must be an object")

        product_type = str(item.get("product_type") or "").strip()
        if not product_type:
            raise ValueError(f"products[{index}].product_type is required")

        try:
            num_bags = float(item.get("num_bags") or 0)
        except (TypeError, ValueError):
            raise ValueError(f"products[{index}].num_bags must be a number")
        if num_bags <= 0:
            raise ValueError(f"products[{index}].num_bags must be greater than 0")

        try:
            weight_per_bag = float(item.get("weight_per_bag") or 0)
        except (TypeError, ValueError):
            raise ValueError(f"products[{index}].weight_per_bag must be a number")
        if weight_per_bag <= 0:
            raise ValueError(f"products[{index}].weight_per_bag must be greater than 0")

        total_weight = num_bags * weight_per_bag
        parsed.append({
            "product_type": product_type,
            "num_bags": num_bags,
            "weight_per_bag": weight_per_bag,
            "total_weight": total_weight,
        })

    return parsed


@dispatch_bp.post("")
def create_dispatch_entry():
    try:
        payload = json_body()
        date = parse_datetime(required(payload, "date"), "date")
        if date is None:
            raise ValueError("date is required")
        party_name = required(payload, "party_name")
        party_phone = payload.get("party_phone", "").strip() or None
        party_address = payload.get("party_address", "").strip() or None
        pincode = payload.get("pincode", "").strip() or None
        vehicle_no = required(payload, "vehicle_no")
        products = _parse_dispatch_products(payload.get("products"))
        price = parse_float(payload, "price")
    except ValueError as exc:
        return error(str(exc))

    try:
        with db_session() as db:
            # Validate all product types exist
            for prod in products:
                product_type = (
                    db.execute(
                        select(ProductType).where(
                            ProductType.name.ilike(prod["product_type"])
                        )
                    )
                    .scalars()
                    .one_or_none()
                )
                if not product_type:
                    return error(f"Invalid product type: {prod['product_type']}")

            entry = DispatchEntry(
                client_id=DEFAULT_CLIENT_ID,
                date=date,
                party_name=party_name,
                party_phone=party_phone,
                party_address=party_address,
                pincode=pincode,
                vehicle_no=vehicle_no,
                price=price,
                last_modified_at=datetime.utcnow(),
            )
            db.add(entry)
            db.flush()

            # Add products
            for prod in products:
                product = DispatchProduct(
                    dispatch_id=entry.id,
                    product_type=prod["product_type"],
                    num_bags=prod["num_bags"],
                    weight_per_bag=prod["weight_per_bag"],
                    total_weight=prod["total_weight"],
                )
                db.add(product)
                # Update stock ledger for each product
                add_feed_dispatched(
                    db=db,
                    client_id=DEFAULT_CLIENT_ID,
                    feed_type=prod["product_type"],
                    quantity=prod["total_weight"],
                    date=date,
                    weight_per_bag=prod["weight_per_bag"],
                )

            db.flush()
            entry = (
                db.execute(select(DispatchEntry).options(selectinload(DispatchEntry.products)).where(DispatchEntry.id == entry.id))
                .scalars()
                .one()
            )
            return jsonify(_serialize_dispatch(entry))
    except ValueError as exc:
        return error(str(exc))


@dispatch_bp.put("/<int:entry_id>")
def update_dispatch_entry(entry_id: int):
    try:
        payload = json_body()
        date = parse_datetime(required(payload, "date"), "date")
        if date is None:
            raise ValueError("date is required")
        party_name = required(payload, "party_name")
        party_phone = payload.get("party_phone", "").strip() or None
        party_address = payload.get("party_address", "").strip() or None
        pincode = payload.get("pincode", "").strip() or None
        vehicle_no = required(payload, "vehicle_no")
        products = _parse_dispatch_products(payload.get("products"))
        price = parse_float(payload, "price")
    except ValueError as exc:
        return error(str(exc))

    try:
        with db_session() as db:
            entry = (
                db.execute(
                    select(DispatchEntry).options(selectinload(DispatchEntry.products)).where(
                        DispatchEntry.id == entry_id,
                        DispatchEntry.client_id == DEFAULT_CLIENT_ID,
                    )
                )
                .scalars()
                .one_or_none()
            )
            if not entry:
                return error("Dispatch entry not found", 404)

            # Validate all product types exist
            for prod in products:
                product_type = (
                    db.execute(
                        select(ProductType).where(
                            ProductType.name.ilike(prod["product_type"])
                        )
                    )
                    .scalars()
                    .one_or_none()
                )
                if not product_type:
                    return error(f"Invalid product type: {prod['product_type']}")

            # Update entry
            entry.date = date
            entry.party_name = party_name
            entry.party_phone = party_phone
            entry.party_address = party_address
            entry.pincode = pincode
            entry.vehicle_no = vehicle_no
            entry.price = price
            entry.last_modified_at = datetime.utcnow()

            # Delete old products
            for product in list(entry.products):
                db.delete(product)
            db.flush()

            # Add new products
            for prod in products:
                product = DispatchProduct(
                    dispatch_id=entry.id,
                    product_type=prod["product_type"],
                    num_bags=prod["num_bags"],
                    weight_per_bag=prod["weight_per_bag"],
                    total_weight=prod["total_weight"],
                )
                db.add(product)

            db.flush()
            rebuild_feed_stock_ledger(db=db, client_id=DEFAULT_CLIENT_ID)
            entry = (
                db.execute(select(DispatchEntry).options(selectinload(DispatchEntry.products)).where(DispatchEntry.id == entry.id))
                .scalars()
                .one()
            )
            return jsonify(_serialize_dispatch(entry))
    except ValueError as exc:
        return error(str(exc))


@dispatch_bp.delete("/<int:entry_id>")
def delete_dispatch_entry(entry_id: int):
    with db_session() as db:
        entry = (
            db.execute(
                select(DispatchEntry).where(
                    DispatchEntry.id == entry_id,
                    DispatchEntry.client_id == DEFAULT_CLIENT_ID,
                )
            )
            .scalars()
            .one_or_none()
        )
        if not entry:
            return error("Dispatch entry not found", 404)

        db.delete(entry)
        db.flush()
        rebuild_feed_stock_ledger(db=db, client_id=DEFAULT_CLIENT_ID)
        return jsonify({"id": entry_id, "deleted": True})


@dispatch_bp.get("/download")
def download_dispatch():
    try:
        from_date = parse_datetime(request.args.get("from_date"), "from_date")
        to_date = parse_datetime(request.args.get("to_date"), "to_date")
    except ValueError as exc:
        return error(str(exc))

    file_format = request.args.get("format", "pdf").lower()

    with db_session() as db:
        query = select(DispatchEntry).options(selectinload(DispatchEntry.products)).where(DispatchEntry.client_id == DEFAULT_CLIENT_ID)
        if from_date:
            query = query.where(DispatchEntry.date >= from_date)
        if to_date:
            query = query.where(DispatchEntry.date <= to_date)
        query = query.order_by(DispatchEntry.date.desc())
        rows = db.execute(query).scalars().all()

    headers = ["Date", "Party Name", "Vehicle No", "Product Type", "Num Bags", "Weight Per Bag", "Total Weight", "Price"]
    data_rows = []
    for row in rows:
        for product in row.products:
            data_rows.append((
                row.date.strftime("%Y-%m-%d"),
                row.party_name,
                row.vehicle_no,
                product.product_type,
                product.num_bags,
                product.weight_per_bag,
                product.total_weight,
                row.price or "",
            ))

    if file_format == "csv":
        return Response(
            export_table_to_csv(headers, data_rows),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=dispatch_report.csv"},
        )
    if file_format in ("excel", "xlsx"):
        return Response(
            export_table_to_excel("Dispatch Report", headers, data_rows),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=dispatch_report.xlsx"},
        )
    return Response(
        export_table_to_pdf("Dispatch Report", headers, data_rows),
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=dispatch_report.pdf"},
    )


@dispatch_bp.get("/<int:entry_id>/download")
def download_single_dispatch_entry(entry_id: int):
    file_format = request.args.get("format", "pdf").lower()

    with db_session() as db:
        row = (
            db.execute(
                select(DispatchEntry).options(selectinload(DispatchEntry.products)).where(
                    DispatchEntry.id == entry_id,
                    DispatchEntry.client_id == DEFAULT_CLIENT_ID,
                )
            )
            .scalars()
            .one_or_none()
        )

    if not row:
        return error("Dispatch entry not found", 404)

    headers = ["Date", "Party Name", "Vehicle No", "Product Type", "Num Bags", "Weight Per Bag", "Total Weight", "Price"]
    data_rows = []
    for product in row.products:
        data_rows.append((
            row.date.strftime("%Y-%m-%d"),
            row.party_name,
            row.vehicle_no,
            product.product_type,
            product.num_bags,
            product.weight_per_bag,
            product.total_weight,
            row.price or "",
        ))

    filename = f"dispatch_{entry_id}_report"

    if file_format == "csv":
        return Response(
            export_table_to_csv(headers, data_rows),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}.csv"},
        )
    if file_format in ("excel", "xlsx"):
        return Response(
            export_table_to_excel("Dispatch Entry Report", headers, data_rows),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}.xlsx"},
        )
    return Response(
        export_table_to_pdf("Dispatch Entry Report", headers, data_rows),
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}.pdf"},
    )


@dispatch_bp.get("/<int:entry_id>/invoice")
def download_invoice(entry_id: int):
    """Download invoice as PDF for a dispatch entry."""
    with db_session() as db:
        entry = (
            db.execute(
                select(DispatchEntry).options(selectinload(DispatchEntry.products)).where(
                    DispatchEntry.id == entry_id,
                    DispatchEntry.client_id == DEFAULT_CLIENT_ID,
                )
            )
            .scalars()
            .one_or_none()
        )
    
    if not entry:
        return error("Dispatch entry not found", 404)
    
    try:
        pdf_buffer = generate_invoice_pdf(entry, entry.products)
        return Response(
            pdf_buffer.getvalue(),
            mimetype="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=invoice_{entry_id}.pdf"},
        )
    except Exception as exc:
        return error(f"Failed to generate invoice: {str(exc)}")
