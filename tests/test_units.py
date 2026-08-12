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
def test_build_inputs_env_and_positional():
    params = [
        Parameter(name="branch", type=ParamType.text),
        Parameter(name="force", type=ParamType.checkbox),
    ]
    env, cli = _build_inputs(params, {"branch": "main", "force": True})
    assert env["branch"] == "main"
    assert env["force"] == "true"
    # Positional, in parameter order, no --name flags.
    assert cli == ["main", "true"]


def test_build_inputs_checkbox_false_positional():
    params = [Parameter(name="force", type=ParamType.checkbox)]
    env, cli = _build_inputs(params, {"force": False})
    assert env["force"] == "false"
    assert cli == ["false"]


def test_build_inputs_checkbox_group_multi():
    params = [Parameter(name="envs", type=ParamType.checkbox, options=["dev", "prod", "qa"])]
    env, cli = _build_inputs(params, {"envs": ["dev", "prod"]})
    assert env["envs"] == "dev,prod"
    # Each selected value is its own positional arg, in order.
    assert cli == ["dev", "prod"]


def test_build_inputs_order_and_types():
    params = [
        Parameter(name="name", type=ParamType.text),
        Parameter(name="count", type=ParamType.number),
        Parameter(name="mode", type=ParamType.select, options=["a", "b"]),
    ]
    env, cli = _build_inputs(
        params, {"name": "svc", "count": 3, "mode": "b"}
    )
    assert cli == ["svc", "3", "b"]
    assert env == {"name": "svc", "count": "3", "mode": "b"}


def test_build_inputs_file_param_positional():
    # A file param's value has already been resolved to a basename by the time
    # _build_inputs runs; it is passed as a single positional arg.
    params = [Parameter(name="upload", type=ParamType.file)]
    env, cli = _build_inputs(params, {"upload": "data.csv"})
    assert cli == ["data.csv"]
    assert env["upload"] == "data.csv"


def test_paramtype_file_exists():
    assert ParamType.file.value == "file"
    # File params require no options/default validation.
    Parameter(name="f", type=ParamType.file)


# --------------------------------------------------------------- validators
def test_number_default_negative_rejected():
    with pytest.raises(Exception):
        Parameter(name="n", type=ParamType.number, default="-3")


def test_number_default_non_numeric_rejected():
    with pytest.raises(Exception):
        Parameter(name="n", type=ParamType.number, default="abc")


def test_select_default_must_be_in_options():
    with pytest.raises(Exception):
        Parameter(name="s", type=ParamType.select, options=["a", "b"], default="c")
    # valid default is accepted
    Parameter(name="s", type=ParamType.select, options=["a", "b"], default="a")


def test_checkbox_group_default_subset():
    with pytest.raises(Exception):
        Parameter(name="c", type=ParamType.checkbox, options=["a", "b"], default="a,z")
    Parameter(name="c", type=ParamType.checkbox, options=["a", "b"], default="a,b")
