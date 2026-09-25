"""Validated shape of a saved sidebar layout.

This is a fixed contract shared with the frontend team building the
customizable-sidebar UI - do not change field names/shapes here without
updating them; the frontend validates against this exact JSON shape.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SidebarLayoutGroup(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1)
    kind: Literal["builtin", "custom"]
    #: Only meaningful when kind="builtin" - matches a NavGroup's stable
    #: key on the frontend.
    builtinKey: str | None = None
    #: Rename override. Only meaningful if set (non-null).
    label: str | None = None
    order: int
    archived: bool = False


class SidebarLayoutItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    #: Matches one of `SidebarLayout.groups[].id`.
    groupId: str = Field(min_length=1)
    order: int
    archived: bool = False


class SidebarLayout(BaseModel):
    """The full saved layout: group definitions + per-item placement.

    `items` is keyed by the frontend's stable item-key string.
    """

    model_config = ConfigDict(extra="ignore")

    groups: list[SidebarLayoutGroup] = Field(default_factory=list)
    items: dict[str, SidebarLayoutItem] = Field(default_factory=dict)


class SidebarLayoutEnvelope(BaseModel):
    """Request/response body for both sidebar-layout endpoints.

    `layout=None` means "no customization saved" (GET) or "reset to
    defaults" (PUT) - never an error condition.
    """

    layout: SidebarLayout | None = None
