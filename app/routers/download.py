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

    outputs_root = settings.outputs_dir.resolve()

    # Artifacts always live at <outputs_dir>/<execution_id>/<...>. The DB stores
    # the absolute path as it was at execution time, but the outputs volume can
    # be mounted at a different path (that is the whole point of a separate
    # STORE_DIR volume), so re-anchor the portion from the execution_id onward
    # onto the CURRENT outputs_dir. This keeps historical downloads working
    # across a volume relocation. Fall back to the stored path if re-anchoring
    # isn't possible.
    stored = Path(row["path"])
    eid = row["execution_id"]
    path = None
    if eid and eid in stored.parts:
        rel = stored.parts[stored.parts.index(eid):]
        path = outputs_root.joinpath(*rel).resolve()
    if path is None or not path.is_file():
        alt = stored.resolve()
        if alt.is_file():
            path = alt
    if path is None:
        raise HTTPException(status_code=410, detail="File no longer available")

    # Defence in depth: the artifact must live under the outputs directory.
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
