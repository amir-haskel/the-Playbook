"""Pydantic schemas for Playbook actions, parameters and executions."""
from __future__ import annotations

import re
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# Parameter names may contain spaces (e.g. "Target Namespace"). The rule is
# applied to the *trimmed* value with internal whitespace runs collapsed to a
# single space: start with a letter, then letters/digits/space/underscore/hyphen,
# length 1-64. (The env-var key used at execution time is derived separately in
# executor.py, since OS env names cannot contain spaces.)
_PARAM_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 _-]*$")
_PARAM_NAME_MAXLEN = 64

# Allowed dynamic-option sort modes.
_SORT_MODES = {"none", "alpha", "version"}


class ParamType(str, Enum):
    text = "text"
    number = "number"
    checkbox = "checkbox"
    radio = "radio"
    select = "select"
    dynamic_select = "dynamic_select"
    file = "file"          # user-uploaded file; value is an upload token


class Interpreter(str, Enum):
    auto = "auto"          # infer from file extension
    python = "python"
    bash = "bash"
    powershell = "powershell"


class OptionItem(BaseModel):
    value: str
    label: str


class Parameter(BaseModel):
    """A single input field rendered in the execution modal."""

    name: str = Field(...)
    # `label` is retained for backend compatibility but is no longer collected by
    # the UI; it auto-mirrors `name` (see the validator) so any server-side
    # reference to `param.label` keeps working while developers see `name`.
    label: str = ""
    type: ParamType = ParamType.text
    required: bool = False
    default: Optional[Any] = None

    # Static choices for select/radio/checkbox-group.
    options: list[str] = Field(default_factory=list)

    # When set on a checkbox param, its options are fetched from the dynamic
    # source (endpoint/response_key/auth_header below) and rendered as a
    # multi-select checkbox group. `select_all` adds a leading "Select all" box.
    select_all: bool = False

    # Dynamic dropdowns: fetched live from GitLab/OpenShift APIs.
    #   dynamic_type   -> which source (e.g. "gitlab-branches", "oc-namespaces",
    #                     or "custom")
    #   endpoint       -> API path/URL (relative to the source base or absolute)
    #   response_key   -> parser expression, e.g. "[].name" or "items[].metadata.name"
    #   auth_header    -> header template with secret placeholders, e.g.
    #                     "PRIVATE-TOKEN: ${GITLAB_TOKEN}"
    dynamic_type: Optional[str] = None
    endpoint: Optional[str] = None
    response_key: Optional[str] = None
    auth_header: Optional[str] = None

    # Ordering applied to dynamically-fetched options (dynamic_select or a
    # dynamic-source checkbox). "none" preserves as-returned order; "alpha" sorts
    # case-insensitively by label; "version" applies a natural/version-aware sort.
    sort: str = "none"

    def label_or_name(self) -> str:
        return self.label or self.name

    @field_validator("name", mode="before")
    @classmethod
    def _normalize_name(cls, v: Any) -> str:
        """Trim, collapse internal whitespace, and validate the parameter name.

        Leading/trailing whitespace is stripped and internal runs of whitespace
        are collapsed to a single space, so "  Target   Namespace " becomes
        "Target Namespace". Empty/whitespace-only names are rejected.
        """
        if not isinstance(v, str):
            raise ValueError("parameter name must be a string")
        collapsed = " ".join(v.split())
        if not collapsed:
            raise ValueError("parameter name must not be empty")
        if len(collapsed) > _PARAM_NAME_MAXLEN:
            raise ValueError(
                f"parameter name must be 1-{_PARAM_NAME_MAXLEN} characters"
            )
        if not _PARAM_NAME_RE.match(collapsed):
            raise ValueError(
                "parameter name must start with a letter and contain only "
                "letters, digits, spaces, underscores or hyphens"
            )
        return collapsed

    @field_validator("sort", mode="before")
    @classmethod
    def _normalize_sort(cls, v: Any) -> str:
        """Normalize the sort mode; unknown values fall back to 'none'."""
        if isinstance(v, str):
            candidate = v.strip().lower()
            if candidate in _SORT_MODES:
                return candidate
        return "none"

    @model_validator(mode="after")
    def _check_defaults(self) -> "Parameter":
        """Validate defaults against options and numeric constraints."""
        name = self.name
        d = self.default
        has_default = d is not None and not (isinstance(d, str) and d.strip() == "")

        # Label auto-mirrors name — the UI only collects `name`.
        if not self.label:
            self.label = self.name

        # A checkbox whose options are fetched from a dynamic API source. It
        # carries an endpoint/dynamic_type like a dynamic_select but renders as a
        # multi-select checkbox group and executes as a comma-joined checkbox
        # value (executor.py path unchanged). The executor tells a checkbox
        # *group* from a boolean flag by a non-empty `options` list, so we seed a
        # placeholder; the real options are fetched live at render time and never
        # come from this list. Its presence also relaxes the default-in-options
        # check below (options are unknown until fetched).
        dynamic_checkbox = self.type == ParamType.checkbox and bool(
            self.endpoint or self.dynamic_type
        )
        if dynamic_checkbox and not self.options:
            self.options = ["__dynamic__"]

        if self.type == ParamType.number and has_default:
            try:
                n = float(str(d))
            except (TypeError, ValueError):
                raise ValueError(f"parameter '{name}': default must be a number")
            if n < 0:
                raise ValueError(f"parameter '{name}': default must be 0 or greater")

        if self.type in (ParamType.select, ParamType.radio) and has_default:
            if self.options and str(d) not in self.options:
                raise ValueError(
                    f"parameter '{name}': default '{d}' is not in the options list"
                )

        # Checkbox with options is a multi-select group; each default must be a
        # valid option. A checkbox with no options is a plain boolean flag.
        if self.type == ParamType.checkbox and self.options and has_default and not dynamic_checkbox:
            defaults = [x.strip() for x in str(d).split(",") if x.strip()]
            bad = [x for x in defaults if x not in self.options]
            if bad:
                raise ValueError(
                    f"parameter '{name}': default(s) {bad} not in the options list"
                )
        return self


class TagType(str, Enum):
    function = "function"   # colored, groups actions by purpose (max 1 per action)
    team = "team"           # colorless, uppercase, top-right badge (0 or 1 per action)


class TagBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=40)
    color: str = "slate"   # a palette key (see TAG_COLORS on the frontend)
    type: TagType = TagType.function


class TagCreate(TagBase):
    pass


class Tag(TagBase):
    id: str
    created_at: str


class ActionBase(BaseModel):
    title: str
    description: str = ""
    icon: str = "box"                 # icon key (see icons.js), not an emoji
    tags: list[str] = Field(default_factory=list)   # tag ids from the bank
    script_path: str
    interpreter: Interpreter = Interpreter.auto
    parameters: list[Parameter] = Field(default_factory=list)
    output_subdir: str = ""


class ActionCreate(ActionBase):
    pass


class ActionUpdate(ActionBase):
    pass


class Action(ActionBase):
    id: str
    created_at: str
    updated_at: str

    def public_dict(self, include_secrets: bool = False) -> dict[str, Any]:
        """Representation sent to the dashboard / admin builder.

        ``auth_header`` is an env-var *reference* template (e.g.
        ``PRIVATE-TOKEN: ${NEXUS_TOKEN}``), not a real secret — the actual value
        is resolved server-side only, at fetch time, from environment variables.
        It is **stripped from the public dashboard payload** (the default) and
        included only for the authenticated admin builder
        (``include_secrets=True``), so the editor can display and re-save the
        reference instead of silently wiping it. The concrete secret never
        reaches the browser in either case.
        """
        data = self.model_dump(mode="json")
        if not include_secrets:
            for param in data.get("parameters", []):
                param.pop("auth_header", None)
        return data


class ExecuteRequest(BaseModel):
    """Body of POST /api/v1/execute/{action_id}: raw param name -> value."""

    values: dict[str, Any] = Field(default_factory=dict)


class ExecutionState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    STOPPED = "STOPPED"     # gracefully stopped by the user mid-run


class ArtifactInfo(BaseModel):
    file_id: str
    filename: str
    size: int


class LoginRequest(BaseModel):
    password: str
