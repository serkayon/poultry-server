from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class PLCDataResponse(BaseModel):
    id: int
    running_status: bool
    ambient_temp: Optional[float] = None
    humidity: Optional[float] = None
    pressure_before: Optional[float] = None
    pressure_after: Optional[float] = None
    conditioner_temp: Optional[float] = None
    bagging_temp: Optional[float] = None
    motor_temp: Optional[float] = None
    motor_rpm: Optional[float] = None
    pellet_feeder_speed: Optional[float] = None
    pellet_motor_load: Optional[float] = None
    recorded_at: datetime

    class Config:
        from_attributes = True
