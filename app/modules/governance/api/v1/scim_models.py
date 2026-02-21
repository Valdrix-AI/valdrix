from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .scim_schemas import SCIM_LIST_SCHEMA


class ScimListResponse(BaseModel):
    schemas: list[str] = Field(default_factory=lambda: [SCIM_LIST_SCHEMA])
    totalResults: int
    startIndex: int
    itemsPerPage: int
    Resources: list[dict[str, Any]]

    model_config = ConfigDict(extra="forbid")


class ScimEmail(BaseModel):
    value: EmailStr
    primary: bool | None = None
    type: str | None = None

    model_config = ConfigDict(extra="ignore")


class ScimGroupRef(BaseModel):
    value: str | None = None
    display: str | None = None

    model_config = ConfigDict(extra="ignore")


class ScimMemberRef(BaseModel):
    value: str | None = None
    display: str | None = None

    model_config = ConfigDict(extra="ignore")


class ScimGroupCreate(BaseModel):
    displayName: str = Field(min_length=1, max_length=255)
    externalId: str | None = Field(default=None, max_length=255)
    members: list[ScimMemberRef] | None = None

    model_config = ConfigDict(extra="ignore")


class ScimGroupPut(BaseModel):
    displayName: str = Field(min_length=1, max_length=255)
    externalId: str | None = Field(default=None, max_length=255)
    members: list[ScimMemberRef] | None = None

    model_config = ConfigDict(extra="ignore")


class ScimUserCreate(BaseModel):
    userName: EmailStr
    active: bool = True
    emails: list[ScimEmail] | None = None
    groups: list[ScimGroupRef] | None = None

    model_config = ConfigDict(extra="ignore")


class ScimUserPut(BaseModel):
    userName: EmailStr
    active: bool = True
    emails: list[ScimEmail] | None = None
    groups: list[ScimGroupRef] | None = None

    model_config = ConfigDict(extra="ignore")


class ScimPatchOperation(BaseModel):
    op: Literal["add", "replace", "remove"]
    path: str | None = None
    value: Any | None = None

    model_config = ConfigDict(extra="ignore")


class ScimPatchRequest(BaseModel):
    Operations: list[ScimPatchOperation] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")
