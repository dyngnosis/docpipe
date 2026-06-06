import json
import os
import uuid
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    Form,
    HTTPException,
    Request,
    UploadFile,
    File,
    status,
)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from passlib.hash import bcrypt as bcrypt_hash
from pydantic import BaseModel

from auth import (
    SESSION_COOKIE,
    create_session_token,
    get_current_user,
    get_current_user_optional,
    require_admin,
)
from converter import OUTPUT_DIR, SUPPORTED_FORMATS, run_conversion
from db import get_db, init_db
from pipeline import Pipeline, PipelineStep

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/data/uploads")
ALLOWED_EXTENSIONS = {".md", ".markdown", ".html", ".htm", ".txt", ".rst", ".tex", ".docx", ".odt"}

app = FastAPI(title="Docpipe", description="Document conversion service")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.on_event("startup")
async def startup():
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    init_db()


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user = get_current_user_optional(request)
    if user:
        return RedirectResponse("/dashboard", status_code=302)
    return RedirectResponse("/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_current_user_optional(request)
    if user:
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    with get_db() as db:
        row = db.execute(
            "SELECT id, password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
    if not row or not bcrypt_hash.verify(password, row["password_hash"]):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid username or password"},
            status_code=401,
        )
    token = create_session_token(row["id"])
    response = RedirectResponse("/dashboard", status_code=302)
    response.set_cookie(
        SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=60 * 60 * 8
    )
    return response


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "error": None})


@app.post("/register")
async def register_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    email: str = Form(""),
):
    if len(username) < 3:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Username must be at least 3 characters"},
            status_code=400,
        )
    if len(password) < 6:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Password must be at least 6 characters"},
            status_code=400,
        )
    ph = bcrypt_hash.hash(password)
    try:
        with get_db() as db:
            db.execute(
                "INSERT INTO users (username, password_hash, email) VALUES (?, ?, ?)",
                (username, ph, email or None),
            )
    except Exception:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Username already taken"},
            status_code=400,
        )
    return RedirectResponse("/login?registered=1", status_code=302)


@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    return response


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: dict = Depends(get_current_user)):
    with get_db() as db:
        doc_count = db.execute(
            "SELECT COUNT(*) as c FROM documents WHERE user_id = ?", (user["id"],)
        ).fetchone()["c"]
        job_count = db.execute(
            "SELECT COUNT(*) as c FROM jobs WHERE user_id = ?", (user["id"],)
        ).fetchone()["c"]
        recent_jobs = db.execute(
            """SELECT j.*, d.original_name FROM jobs j
               LEFT JOIN documents d ON j.document_id = d.id
               WHERE j.user_id = ? ORDER BY j.created_at DESC LIMIT 5""",
            (user["id"],),
        ).fetchall()
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "doc_count": doc_count,
            "job_count": job_count,
            "recent_jobs": [dict(r) for r in recent_jobs],
        },
    )


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

@app.get("/documents", response_class=HTMLResponse)
async def documents_page(request: Request, user: dict = Depends(get_current_user)):
    with get_db() as db:
        docs = db.execute(
            "SELECT * FROM documents WHERE user_id = ? ORDER BY uploaded_at DESC",
            (user["id"],),
        ).fetchall()
    return templates.TemplateResponse(
        "documents.html",
        {"request": request, "user": user, "documents": [dict(d) for d in docs]},
    )


@app.post("/documents/upload")
async def upload_document(
    request: Request,
    user: dict = Depends(get_current_user),
    file: UploadFile = File(...),
):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return templates.TemplateResponse(
            "documents.html",
            {
                "request": request,
                "user": user,
                "documents": [],
                "error": f"Unsupported file type: {ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
            },
            status_code=400,
        )
    uid = uuid.uuid4().hex
    stored_name = f"{uid}{ext}"
    dest = os.path.join(UPLOAD_DIR, stored_name)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    size = os.path.getsize(dest)
    fmt = ext.lstrip(".")
    with get_db() as db:
        db.execute(
            "INSERT INTO documents (user_id, filename, original_name, format, size) VALUES (?, ?, ?, ?, ?)",
            (user["id"], stored_name, file.filename, fmt, size),
        )
    return RedirectResponse("/documents", status_code=302)


@app.post("/documents/{doc_id}/delete")
async def delete_document(
    doc_id: int, request: Request, user: dict = Depends(get_current_user)
):
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM documents WHERE id = ? AND user_id = ?", (doc_id, user["id"])
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")
        path = os.path.join(UPLOAD_DIR, row["filename"])
        if os.path.exists(path):
            os.remove(path)
        db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    return RedirectResponse("/documents", status_code=302)


# ---------------------------------------------------------------------------
# Convert
# ---------------------------------------------------------------------------

@app.get("/convert", response_class=HTMLResponse)
async def convert_page(request: Request, user: dict = Depends(get_current_user)):
    with get_db() as db:
        docs = db.execute(
            "SELECT * FROM documents WHERE user_id = ? ORDER BY uploaded_at DESC",
            (user["id"],),
        ).fetchall()
        pipelines = db.execute(
            "SELECT id, name FROM pipelines WHERE user_id = ? ORDER BY name",
            (user["id"],),
        ).fetchall()
    return templates.TemplateResponse(
        "convert.html",
        {
            "request": request,
            "user": user,
            "documents": [dict(d) for d in docs],
            "formats": SUPPORTED_FORMATS,
            "pipelines": [dict(p) for p in pipelines],
            "error": None,
            "success": None,
        },
    )


@app.post("/convert")
async def convert_post(
    request: Request,
    user: dict = Depends(get_current_user),
    document_id: int = Form(...),
    output_format: str = Form(""),
    output_name: str = Form("output"),
    pipeline_id: Optional[int] = Form(None),
):
    with get_db() as db:
        doc = db.execute(
            "SELECT * FROM documents WHERE id = ? AND user_id = ?",
            (document_id, user["id"]),
        ).fetchone()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

    input_path = os.path.join(UPLOAD_DIR, doc["filename"])
    job_id = uuid.uuid4().hex
    now = datetime.utcnow().isoformat()

    # --- Pipeline mode: run each step sequentially -----------------------
    if pipeline_id is not None:
        with get_db() as db:
            pl_row = db.execute(
                "SELECT * FROM pipelines WHERE id = ? AND user_id = ?",
                (pipeline_id, user["id"]),
            ).fetchone()
        if not pl_row:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        pl = Pipeline.from_dict(json.loads(pl_row["definition"]))
        steps = pl.steps

        with get_db() as db:
            db.execute(
                """INSERT INTO jobs (user_id, document_id, job_id, output_format, output_name,
                                    pipeline_id, status, started_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'running', ?, ?)""",
                (user["id"], document_id, job_id,
                 steps[-1].output_format if steps else "",
                 output_name, pipeline_id, now, now),
            )

        current_path = input_path
        result = {"success": True, "output_path": input_path, "stdout": "", "stderr": ""}
        basename = Path(doc["original_name"]).stem

        for step in steps:
            step_output_name = step.output_name_template.format(basename=basename)
            result = run_conversion(job_id, current_path, step.output_format, step_output_name)
            if not result["success"]:
                break
            current_path = result["output_path"]

    # --- Single-step mode (original behaviour) ---------------------------
    else:
        if output_format not in SUPPORTED_FORMATS:
            raise HTTPException(status_code=400, detail="Unsupported output format")

        with get_db() as db:
            db.execute(
                """INSERT INTO jobs (user_id, document_id, job_id, output_format, output_name,
                                    status, started_at, created_at)
                   VALUES (?, ?, ?, ?, ?, 'running', ?, ?)""",
                (user["id"], document_id, job_id, output_format, output_name, now, now),
            )

        result = run_conversion(job_id, input_path, output_format, output_name)

    finished = datetime.utcnow().isoformat()

    if result["success"]:
        status_val = "completed"
        error_val = None
    else:
        status_val = "failed"
        error_val = result["stderr"][:1000] if result["stderr"] else "Unknown error"

    with get_db() as db:
        db.execute(
            """UPDATE jobs SET status = ?, output_path = ?, error = ?, finished_at = ?
               WHERE job_id = ?""",
            (status_val, result["output_path"], error_val, finished, job_id),
        )

    with get_db() as db:
        docs = db.execute(
            "SELECT * FROM documents WHERE user_id = ? ORDER BY uploaded_at DESC",
            (user["id"],),
        ).fetchall()
        pipelines = db.execute(
            "SELECT id, name FROM pipelines WHERE user_id = ? ORDER BY name",
            (user["id"],),
        ).fetchall()

    msg = f"Conversion {'succeeded' if result['success'] else 'failed'}."
    return templates.TemplateResponse(
        "convert.html",
        {
            "request": request,
            "user": user,
            "documents": [dict(d) for d in docs],
            "formats": SUPPORTED_FORMATS,
            "pipelines": [dict(p) for p in pipelines],
            "error": None if result["success"] else (error_val or msg),
            "success": msg if result["success"] else None,
            "job_id": job_id,
        },
    )


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

@app.get("/jobs", response_class=HTMLResponse)
async def jobs_page(request: Request, user: dict = Depends(get_current_user)):
    with get_db() as db:
        jobs = db.execute(
            """SELECT j.*, d.original_name FROM jobs j
               LEFT JOIN documents d ON j.document_id = d.id
               WHERE j.user_id = ? ORDER BY j.created_at DESC""",
            (user["id"],),
        ).fetchall()
    return templates.TemplateResponse(
        "jobs.html",
        {"request": request, "user": user, "jobs": [dict(j) for j in jobs]},
    )


@app.get("/jobs/{job_id}/download")
async def download_output(
    job_id: str, request: Request, user: dict = Depends(get_current_user)
):
    with get_db() as db:
        job = db.execute(
            "SELECT * FROM jobs WHERE job_id = ? AND user_id = ?", (job_id, user["id"])
        ).fetchone()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed" or not job["output_path"]:
        raise HTTPException(status_code=400, detail="Output not available")
    if not os.path.exists(job["output_path"]):
        raise HTTPException(status_code=404, detail="Output file missing from disk")
    filename = Path(job["output_path"]).name
    return FileResponse(job["output_path"], filename=filename)


# ---------------------------------------------------------------------------
# Pipelines — request/response models
# ---------------------------------------------------------------------------

class StepSpec(BaseModel):
    output_format: str
    output_name_template: str = "{basename}"


class PipelineCreateRequest(BaseModel):
    name: str
    description: str = ""
    steps: List[StepSpec]


class PipelineImportRequest(BaseModel):
    pipeline_data: str  # base64-encoded binary blob produced by the export endpoint


# ---------------------------------------------------------------------------
# Pipelines — CRUD + import/export
# ---------------------------------------------------------------------------

@app.post("/pipelines", status_code=201)
async def create_pipeline(
    body: PipelineCreateRequest,
    user: dict = Depends(get_current_user),
):
    """Create a named pipeline from a JSON step definition."""
    pl = Pipeline(
        name=body.name.strip(),
        description=body.description,
        steps=[PipelineStep(s.output_format, s.output_name_template) for s in body.steps],
    )
    try:
        pl.validate()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    definition = json.dumps(pl.to_dict())
    try:
        with get_db() as db:
            cur = db.execute(
                """INSERT INTO pipelines (user_id, name, description, definition)
                   VALUES (?, ?, ?, ?)""",
                (user["id"], pl.name, pl.description, definition),
            )
            pipeline_id = cur.lastrowid
    except Exception:
        raise HTTPException(
            status_code=409,
            detail=f"A pipeline named {pl.name!r} already exists for this account.",
        )

    return {"id": pipeline_id, "name": pl.name, "steps": len(pl.steps)}


@app.get("/pipelines")
async def list_pipelines(user: dict = Depends(get_current_user)):
    """List all pipelines belonging to the current user."""
    with get_db() as db:
        rows = db.execute(
            "SELECT id, name, description, created_at FROM pipelines WHERE user_id = ? ORDER BY created_at DESC",
            (user["id"],),
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/pipelines/{pipeline_id}")
async def get_pipeline(pipeline_id: int, user: dict = Depends(get_current_user)):
    """Return the full definition of a single pipeline."""
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM pipelines WHERE id = ? AND user_id = ?",
            (pipeline_id, user["id"]),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    data = dict(row)
    data["definition"] = json.loads(data["definition"])
    return data


@app.delete("/pipelines/{pipeline_id}", status_code=204)
async def delete_pipeline(pipeline_id: int, user: dict = Depends(get_current_user)):
    """Delete a pipeline owned by the current user."""
    with get_db() as db:
        row = db.execute(
            "SELECT id FROM pipelines WHERE id = ? AND user_id = ?",
            (pipeline_id, user["id"]),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Pipeline not found")
        db.execute("DELETE FROM pipelines WHERE id = ?", (pipeline_id,))


@app.get("/pipelines/{pipeline_id}/export")
async def export_pipeline(pipeline_id: int, user: dict = Depends(get_current_user)):
    """
    Export a pipeline as a portable binary blob.

    The response contains a base64-encoded payload that can be handed to the
    /pipelines/import endpoint on any Docpipe instance running a compatible
    runtime version.
    """
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM pipelines WHERE id = ? AND user_id = ?",
            (pipeline_id, user["id"]),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    pl = Pipeline.from_dict(json.loads(row["definition"]))
    blob = pl.to_blob()
    return {"pipeline_id": pipeline_id, "name": pl.name, "pipeline_data": blob}


@app.post("/pipelines/import", status_code=201)
async def import_pipeline(
    body: PipelineImportRequest,
    user: dict = Depends(get_current_user),
):
    """
    Import a pipeline from a portable binary blob.

    Accepts the base64-encoded payload returned by the export endpoint and
    stores it as a new pipeline in the current user's account.  If a pipeline
    with the same name already exists it will be given a numeric suffix to
    avoid collisions.
    """
    try:
        pl = Pipeline.from_blob(body.pipeline_data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid pipeline blob: {exc}")

    # Ensure the imported object is actually a Pipeline with valid steps.
    if not isinstance(pl, Pipeline):
        raise HTTPException(status_code=400, detail="Blob does not contain a Pipeline object")
    try:
        pl.validate()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Resolve name collisions by appending a suffix.
    base_name = pl.name
    with get_db() as db:
        existing = {
            r["name"]
            for r in db.execute(
                "SELECT name FROM pipelines WHERE user_id = ?", (user["id"],)
            ).fetchall()
        }
    if base_name in existing:
        suffix = 2
        while f"{base_name} ({suffix})" in existing:
            suffix += 1
        pl.name = f"{base_name} ({suffix})"

    definition = json.dumps(pl.to_dict())
    with get_db() as db:
        cur = db.execute(
            """INSERT INTO pipelines (user_id, name, description, definition)
               VALUES (?, ?, ?, ?)""",
            (user["id"], pl.name, pl.description, definition),
        )
        pipeline_id = cur.lastrowid

    return {"id": pipeline_id, "name": pl.name, "steps": len(pl.steps)}


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, user: dict = Depends(require_admin)):
    with get_db() as db:
        users = db.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
        jobs = db.execute(
            """SELECT j.*, u.username, d.original_name FROM jobs j
               LEFT JOIN users u ON j.user_id = u.id
               LEFT JOIN documents d ON j.document_id = d.id
               ORDER BY j.created_at DESC LIMIT 100"""
        ).fetchall()
        total_docs = db.execute("SELECT COUNT(*) as c FROM documents").fetchone()["c"]
        total_jobs = db.execute("SELECT COUNT(*) as c FROM jobs").fetchone()["c"]

    # Storage stats
    upload_size = sum(
        f.stat().st_size for f in Path(UPLOAD_DIR).rglob("*") if f.is_file()
    ) if Path(UPLOAD_DIR).exists() else 0
    output_size = sum(
        f.stat().st_size for f in Path(OUTPUT_DIR).rglob("*") if f.is_file()
    ) if Path(OUTPUT_DIR).exists() else 0

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "user": user,
            "users": [dict(u) for u in users],
            "jobs": [dict(j) for j in jobs],
            "total_docs": total_docs,
            "total_jobs": total_jobs,
            "upload_size": upload_size,
            "output_size": output_size,
        },
    )
