from datetime import datetime

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, echo=settings.debug)
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    bind=engine,
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    from . import models  # noqa: F401
    from .models.config import ProductType, Recipe
    from .models.dispatch import DispatchEntry, DispatchProduct
    from .models.plc import MachineState
    from .models.production import ProductionBatch
    from .models.raw_material import RawMaterialType
    from .models.stock import FeedStock
    from .models.user import User, UserRole
    from .services.auth import hash_password
    from sqlalchemy import select

    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    needs_feed_variant_rebuild = False
    if inspector.has_table("production_batches"):
        existing_columns = {col["name"] for col in inspector.get_columns("production_batches")}
        if "batch_no" not in existing_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE production_batches ADD COLUMN batch_no VARCHAR(64)"))
        if "last_modified_at" not in existing_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE production_batches ADD COLUMN last_modified_at TIMESTAMP"))
        if "num_bags" not in existing_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE production_batches ADD COLUMN num_bags FLOAT"))
        if "weight_per_bag" not in existing_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE production_batches ADD COLUMN weight_per_bag FLOAT"))
        if "hmi_duration_seconds" not in existing_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE production_batches ADD COLUMN hmi_duration_seconds FLOAT"))
        if "hmi_completed_count" not in existing_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE production_batches ADD COLUMN hmi_completed_count INTEGER"))
        if "hmi_status" not in existing_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE production_batches ADD COLUMN hmi_status VARCHAR(32)"))
        if "hmi_started_at" not in existing_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE production_batches ADD COLUMN hmi_started_at TIMESTAMP"))
        if "hmi_completed_at" not in existing_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE production_batches ADD COLUMN hmi_completed_at TIMESTAMP"))
        if "stock_posted" not in existing_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE production_batches ADD COLUMN stock_posted BOOLEAN"))
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE production_batches "
                    "SET num_bags = output, weight_per_bag = 1 "
                    "WHERE output > 0 AND (num_bags IS NULL OR weight_per_bag IS NULL)"
                )
            )
            conn.execute(
                text(
                    "UPDATE production_batches "
                    "SET hmi_completed_count = 0 "
                    "WHERE hmi_completed_count IS NULL"
                )
            )
            conn.execute(
                text(
                    "UPDATE production_batches "
                    "SET hmi_status = CASE WHEN output > 0 THEN 'completed' ELSE 'pending' END "
                    "WHERE hmi_status IS NULL OR hmi_status = ''"
                )
            )
            conn.execute(
                text(
                    "UPDATE production_batches "
                    "SET stock_posted = CASE WHEN output > 0 THEN TRUE ELSE FALSE END "
                    "WHERE stock_posted IS NULL"
                )
            )
            conn.execute(
                text(
                    "UPDATE production_batches "
                    "SET hmi_started_at = COALESCE(hmi_started_at, last_modified_at, created_at, date) "
                    "WHERE hmi_started_at IS NULL AND LOWER(COALESCE(hmi_status, '')) IN ('completed', 'stopped')"
                )
            )
            conn.execute(
                text(
                    "UPDATE production_batches "
                    "SET hmi_completed_at = COALESCE(hmi_completed_at, last_modified_at, created_at, hmi_started_at, date) "
                    "WHERE hmi_completed_at IS NULL AND LOWER(COALESCE(hmi_status, '')) IN ('completed', 'stopped')"
                )
            )
    if inspector.has_table("raw_material_entries"):
        existing_columns = {col["name"] for col in inspector.get_columns("raw_material_entries")}
        if "last_modified_at" not in existing_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE raw_material_entries ADD COLUMN last_modified_at TIMESTAMP"))
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE raw_material_entries "
                    "SET last_modified_at = created_at "
                    "WHERE last_modified_at IS NULL"
                )
            )
    if inspector.has_table("plc_data_snapshots"):
        existing_columns = {col["name"] for col in inspector.get_columns("plc_data_snapshots")}
        if "pellet_motor_load" not in existing_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE plc_data_snapshots ADD COLUMN pellet_motor_load FLOAT"))
    if inspector.has_table("product_types"):
        existing_columns = {col["name"] for col in inspector.get_columns("product_types")}
        if "last_modified_at" not in existing_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE product_types ADD COLUMN last_modified_at TIMESTAMP"))
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE product_types "
                    "SET last_modified_at = created_at "
                    "WHERE last_modified_at IS NULL"
                )
            )
    if inspector.has_table("users"):
        existing_columns = {col["name"] for col in inspector.get_columns("users")}
        if "settings_pin_hash" not in existing_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN settings_pin_hash VARCHAR(255)"))
        scoped_pin_columns = [
            "pin_rm_entry_edit_hash",
            "pin_rm_lab_edit_hash",
            "pin_dispatch_edit_hash",
            "pin_production_details_edit_hash",
            "pin_production_report_access_hash",
            "pin_recipe_access_hash",
        ]
        for column_name in scoped_pin_columns:
            if column_name not in existing_columns:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {column_name} VARCHAR(255)"))
        default_pin_value = "1234"
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE users "
                    "SET settings_pin_hash = :pin_hash "
                    "WHERE settings_pin_hash IS NULL OR settings_pin_hash = ''"
                ),
                {"pin_hash": default_pin_value},
            )
            for column_name in scoped_pin_columns:
                conn.execute(
                    text(
                        f"UPDATE users "
                        f"SET {column_name} = :pin_hash "
                        f"WHERE {column_name} IS NULL OR {column_name} = ''"
                    ),
                    {"pin_hash": default_pin_value},
                )
    if inspector.has_table("feed_stock"):
        existing_columns = {col["name"] for col in inspector.get_columns("feed_stock")}
        if "bag_weight_grams" not in existing_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE feed_stock ADD COLUMN bag_weight_grams INTEGER"))
            needs_feed_variant_rebuild = True

    with SessionLocal() as session:
        # Normalize legacy hashed PINs to plain 4-digit values.
        # Any non-4-digit stored value is reset to the default 1234.
        scoped_pin_fields = [
            "settings_pin_hash",
            "pin_rm_entry_edit_hash",
            "pin_rm_lab_edit_hash",
            "pin_dispatch_edit_hash",
            "pin_production_details_edit_hash",
            "pin_production_report_access_hash",
            "pin_recipe_access_hash",
        ]
        users = session.execute(select(User)).scalars().all()
        for user in users:
            for field_name in scoped_pin_fields:
                existing_pin_value = str(getattr(user, field_name, "") or "").strip()
                if not existing_pin_value.isdigit() or len(existing_pin_value) != 4:
                    setattr(user, field_name, "1234")

        if session.execute(select(RawMaterialType).limit(1)).scalars().one_or_none() is None:
            for name in ["MAIZE", "SOYA", "DORB", "DDGS", "MDOC", "MGL"]:
                session.add(RawMaterialType(name=name))

        if session.get(MachineState, 1) is None:
            session.add(MachineState(id=1, is_running=False, active_batch_id=None))
        if session.execute(select(User).limit(1)).scalars().one_or_none() is None:
            default_pin_hash = "1234"
            session.add(
                User(
                    email="client@gmail.com",
                    hashed_password=hash_password("open@123"),
                    settings_pin_hash=default_pin_hash,
                    pin_rm_entry_edit_hash=default_pin_hash,
                    pin_rm_lab_edit_hash=default_pin_hash,
                    pin_dispatch_edit_hash=default_pin_hash,
                    pin_production_details_edit_hash=default_pin_hash,
                    pin_production_report_access_hash=default_pin_hash,
                    pin_recipe_access_hash=default_pin_hash,
                    full_name="Client User",
                    role=UserRole.customer.value,
                    company_name="Feed Mill Intelligence",
                    address=None,
                    logo_url=None,
                    is_active=True,
                    created_by_id=None,
                )
            )

        existing_product_type_names = {
            item.name.strip().lower()
            for item in session.execute(select(ProductType)).scalars().all()
            if item.name and item.name.strip()
        }
        discovered_product_types: set[str] = set()
        for (name,) in session.execute(select(Recipe.name)).all():
            if isinstance(name, str) and name.strip():
                discovered_product_types.add(name.strip())
        for (name,) in session.execute(select(ProductionBatch.product_name)).all():
            if isinstance(name, str) and name.strip():
                discovered_product_types.add(name.strip())
        for (name,) in session.execute(select(FeedStock.feed_type)).all():
            if isinstance(name, str) and name.strip():
                discovered_product_types.add(name.strip())
        for (name,) in session.execute(select(DispatchProduct.product_type)).all():
            if isinstance(name, str) and name.strip():
                discovered_product_types.add(name.strip())

        for name in sorted(discovered_product_types, key=str.lower):
            if name.lower() not in existing_product_type_names:
                session.add(ProductType(name=name, last_modified_at=datetime.utcnow()))
                existing_product_type_names.add(name.lower())

        session.commit()

        if needs_feed_variant_rebuild:
            from .services.stock import rebuild_feed_stock_ledger

            client_ids = {
                client_id
                for (client_id,) in session.execute(select(ProductionBatch.client_id).distinct()).all()
                if client_id is not None
            }
            client_ids.update(
                client_id
                for (client_id,) in session.execute(select(DispatchEntry.client_id).distinct()).all()
                if client_id is not None
            )
            client_ids.update(
                client_id
                for (client_id,) in session.execute(select(FeedStock.client_id).distinct()).all()
                if client_id is not None
            )
            if not client_ids:
                client_ids = {1}

            for client_id in sorted(client_ids):
                rebuild_feed_stock_ledger(db=session, client_id=int(client_id))
            session.commit()
