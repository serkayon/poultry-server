from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class DispatchCreate(BaseModel):
    date: datetime
    party_name: str
    vehicle_no: str
    quantity: float
    product_type: str
    price: Optional[float] = None


class DispatchResponse(BaseModel):
    id: int
    date: datetime
    party_name: str
    vehicle_no: str
    quantity: float
    product_type: str
    price: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True
