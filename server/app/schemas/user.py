import uuid

from pydantic import BaseModel


class UserBrief(BaseModel):
    id: uuid.UUID
    display_name: str
    role: str

    model_config = {"from_attributes": True}
