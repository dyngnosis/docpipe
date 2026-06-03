# Docpipe

A self-hosted document conversion and processing pipeline built with FastAPI and pandoc.

## Features

- Register / Login / Logout with signed-cookie sessions
- Upload source documents (Markdown, HTML, plain text, DOCX, etc.)
- Convert documents between formats using pandoc
- View conversion job history
- Download converted files
- Admin panel: users, jobs, storage stats

## Quick Start

### Docker Compose

```bash
docker-compose up --build
```

Then open http://localhost:3005 and log in with `admin` / `admin123`.

### Local Development

```bash
# Install system deps (Debian/Ubuntu)
sudo apt-get install pandoc

# Install Python deps
pip install -r requirements.txt

# Run
mkdir -p /data/uploads /data/outputs
DATABASE_PATH=/data/docpipe.db UPLOAD_DIR=/data/uploads OUTPUT_DIR=/data/outputs \
  uvicorn main:app --reload --port 3005
```

## Stack

- Python 3.12 + FastAPI
- Jinja2 templates + Bootstrap 5
- SQLite (stdlib `sqlite3`)
- Session auth via `itsdangerous`
- `subprocess` + pandoc for conversions
- uvicorn
