from pydantic import BaseModel
from typing import List, Optional
from database import User

class EmailConfig(BaseModel):
    digest_time_utc: str = "08:00"
    max_articles: int = 10
    min_relevance: int = 5

class NewsItem(BaseModel):
    id: str
    title: str
    url: str
    source: str
    summary: Optional[str]
    category: Optional[str]
    relevance_score: int
    is_product_or_tool: bool
    competitors: Optional[List[dict]]
    competitive_advantage: Optional[str]

class UserCreate(BaseModel):
    email: str
    name: str
    categories: Optional[List[str]] = []
    min_relevance: int = 5
