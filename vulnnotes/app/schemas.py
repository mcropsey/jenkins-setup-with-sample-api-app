from __future__ import annotations
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ── User ──────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str
    email: Optional[str] = None
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    is_admin: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Note ──────────────────────────────────────────────────────────────────────

class NoteCreate(BaseModel):
    title: str
    content: str


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None


class NoteOut(BaseModel):
    id: int
    title: str
    content: str
    owner_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Auth ──────────────────────────────────────────────────────────────────────

class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None
