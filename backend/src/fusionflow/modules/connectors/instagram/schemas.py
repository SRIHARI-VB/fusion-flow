from __future__ import annotations

from pydantic import BaseModel, Field


class IceBreakerQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=80)
    payload: str = Field(min_length=1, max_length=200)


class IceBreakersRequest(BaseModel):
    questions: list[IceBreakerQuestion] = Field(max_length=4)


class InstagramMediaOut(BaseModel):
    """One post/reel, as returned by `GET /{ig-id}/media` - the post/reel
    picker's row shape. Every field but `id`/`media_type` is optional:
    Meta omits `caption` when a post has none, `media_url` for some
    restricted/expired media, and `thumbnail_url` for anything that
    isn't a video."""

    id: str
    media_type: str
    caption: str | None = None
    media_url: str | None = None
    thumbnail_url: str | None = None
    permalink: str | None = None
    timestamp: str | None = None


class InstagramMediaPage(BaseModel):
    """One page of `list_media` - a tenant with hundreds of posts/reels
    can't be handed the whole account in one response, so the post/reel
    picker (Comment Automation/Comment Moderation's "scope to specific
    posts/reels" option) pages through it via Meta's own cursor, `after`.
    `next_cursor: None` means this was the last page."""

    items: list[InstagramMediaOut]
    next_cursor: str | None = None
