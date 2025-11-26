from typing import List
from pydantic import BaseModel


class Message(BaseModel):
    id: str
    user_id: str
    user_name: str
    timestamp: str
    message: str


class SearchResponse(BaseModel):
    query: str
    page: int
    page_size: int
    total: int
    items: List[Message]
