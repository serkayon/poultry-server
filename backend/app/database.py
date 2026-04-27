from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, echo=settings.debug)
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    bind=engine,
)


# Define Base.

class Base(DeclarativeBase):
    pass


# Get db.

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


# Handle init db.

def init_db():
    from . import models  # noqa: F401
    from .models.plc import MachineState
    from .models.raw_material import RawMaterialType
    from .models.user import User, UserRole
    from .services.auth import hash_password

    Base.metadata.create_all(bind=engine)
    _drop_legacy_client_id_columns()

    with SessionLocal() as session:
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
                    password=hash_password("open@123"),
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

        session.commit()


# Drop legacy multi-tenant columns now that the app runs single-tenant.
def _drop_legacy_client_id_columns() -> None:
    with engine.begin() as conn:
        if conn.dialect.name != "postgresql":
            return

        conn.execute(
            text(
                "ALTER TABLE IF EXISTS raw_material_stock "
                "DROP CONSTRAINT IF EXISTS uq_raw_material_stock_client_rm"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE IF EXISTS feed_stock "
                "DROP CONSTRAINT IF EXISTS uq_feed_stock_client_feed_variant"
            )
        )

        tables = [
            "production_batches",
            "raw_material_entries",
            "dispatch_entries",
            "raw_material_ledger",
            "raw_material_stock",
            "feed_stock_ledger",
            "feed_stock",
            "plc_data_snapshots",
        ]
        for table in tables:
            conn.execute(text(f"ALTER TABLE IF EXISTS {table} DROP COLUMN IF EXISTS client_id"))

        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'uq_raw_material_stock_rm'
                    ) THEN
                        ALTER TABLE raw_material_stock
                        ADD CONSTRAINT uq_raw_material_stock_rm UNIQUE (rm_name);
                    END IF;
                END$$;
                """
            )
        )
        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'uq_feed_stock_feed_variant'
                    ) THEN
                        ALTER TABLE feed_stock
                        ADD CONSTRAINT uq_feed_stock_feed_variant
                        UNIQUE (feed_type, bag_weight_grams);
                    END IF;
                END$$;
                """
            )
        )
