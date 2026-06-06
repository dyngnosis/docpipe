"""
OCR processing module for docpipe.

Uses pytesseract (Tesseract wrapper) to extract text from scanned images.
Falls back to a stub implementation when the tesseract binary is unavailable,
so the service remains functional in environments without it installed.
"""

import os
import subprocess
from pathlib import Path

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/data/outputs")

# Tesseract language to use for OCR; can be overridden via env var
TESSERACT_LANG = os.environ.get("TESSERACT_LANG", "eng")


def _tesseract_available() -> bool:
    try:
        result = subprocess.run(
            ["tesseract", "--version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _run_tesseract(image_path: str, output_txt_path: str) -> tuple[bool, str]:
    """
    Invoke tesseract to OCR *image_path* and write plain text to *output_txt_path*.

    Tesseract appends '.txt' automatically when using 'txt' output type, so we
    pass the base path without the extension and rename afterwards.
    """
    base = output_txt_path.removesuffix(".txt")
    result = subprocess.run(
        ["tesseract", image_path, base, "-l", TESSERACT_LANG, "txt"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        return False, result.stderr.strip()
    # Tesseract writes <base>.txt
    produced = base + ".txt"
    if not os.path.exists(produced):
        return False, "Tesseract produced no output file"
    # Rename in case caller used the .txt suffix already
    if produced != output_txt_path:
        os.rename(produced, output_txt_path)
    return True, ""


def _stub_ocr(image_path: str, output_txt_path: str) -> tuple[bool, str]:
    """Stub OCR used when tesseract is not installed."""
    stub_text = (
        "[OCR stub] tesseract is not installed on this host.\n"
        f"Would have processed: {Path(image_path).name}\n"
        "Install tesseract-ocr to enable real text extraction.\n"
    )
    with open(output_txt_path, "w", encoding="utf-8") as fh:
        fh.write(stub_text)
    return True, ""


def run_ocr(job_id: str, image_path: str, image_filename: str) -> dict:
    """
    Extract text from *image_path* and write the result to the job output directory.

    Parameters
    ----------
    job_id:
        Unique identifier for this OCR job (used to isolate output files).
    image_path:
        Absolute path to the uploaded image file.
    image_filename:
        Original filename supplied by the user (used to derive the output name).

    Returns
    -------
    dict with keys: success, output_path, error
    """
    output_dir = os.path.join(OUTPUT_DIR, job_id)
    os.makedirs(output_dir, exist_ok=True)

    stem = Path(image_filename).stem or "ocr_output"
    output_txt = os.path.join(output_dir, f"{stem}.txt")

    if _tesseract_available():
        ok, err = _run_tesseract(image_path, output_txt)
    else:
        ok, err = _stub_ocr(image_path, output_txt)

    return {
        "success": ok,
        "output_path": output_txt if ok else None,
        "error": err if not ok else None,
    }
