from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return str(uuid4())


StatusFlag = Literal["active", "archived"]
RoleFlag = Literal["main", "banker", "mule", "utility"]
RotateFlag = Literal["rotate", "no_rotate", "shared"]


class Character(BaseModel):
    id: str = Field(default_factory=_uuid)
    account_id: str
    name: str
    char_class: Optional[str] = None
    level: Optional[int] = None
    notes: Optional[str] = None
    created_at: str = Field(default_factory=_now)


class Tag(BaseModel):
    id: str = Field(default_factory=_uuid)
    name: str


class Account(BaseModel):
    id: str = Field(default_factory=_uuid)
    label: str
    # username and password are stored encrypted; these hold the decrypted
    # plaintext only while in memory (never persisted as plaintext).
    username: Optional[str] = None
    password: Optional[str] = None
    owner: Optional[str] = None
    shared_by: Optional[str] = None
    status: StatusFlag = "active"
    role_flag: Optional[RoleFlag] = None
    rotate_flag: Optional[RotateFlag] = None
    notes: Optional[str] = None
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    # Populated by DB layer when loading full account detail
    characters: List[Character] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class VaultMeta(BaseModel):
    kdf_salt: bytes
    kdf_time_cost: int = 3
    kdf_memory_cost: int = 65536  # 64 MB
    kdf_parallelism: int = 1
    schema_version: int = 1
    created_at: str = Field(default_factory=_now)
