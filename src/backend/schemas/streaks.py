from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class StreakStatusResponse(BaseModel):
    is_active: bool = True
    streak_count: int = 14
    longest_streak: int = 21
    cadence: str = "daily"
    target_time: str = "09:30 AM"
    selected_platforms: List[str] = Field(default_factory=lambda: ["linkedin", "x"])
    auto_pilot_enabled: bool = True
    today_dispatched: bool = False
    last_dispatched_at: Optional[datetime] = None
    next_scheduled_at: Optional[datetime] = None


class UpdateStreakConfigRequest(BaseModel):
    is_active: Optional[bool] = None
    cadence: Optional[str] = None
    target_time: Optional[str] = None
    selected_platforms: Optional[List[str]] = None
    auto_pilot_enabled: Optional[bool] = None
    asset_folder_uri: Optional[str] = None


class ContributionDayItem(BaseModel):
    date: str
    count: int = 0
    level: int = 0  # 0 to 4 for GitHub-style green intensity


class StreakHeatmapResponse(BaseModel):
    total_contributions: int = 0
    current_streak: int = 0
    longest_streak: int = 0
    days: List[ContributionDayItem] = Field(default_factory=list)
