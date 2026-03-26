from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class RawMaterialEntryCreate(BaseModel):
    date: datetime
    rm_type: str
    supplier: str
    challan_no: str
    vehicle_no: str
    total_weight: float
    remarks: Optional[str] = None


class LabReportCreate(BaseModel):
    entry_id: int
    protein: Optional[float] = None
    fat: Optional[float] = None
    nitrogen: Optional[float] = None
    fiber: Optional[float] = None
    ash: Optional[float] = None
    calcium: Optional[float] = None
    phosphorus: Optional[float] = None
    salt: Optional[float] = None
    moisture: Optional[float] = None
    fungus: Optional[str] = None
    broke: Optional[str] = None
    water_damage: Optional[str] = None
    small: Optional[str] = None
    dunkey: Optional[str] = None
    fm: Optional[str] = None
    maize_count: Optional[str] = None
    colour: Optional[str] = None
    smell: Optional[str] = None


class RawMaterialEntryResponse(BaseModel):
    id: int
    date: datetime
    rm_type: str
    supplier: str
    challan_no: str
    vehicle_no: str
    total_weight: float
    remarks: Optional[str] = None
    has_lab_report: bool = False
    created_at: datetime
    last_modified_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LabReportResponse(BaseModel):
    id: int
    entry_id: int
    protein: Optional[float] = None
    fat: Optional[float] = None
    moisture: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True
