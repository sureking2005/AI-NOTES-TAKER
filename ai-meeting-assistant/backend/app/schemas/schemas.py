from pydantic import BaseModel, Field
from typing import List


class ActionItem(BaseModel):
    task: str
    owner: str
    due_date: str
    priority: str
    confidence_score: int = Field(ge=0, le=100)


class MoMSchema(BaseModel):
    Summary_by_Topics: List[str] = Field(default_factory=list, alias="Summary by Topics")
    Key_Discussion_Points: List[str] = Field(default_factory=list, alias="Key Discussion Points")
    Decisions: List[str] = Field(default_factory=list)
    Action_Items: List[ActionItem] = Field(default_factory=list, alias="Action Items")
    Risks: List[str] = Field(default_factory=list)
    Open_Questions: List[str] = Field(default_factory=list, alias="Open Questions")

    class Config:
        populate_by_name = True