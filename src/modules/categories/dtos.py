from datetime import datetime
from pydantic import BaseModel, UUID4

class CreateCategoryDTO(BaseModel):
    title: str
    color: str
    icon_name: str
    type: str


class UpdateCategoryDTO(BaseModel):
    title: str | None = None
    color: str | None = None
    icon_name: str | None = None
    type: str | None = None


class CategoryResponse(BaseModel):
    code: UUID4
    title: str
    color: str
    icon_name: str
    created_at: datetime
    type: str

    model_config = {"from_attributes": True}
