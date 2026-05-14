from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class APIParameter(BaseModel):
    name: str
    type: str = "string"
    required: bool = False
    description: Optional[str] = None
    location: Literal["query", "path", "header", "body"] = "query"


class APIEndpoint(BaseModel):
    path: str
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"]
    summary: str
    parameters: List[APIParameter] = Field(default_factory=list)
    response_description: Optional[str] = None


class AuthMethod(BaseModel):
    type: Literal["bearer", "api_key", "none"] = "none"
    header_name: Optional[str] = "Authorization"


class APISchema(BaseModel):
    title: str
    base_url: str
    version: str = "1.0"
    auth: AuthMethod = Field(default_factory=AuthMethod)
    endpoints: List[APIEndpoint]
    confidence_score: float = 1.0
    extraction_notes: List[str] = Field(default_factory=list)
