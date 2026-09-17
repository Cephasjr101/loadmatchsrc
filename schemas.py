from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# ---------- users & auth ----------

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    role: str = Field(pattern="^(shipper|carrier)$")
    company_name: str = ""


class UserOut(BaseModel):
    id: int
    email: str
    role: str
    company_name: str

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


# ---------- loads ----------

class LoadCreate(BaseModel):
    title: str = ""
    origin_city: str
    origin_lat: float
    origin_lng: float
    dest_city: str
    dest_lat: float
    dest_lng: float
    equipment_type: str
    weight_kg: float = Field(gt=0)
    pickup_time: datetime


class LoadUpdate(BaseModel):
    title: str | None = None
    origin_city: str | None = None
    origin_lat: float | None = None
    origin_lng: float | None = None
    dest_city: str | None = None
    dest_lat: float | None = None
    dest_lng: float | None = None
    equipment_type: str | None = None
    weight_kg: float | None = Field(default=None, gt=0)
    pickup_time: datetime | None = None


class LoadOut(BaseModel):
    id: int
    shipper_id: int
    title: str
    origin_city: str
    origin_lat: float
    origin_lng: float
    dest_city: str
    dest_lat: float
    dest_lng: float
    equipment_type: str
    weight_kg: float
    pickup_time: datetime
    status: str
    assigned_truck_id: int | None
    assigned_carrier_id: int | None
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- trucks ----------

class TruckCreate(BaseModel):
    name: str = ""
    equipment_type: str
    capacity_kg: float = Field(gt=0)
    current_lat: float
    current_lng: float
    available_from: datetime
    available_until: datetime


class TruckUpdate(BaseModel):
    name: str | None = None
    equipment_type: str | None = None
    capacity_kg: float | None = Field(default=None, gt=0)
    current_lat: float | None = None
    current_lng: float | None = None
    available_from: datetime | None = None
    available_until: datetime | None = None


class TruckOut(BaseModel):
    id: int
    carrier_id: int
    name: str
    equipment_type: str
    capacity_kg: float
    current_lat: float
    current_lng: float
    available_from: datetime
    available_until: datetime
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- offers ----------

class OfferCreate(BaseModel):
    amount: float = Field(gt=0)
    truck_id: int | None = None


class OfferOut(BaseModel):
    id: int
    load_id: int
    carrier_id: int
    truck_id: int | None
    amount: float
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
