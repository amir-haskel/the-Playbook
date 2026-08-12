"""Accept user file uploads for ``file``-type execution parameters.

An upload is staged under a per-upload token directory; the returned token is
later submitted as the value of a ``file`` parameter, which the executor
resolves and copies into the execution working dir at run time.
"""
from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, File, UploadFile

from ..config import settings

router = APIRouter(prefix="/api/v1", tags=["uploads"])


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)) -> dict:
    """Stage a multipart-uploaded file and return its opaque token.

    The file is saved under ``uploads_dir / <token> / <sanitized-basename>``.
    Any path components in the client-supplied filename are stripped.
    """
    token = uuid.uuid4().hex

    # Strip any path components the client may have sent; keep the basename only.
    raw_name = file.filename or ""
    basename = os.path.basename(raw_name.replace("\\", "/")).strip()
    if not basename:
        basename = "upload.bin"

    stage_dir = settings.uploads_dir / token
    stage_dir.mkdir(parents=True, exist_ok=True)
    dest = stage_dir / basename

    with dest.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
    await file.close()

    return {"token": token, "filename": basename}
