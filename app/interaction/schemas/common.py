from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    """Base DTO: snake_case in Python, camelCase on the wire."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class ErrorBody(ApiModel):
    code: str
    message: str
    details: dict[str, Any] = {}


class ErrorResponse(ApiModel):
    error: ErrorBody
