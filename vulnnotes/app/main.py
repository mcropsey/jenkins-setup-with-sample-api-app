from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import models, schemas
from .auth import create_access_token, get_current_user, hash_password, verify_password
from .database import engine, get_db

models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="VulnNotes API",
    description=(
        "Intentionally vulnerable Notes API for security training. "
        "Contains BOLA (API1:2023) and weak JWT design. For lab use only."
    ),
    version="1.0.0",
    openapi_tags=[
        {"name": "auth", "description": "Registration, login, current user"},
        {"name": "notes", "description": "CRUD — BOLA present on by-ID endpoints"},
        {"name": "system", "description": "Stats, seed, health"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory 24-hour request counter
_req_log: deque = deque()
_req_lock = threading.Lock()


@app.middleware("http")
async def track_requests(request, call_next):
    now = datetime.now(timezone.utc)
    with _req_lock:
        _req_log.append(now)
        cutoff = now - timedelta(hours=24)
        while _req_log and _req_log[0] < cutoff:
            _req_log.popleft()
    response = await call_next(request)
    response.headers["X-VulnNotes-Version"] = "1.0.0"
    return response


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse("static/index.html")


# ── System ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["system"], operation_id="health_check")
def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/stats", tags=["system"], operation_id="get_stats")
def get_stats(db: Session = Depends(get_db)):
    total_notes = db.query(models.Note).count()
    active_users = db.query(models.User).count()
    today = datetime.now(timezone.utc).date()
    notes_today = db.query(models.Note).filter(
        models.Note.created_at >= datetime(today.year, today.month, today.day)
    ).count()
    all_notes = db.query(models.Note).all()
    avg_len = int(sum(len(n.content) for n in all_notes) / max(len(all_notes), 1))
    with _req_lock:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        req_24h = sum(1 for t in _req_log if t >= cutoff)
    return {
        "total_notes": total_notes,
        "active_users": active_users,
        "notes_today": notes_today,
        "avg_note_length": avg_len,
        "api_requests_24h": req_24h,
    }


@app.post("/api/seed", tags=["system"], operation_id="seed_data", status_code=201)
def seed_data(db: Session = Depends(get_db)):
    USERS = [
        {"username": "alice",   "password": "alice123",  "email": "alice@lab.local",   "is_admin": False},
        {"username": "bob",     "password": "bob12345",  "email": "bob@lab.local",     "is_admin": False},
        {"username": "charlie", "password": "charlie1",  "email": "charlie@lab.local", "is_admin": False},
        {"username": "admin",   "password": "admin123",  "email": "admin@lab.local",   "is_admin": True},
    ]
    NOTES = [
        ("alice",   "Meeting notes Q3",         "Discussed roadmap, security priorities, and Q4 planning. Key items: API hardening, pentest scheduled for October."),
        ("alice",   "Shopping list",             "Milk, eggs, bread, coffee (dark roast), almond flour, oat milk"),
        ("alice",   "Private — salary info",     "My current salary: $142,000. Negotiating bonus structure. Do not share with anyone."),
        ("bob",     "Project ideas",             "1. Build a Rust CLI tool. 2. Contribute to open source. 3. Set up home lab with Proxmox."),
        ("bob",     "Gym routine",               "Mon: chest/tri. Wed: back/bi. Fri: legs. Sat: cardio 5k run."),
        ("charlie", "Study notes — OSCP",        "Enumeration: nmap -sV -sC. Buffer overflow methodology. Privilege escalation checklist. Active Directory notes."),
        ("charlie", "API keys — dev env",        "STRIPE_TEST_KEY=sk_test_abc123... SENDGRID_API_KEY=SG.xyz... (test credentials only, not real)"),
        ("admin",   "Admin — user mgmt log",     "2026-08-01: Onboarded alice, bob, charlie. 2026-08-10: Reset bob password upon request."),
        ("alice",   "Book recommendations",      "Designing Data-Intensive Applications, The Phoenix Project, Clean Architecture"),
        ("bob",     "Home network plan",         "Switch to 10GbE backbone. Add Proxmox node. VLANs: IoT, trusted, DMZ, management."),
    ]

    uid_map: dict[str, int] = {}
    created_users = 0
    for u in USERS:
        existing = db.query(models.User).filter(models.User.username == u["username"]).first()
        if not existing:
            user = models.User(
                username=u["username"],
                email=u["email"],
                hashed_password=hash_password(u["password"]),
                is_admin=u["is_admin"],
            )
            db.add(user)
            db.flush()
            uid_map[u["username"]] = user.id
            created_users += 1
        else:
            uid_map[u["username"]] = existing.id

    db.commit()
    created_notes = 0
    for username, title, content in NOTES:
        owner_id = uid_map.get(username)
        if owner_id:
            db.add(models.Note(title=title, content=content, owner_id=owner_id))
            created_notes += 1
    db.commit()
    return {"created_users": created_users, "created_notes": created_notes, "message": "Seed complete"}


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.post("/api/auth/register", tags=["auth"], operation_id="register_user",
          response_model=schemas.UserOut, status_code=201)
def register(user_in: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.username == user_in.username).first():
        raise HTTPException(status_code=400, detail="Username already registered")
    user = models.User(
        username=user_in.username,
        email=user_in.email,
        hashed_password=hash_password(user_in.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/api/auth/login", tags=["auth"], operation_id="login_user",
          response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    return {"access_token": create_access_token({"sub": user.username}), "token_type": "bearer"}


@app.get("/api/users/me", tags=["auth"], operation_id="get_current_user_info",
         response_model=schemas.UserOut)
def get_me(current_user: models.User = Depends(get_current_user)):
    return current_user


# ── Notes ─────────────────────────────────────────────────────────────────────

@app.get("/api/notes/public/recent", tags=["notes"], operation_id="get_recent_public_notes")
def public_recent(db: Session = Depends(get_db)):
    notes = db.query(models.Note).order_by(models.Note.created_at.desc()).limit(10).all()
    return [
        {"id": n.id, "title": n.title, "preview": n.content[:80], "created_at": n.created_at}
        for n in notes
    ]


@app.get("/api/notes", tags=["notes"], operation_id="list_own_notes",
         response_model=List[schemas.NoteOut])
def list_notes(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(models.Note).filter(models.Note.owner_id == current_user.id).all()


@app.post("/api/notes", tags=["notes"], operation_id="create_note",
          response_model=schemas.NoteOut, status_code=201)
def create_note(
    note_in: schemas.NoteCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = models.Note(title=note_in.title, content=note_in.content, owner_id=current_user.id)
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


# BOLA: any authenticated user can read any note by ID — ownership is NOT checked
@app.get("/api/notes/{note_id}", tags=["notes"], operation_id="get_note_by_id",
         response_model=schemas.NoteOut)
def get_note(
    note_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = db.query(models.Note).filter(models.Note.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    # INTENTIONAL BOLA — ownership check omitted
    # Fix: if note.owner_id != current_user.id: raise HTTPException(403, "Not authorized")
    return note


# BOLA: any authenticated user can overwrite any note by ID
@app.put("/api/notes/{note_id}", tags=["notes"], operation_id="update_note",
         response_model=schemas.NoteOut)
def update_note(
    note_id: int,
    note_in: schemas.NoteUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = db.query(models.Note).filter(models.Note.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    # INTENTIONAL BOLA — ownership check omitted
    if note_in.title is not None:
        note.title = note_in.title
    if note_in.content is not None:
        note.content = note_in.content
    note.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(note)
    return note


# BOLA: any authenticated user can delete any note by ID
@app.delete("/api/notes/{note_id}", tags=["notes"], operation_id="delete_note",
            status_code=204)
def delete_note(
    note_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = db.query(models.Note).filter(models.Note.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    # INTENTIONAL BOLA — ownership check omitted
    db.delete(note)
    db.commit()
