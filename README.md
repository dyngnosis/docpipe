# Docpipe

A self-hosted document conversion service built with FastAPI and pandoc.

**This project is an educational CWE-78 (OS Command Injection) demonstration** intended for security research and training datasets. Do not deploy with `SECRET_KEY=change-me` in production.

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

## Security Note — CWE-78

The `run_conversion()` function in `converter.py` contains a deliberate OS command injection vulnerability. The developer correctly applies `shlex.quote()` to the `input_path` (a value they control) but assembles `output_path` directly from user-supplied `output_name` without shell-quoting, then passes the entire command string to `subprocess.run(..., shell=True)`.

Because `os.path.basename()` strips `/` characters but not shell metacharacters, an attacker can supply an `output_name` like:

```
report; id
report$(whoami)
report`cat /etc/passwd`
```

and inject arbitrary OS commands.

**Fix:** use `shlex.quote(output_path)` in the `cmd` string, or — better — pass the command as a list and omit `shell=True`.

## Stack

- Python 3.12 + FastAPI
- Jinja2 templates + Bootstrap 5
- SQLite (stdlib `sqlite3`)
- Session auth via `itsdangerous`
- `subprocess` + pandoc for conversions
- uvicorn
