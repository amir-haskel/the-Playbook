"""Unit tests for Playbook core helpers: response-key parser, secret
substitution, script-path validation, and input translation."""
import asyncio
import os

import pytest

from app import http_client
from app import secrets as secret_utils
from app.http_client import parse_response_key
from app.executor import _build_inputs, _env_key
from app.models import OptionItem, Parameter, ParamType


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


# --------------------------------------------------- durable console log
def test_persist_and_load_console_roundtrip(tmp_path, monkeypatch):
    """Buffered lines are flushed to disk and read back for post-restart replay."""
    from app import executor
    from app.config import settings

    monkeypatch.setattr(settings, "outputs_dir", tmp_path)
    exec_id = "exec1"
    (tmp_path / exec_id).mkdir()
    execution = executor.Execution(
        id=exec_id,
        action_id="a1",
        console_path=tmp_path / exec_id / executor._CONSOLE_LOG_NAME,
    )
    execution.lines = [("stdout", "hello"), ("stderr", "oops"), ("stdout", "done")]

    executor._persist_console(execution)

    assert (tmp_path / exec_id / executor._CONSOLE_LOG_NAME).is_file()
    assert executor.load_persisted_console(exec_id) == ["hello", "oops", "done"]


def test_load_console_missing_returns_none(tmp_path, monkeypatch):
    from app import executor
    from app.config import settings

    monkeypatch.setattr(settings, "outputs_dir", tmp_path)
    assert executor.load_persisted_console("does-not-exist") is None


# --------------------------------------------------- startup reconciliation
def test_reconcile_orphaned_executions(tmp_path, monkeypatch):
    """RUNNING/PENDING rows become FAILED on boot; terminal rows are untouched."""
    from app import database as db
    from app import store
    from app.config import settings

    monkeypatch.setattr(settings, "db_path", str(tmp_path / "recon.db"))
    monkeypatch.setattr(db, "_conn", None)
    db.init_db()
    try:
        now = "2026-01-01T00:00:00+00:00"
        for eid, status in [
            ("r1", "RUNNING"),
            ("p1", "PENDING"),
            ("s1", "SUCCESS"),
            ("f1", "FAILED"),
            ("x1", "STOPPED"),
        ]:
            db.execute(
                "INSERT INTO executions (id, action_id, status, created_at) "
                "VALUES (?, ?, ?, ?)",
                (eid, "a", status, now),
            )

        assert store.reconcile_orphaned_executions() == 2

        rows = {
            r["id"]: (r["status"], r["finished_at"])
            for r in db.query_all("SELECT id, status, finished_at FROM executions")
        }
        assert rows["r1"][0] == "FAILED" and rows["r1"][1] is not None
        assert rows["p1"][0] == "FAILED" and rows["p1"][1] is not None
        assert rows["s1"][0] == "SUCCESS"
        assert rows["f1"][0] == "FAILED"
        assert rows["x1"][0] == "STOPPED"
        # Idempotent: a second pass reconciles nothing.
        assert store.reconcile_orphaned_executions() == 0
    finally:
        conn = db._conn
        if conn is not None:
            conn.close()
        monkeypatch.setattr(db, "_conn", None)


# --------------------------------------------------------------- script listing
def test_list_scripts_excludes_dotfiles(tmp_path, monkeypatch):
    """Hidden/dotfiles (and files under dot-directories) are not listed."""
    scripts_dir = tmp_path / "scripts"
    (scripts_dir / "sub").mkdir(parents=True)
    (scripts_dir / ".git").mkdir()

    (scripts_dir / "hello.py").write_text("print('hi')")
    (scripts_dir / "deploy.sh").write_text("echo hi")
    (scripts_dir / "sub" / "task.py").write_text("print('hi')")
    # Dotfiles that still carry a runnable extension — these must be filtered.
    (scripts_dir / ".hidden.py").write_text("print('hi')")
    (scripts_dir / ".secret.sh").write_text("echo hi")
    # A runnable file living under a dot-directory must also be filtered.
    (scripts_dir / ".git" / "hook.py").write_text("print('hi')")

    from app import scripts as script_utils
    from app.config import settings

    monkeypatch.setattr(settings, "scripts_dir", scripts_dir)

    listed = script_utils.list_scripts()
    assert listed == ["deploy.sh", "hello.py", "sub/task.py"]
    assert not any(part.startswith(".") for name in listed for part in name.split("/"))


def test_list_and_resolve_scripts_in_configmap_layout(tmp_path, monkeypatch):
    """A ConfigMap volume stores files under a hidden timestamped dir and
    exposes them through symlinks (``deploy -> ..data/deploy``). Nested scripts
    must be listed once, by their logical path, and still resolve."""
    root = tmp_path / "scripts"
    real = root / "..2026_01_01_00_00_00.000000001"
    (real / "deploy").mkdir(parents=True)
    (real / "deploy" / "rollout.sh").write_text("echo hi")
    (real / "hello.py").write_text("print('hi')")
    try:
        os.symlink(real.name, root / "..data", target_is_directory=True)
        os.symlink(os.path.join("..data", "deploy"), root / "deploy", target_is_directory=True)
        os.symlink(os.path.join("..data", "hello.py"), root / "hello.py")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted on this platform/user")

    from app import scripts as script_utils
    from app.config import settings

    monkeypatch.setattr(settings, "scripts_dir", root)

    assert script_utils.list_scripts() == ["deploy/rollout.sh", "hello.py"]
    assert script_utils.resolve_script("deploy/rollout.sh").read_text() == "echo hi"


# --------------------------------------------------------------- pagination
class _FakeResponse:
    """Minimal stand-in for httpx.Response used by fetch_options."""

    def __init__(self, payload, headers=None):
        self._payload = payload
        self.headers = httpx_headers(headers or {})

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def httpx_headers(mapping):
    """Case-insensitive header mapping mirroring httpx.Headers.get()."""
    lower = {k.lower(): v for k, v in mapping.items()}

    class _H:
        def get(self, key, default=None):
            return lower.get(key.lower(), default)

    return _H()


class _FakeClient:
    """Async context-manager stub that serves queued pages by URL sequence."""

    def __init__(self, pages):
        # pages: list of _FakeResponse, returned in request order.
        self._pages = list(pages)
        self.requested_urls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None):
        self.requested_urls.append(url)
        if not self._pages:
            raise AssertionError(f"unexpected extra request to {url}")
        return self._pages.pop(0)


def _install_fake_client(monkeypatch, client):
    monkeypatch.setattr(http_client.httpx, "AsyncClient", lambda *a, **k: client)


def _param(endpoint, response_key):
    return Parameter(
        name="opt",
        type=ParamType.dynamic_select,
        endpoint=endpoint,
        response_key=response_key,
    )


def test_pagination_link_header_rel_next(monkeypatch):
    """GitLab-style Link: rel=next chain is followed to exhaustion."""
    pages = [
        _FakeResponse(
            [{"name": "main"}, {"name": "dev"}],
            {"Link": '<https://gl/api?page=2>; rel="next"'},
        ),
        _FakeResponse(
            [{"name": "feat"}],
            {"Link": '<https://gl/api?page=2>; rel="prev"'},  # no next -> stop
        ),
    ]
    client = _FakeClient(pages)
    _install_fake_client(monkeypatch, client)

    opts = asyncio.run(http_client.fetch_options(_param("https://gl/api?page=1", "[].name")))
    assert [o.value for o in opts] == ["main", "dev", "feat"]
    assert client.requested_urls == ["https://gl/api?page=1", "https://gl/api?page=2"]


def test_pagination_x_next_page_header(monkeypatch):
    """GitLab X-Next-Page header drives the ?page= query until it blanks out."""
    pages = [
        _FakeResponse([{"name": "a"}], {"X-Next-Page": "2"}),
        _FakeResponse([{"name": "b"}], {"X-Next-Page": ""}),  # blank -> last page
    ]
    client = _FakeClient(pages)
    _install_fake_client(monkeypatch, client)

    opts = asyncio.run(http_client.fetch_options(_param("https://gl/api?per_page=100", "[].name")))
    assert [o.value for o in opts] == ["a", "b"]
    assert "page=2" in client.requested_urls[1]


def test_pagination_nexus_continuation_token(monkeypatch):
    """Nexus continuationToken is followed until the token is absent/null."""
    pages = [
        _FakeResponse({"items": [{"name": "art-1"}], "continuationToken": "TOK1"}),
        _FakeResponse({"items": [{"name": "art-2"}], "continuationToken": None}),
    ]
    client = _FakeClient(pages)
    _install_fake_client(monkeypatch, client)

    opts = asyncio.run(http_client.fetch_options(
        _param("https://nexus/service/rest/v1/components?repository=r", "items[].name")
    ))
    assert [o.value for o in opts] == ["art-1", "art-2"]
    assert "continuationToken=TOK1" in client.requested_urls[1]


def test_pagination_generic_page_increment_and_dedup(monkeypatch):
    """Generic ?page= increment stops on an empty page; duplicates are merged."""
    pages = [
        _FakeResponse([{"name": "x"}, {"name": "y"}]),
        _FakeResponse([{"name": "y"}, {"name": "z"}]),  # 'y' duplicate
        _FakeResponse([]),                               # empty -> stop
    ]
    client = _FakeClient(pages)
    _install_fake_client(monkeypatch, client)

    opts = asyncio.run(http_client.fetch_options(_param("https://api?page=1", "[].name")))
    assert [o.value for o in opts] == ["x", "y", "z"]
    assert client.requested_urls == [
        "https://api?page=1",
        "https://api?page=2",
        "https://api?page=3",
    ]


def test_pagination_no_param_single_page(monkeypatch):
    """Without a paging signal (no header/token/page param) only one request is made."""
    pages = [_FakeResponse([{"name": "solo"}])]
    client = _FakeClient(pages)
    _install_fake_client(monkeypatch, client)

    opts = asyncio.run(http_client.fetch_options(_param("https://api/list", "[].name")))
    assert [o.value for o in opts] == ["solo"]
    assert client.requested_urls == ["https://api/list"]


# --------------------------------------------------- parameter name rule
def test_name_allows_spaces_and_is_collapsed():
    """Spaces are allowed; leading/trailing trimmed and internal runs collapsed."""
    p = Parameter(name="  Target   Namespace  ", type=ParamType.text)
    assert p.name == "Target Namespace"
    # underscores and hyphens are also allowed after the leading letter
    assert Parameter(name="my-param_v2", type=ParamType.text).name == "my-param_v2"


def test_name_rejects_empty_and_invalid():
    for bad in ["", "   ", "\t\n", "1leads-with-digit", "-leads-with-hyphen", "has!bang"]:
        with pytest.raises(Exception):
            Parameter(name=bad, type=ParamType.text)
    # length cap (>64) is rejected
    with pytest.raises(Exception):
        Parameter(name="A" * 65, type=ParamType.text)


# --------------------------------------------------- env-key sanitization
def test_env_key_sanitization():
    assert _env_key("Target Namespace") == "Target_Namespace"
    # A run of *invalid* chars collapses to one _, but underscores are valid
    # env chars and are preserved as-is.
    assert _env_key("a--b__c") == "a_b__c"
    assert _env_key("a  b.c/d") == "a_b_c_d"
    assert _env_key("  spaced  ") == "spaced"  # stripped edges
    assert _env_key("2fa") == "_2fa"           # digit-leading gets a prefix
    assert _env_key("!!!") == "_"              # empty result gets a prefix
    assert _env_key("plain") == "plain"


def test_build_inputs_spaced_name_uses_sanitized_env_key():
    """Env var name is sanitized; the CLI positional value is unchanged; the
    lookup key stays the literal (spaced) name."""
    params = [Parameter(name="Target Namespace", type=ParamType.text)]
    env, cli = _build_inputs(params, {"Target Namespace": "prod"})
    assert env == {"Target_Namespace": "prod"}
    assert cli == ["prod"]


# --------------------------------------------------- dynamic-option sorting
def test_sort_field_normalizes():
    assert Parameter(name="p", type=ParamType.dynamic_select).sort == "none"
    assert Parameter(name="p", type=ParamType.dynamic_select, sort="ALPHA").sort == "alpha"
    assert Parameter(name="p", type=ParamType.dynamic_select, sort="bogus").sort == "none"


def _opts(*values):
    return [OptionItem(value=v, label=v) for v in values]


def test_sort_none_preserves_order():
    given = _opts("banana", "apple", "cherry")
    assert [o.value for o in http_client._sort_options(given, "none")] == [
        "banana", "apple", "cherry"
    ]


def test_sort_alpha_case_insensitive():
    given = _opts("Banana", "apple", "Cherry")
    assert [o.value for o in http_client._sort_options(given, "alpha")] == [
        "apple", "Banana", "Cherry"
    ]


def test_sort_version_natural():
    # The load-bearing case: 1.2.10 must sort AFTER 1.2.9, and v2 before v10.
    given = _opts("1.2.10", "1.2.9", "v10", "v2", "1.10.0", "1.2.0")
    ordered = [o.value for o in http_client._sort_options(given, "version")]
    assert ordered.index("1.2.9") < ordered.index("1.2.10")
    assert ordered.index("v2") < ordered.index("v10")
    assert ordered.index("1.2.0") < ordered.index("1.2.9") < ordered.index("1.10.0")


def test_sort_version_pure_numeric():
    given = _opts("10", "2", "1", "20")
    assert [o.value for o in http_client._sort_options(given, "version")] == [
        "1", "2", "10", "20"
    ]


# --------------------------------------------------- SSE Last-Event-ID resume
class _FakeRequest:
    """Minimal stand-in exposing only the header lookup _resume_index needs."""

    def __init__(self, headers):
        self.headers = httpx_headers(headers)


def test_resume_index_from_last_event_id():
    from app.routers.execute import _resume_index

    # No header -> start from the top.
    assert _resume_index(_FakeRequest({})) == 0
    # Valid id N -> resume at N+1 (no duplicate of the already-seen line).
    assert _resume_index(_FakeRequest({"Last-Event-ID": "4"})) == 5
    assert _resume_index(_FakeRequest({"Last-Event-ID": "0"})) == 1
    # Garbage / negative -> start from the top.
    assert _resume_index(_FakeRequest({"Last-Event-ID": "nope"})) == 0
    assert _resume_index(_FakeRequest({"Last-Event-ID": "-3"})) == 0


def test_sse_line_carries_id_and_status_does_not():
    from app.routers.execute import _sse

    line = _sse("stdout", {"line": "hi"}, event_id=7)
    assert line.startswith("id: 7\n")
    assert "event: stdout\n" in line
    status = _sse("status", {"status": "SUCCESS"})
    assert not status.startswith("id:")
    assert "id:" not in status


def test_pagination_page_cap(monkeypatch):
    """A full-but-always-new endpoint is bounded by MAX_PAGES."""
    # Every page returns a fresh unique value and keeps signalling a next page.
    responses = [
        _FakeResponse([{"name": f"v{i}"}], {"X-Next-Page": str(i + 2)})
        for i in range(http_client.MAX_PAGES + 5)
    ]
    client = _FakeClient(responses)
    _install_fake_client(monkeypatch, client)

    opts = asyncio.run(http_client.fetch_options(_param("https://gl/api?page=1", "[].name")))
    assert len(client.requested_urls) == http_client.MAX_PAGES
    assert len(opts) == http_client.MAX_PAGES
