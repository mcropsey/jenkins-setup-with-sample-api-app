# VulnNotes — Deployment & Implementation Record

**Date:** August 22, 2026  
**Server:** 192.168.1.98 (Rocky Linux 9)  
**App URL:** http://192.168.1.98:8000  
**OpenAPI spec:** http://192.168.1.98:8000/openapi.json  
**Swagger UI:** http://192.168.1.98:8000/docs

---

## What Was Built

The VulnNotes project was implemented from scratch. It is a fully interactive FastAPI application with:

- A **single-page app UI** — login, note management, and a built-in BOLA exploit lab, all operable from the browser without touching the API directly
- A **REST API** with intentional BOLA (API1:2023) and weak JWT vulnerabilities for security training
- Full **OpenAPI / Swagger** documentation for use with Noname/Akamai Active Testing
- Two **Python traffic scripts** for generating normal baseline traffic and demonstrating the BOLA exploit

---

## File Layout

```
Downloads/vulnnotes/              ← full app source
├── app/
│   ├── __init__.py
│   ├── database.py               ← SQLite engine, DB_PATH env var, session
│   ├── models.py                 ← User + Note SQLAlchemy models
│   ├── schemas.py                ← Pydantic v2 request/response schemas
│   ├── auth.py                   ← JWT (intentionally weak), bcrypt, OAuth2
│   └── main.py                   ← FastAPI app, all routes, BOLA present
├── static/
│   └── index.html                ← Full interactive SPA (login, notes, BOLA lab)
├── Dockerfile
└── requirements.txt

Downloads/normal_traffic.py       ← baseline traffic script
Downloads/exploit_bola.py         ← BOLA exploit script
Downloads/vulnnotes-openapi.json  ← OpenAPI 3.1 spec (for Active Testing import)
```

Scripts are also deployed to `/home/mcropsey/notes-test/` on 192.168.1.98.

---

## How to Use the App

### 1. Open the dashboard

Navigate to **http://192.168.1.98:8000** in a browser.

### 2. Seed demo data (first time only)

On the login screen click **"Seed demo users + notes"**, or run:

```bash
curl -X POST http://192.168.1.98:8000/api/seed
```

This creates four demo users and ten sample notes. Safe to run multiple times — skips existing usernames.

### 3. Log in

Use one of the **quick-login buttons** on the login screen, or type credentials manually:

| Username | Password | Role |
|----------|----------|------|
| alice | alice123 | user |
| bob | bob12345 | user |
| charlie | charlie1 | user |
| admin | admin123 | admin |

### 4. Manage notes (sidebar: My Notes / New Note)

- **My Notes** — lists all notes belonging to the logged-in user. Click a note to view it in full. Use the **EDIT** button to modify the title or content in-place. Use **DEL** to delete.
- **New Note** — form to create a new note with title and content.

### 5. Exploit the BOLA vulnerability (sidebar: BOLA Lab)

The BOLA Lab lets you hit the vulnerable endpoints directly from the UI:

| Tool | What it does |
|------|-------------|
| **Read Any Note By ID** | Enter any note ID — you can read notes belonging to other users. Shows a `⚠ BOLA` warning when the note's owner ID differs from your user ID. |
| **Overwrite Any Note By ID** | Enter an ID and replacement content — overwrites another user's note. |
| **Delete Any Note By ID** | Deletes any note regardless of owner. |
| **Enumerate IDs** | Walk a range of note IDs and report which ones are readable and whether they belong to you or another user. This is the aggressive pattern Active Testing should flag. |

**Suggested demo sequence:**
1. Log in as **alice** — note the IDs of her notes in My Notes
2. Logout, log in as **bob**
3. Go to BOLA Lab → Read Any Note By ID → enter one of Alice's IDs
4. Bob reads Alice's private note — `⚠ BOLA READ SUCCEEDED`
5. Overwrite it, then log back in as Alice to see the tampered content

### 6. Explore the API

- **SWAGGER button** (top-right header) → opens Swagger UI at `/docs`
- **ReDoc** → `/redoc`
- **Raw OpenAPI spec** → `/openapi.json` (use this URL when configuring Active Testing)
- **API Stats** (sidebar) → live request counts, note counts, recent public feed

---

## Running the Traffic Scripts (on 192.168.1.98)

### Establish a normal baseline

```bash
cd ~/notes-test
python3 normal_traffic.py --base-url http://192.168.1.98:8000 --duration 120 --workers 4
```

| Flag | Default | Description |
|------|---------|-------------|
| `--base-url` | `http://localhost:8000` | API target |
| `--duration` | `120` | Run duration in seconds |
| `--workers` | `4` | Concurrent users (max 4) |

Each worker logs in as a different demo user and performs only legitimate own-object operations: create note, list own notes, read own note by ID, update own note, occasional delete, plus `/me`, `/stats`, `/health`, and `/api/notes/public/recent`. Auto-seeds if the database is empty.

### Run the BOLA exploit

```bash
# Standard — Alice creates a private note, Bob reads + overwrites it
python3 exploit_bola.py --base-url http://192.168.1.98:8000

# Aggressive — Bob enumerates IDs 1–50 and reports all cross-user reads
python3 exploit_bola.py --base-url http://192.168.1.98:8000 --aggressive
```

---

## Recommended Lab Workflow (Noname Active Testing)

1. Seed: `curl -X POST http://192.168.1.98:8000/api/seed`
2. Run `normal_traffic.py` for 2–5 minutes to establish a baseline
3. Configure Active Testing with the OpenAPI spec at `http://192.168.1.98:8000/openapi.json` and the four demo credentials
4. Let Active Testing learn the normal pattern
5. Run `exploit_bola.py --aggressive` — this is the cross-user access pattern to detect
6. Confirm a BOLA finding appears in the Active Testing console
7. **(Fix exercise)** Add the ownership check in `app/main.py` (see below), rebuild the container, re-run the exploit — the finding should clear

---

## API Reference

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `/` | No | Interactive SPA dashboard |
| GET | `/health` | No | Health check |
| GET | `/docs` | No | Swagger UI |
| GET | `/redoc` | No | ReDoc |
| GET | `/openapi.json` | No | OpenAPI 3.1 spec |
| GET | `/api/stats` | No | Aggregate metrics |
| POST | `/api/seed` | No | Create demo users + notes |
| POST | `/api/auth/register` | No | Create user |
| POST | `/api/auth/login` | No | Login → JWT |
| GET | `/api/users/me` | JWT | Current user info |
| GET | `/api/notes` | JWT | List **own** notes only (correct) |
| POST | `/api/notes` | JWT | Create note |
| GET | `/api/notes/public/recent` | No | Public truncated feed |
| GET | `/api/notes/{id}` | JWT | **BOLA** — no ownership check |
| PUT | `/api/notes/{id}` | JWT | **BOLA** — no ownership check |
| DELETE | `/api/notes/{id}` | JWT | **BOLA** — no ownership check |

---

## Intentional Vulnerabilities

### API1:2023 — Broken Object Level Authorization (BOLA)

`GET /api/notes/{id}`, `PUT /api/notes/{id}`, and `DELETE /api/notes/{id}` verify only that the caller holds a valid JWT. They do **not** check `note.owner_id == current_user.id`.

Any authenticated user who knows or guesses a note ID can read, modify, or delete it.

**Fix (Jenkins exercise):** In `app/main.py`, add to `get_note`, `update_note`, and `delete_note`:

```python
if note.owner_id != current_user.id:
    raise HTTPException(status_code=403, detail="Not authorized to access this note")
```

Then rebuild and redeploy the container (see Useful Commands below). Re-run the exploit — BOLA Lab will show 403s and Active Testing should clear the finding.

### Weak JWT

- Secret key is a static string baked into source (`app/auth.py`)
- Token lifetime is 24 hours (intentionally long)
- Tokens can be forged offline if the secret is known

---

## Server Setup (192.168.1.98)

### Docker CE

Rocky Linux 9 ships with Podman. Docker CE was installed with `--allowerasing` to replace the `podman-docker` shim:

```bash
sudo dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo
sudo dnf install -y --allowerasing docker-ce docker-ce-cli containerd.io docker-buildx-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker mcropsey
```

### Python3 + httpx

```bash
sudo dnf install -y python3 python3-pip
sudo pip3 install httpx
```

### Container

```bash
docker run -d --name vulnnotes --restart=always \
  -p 8000:8000 \
  -v vulnnotes-data:/app/data \
  vulnnotes:latest
```

The SQLite database lives in the named volume `vulnnotes-data` — it survives container restarts and recreations.

---

## Useful Commands (on 192.168.1.98)

```bash
# Check status
docker ps | grep vulnnotes

# Tail logs
docker logs -f vulnnotes

# Restart
docker restart vulnnotes

# Rebuild after changing app source
cd /tmp/vulnnotes-build
docker build -t vulnnotes:latest .
docker stop vulnnotes && docker rm vulnnotes
docker run -d --name vulnnotes --restart=always -p 8000:8000 -v vulnnotes-data:/app/data vulnnotes:latest

# Re-seed data
curl -X POST http://192.168.1.98:8000/api/seed

# Health check
curl http://192.168.1.98:8000/health
```

---

## Implementation Notes & Fixes Applied

| Area | What was done | Why |
|------|--------------|-----|
| Interactive SPA UI | Rebuilt `index.html` from stats-only dashboard to full SPA with login, note CRUD, and BOLA Lab | Original read-only dashboard gave no way to operate the app or hit APIs from the browser |
| CORS middleware | Added `CORSMiddleware(allow_origins=["*"])` | Required for Noname Active Testing to reach the API from its scanner origin |
| OpenAPI operation IDs | Added `operation_id=` to every route | Active Testing uses operation IDs to track and correlate findings across runs |
| Route ordering | `GET /api/notes/public/recent` defined before `GET /api/notes/{note_id}` | FastAPI matches routes in order; the literal path must come first |
| Database persistence | `DB_PATH` env var + named Docker volume `vulnnotes-data` | SQLite file survives container restarts |
| `updated_at` handling | Set explicitly in `update_note` rather than relying on SQLAlchemy `onupdate` | `onupdate` is unreliable with SQLite; explicit assignment is always correct |
| Docker `HEALTHCHECK` | Added `curl /health` healthcheck to Dockerfile | Allows `docker ps` to report container health; useful for Jenkins pipeline wait steps |
| `bcrypt` version pinned | Pinned `bcrypt==3.2.2` in requirements.txt | `passlib` 1.7.4 raises a `ValueError` on startup with `bcrypt` 4.x due to a strict 72-byte password limit check |
| Python 3.9 compatibility | Changed `str \| None` type hints to `Optional[str]` in both scripts | Rocky Linux 9 ships Python 3.9; the `X \| Y` union syntax requires Python 3.10+ |
| Script auto-seed | Both scripts auto-seed if database is empty | Removes manual seed step from lab workflow |
| Script connectivity check | Both scripts verify `/health` on startup | Fails fast with a clear error instead of cryptic connection-refused messages |
| Colored terminal output | ANSI colour in both scripts | Makes normal vs. exploit traffic easy to distinguish at a glance |

---

**For lab and educational use only. Do not expose to the public internet.**
