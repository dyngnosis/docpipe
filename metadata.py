"""Extract document metadata from uploaded files.

Supports: HTML (title tag), plain text (first line as title), Markdown (first # heading).
For DOCX, falls back to filename if python-docx is unavailable.
"""
from __future__ import annotations
import os
import re

def extract_metadata(filepath: str) -> dict:
    """Return a dict with 'title' and 'author' extracted from the document.

    For HTML files the <title> tag is used; for Markdown the first H1 heading;
    for plain text the first non-empty line. Author is extracted from HTML <meta>
    tags when present. Falls back to empty strings on any error.
    """
    result = {"title": "", "author": "", "word_count": 0, "format": ""}
    try:
        ext = os.path.splitext(filepath)[1].lower()
        result["format"] = ext.lstrip(".")

        with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read(65536)  # read first 64 KB

        if ext in (".html", ".htm"):
            # Extract <title> tag content — the document's own declared title
            m = re.search(r"<title[^>]*>(.*?)</title>", content, re.IGNORECASE | re.DOTALL)
            if m:
                result["title"] = m.group(1).strip()
            # Extract author from <meta name="author" content="...">
            am = re.search(r'<meta\s+name=["\']author["\']\s+content=["\'](.*?)["\']',
                           content, re.IGNORECASE)
            if am:
                result["author"] = am.group(1).strip()

        elif ext == ".md":
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("# "):
                    result["title"] = line[2:].strip()
                    break
                if line and not result["title"]:
                    result["title"] = line[:120]

        else:
            for line in content.splitlines():
                line = line.strip()
                if line:
                    result["title"] = line[:120]
                    break

        result["word_count"] = len(content.split())

    except Exception:
        pass

    return result
