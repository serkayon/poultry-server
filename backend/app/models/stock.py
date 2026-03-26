from sqlalchemy import String, Float, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from ..database import Base


class RMStockLedger(Base):
    __tablename__ = "rm_stock_ledger"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(Integer)
    date: Mapped[datetime] = mapped_column(DateTime)
    rm_name: Mapped[str] = mapped_column(String(100))
    opening_stock: Mapped[float] = mapped_column(Float, default=0)
    received: Mapped[float] = mapped_column(Float, default=0)
    consumption: Mapped[float] = mapped_column(Float, default=0)
    closing_stock: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FeedStock(Base):
    __tablename__ = "feed_stock"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(Integer)
    date: Mapped[datetime] = mapped_column(DateTime)
    feed_type: Mapped[str] = mapped_column(String(100))
    # Bag size bucket key in grams (e.g. 25000 for 25kg bag).
    # Keeps 25kg and 50kg stock as separate ledgers for the same product.
    bag_weight_grams: Mapped[int | None] = mapped_column(Integer, nullable=True)
    opening_stock: Mapped[float] = mapped_column(Float, default=0)
    produced: Mapped[float] = mapped_column(Float, default=0)
    dispatched: Mapped[float] = mapped_column(Float, default=0)
    closing_stock: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
