from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta

from core.security import create_access_token, verify_password, get_password_hash
from db import Database

router = APIRouter()


@router.post("/api/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """Standard OAuth2 password flow: returns JWT access token."""
    user = Database.get_user_by_email(form_data.username)
    if not user:
        raise HTTPException(status_code=400, detail="Usuário ou senha inválidos")

    if not verify_password(form_data.password, user.get("password_hash")):
        raise HTTPException(status_code=400, detail="Usuário ou senha inválidos")

    access_token_expires = timedelta(minutes=60*8)
    token = create_access_token({"user_id": user["id"], "email": user["email"], "role": user.get("role", "student")}, expires_delta=access_token_expires)
    return {"access_token": token, "token_type": "bearer"}
