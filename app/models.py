"""Pydantic schemas for OpsPulse actions, parameters and executions."""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


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


class ActionBase(BaseModel):
    title: str
    description: str = ""
    icon: str = ""
    color: str = "slate"
    category: str = "General"
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
