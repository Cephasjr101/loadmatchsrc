import os
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from fastapi import APIRouter, HTTPException
# reuse make_token + JWT settings from auth_google (import them instead of duplicating)

router = APIRouter(prefix="/auth", tags=["auth"])
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

class RegisterIn(BaseModel):
    name: str
    email: EmailStr
    password: str          # add a min_length validator in production

class LoginIn(BaseModel):
    email: EmailStr
    password: str

@router.post("/register")
def register(body: RegisterIn):
    # TODO: check email isn't taken, then persist to your DB:
    #   user = User(name=body.name, email=body.email,
    #               password_hash=pwd.hash(body.password))
    #   db.add(user); db.commit()
    token = make_token({"sub": body.email, "name": body.name, "provider": "email"})
    return {"access_token": token, "email": body.email, "name": body.name}

@router.post("/login")
def login(body: LoginIn):
    # TODO: fetch user by email from DB, then:
    #   if not user or not pwd.verify(body.password, user.password_hash):
    #       raise HTTPException(401, "Invalid email or password")
    token = make_token({"sub": body.email, "provider": "email"})
    return {"access_token": token, "email": body.email}
