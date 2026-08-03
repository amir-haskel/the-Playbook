"""Pydantic schemas for OpsPulse actions, parameters and executions."""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


class ParamType(str, Enum):
    text = "text"
    number = "number"
    checkbox = "checkbox"
    radio = "radio"
    select = "select"
    dynamic_select = "dynamic_select"


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

    name: str = Field(..., pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    label: str = ""
    type: ParamType = ParamType.text
    required: bool = False
    default: Optional[Any] = None

    # Static choices for select/radio.
    options: list[str] = Field(default_factory=list)

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

    def label_or_name(self) -> str:
        return self.label or self.name

    @model_validator(mode="after")
    def _check_defaults(self) -> "Parameter":
        """Validate defaults against options and numeric constraints."""
        name = self.name
        d = self.default
        has_default = d is not None and not (isinstance(d, str) and d.strip() == "")

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
        if self.type == ParamType.checkbox and self.options and has_default:
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

    def public_dict(self) -> dict[str, Any]:
        """Sanitised representation sent to the dashboard.

        Strips server-side secret templates (auth_header) from parameters so
        tokens can never leak to the browser.
        """
        data = self.model_dump(mode="json")
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


class ArtifactInfo(BaseModel):
    file_id: str
    filename: str
    size: int


class LoginRequest(BaseModel):
    password: str
