import os
import httpx
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt

router = APIRouter(prefix="/auth/google", tags=["auth"])

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI",
                         "https://waynook1-1.onrender.com/auth/google/callback")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://waynook1-1.onrender.com")
JWT_SECRET = os.getenv("JWT_SECRET")           # set a long random string in Render!
JWT_ALG = "HS256"
TOKEN_TTL_DAYS = 7


def make_token(payload: dict) -> str:
    data = {**payload, "exp": datetime.now(timezone.utc) + timedelta(days=TOKEN_TTL_DAYS)}
    return jwt.encode(data, JWT_SECRET, algorithm=JWT_ALG)


security = HTTPBearer(auto_error=False)

def current_user(creds: HTTPAuthorizationCredentials = Depends(security)):
    """Use this to protect endpoints: user = Depends(current_user)"""
    if not creds:
        raise HTTPException(401, "Not authenticated")
    try:
        return jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.JWTError:
        raise HTTPException(401, "Invalid or expired token")


@router.get("/login")
def google_login():
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(500, "Google login not configured — set GOOGLE_CLIENT_ID")
    url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={GOOGLE_CLIENT_ID}"
        "&response_type=code"
        f"&redirect_uri={REDIRECT_URI}"
        "&scope=openid%20email%20profile"
        "&access_type=offline"
        "&prompt=consent"
    )
    return RedirectResponse(url)


@router.get("/callback")
async def google_callback(code: str = Query(...)):
    async with httpx.AsyncClient() as client:
        tok = await client.post("https://oauth2.googleapis.com/token", data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        })
        if tok.status_code != 200:
            raise HTTPException(401, "Google token exchange failed")
        access = tok.json()["access_token"]

        info = await client.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access}"})
        if info.status_code != 200:
            raise HTTPException(401, "Failed to fetch Google profile")

    g = info.json()
    email, name, sub = g.get("email"), g.get("name"), g["sub"]

    # TODO: upsert into your DB — find or create user by email, store google sub.
    # This is where your existing User model plugs in. For now, the JWT carries identity.

    token = make_token({"sub": email, "name": name, "provider": "google"})
    sep = "&" if "?" in FRONTEND_URL else "?"
    return RedirectResponse(f"{FRONTEND_URL}{sep}token={token}&email={email}&name={name.replace(' ', '%20')}")
