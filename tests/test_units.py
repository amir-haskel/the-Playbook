"""Unit tests for OpsPulse core helpers: response-key parser, secret
substitution, script-path validation, and input translation."""
import os

import pytest

from app import secrets as secret_utils
from app.http_client import parse_response_key
from app.executor import _build_inputs
from app.models import Parameter, ParamType


# --------------------------------------------------------------- parser
def test_parse_list_projection():
    data = [{"name": "main"}, {"name": "dev"}]
    assert parse_response_key(data, "[].name") == ["main", "dev"]


def test_parse_nested_container():
    data = {"items": [{"metadata": {"name": "ns1"}}, {"metadata": {"name": "ns2"}}]}
    assert parse_response_key(data, "items[].metadata.name") == ["ns1", "ns2"]


def test_parse_scalar_list_no_key():
    assert parse_response_key(["a", "b", "c"], "") == ["a", "b", "c"]


def test_parse_dotted_scalar():
    assert parse_response_key({"value": "x"}, "value") == ["x"]


def test_parse_missing_key_is_empty():
    assert parse_response_key([{"name": "main"}], "[].missing") == []


# --------------------------------------------------------------- secrets
def test_substitute_env(monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "abc123")
    assert secret_utils.substitute("Bearer ${GITLAB_TOKEN}") == "Bearer abc123"


def test_substitute_unknown_is_blank():
    assert secret_utils.substitute("x=${NOPE_MISSING}") == "x="


def test_parse_header(monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "tok")
    assert secret_utils.parse_header("PRIVATE-TOKEN: ${GITLAB_TOKEN}") == {
        "PRIVATE-TOKEN": "tok"
    }


def test_parse_header_blank():
    assert secret_utils.parse_header("") == {}
    assert secret_utils.parse_header("no-colon") == {}


# --------------------------------------------------------------- script paths
def test_resolve_script_confined(tmp_path, monkeypatch):
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "ok.py").write_text("print('hi')")

    from app import scripts as script_utils
    from app.config import settings

    monkeypatch.setattr(settings, "scripts_dir", scripts_dir)

    resolved = script_utils.resolve_script("ok.py")
    assert resolved.name == "ok.py"

    with pytest.raises(script_utils.ScriptError):
        script_utils.resolve_script("../escape.py")
    with pytest.raises(script_utils.ScriptError):
        script_utils.resolve_script("missing.py")


# --------------------------------------------------------------- input passing
def test_build_inputs_env_and_cli():
    params = [
        Parameter(name="branch", type=ParamType.text),
        Parameter(name="force", type=ParamType.checkbox),
    ]
    env, cli = _build_inputs(params, {"branch": "main", "force": True})
    assert env["branch"] == "main"
    assert env["force"] == "true"
    assert "--branch" in cli and "main" in cli
    assert "--force" in cli          # bare flag when true


def test_build_inputs_checkbox_false_omits_flag():
    params = [Parameter(name="force", type=ParamType.checkbox)]
    env, cli = _build_inputs(params, {"force": False})
    assert env["force"] == "false"
    assert "--force" not in cli
