from __future__ import annotations

from pydantic import BaseModel, Field


class IceBreakerQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=80)
    payload: str = Field(min_length=1, max_length=200)


class IceBreakersRequest(BaseModel):
    questions: list[IceBreakerQuestion] = Field(max_length=4)
