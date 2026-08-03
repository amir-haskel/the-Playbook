"""Action persistence helpers shared across routers."""
from __future__ import annotations

import datetime as _dt
import sqlite3
import uuid

from . import database as db
from .models import Action, ActionBase, Parameter


def _utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _row_to_action(row: sqlite3.Row) -> Action:
    params = [Parameter(**p) for p in db.loads(row["parameters"])]
    return Action(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        icon=row["icon"],
        color=row["color"],
        category=row["category"],
        script_path=row["script_path"],
        interpreter=row["interpreter"],
        parameters=params,
        output_subdir=row["output_subdir"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def list_actions() -> list[Action]:
    rows = db.query_all("SELECT * FROM actions ORDER BY category, title")
    return [_row_to_action(r) for r in rows]


def get_action(action_id: str) -> Action | None:
    row = db.query_one("SELECT * FROM actions WHERE id=?", (action_id,))
    return _row_to_action(row) if row else None


def create_action(data: ActionBase) -> Action:
    now = _utcnow()
    action_id = uuid.uuid4().hex
    params_json = db.dumps([p.model_dump(mode="json") for p in data.parameters])
    db.execute(
        "INSERT INTO actions (id, title, description, icon, color, category, "
        "script_path, interpreter, parameters, output_subdir, created_at, "
        "updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            action_id,
            data.title,
            data.description,
            data.icon,
            data.color,
            data.category,
            data.script_path,
            data.interpreter.value,
            params_json,
            data.output_subdir,
            now,
            now,
        ),
    )
    action = get_action(action_id)
    assert action is not None
    return action


def update_action(action_id: str, data: ActionBase) -> Action | None:
    if get_action(action_id) is None:
        return None
    params_json = db.dumps([p.model_dump(mode="json") for p in data.parameters])
    db.execute(
        "UPDATE actions SET title=?, description=?, icon=?, color=?, category=?, "
        "script_path=?, interpreter=?, parameters=?, output_subdir=?, updated_at=? "
        "WHERE id=?",
        (
            data.title,
            data.description,
            data.icon,
            data.color,
            data.category,
            data.script_path,
            data.interpreter.value,
            params_json,
            data.output_subdir,
            _utcnow(),
            action_id,
        ),
    )
    return get_action(action_id)


def delete_action(action_id: str) -> bool:
    if get_action(action_id) is None:
        return False
    db.execute("DELETE FROM actions WHERE id=?", (action_id,))
    return True
