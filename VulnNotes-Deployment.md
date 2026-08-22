# VulnNotes — Deployment & Implementation Record

**Date:** August 22, 2026  
**Server:** 192.168.1.98 (Rocky Linux 9)  
**App URL:** http://192.168.1.98:8000

---

## What Was Built

The VulnNotes project was implemented from scratch based on the design spec in `VulnNotes-Guide.md`. Everything was created new — no source files existed prior to this session.

### Application

A FastAPI REST API with an intentional BOLA vulnerability (API1:2023), a techy dark web dashboard, and full OpenAPI documentation. Designed specifically for training Noname/Akamai Active Testing to distinguish normal from abnormal API behaviour.

### Scripts

Two Python scripts for traffic generation:

| Script | Purpose |
|--------|---------|
| `normal_traffic.py` | Generates realistic legitimate user traffic to establish a baseline |
| `exploit_bola.py` | Demonstrates cross-user note access (BOLA) to produce anomalous traffic |

---

## File Layout

```
Downloads/vulnnotes/          ← full app source (save this)
├── app/
│   ├── __init__.py
│   ├── database.py           ← SQLite engine, session, DB_PATH env var
│   ├── models.py             ← User + Note SQLAlchemy models
│   ├── schemas.py            ← Pydantic v2 request/response schemas
│   ├── auth.py               ← JWT (intentionally weak), bcrypt, OAuth2
│   └── main.py               ← FastAPI app, all routes, BOLA present
├── static/
│   └── index.html            ← Techy dark dashboard (live stats, seed, creds)
├── Dockerfile
└── requirements.txt

Downloads/normal_traffic.py   ← baseline script (copy also at ~/notes-test/)
Downloads/exploit_bola.py     ← BOLA exploit script (copy also at ~/notes-test/)
```

---

## Server Setup (192.168.1.98)

### Docker CE installed

Rocky Linux 9 ships with Podman. Docker CE was installed with `--allowerasing` to replace the `podman-docker` shim:

```bash
sudo dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo
sudo dnf install -y --allowerasing docker-ce docker-ce-cli containerd.io docker-buildx-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker mcropsey
```

### Python3 + httpx installed

```bash
sudo dnf install -y python3 python3-pip
sudo pip3 install httpx
```

### VulnNotes container running

```bash
docker run -d --name vulnnotes --restart=always \
  -p 8000:8000 \
  -v vulnnotes-data:/app/data \
  vulnnotes:latest
```

The SQLite database is in the named volume `vulnnotes-data` and survives container restarts and recreations.

---

## App Endpoints

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `/` | No | Dashboard |
| GET | `/health` | No | Health check |
| GET | `/docs` | No | Swagger UI |
| GET | `/redoc` | No | ReDoc |
| GET | `/openapi.json` | No | OpenAPI spec for Active Testing |
| POST | `/api/seed` | No | Create demo users + notes |
| GET | `/api/stats` | No | Dashboard metrics |
| POST | `/api/auth/register` | No | Create user |
| POST | `/api/auth/login` | No | Login → JWT |
| GET | `/api/users/me` | JWT | Current user |
| GET | `/api/notes` | JWT | List **own** notes (correct) |
| POST | `/api/notes` | JWT | Create note |
| GET | `/api/notes/public/recent` | No | Public feed |
| GET | `/api/notes/{id}` | JWT | **BOLA** — no ownership check |
| PUT | `/api/notes/{id}` | JWT | **BOLA** — no ownership check |
| DELETE | `/api/notes/{id}` | JWT | **BOLA** — no ownership check |

---

## Demo Accounts

| Username | Password | Role |
|----------|----------|------|
| alice | alice123 | user |
| bob | bob12345 | user |
| charlie | charlie1 | user |
| admin | admin123 | admin |

Create them by calling `POST /api/seed` (button on the dashboard, or `curl -X POST http://192.168.1.98:8000/api/seed`).

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

### Weak JWT

- Secret key is a static string baked into source (`app/auth.py`)
- Token lifetime is 24 hours (intentionally long)
- Tokens can be forged offline if the secret is known

---

## Traffic Scripts

Scripts are installed at `/home/mcropsey/notes-test/` on 192.168.1.98.

### normal_traffic.py

Generates realistic legitimate API usage across all four demo accounts using concurrent threads.

```bash
cd ~/notes-test
python3 normal_traffic.py --base-url http://192.168.1.98:8000 --duration 120 --workers 4
```

Options:

| Flag | Default | Description |
|------|---------|-------------|
| `--base-url` | `http://localhost:8000` | API target |
| `--duration` | `120` | How long to run in seconds |
| `--workers` | `4` | Concurrent users (max 4) |

Behaviour: each worker logs in, then randomly performs only **own-object** operations — create note, list own notes, read own note by ID, update own note, occasionally delete own note, plus `/me`, `/stats`, `/health`, and `/api/notes/public/recent`. Auto-seeds if the database is empty.

### exploit_bola.py

Produces the cross-user access pattern that Active Testing should detect.

```bash
# Standard proof (read + overwrite Alice's note as Bob)
python3 exploit_bola.py --base-url http://192.168.1.98:8000

# Aggressive (enumerate IDs 1-50, report every cross-user readable note)
python3 exploit_bola.py --base-url http://192.168.1.98:8000 --aggressive
```

Standard mode flow:
1. Alice creates a clearly private note (salary/bank content)
2. Bob reads Alice's note by ID — **succeeds** (BOLA read)
3. Bob overwrites Alice's note content — **succeeds** (BOLA write)
4. Alice reads her own note — sees Bob's tampered content

Aggressive mode: Bob walks note IDs 1-50 and reports every readable note with its owner ID, highlighting cross-user reads.

---

## Recommended Lab Workflow

1. **Start fresh:** `curl -X POST http://192.168.1.98:8000/api/seed`
2. **Establish baseline:** run `normal_traffic.py` for 2-5 minutes
3. **Let Active Testing baseline** the normal pattern
4. **Run exploit:** `python3 exploit_bola.py --base-url http://192.168.1.98:8000`
5. **Confirm detection** in Noname/Active Testing console — expect BOLA finding
6. **Fix:** add ownership check in `app/main.py`, rebuild container, re-run exploit — finding should clear

For the Jenkins pipeline:
- Stage 1: checkout + `docker build`
- Stage 2: smoke test (`/health`, `/openapi.json`)
- Stage 3: Active Testing scan with OpenAPI at `http://<container>:8000/openapi.json`
- Stage 4: gate on high/critical findings

---

## Useful Commands (on 192.168.1.98)

```bash
# Check container
docker ps | grep vulnnotes

# Tail logs
docker logs -f vulnnotes

# Restart
docker restart vulnnotes

# Rebuild after code change
cd /tmp/vulnnotes-build
docker build -t vulnnotes:latest .
docker stop vulnnotes && docker rm vulnnotes
docker run -d --name vulnnotes --restart=always -p 8000:8000 -v vulnnotes-data:/app/data vulnnotes:latest

# Re-seed
curl -X POST http://192.168.1.98:8000/api/seed

# Health check
curl http://192.168.1.98:8000/health
```

---

## Improvements Made vs. Original Design Spec

| Area | Change | Reason |
|------|--------|--------|
| CORS middleware | Added `CORSMiddleware(allow_origins=["*"])` | Required for Noname Active Testing to reach the API from its scanner origin |
| OpenAPI operation IDs | Added `operation_id=` to every route | Active Testing uses operation IDs to track and correlate findings across runs |
| Route ordering | `GET /api/notes/public/recent` defined before `GET /api/notes/{note_id}` | FastAPI matches routes in order; defining the literal path first prevents ambiguity |
| Database persistence | `DB_PATH` env var + named Docker volume `vulnnotes-data` | SQLite file survives container restarts; original spec had no persistence strategy |
| `updated_at` handling | Set explicitly in `update_note` rather than relying on SQLAlchemy `onupdate` | `onupdate` is unreliable with SQLite; explicit assignment is always correct |
| Docker `HEALTHCHECK` | Added `curl /health` healthcheck to Dockerfile | Allows `docker ps` to report health state; useful for Jenkins pipeline wait steps |
| Script auto-seed | Both scripts auto-seed if database is empty | Removes manual seed step from lab workflow |
| Script connectivity check | Both scripts verify `/health` before starting | Fails fast with a clear error instead of cryptic connection refused messages |
| Script colored output | ANSI colour output in both scripts | Makes normal vs. exploit traffic easy to distinguish at a glance |
| Aggressive mode output table | Tabular output with BOLA marker per note ID | Makes it obvious exactly which IDs are cross-user reads vs. own-object reads |

---

**For lab and educational use only. Do not expose to the public internet.**
