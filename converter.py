import os
import shlex
import subprocess

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


def run_conversion(job_id: str, input_path: str, output_format: str, output_name: str) -> dict:
    """
    Convert a document using pandoc.

    output_name: user-provided base name for the output file (e.g. "my-report")
    """
    output_dir = os.path.join(OUTPUT_DIR, job_id)
    os.makedirs(output_dir, exist_ok=True)

    # Use os.path.basename() to strip any path traversal from the output name.
    # This prevents writing to ../../etc/ etc. — a common path traversal defense.
    safe_name = os.path.basename(output_name)
    if not safe_name:
        safe_name = "output"

    output_path = os.path.join(output_dir, f"{safe_name}.{output_format}")

    # BUG: os.path.basename() strips directory separators but NOT shell metacharacters.
    # os.path.basename("report; id") == "report; id"
    # So output_path becomes "/data/outputs/<job_id>/report; id.<fmt>"
    # and the semicolon splits the command, executing "id" as a separate command.
    cmd = f"pandoc {shlex.quote(input_path)} -o {output_path}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)

    return {
        "success": result.returncode == 0,
        "output_path": output_path,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
