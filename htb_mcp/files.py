from __future__ import annotations

import re
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlparse

from .errors import HTBError

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._ -]+")


def safe_filename(name: str, fallback: str) -> str:
    candidate = _SAFE_NAME_RE.sub("_", name).strip(" .")
    return candidate or fallback


def filename_from_url(url: str, fallback: str) -> str:
    path_name = Path(unquote(urlparse(url).path)).name
    return safe_filename(path_name, fallback)


def filename_from_content_disposition(value: str | None, fallback: str) -> str:
    if not value:
        return fallback
    for part in value.split(";"):
        part = part.strip()
        if part.lower().startswith("filename*="):
            _, raw = part.split("=", 1)
            raw = raw.strip().strip('"')
            if "''" in raw:
                raw = raw.split("''", 1)[1]
            return safe_filename(unquote(raw), fallback)
        if part.lower().startswith("filename="):
            _, raw = part.split("=", 1)
            return safe_filename(raw.strip().strip('"'), fallback)
    return fallback


def ensure_within(root: Path, path: Path) -> Path:
    root_resolved = root.resolve()
    path_resolved = path.resolve()
    if path_resolved != root_resolved and root_resolved not in path_resolved.parents:
        raise HTBError(f"Refusing to write outside download root: {root_resolved}")
    return path_resolved


def write_download(
    root: Path,
    subdir: str,
    filename: str,
    content: bytes,
    *,
    overwrite: bool = False,
) -> Path:
    destination_dir = ensure_within(root, root / subdir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = ensure_within(root, destination_dir / safe_filename(filename, "download.bin"))
    if destination.exists() and not overwrite:
        raise HTBError(f"File already exists: {destination}. Set overwrite=True to replace it.")
    try:
        destination.write_bytes(content)
    except OSError as exc:
        raise HTBError(f"Could not write download to {destination}: {exc}") from exc
    return destination


def extract_zip_archive(
    zip_path: Path,
    root: Path,
    subdir: str,
    *,
    password: str | None = None,
    overwrite: bool = False,
) -> Path:
    destination = ensure_within(root, root / subdir)
    if destination.exists() and any(destination.iterdir()) and not overwrite:
        raise HTBError(f"Extraction directory is not empty: {destination}. Set overwrite=True to reuse it.")
    destination.mkdir(parents=True, exist_ok=True)
    password_bytes = password.encode() if password else None

    try:
        with zipfile.ZipFile(zip_path) as archive:
            for member in archive.infolist():
                target = ensure_within(destination, destination / member.filename)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member, pwd=password_bytes) as source:
                    target.write_bytes(source.read())
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise HTBError(f"Could not extract ZIP archive {zip_path}: {exc}") from exc

    return destination
