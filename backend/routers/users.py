from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from database import get_db
from typing import List, Optional

router = APIRouter()

class UserCreate(BaseModel):
    email: str
    name: str
    categories: Optional[List[str]] = []
    min_relevance: int = 5

class UserUpdate(BaseModel):
    name: Optional[str] = None
    categories: Optional[List[str]] = None
    min_relevance: Optional[int] = None
    active: Optional[bool] = None

@router.get("")
async def list_users():
    async with get_db() as db:
        users = await db.get_active_users()
    return {"users": [u.to_dict() for u in users]}

@router.post("")
async def create_user(data: UserCreate):
    async with get_db() as db:
        user = await db.create_user(
            email=data.email, name=data.name,
            categories=data.categories, min_relevance=data.min_relevance
        )
    return {"user": user.to_dict()}

@router.delete("/{email}")
async def delete_user(email: str):
    async with get_db() as db:
        await db.delete_user(email)
    return {"message": f"User {email} removed"}
