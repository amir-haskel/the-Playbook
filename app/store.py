"""Action persistence helpers shared across routers."""
from __future__ import annotations

import datetime as _dt
import sqlite3
import uuid

from . import database as db
from .models import Action, ActionBase, Parameter, Tag, TagBase


def _utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _row_to_action(row: sqlite3.Row) -> Action:
    params = [Parameter(**p) for p in db.loads(row["parameters"])]
    keys = row.keys()
    tags = db.loads(row["tags"]) if "tags" in keys else []
    return Action(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        icon=row["icon"] or "box",
        tags=tags,
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
    tags_json = db.dumps(data.tags)
    db.execute(
        "INSERT INTO actions (id, title, description, icon, tags, "
        "script_path, interpreter, parameters, output_subdir, created_at, "
        "updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            action_id,
            data.title,
            data.description,
            data.icon,
            tags_json,
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
    tags_json = db.dumps(data.tags)
    db.execute(
        "UPDATE actions SET title=?, description=?, icon=?, tags=?, "
        "script_path=?, interpreter=?, parameters=?, output_subdir=?, updated_at=? "
        "WHERE id=?",
        (
            data.title,
            data.description,
            data.icon,
            tags_json,
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


# ----------------------------------------------------------------- tags
def _row_to_tag(row: sqlite3.Row) -> Tag:
    keys = row.keys()
    tag_type = row["type"] if "type" in keys else "function"
    return Tag(
        id=row["id"], name=row["name"], color=row["color"],
        type=tag_type, created_at=row["created_at"],
    )


def list_tags() -> list[Tag]:
    rows = db.query_all("SELECT * FROM tags ORDER BY name COLLATE NOCASE")
    return [_row_to_tag(r) for r in rows]


def get_tag(tag_id: str) -> Tag | None:
    row = db.query_one("SELECT * FROM tags WHERE id=?", (tag_id,))
    return _row_to_tag(row) if row else None


def create_tag(data: TagBase) -> Tag:
    tag_id = uuid.uuid4().hex
    db.execute(
        "INSERT INTO tags (id, name, color, type, created_at) VALUES (?,?,?,?,?)",
        (tag_id, data.name.strip(), data.color, data.type.value, _utcnow()),
    )
    tag = get_tag(tag_id)
    assert tag is not None
    return tag


def update_tag(tag_id: str, data: TagBase) -> Tag | None:
    if get_tag(tag_id) is None:
        return None
    db.execute(
        "UPDATE tags SET name=?, color=?, type=? WHERE id=?",
        (data.name.strip(), data.color, data.type.value, tag_id),
    )
    return get_tag(tag_id)


def delete_tag(tag_id: str) -> bool:
    if get_tag(tag_id) is None:
        return False
    db.execute("DELETE FROM tags WHERE id=?", (tag_id,))
    # Remove the deleted tag id from any actions that referenced it.
    for action in list_actions():
        if tag_id in action.tags:
            remaining = [t for t in action.tags if t != tag_id]
            db.execute(
                "UPDATE actions SET tags=? WHERE id=?",
                (db.dumps(remaining), action.id),
            )
    return True
