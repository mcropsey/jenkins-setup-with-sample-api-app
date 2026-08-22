#!/usr/bin/env python3
"""
normal_traffic.py — Baseline traffic generator for VulnNotes
Generates realistic legitimate user behaviour so Noname / Akamai Active Testing
can learn a normal baseline before the BOLA exploit is introduced.

Usage:
  python normal_traffic.py --base-url http://192.168.1.98:8000 --duration 120 --workers 4
"""

import argparse
import random
import sys
import threading
import time
from datetime import datetime
from typing import Optional

try:
    import httpx
except ImportError:
    print("[ERROR] httpx not installed. Run:  pip install httpx")
    sys.exit(1)

# ── ANSI colours ──────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
CYAN   = "\033[96m"
YELLOW = "\033[93m"
DIM    = "\033[2m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

ACCOUNTS = [
    {"username": "alice",   "password": "alice123"},
    {"username": "bob",     "password": "bob12345"},
    {"username": "charlie", "password": "charlie1"},
    {"username": "admin",   "password": "admin123"},
]

NOTE_TITLES = [
    "Daily standup notes", "Meeting summary", "TODO list", "Research links",
    "Book notes", "Project ideas", "Weekly recap", "Personal journal",
    "Shopping list", "Learning goals",
]
NOTE_CONTENTS = [
    "Reviewed PRs, discussed deployment strategy, aligned on API contract.",
    "Remember to check the backlog. Priority: security hardening this sprint.",
    "1. Write unit tests. 2. Update docs. 3. Review PR from Charlie.",
    "Interesting article on API security: OWASP Top 10 2023 changes.",
    "Notes from Clean Architecture chapter 5 — boundary rules.",
    "Potential project: build a lightweight JWT validator CLI tool.",
    "Good week overall. Deployed two features. One minor incident resolved.",
    "Feeling productive. Focus on deep work in the mornings.",
    "Oat milk, coffee beans, pasta, tomatoes, olive oil.",
    "Learn Rust basics, contribute to OSS, read one book per month.",
]

_lock   = threading.Lock()
_counts = {"ok": 0, "err": 0}
_stop   = threading.Event()


def log(worker: str, action: str, status: str, detail: str = ""):
    ts = datetime.now().strftime("%H:%M:%S")
    colour = GREEN if status == "200" else YELLOW
    with _lock:
        print(f"{DIM}{ts}{RESET} {CYAN}[{worker}]{RESET} {action:<30} {colour}{status}{RESET} {DIM}{detail}{RESET}")


def ensure_seed(base_url: str):
    try:
        with httpx.Client(base_url=base_url, timeout=10) as client:
            r = client.get("/api/stats")
            if r.status_code == 200 and r.json().get("total_notes", 0) == 0:
                print(f"{YELLOW}[setup] No data found — running seed...{RESET}")
                client.post("/api/seed")
                print(f"{GREEN}[setup] Seed complete.{RESET}")
    except Exception as e:
        print(f"{YELLOW}[setup] Could not auto-seed: {e}{RESET}")


def login(client: httpx.Client, username: str, password: str) -> Optional[str]:
    try:
        r = client.post("/api/auth/login", data={"username": username, "password": password})
        if r.status_code == 200:
            return r.json()["access_token"]
    except Exception:
        pass
    return None


def worker_loop(worker_id: int, base_url: str, account: dict, duration: float):
    name = f"w{worker_id}:{account['username']}"
    headers = {}

    with httpx.Client(base_url=base_url, timeout=10, headers=headers) as client:
        token = login(client, account["username"], account["password"])
        if not token:
            log(name, "login", "FAIL", "could not authenticate")
            return
        log(name, "login", "200", f"authenticated as {account['username']}")
        client.headers["Authorization"] = f"Bearer {token}"
        own_note_ids: list[int] = []

        # Pre-populate own note list
        try:
            r = client.get("/api/notes")
            if r.status_code == 200:
                own_note_ids = [n["id"] for n in r.json()]
        except Exception:
            pass

        end_time = time.time() + duration

        while not _stop.is_set() and time.time() < end_time:
            action = random.choices(
                ["create", "list", "get_own", "update_own", "me", "stats", "health", "recent", "delete_own"],
                weights=[15,      20,    20,        10,          10,    10,     5,        8,         2],
            )[0]

            try:
                if action == "create":
                    title   = random.choice(NOTE_TITLES) + f" {random.randint(1,999)}"
                    content = random.choice(NOTE_CONTENTS)
                    r = client.post("/api/notes", json={"title": title, "content": content})
                    log(name, "POST /api/notes", str(r.status_code), title[:30])
                    if r.status_code == 201:
                        own_note_ids.append(r.json()["id"])
                    with _lock:
                        _counts["ok" if r.status_code < 400 else "err"] += 1

                elif action == "list":
                    r = client.get("/api/notes")
                    log(name, "GET  /api/notes", str(r.status_code), f"{len(r.json())} notes" if r.status_code == 200 else "")
                    if r.status_code == 200:
                        own_note_ids = [n["id"] for n in r.json()]
                    with _lock:
                        _counts["ok" if r.status_code < 400 else "err"] += 1

                elif action == "get_own" and own_note_ids:
                    nid = random.choice(own_note_ids)
                    r = client.get(f"/api/notes/{nid}")
                    log(name, f"GET  /api/notes/{nid}", str(r.status_code), "(own note)")
                    with _lock:
                        _counts["ok" if r.status_code < 400 else "err"] += 1

                elif action == "update_own" and own_note_ids:
                    nid = random.choice(own_note_ids)
                    new_content = random.choice(NOTE_CONTENTS) + " [updated]"
                    r = client.put(f"/api/notes/{nid}", json={"content": new_content})
                    log(name, f"PUT  /api/notes/{nid}", str(r.status_code), "(own note)")
                    with _lock:
                        _counts["ok" if r.status_code < 400 else "err"] += 1

                elif action == "delete_own" and len(own_note_ids) > 2:
                    nid = own_note_ids.pop(random.randrange(len(own_note_ids)))
                    r = client.delete(f"/api/notes/{nid}")
                    log(name, f"DEL  /api/notes/{nid}", str(r.status_code), "(own note)")
                    with _lock:
                        _counts["ok" if r.status_code < 400 else "err"] += 1

                elif action == "me":
                    r = client.get("/api/users/me")
                    log(name, "GET  /api/users/me", str(r.status_code))
                    with _lock:
                        _counts["ok" if r.status_code < 400 else "err"] += 1

                elif action == "stats":
                    r = client.get("/api/stats")
                    log(name, "GET  /api/stats", str(r.status_code))
                    with _lock:
                        _counts["ok" if r.status_code < 400 else "err"] += 1

                elif action == "health":
                    r = client.get("/health")
                    log(name, "GET  /health", str(r.status_code))
                    with _lock:
                        _counts["ok" if r.status_code < 400 else "err"] += 1

                elif action == "recent":
                    r = client.get("/api/notes/public/recent")
                    log(name, "GET  /api/notes/public/recent", str(r.status_code))
                    with _lock:
                        _counts["ok" if r.status_code < 400 else "err"] += 1

            except Exception as e:
                log(name, action, "ERR", str(e))
                with _lock:
                    _counts["err"] += 1

            time.sleep(random.uniform(0.3, 1.8))


def main():
    parser = argparse.ArgumentParser(description="VulnNotes normal traffic generator")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--duration", type=int, default=120, help="Run duration in seconds (default 120)")
    parser.add_argument("--workers",  type=int, default=4,   help="Concurrent worker count (default 4, max 4)")
    args = parser.parse_args()

    args.workers = min(args.workers, len(ACCOUNTS))

    print(f"\n{BOLD}{CYAN}VulnNotes — Normal Traffic Generator{RESET}")
    print(f"{DIM}Target : {args.base_url}{RESET}")
    print(f"{DIM}Workers: {args.workers}  |  Duration: {args.duration}s{RESET}\n")

    # Connectivity check
    try:
        r = httpx.get(f"{args.base_url}/health", timeout=5)
        if r.status_code != 200:
            raise ValueError(f"Health check returned {r.status_code}")
        print(f"{GREEN}[ok] API reachable at {args.base_url}{RESET}\n")
    except Exception as e:
        print(f"\033[91m[ERROR] Cannot reach API: {e}\033[0m")
        sys.exit(1)

    ensure_seed(args.base_url)

    threads = []
    accounts = ACCOUNTS[:args.workers]
    for i, account in enumerate(accounts):
        t = threading.Thread(target=worker_loop, args=(i + 1, args.base_url, account, args.duration), daemon=True)
        threads.append(t)

    start = time.time()
    for t in threads:
        t.start()

    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        _stop.set()
        print(f"\n{YELLOW}[interrupted]{RESET}")

    elapsed = time.time() - start
    print(f"\n{BOLD}── Summary ──────────────────────────────{RESET}")
    print(f"  Duration : {elapsed:.1f}s")
    print(f"  Success  : {GREEN}{_counts['ok']}{RESET}")
    print(f"  Errors   : {YELLOW}{_counts['err']}{RESET}")
    print(f"{DIM}Normal baseline traffic complete. Ready to run exploit_bola.py.{RESET}\n")


if __name__ == "__main__":
    main()
