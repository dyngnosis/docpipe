import os
from pathlib import Path

VERSIONS_DIR = os.environ.get("VERSIONS_DIR", "/data/versions")


def version_path(doc_id: int, version_id: str, ext: str) -> str:
    """Return the filesystem path for a stored document version file."""
    return os.path.join(VERSIONS_DIR, str(doc_id), f"{version_id}.{ext}")


def store_version(doc_id: int, version_number: int, source_path: str, ext: str) -> int:
    """
    Copy a completed conversion output into the versioned storage tree.

    Returns the byte size of the stored file.
    """
    dest_dir = os.path.join(VERSIONS_DIR, str(doc_id))
    os.makedirs(dest_dir, exist_ok=True)

    dest = version_path(doc_id, str(version_number), ext)
    with open(source_path, "rb") as src, open(dest, "wb") as dst:
        while chunk := src.read(65536):
            dst.write(chunk)

    return os.path.getsize(dest)


def read_version_file(doc_id: int, version_id: str, ext: str) -> str:
    """
    Resolve and return the full path to a version file.

    doc_id is validated against the database by the caller; version_id
    is provided by the client and used directly to build the path.
    """
    path = os.path.join(VERSIONS_DIR, str(doc_id), f"{version_id}.{ext}")
    return path
