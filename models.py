from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # shipper | carrier
    company_name = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    loads = relationship("Load", back_populates="shipper")
    trucks = relationship("Truck", back_populates="carrier")
    offers = relationship("Offer", back_populates="carrier")


class Load(Base):
    __tablename__ = "loads"

    id = Column(Integer, primary_key=True, index=True)
    shipper_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, default="")
    origin_city = Column(String, nullable=False)
    origin_lat = Column(Float, nullable=False)
    origin_lng = Column(Float, nullable=False)
    dest_city = Column(String, nullable=False)
    dest_lat = Column(Float, nullable=False)
    dest_lng = Column(Float, nullable=False)
    equipment_type = Column(String, nullable=False)
    weight_kg = Column(Float, nullable=False)
    pickup_time = Column(DateTime, nullable=False)
    status = Column(String, default="open", index=True)  # open|assigned|in_transit|delivered|cancelled
    assigned_truck_id = Column(Integer, ForeignKey("trucks.id"), nullable=True)
    assigned_carrier_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    shipper = relationship("User", back_populates="loads")
    offers = relationship("Offer", back_populates="load")


class Truck(Base):
    __tablename__ = "trucks"

    id = Column(Integer, primary_key=True, index=True)
    carrier_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, default="")
    equipment_type = Column(String, nullable=False)
    capacity_kg = Column(Float, nullable=False)
    current_lat = Column(Float, nullable=False)
    current_lng = Column(Float, nullable=False)
    available_from = Column(DateTime, nullable=False)
    available_until = Column(DateTime, nullable=False)
    status = Column(String, default="available", index=True)  # available|assigned
    created_at = Column(DateTime, default=datetime.utcnow)

    carrier = relationship("User", back_populates="trucks")
    offers = relationship("Offer", back_populates="truck")


class Offer(Base):
    __tablename__ = "offers"

    id = Column(Integer, primary_key=True, index=True)
    load_id = Column(Integer, ForeignKey("loads.id"), nullable=False)
    carrier_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    truck_id = Column(Integer, ForeignKey("trucks.id"), nullable=True)
    amount = Column(Float, nullable=False)
    status = Column(String, default="pending", index=True)  # pending|accepted|rejected|withdrawn
    created_at = Column(DateTime, default=datetime.utcnow)

    load = relationship("Load", back_populates="offers")
    carrier = relationship("User", back_populates="offers")
    truck = relationship("Truck", back_populates="offers")
