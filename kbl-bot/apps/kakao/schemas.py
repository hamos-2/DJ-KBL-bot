"""Pydantic v2 schemas for Kakao OpenBuilder Skill request/response."""

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class KakaoUser(BaseModel):
    """Identifies the KakaoTalk user making the request."""

    id: str = Field(..., description="KakaoTalk botUserKey")


class KakaoUserRequest(BaseModel):
    """Wraps the user identity and utterance inside the Skill payload."""

    user: KakaoUser
    utterance: str = Field(default="", description="User utterance text (e.g. '#KT vs LG')")


class KakaoAction(BaseModel):
    """Identifies which Skill action was triggered."""

    name: str = Field(..., description="Skill action name")
    params: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)


class KakaoSkillPayload(BaseModel):
    """Top-level Kakao OpenBuilder Skill request payload."""

    user_request: KakaoUserRequest = Field(..., alias="userRequest")
    action: KakaoAction
    contexts: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class SimpleText(BaseModel):
    """Kakao SimpleText output component."""

    text: str


class SimpleTextOutput(BaseModel):
    """Wraps SimpleText as an output component."""

    simpleText: SimpleText


class QuickReply(BaseModel):
    """Kakao quick-reply button."""

    action: str = Field(default="message")
    label: str
    messageText: str


class KakaoTemplate(BaseModel):
    """Kakao Skill response template."""

    outputs: list[dict[str, Any]]
    quickReplies: list[QuickReply] = Field(default_factory=list)


class KakaoSkillResponse(BaseModel):
    """Top-level Kakao OpenBuilder Skill response (always HTTP 200)."""

    version: str = Field(default="2.0")
    template: KakaoTemplate
