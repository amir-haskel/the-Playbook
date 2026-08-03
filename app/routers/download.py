"""Stream generated artifact files to the browser."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .. import database as db
from ..config import settings

router = APIRouter(prefix="/api/v1", tags=["download"])


@router.get("/download/{file_id}")
def download(file_id: str) -> FileResponse:
    row = db.query_one("SELECT * FROM artifacts WHERE file_id=?", (file_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="File not found")

    path = Path(row["path"]).resolve()

    # Defence in depth: the artifact must live under the outputs directory.
    outputs_root = settings.outputs_dir.resolve()
    try:
        path.relative_to(outputs_root)
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    if not path.is_file():
        raise HTTPException(status_code=410, detail="File no longer available")

    return FileResponse(
        path,
        filename=row["filename"],
        media_type="application/octet-stream",
    )
