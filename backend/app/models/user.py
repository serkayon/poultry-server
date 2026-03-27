from sqlalchemy import String, Boolean, DateTime, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
import enum

from ..database import Base


class UserRole(str, enum.Enum):
    vendor = "vendor"
    customer = "customer"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    settings_pin_hash: Mapped[str] = mapped_column(String(255), default="1234")
    pin_rm_entry_edit_hash: Mapped[str] = mapped_column(String(255), default="1234")
    pin_rm_lab_edit_hash: Mapped[str] = mapped_column(String(255), default="1234")
    pin_dispatch_edit_hash: Mapped[str] = mapped_column(String(255), default="1234")
    pin_production_details_edit_hash: Mapped[str] = mapped_column(String(255), default="1234")
    pin_production_report_access_hash: Mapped[str] = mapped_column(String(255), default="1234")
    pin_recipe_access_hash: Mapped[str] = mapped_column(String(255), default="1234")
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))  # vendor | customer
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[int | None] = mapped_column(nullable=True)  # vendor who created this customer
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
