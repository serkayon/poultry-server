from sqlalchemy import String, Float, DateTime, Integer, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime

from ..database import Base


class RawMaterialType(Base):
    __tablename__ = "raw_material_types"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)  # MAIZE, SOYA, DORB, DDGS, MDOC, MGL etc.
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_modified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RawMaterialEntry(Base):
    __tablename__ = "raw_material_entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(Integer)
    date: Mapped[datetime] = mapped_column(DateTime)
    rm_type: Mapped[str] = mapped_column(String(100))
    supplier: Mapped[str] = mapped_column(String(255))
    challan_no: Mapped[str] = mapped_column(String(100))
    vehicle_no: Mapped[str] = mapped_column(String(50))
    total_weight: Mapped[float] = mapped_column(Float)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_modified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    lab_report: Mapped["RawMaterialLabReport | None"] = relationship(
        "RawMaterialLabReport", back_populates="entry", uselist=False
    )


class RawMaterialLabReport(Base):
    __tablename__ = "raw_material_lab_reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("raw_material_entries.id"), unique=True)
    entry: Mapped["RawMaterialEntry"] = relationship("RawMaterialEntry", back_populates="lab_report")

    protein: Mapped[float | None] = mapped_column(Float, nullable=True)
    fat: Mapped[float | None] = mapped_column(Float, nullable=True)
    nitrogen: Mapped[float | None] = mapped_column(Float, nullable=True)
    fiber: Mapped[float | None] = mapped_column(Float, nullable=True)
    ash: Mapped[float | None] = mapped_column(Float, nullable=True)
    calcium: Mapped[float | None] = mapped_column(Float, nullable=True)
    phosphorus: Mapped[float | None] = mapped_column(Float, nullable=True)
    salt: Mapped[float | None] = mapped_column(Float, nullable=True)
    moisture: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Maize-specific
    fungus: Mapped[str | None] = mapped_column(String(50), nullable=True)
    broke: Mapped[str | None] = mapped_column(String(50), nullable=True)
    water_damage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    small: Mapped[str | None] = mapped_column(String(50), nullable=True)
    dunkey: Mapped[str | None] = mapped_column(String(50), nullable=True)
    fm: Mapped[str | None] = mapped_column(String(50), nullable=True)
    maize_count: Mapped[str | None] = mapped_column(String(50), nullable=True)
    colour: Mapped[str | None] = mapped_column(String(50), nullable=True)
    smell: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
