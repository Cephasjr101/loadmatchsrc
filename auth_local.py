from pydantic import BaseModel, EmailStr
from fastapi import APIRouter
from auth_google import make_token

router = APIRouter(prefix="/auth", tags=["auth"])

class RegisterIn(BaseModel):
    name: str
    email: EmailStr
    password: str

@router.post("/register")
def register(body: RegisterIn):
    token = make_token({"sub": body.email, "name": body.name, "provider": "email"})
    return {"access_token": token, "email": body.email, "name": body.name}
