from __future__ import annotations

from datetime import datetime as DateTime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TrainEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw: str = Field(..., description="Raw status line extracted from upstream HTML")
    type: Literal["Arrived", "Departed"] | None = Field(None)
    station: str | None = Field(None)
    code: str | None = Field(None)
    datetime: DateTime | None = Field(None)
    delay: str | None = Field(None)


class TrainInstance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: str | None = Field(None, description="Journey start date")
    status: Literal["running", "completed", "scheduled", "unknown"] = Field(
        "unknown", description="Current status of this journey instance"
    )
    is_today: bool = Field(False, description="Whether this instance is today's run")
    last_update: DateTime | None = Field(None)
    events: list[TrainEvent] = Field(default_factory=list)


class TrainStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    train_number: int = Field(..., description="5-digit Indian Railways train number")
    start_date: str | None = Field(None, description="Primary journey start date")
    status: Literal["running", "completed", "scheduled", "unknown"] = Field("unknown")
    last_update: DateTime | None = Field(None)
    events: list[TrainEvent] = Field(default_factory=list)
    instances: list[TrainInstance] = Field(
        default_factory=list,
        description="All journey instances — today running, completed, upcoming"
    )