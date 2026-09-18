import logging
import os
from app.routers import auth_google
app.include_router(auth_google.router)
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

import firebase_auth
import matching
import models
import schemas
import security
from database import Base, engine, get_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("loadmatch")

app = FastAPI(title="LoadMatch API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

STATIC_DIR = Path(os.getenv("STATIC_DIR", "./static"))
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

bearer_scheme = HTTPBearer(auto_error=False)


# ---------- auth helpers ----------

def _unauthorized(detail="Invalid or missing authentication token"):
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if credentials is None:
        raise _unauthorized("Not authenticated")
    token = credentials.credentials

    # 1) Try Firebase ID token (only when Firebase is configured)
    decoded = firebase_auth.verify_firebase_token(token)
    if decoded is not None:
        email = (decoded.get("email") or "").lower()
        if not email:
            raise _unauthorized("Firebase token has no email claim")
        user = db.query(models.User).filter(models.User.email == email).first()
        if user is None:
            # Auto-provision a local user for this Firebase identity.
            role = decoded.get("role") or "shipper"
            if role not in ("shipper", "carrier"):
                role = "shipper"
            company_name = decoded.get("company_name") or email.split("@")[0]
            user = models.User(
                email=email,
                password_hash=security.hash_password(os.urandom(16).hex()),
                role=role,
                company_name=company_name,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        return user

    # 2) Fall back to local JWT
    payload = security.decode_token(token)
    if payload is None:
        raise _unauthorized()
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError):
        raise _unauthorized()
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise _unauthorized("User no longer exists")
    return user


def require_shipper(user):
    if user.role != "shipper":
        raise HTTPException(status_code=403, detail="Shipper account required")


def require_carrier(user):
    if user.role != "carrier":
        raise HTTPException(status_code=403, detail="Carrier account required")


# ---------- auth ----------

@app.post("/auth/register", response_model=schemas.UserOut, status_code=201)
def register(body: schemas.UserCreate, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.query(models.User).filter(models.User.email == email).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    user = models.User(
        email=email,
        password_hash=security.hash_password(body.password),
        role=body.role,
        company_name=body.company_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/auth/login", response_model=schemas.Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form.username.lower()).first()
    if user is None or not security.verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return {"access_token": security.create_token(user.id, user.role), "token_type": "bearer"}


@app.get("/me", response_model=schemas.UserOut)
def read_me(user=Depends(get_current_user)):
    return user


# ---------- loads ----------

@app.post("/loads", response_model=schemas.LoadOut, status_code=201)
def create_load(
    body: schemas.LoadCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    require_shipper(user)
    load = models.Load(shipper_id=user.id, **body.model_dump())
    db.add(load)
    db.commit()
    db.refresh(load)
    return load


@app.get("/loads", response_model=list[schemas.LoadOut])
def list_loads(
    status: str | None = None,
    equipment_type: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.Load)
    if status:
        q = q.filter(models.Load.status == status)
    if equipment_type:
        q = q.filter(models.Load.equipment_type == equipment_type)
    return q.order_by(models.Load.created_at.desc()).all()


def _get_owned_load(load_id: int, user, db: Session):
    load = db.get(models.Load, load_id)
    if load is None:
        raise HTTPException(status_code=404, detail="Load not found")
    if user.role != "shipper" or load.shipper_id != user.id:
        raise HTTPException(status_code=403, detail="You do not own this load")
    return load


@app.get("/loads/{load_id}", response_model=schemas.LoadOut)
def get_load(load_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return _get_owned_load(load_id, user, db)


@app.patch("/loads/{load_id}", response_model=schemas.LoadOut)
def update_load(
    load_id: int,
    body: schemas.LoadUpdate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    load = _get_owned_load(load_id, user, db)
    if load.status != "open":
        raise HTTPException(status_code=400, detail="Only open loads can be edited")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(load, field, value)
    db.commit()
    db.refresh(load)
    return load


@app.delete("/loads/{load_id}")
def delete_load(load_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    load = _get_owned_load(load_id, user, db)
    if load.status in ("in_transit", "delivered"):
        raise HTTPException(status_code=400, detail="Cannot cancel a load that is in transit or delivered")
    for offer in load.offers:
        if offer.status == "pending":
            offer.status = "rejected"
    if load.assigned_truck_id:
        truck = db.get(models.Truck, load.assigned_truck_id)
        if truck is not None:
            truck.status = "available"
    load.status = "cancelled"
    db.commit()
    return {"ok": True, "status": "cancelled"}


# ---------- trucks ----------

@app.post("/trucks", response_model=schemas.TruckOut, status_code=201)
def create_truck(
    body: schemas.TruckCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    require_carrier(user)
    truck = models.Truck(carrier_id=user.id, **body.model_dump())
    db.add(truck)
    db.commit()
    db.refresh(truck)
    return truck


@app.get("/trucks", response_model=list[schemas.TruckOut])
def list_trucks(
    status: str | None = None,
    equipment_type: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.Truck)
    if status:
        q = q.filter(models.Truck.status == status)
    if equipment_type:
        q = q.filter(models.Truck.equipment_type == equipment_type)
    return q.order_by(models.Truck.created_at.desc()).all()


def _get_owned_truck(truck_id: int, user, db: Session):
    truck = db.get(models.Truck, truck_id)
    if truck is None:
        raise HTTPException(status_code=404, detail="Truck not found")
    if user.role != "carrier" or truck.carrier_id != user.id:
        raise HTTPException(status_code=403, detail="You do not own this truck")
    return truck


@app.get("/trucks/{truck_id}", response_model=schemas.TruckOut)
def get_truck(truck_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return _get_owned_truck(truck_id, user, db)


@app.patch("/trucks/{truck_id}", response_model=schemas.TruckOut)
def update_truck(
    truck_id: int,
    body: schemas.TruckUpdate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    truck = _get_owned_truck(truck_id, user, db)
    if truck.status != "available":
        raise HTTPException(status_code=400, detail="Assigned trucks cannot be edited")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(truck, field, value)
    db.commit()
    db.refresh(truck)
    return truck


# ---------- matching ----------

@app.get("/loads/{load_id}/matches")
def get_matches(load_id: int, db: Session = Depends(get_db)):
    load = db.get(models.Load, load_id)
    if load is None or load.status == "cancelled":
        raise HTTPException(status_code=404, detail="Load not found")
    trucks = db.query(models.Truck).filter(models.Truck.status == "available").all()
    results = matching.compatible_trucks(load, trucks)
    return [
        {
            "truck": schemas.TruckOut.model_validate(r["truck"]),
            "distance_km": r["distance_km"],
            "score": r["score"],
        }
        for r in results
    ]


# ---------- offers ----------

@app.post("/loads/{load_id}/offers", response_model=schemas.OfferOut, status_code=201)
def create_offer(
    load_id: int,
    body: schemas.OfferCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    require_carrier(user)
    load = db.get(models.Load, load_id)
    if load is None or load.status == "cancelled":
        raise HTTPException(status_code=404, detail="Load not found")
    if load.status != "open":
        raise HTTPException(status_code=400, detail="Load is not open for offers")
    if body.truck_id is not None:
        truck = db.get(models.Truck, body.truck_id)
        if truck is None or truck.carrier_id != user.id:
            raise HTTPException(status_code=400, detail="Truck not found or not yours")
        if truck.status != "available":
            raise HTTPException(status_code=400, detail="That truck is not available")
    offer = models.Offer(load_id=load.id, carrier_id=user.id, truck_id=body.truck_id, amount=body.amount)
    db.add(offer)
    db.commit()
    db.refresh(offer)
    return offer


@app.get("/loads/{load_id}/offers", response_model=list[schemas.OfferOut])
def list_offers(load_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    load = db.get(models.Load, load_id)
    if load is None:
        raise HTTPException(status_code=404, detail="Load not found")
    q = db.query(models.Offer).filter(models.Offer.load_id == load.id)
    if user.role == "shipper":
        if load.shipper_id != user.id:
            raise HTTPException(status_code=403, detail="You do not own this load")
    else:
        q = q.filter(models.Offer.carrier_id == user.id)
    return q.order_by(models.Offer.created_at.desc()).all()


@app.post("/offers/{offer_id}/accept", response_model=schemas.OfferOut)
def accept_offer(offer_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    require_shipper(user)
    offer = db.get(models.Offer, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="Offer not found")
    if offer.load.shipper_id != user.id:
        raise HTTPException(status_code=403, detail="You do not own this load")
    if offer.status != "pending":
        raise HTTPException(status_code=400, detail="Offer is no longer pending")
    load = offer.load
    if load.status != "open":
        raise HTTPException(status_code=400, detail="Load is no longer open")

    # Resolve the truck: the one named on the offer, else best compatible of carrier's fleet.
    truck = None
    if offer.truck_id is not None:
        truck = db.get(models.Truck, offer.truck_id)
    if truck is None or truck.status != "available":
        fleet = db.query(models.Truck).filter(models.Truck.carrier_id == offer.carrier_id).all()
        candidates = matching.compatible_trucks(load, fleet)
        truck = candidates[0]["truck"] if candidates else None
    if truck is None:
        raise HTTPException(status_code=400, detail="Carrier has no available compatible truck")

    # Atomic accept: mark offer accepted, reject other pending offers, book truck, assign load.
    offer.status = "accepted"
    for other in load.offers:
        if other.id != offer.id and other.status == "pending":
            other.status = "rejected"
    truck.status = "assigned"
    load.status = "assigned"
    load.assigned_truck_id = truck.id
    load.assigned_carrier_id = offer.carrier_id
    db.commit()
    db.refresh(offer)
    return offer


@app.post("/offers/{offer_id}/reject", response_model=schemas.OfferOut)
def reject_offer(offer_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    require_shipper(user)
    offer = db.get(models.Offer, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="Offer not found")
    if offer.load.shipper_id != user.id:
        raise HTTPException(status_code=403, detail="You do not own this load")
    if offer.status != "pending":
        raise HTTPException(status_code=400, detail="Offer is no longer pending")
    offer.status = "rejected"
    db.commit()
    db.refresh(offer)
    return offer


# ---------- load lifecycle ----------

def _get_load_for_transition(load_id: int, user, db: Session, allowed: set):
    load = db.get(models.Load, load_id)
    if load is None:
        raise HTTPException(status_code=404, detail="Load not found")
    is_owner = user.role == "shipper" and load.shipper_id == user.id
    is_assigned_carrier = load.assigned_carrier_id is not None and user.id == load.assigned_carrier_id
    if not (is_owner or is_assigned_carrier):
        raise HTTPException(status_code=403, detail="Not authorized for this load")
    if load.status not in allowed:
        raise HTTPException(
            status_code=400,
            detail="Load status '{}' does not allow this transition".format(load.status),
        )
    return load


@app.post("/loads/{load_id}/pickup", response_model=schemas.LoadOut)
def pickup_load(load_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    load = _get_load_for_transition(load_id, user, db, {"assigned"})
    load.status = "in_transit"
    db.commit()
    db.refresh(load)
    return load


@app.post("/loads/{load_id}/deliver", response_model=schemas.LoadOut)
def deliver_load(load_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    load = _get_load_for_transition(load_id, user, db, {"in_transit"})
    load.status = "delivered"
    if load.assigned_truck_id:
        truck = db.get(models.Truck, load.assigned_truck_id)
        if truck is not None:
            # Free the truck and relocate it to the destination.
            truck.status = "available"
            truck.current_lat = load.dest_lat
            truck.current_lng = load.dest_lng
    db.commit()
    db.refresh(load)
    return load


# ---------- health & root ----------

@app.get("/health")
def health():
    index = STATIC_DIR / "index.html"
    return {"status": "ok", "static": {"enabled": index.exists(), "dir": str(STATIC_DIR)}}


@app.get("/")
def root():
    index = STATIC_DIR / "index.html"
    if index.exists():
        return HTMLResponse(index.read_text(encoding="utf-8"))
    return {"message": "LoadMatch API", "docs": "/docs", "health": "/health"}
