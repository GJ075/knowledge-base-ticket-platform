import uuid

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    role: str
    can_evaluate: bool = False

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    user: UserOut
