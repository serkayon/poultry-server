from sqlalchemy import Boolean, DateTime, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from ..database import Base


class PLCDataSnapshot(Base):
    """Real-time PLC data (Modbus) - written by cloud/Modbus team; we only read via API."""
    __tablename__ = "plc_data_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Client/plant identifier if multi-tenant
    client_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    running_status: Mapped[bool] = mapped_column(Boolean, default=False)
    ambient_temp: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity: Mapped[float | None] = mapped_column(Float, nullable=True)
    pressure_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    pressure_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    conditioner_temp: Mapped[float | None] = mapped_column(Float, nullable=True)
    bagging_temp: Mapped[float | None] = mapped_column(Float, nullable=True)
    motor_temp: Mapped[float | None] = mapped_column(Float, nullable=True)
    motor_rpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    pellet_feeder_speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    pellet_motor_load: Mapped[float | None] = mapped_column(Float, nullable=True)

    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MachineState(Base):
    """Single-row machine state controlled by HMI."""

    __tablename__ = "machine_state"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False, default=1)
    is_running: Mapped[bool] = mapped_column(Boolean, default=False)
    active_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
