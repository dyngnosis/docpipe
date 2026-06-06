import os
import shlex
import subprocess
from datetime import date
from typing import Optional

import jinja2

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/data/outputs")

SUPPORTED_FORMATS = {
    "html": "HTML",
    "pdf": "PDF",
    "docx": "Word Document",
    "odt": "OpenDocument Text",
    "rst": "reStructuredText",
    "plain": "Plain Text",
    "latex": "LaTeX",
    "epub": "EPUB",
}

# Variables available inside header/footer templates
TEMPLATE_VARS = ["title", "page", "total_pages", "date"]


def render_pdf_template(template_str: str, *, title: str, page: int, total: int) -> str:
    """Render a header or footer template string with PDF page variables."""
    rendered = jinja2.Template(template_str).render(
        title=title,
        page=page,
        total_pages=total,
        date=date.today().strftime("%Y-%m-%d"),
    )
    return rendered


def run_conversion(
    job_id: str,
    input_path: str,
    output_format: str,
    output_name: str,
    pdf_template: Optional[dict] = None,
) -> dict:
    """
    Convert a document using pandoc.

    output_name: user-provided base name for the output file (e.g. "my-report")
    pdf_template: optional dict with 'header' and 'footer' template strings,
                  applied only when output_format is 'pdf'.
    """
    output_dir = os.path.join(OUTPUT_DIR, job_id)
    os.makedirs(output_dir, exist_ok=True)

    safe_name = os.path.basename(output_name)
    if not safe_name:
        safe_name = "output"

    output_path = os.path.join(output_dir, f"{safe_name}.{output_format}")

    cmd = f"pandoc {shlex.quote(input_path)} -o {output_path}"

    if output_format == "pdf" and pdf_template:
        doc_title = os.path.splitext(os.path.basename(input_path))[0]

        header_str = pdf_template.get("header", "")
        footer_str = pdf_template.get("footer", "")

        if header_str:
            rendered_header = render_pdf_template(
                header_str, title=doc_title, page=1, total=1
            )
            header_file = os.path.join(output_dir, "header.html")
            with open(header_file, "w", encoding="utf-8") as fh:
                fh.write(f"<div style='font-size:10px;text-align:center'>{rendered_header}</div>")
            cmd += f" --pdf-engine-opt=--header-html={shlex.quote(header_file)}"

        if footer_str:
            rendered_footer = render_pdf_template(
                footer_str, title=doc_title, page=1, total=1
            )
            footer_file = os.path.join(output_dir, "footer.html")
            with open(footer_file, "w", encoding="utf-8") as fh:
                fh.write(f"<div style='font-size:10px;text-align:center'>{rendered_footer}</div>")
            cmd += f" --pdf-engine-opt=--footer-html={shlex.quote(footer_file)}"

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)

    return {
        "success": result.returncode == 0,
        "output_path": output_path,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
