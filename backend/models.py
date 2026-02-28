from pydantic import BaseModel
from typing import List, Optional


class EmailConfig(BaseModel):
    digest_time_utc: str = "08:00"
    max_articles: int = 10
    min_relevance: int = 5


class NewsItem(BaseModel):
    id: str
    title: str
    url: str
    source: str
    summary: Optional[str] = None
    category: Optional[str] = None
    relevance_score: int = 5
    is_product_or_tool: bool = False
    competitors: Optional[List[dict]] = None
    competitive_advantage: Optional[str] = None


class UserCreate(BaseModel):
    email: str
    name: str
    categories: Optional[List[str]] = None
    min_relevance: int = 5
