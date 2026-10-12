"""SlideIn lead-verification job API.

Replaces the old-VPS /opt/reacher/job_api. Serves the exact contract the
workspace-app expects (see workspace-app/app/api/lead-verification/*):

  POST /v0/check_email          single check (x-reacher-secret) -> reacher JSON
  POST /jobs                    bulk CSV upload (x-job-secret) -> {job_id, total_leads}
  GET  /jobs                    recent jobs for history
  GET  /jobs/{id}/status        progress + counts
  GET  /jobs/{id}/stream        SSE: one frame per checked row + terminal frame
  GET  /jobs/{id}/download      verified CSV (original columns + verdict)

Engine: reacherhq/backend on REACHER_URL (default http://127.0.0.1:8090).
Reacher never sends mail; it probes deliverability (syntax/MX/SMTP-RCPT).

Env (see /opt/reacher/job_api/.env):
  JOB_API_SECRET   required, guards /jobs* via x-job-secret
  REACHER_SECRET   required, guards /v0/check_email via x-reacher-secret
  REACHER_URL      reacher backend base (default loopback :8090)
  DATA_DIR         sqlite + csv store (default /opt/reacher/job_api/data)
"""
from __future__ import annotations

import csv
import hmac
import io
import json
import os
import queue
import sqlite3
import threading
import time
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

JOB_API_SECRET = os.environ.get("JOB_API_SECRET", "")
REACHER_SECRET = os.environ.get("REACHER_SECRET", "")
REACHER_URL = os.environ.get("REACHER_URL", "http://127.0.0.1:8090").rstrip("/")
DATA_DIR = Path(os.environ.get("DATA_DIR", "/opt/reacher/job_api/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "jobs.db"

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_ROWS = 10_000
REACHER_TIMEOUT = 25
POOL = ThreadPoolExecutor(max_workers=8)
DB_LOCK = threading.Lock()

app = FastAPI(title="slidein-lead-jobs", docs_url=None, redoc_url=None)


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with DB_LOCK, db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS jobs (
              job_id TEXT PRIMARY KEY, filename TEXT, status TEXT,
              total_leads INTEGER, checked_count INTEGER DEFAULT 0,
              error_message TEXT, created_at TEXT)"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS results (
              job_id TEXT, idx INTEGER, email TEXT, verdict TEXT,
              checked_at TEXT, PRIMARY KEY (job_id, idx))"""
        )


init_db()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def check_secret(provided: str | None, expected: str) -> None:
    if not expected:
        raise HTTPException(500, "server misconfigured: secret not set")
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(401, "bad secret")


def reacher_check(email: str) -> dict:
    """Single reacher call. Returns raw reacher JSON (or {'is_reachable': 'unknown'})."""
    req = urllib.request.Request(
        f"{REACHER_URL}/v0/check_email",
        data=json.dumps({"to_email": email}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=REACHER_TIMEOUT) as resp:
            return json.loads(resp.read().decode() or "{}")
    except Exception as e:  # engine down/timeout -> unknown, never throw
        return {"is_reachable": "unknown", "_error": str(e)[:120]}


def to_verdict(email: str, reach: dict) -> str:
    if "@" not in email or "." not in email.split("@")[-1]:
        return "INVALID_FORMAT"
    r = str(reach.get("is_reachable", "")).lower()
    if r == "safe":
        return "safe"
    if r == "risky":
        return "risky"
    if r == "invalid":
        return "invalid"
    if r == "unknown" and reach.get("_error"):
        return "error"
    return "unknown"


def summarize(job_id: str) -> dict:
    with DB_LOCK, db() as conn:
        rows = conn.execute(
            "SELECT verdict, COUNT(*) c FROM results WHERE job_id=? GROUP BY verdict",
            (job_id,),
        ).fetchall()
    counts = {"safe": 0, "risky": 0, "invalid": 0, "error": 0}
    for r in rows:
        v = r["verdict"]
        if v in ("safe", "risky"):
            counts[v] += r["c"]
        elif v in ("invalid", "INVALID_FORMAT"):
            counts["invalid"] += r["c"]
        else:  # unknown, error -> error bucket (matches frontend categoryOf)
            counts["error"] += r["c"]
    return counts


def job_shape(row: sqlite3.Row) -> dict:
    return {
        "job_id": row["job_id"],
        "filename": row["filename"],
        "created_at": row["created_at"],
        "status": row["status"],
        "total_leads": row["total_leads"],
        "checked_count": row["checked_count"],
        "error_message": row["error_message"],
        "counts": {"summary": summarize(row["job_id"])},
    }


def find_email_column(header: list[str]) -> int:
    for i, h in enumerate(header):
        if "email" in (h or "").strip().lower():
            return i
    return 0


def run_job(job_id: str, emails: list[str]) -> None:
    def one(idx_email: tuple[int, str]) -> None:
        idx, email = idx_email
        try:
            verdict = to_verdict(email, reacher_check(email))
        except Exception:
            verdict = "error"
        with DB_LOCK, db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO results VALUES (?,?,?,?,?)",
                (job_id, idx, email, verdict, now_iso()),
            )
            conn.execute(
                "UPDATE jobs SET checked_count=checked_count+1 WHERE job_id=?",
                (job_id,),
            )

    try:
        list(POOL.map(one, enumerate(emails)))
        final = "done"
    except Exception as e:
        with DB_LOCK, db() as conn:
            conn.execute(
                "UPDATE jobs SET status='failed', error_message=? WHERE job_id=?",
                (str(e)[:300], job_id),
            )
        return
    with DB_LOCK, db() as conn:
        conn.execute("UPDATE jobs SET status=? WHERE job_id=?", (final, job_id))


@app.post("/v0/check_email")
def v0_check_email(body: dict, x_reacher_secret: str | None = Header(None)):
    check_secret(x_reacher_secret, REACHER_SECRET)
    email = str(body.get("to_email", "")).strip()
    if not email:
        raise HTTPException(400, "to_email required")
    return JSONResponse(reacher_check(email))


@app.post("/jobs")
def create_job(file: UploadFile = File(...), x_job_secret: str | None = Header(None)):
    check_secret(x_job_secret, JOB_API_SECRET)
    name = (file.filename or "").lower()
    if not name.endswith(".csv"):
        raise HTTPException(400, "Only .csv files are accepted")
    raw = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "CSV exceeds 5MB")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "CSV must be UTF-8")
    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader if r and any(c.strip() for c in r)][: MAX_ROWS + 1]
    if len(rows) < 2:
        raise HTTPException(400, "CSV has no data rows")
    header, data = rows[0], rows[1 : MAX_ROWS + 1]
    col = find_email_column(header)
    emails = [r[col].strip() if col < len(r) else "" for r in data]
    emails = [e for e in emails if e]
    if not emails:
        raise HTTPException(400, "No emails found in CSV")
    job_id = str(uuid.uuid4())
    (DATA_DIR / f"{job_id}.csv").write_text(text)
    (DATA_DIR / f"{job_id}.header.json").write_text(json.dumps(header))
    with DB_LOCK, db() as conn:
        conn.execute(
            "INSERT INTO jobs VALUES (?,?,?,?,?,?,?)",
            (job_id, file.filename, "running", len(emails), 0, None, now_iso()),
        )
    threading.Thread(target=run_job, args=(job_id, emails), daemon=True).start()
    return {"job_id": job_id, "total_leads": len(emails), "filename": file.filename}


@app.get("/jobs")
def list_jobs(x_job_secret: str | None = Header(None)):
    check_secret(x_job_secret, JOB_API_SECRET)
    with DB_LOCK, db() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
    return [job_shape(r) for r in rows]


@app.get("/jobs/{job_id}/status")
def job_status(job_id: str, x_job_secret: str | None = Header(None)):
    check_secret(x_job_secret, JOB_API_SECRET)
    with DB_LOCK, db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
    if not row:
        raise HTTPException(404, "job not found")
    return job_shape(row)


@app.get("/jobs/{job_id}/stream")
def job_stream(job_id: str, x_job_secret: str | None = Header(None)):
    check_secret(x_job_secret, JOB_API_SECRET)
    with DB_LOCK, db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
    if not row:
        raise HTTPException(404, "job not found")

    def gen():
        sent = -1
        while True:
            with DB_LOCK, db() as conn:
                st = conn.execute(
                    "SELECT status FROM jobs WHERE job_id=?", (job_id,)
                ).fetchone()
                new = conn.execute(
                    "SELECT idx, email, verdict, checked_at FROM results"
                    " WHERE job_id=? AND idx>? ORDER BY idx",
                    (job_id, sent),
                ).fetchall()
            for r in new:
                sent = r["idx"]
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "index": r["idx"],
                            "email": r["email"],
                            "verdict": r["verdict"],
                            "checked_at": r["checked_at"],
                        }
                    )
                    + "\n\n"
                )
            status = st["status"] if st else "failed"
            if status in ("done", "failed"):
                yield "data: " + json.dumps({"status": status}) + "\n\n"
                return
            yield ": keepalive\n\n"
            time.sleep(1)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/jobs/{job_id}/download")
def job_download(job_id: str, x_job_secret: str | None = Header(None)):
    check_secret(x_job_secret, JOB_API_SECRET)
    with DB_LOCK, db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(404, "job not found")
        if row["status"] not in ("done", "failed"):
            raise HTTPException(409, "job still running")
        results = {
            r["idx"]: (r["email"], r["verdict"], r["checked_at"])
            for r in conn.execute(
                "SELECT idx, email, verdict, checked_at FROM results WHERE job_id=?",
                (job_id,),
            )
        }
    orig = (DATA_DIR / f"{job_id}.csv").read_text()
    reader = list(csv.reader(io.StringIO(orig)))
    header = reader[0] + ["reacher_verdict", "checked_at"]
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(header)
    col = find_email_column(reader[0])
    idx = 0
    for r in reader[1:]:
        email = r[col].strip() if col < len(r) else ""
        if not email:
            continue
        v = results.get(idx, (email, "error", ""))
        w.writerow(r + [v[1], v[2]])
        idx += 1
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(out.getvalue(), media_type="text/csv")
