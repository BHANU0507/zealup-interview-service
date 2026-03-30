from typing import List, Optional
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Career info sub-models (used in overview response)
# ---------------------------------------------------------------------------

class CareerStats(BaseModel):
    job_growth: str = ""
    new_jobs_per_year: str = ""
    entry_salary: str = ""
    senior_salary: str = ""


class SalaryBreakdown(BaseModel):
    level: str
    amount: str


class CareerInfo(BaseModel):
    stats: CareerStats = CareerStats()
    responsibilities: List[str] = []
    day_in_the_life: str = ""
    salary_breakdown: List[SalaryBreakdown] = []
    top_companies: List[str] = []
    technologies: List[str] = []


# ---------------------------------------------------------------------------
# Admin request models
# ---------------------------------------------------------------------------

class CareerStatsRequest(BaseModel):
    job_growth: str = ""
    new_jobs_per_year: str = ""
    entry_salary: str = ""
    senior_salary: str = ""


class SalaryBreakdownRequest(BaseModel):
    level: str
    amount: str


class CareerInfoRequest(BaseModel):
    stats: Optional[CareerStatsRequest] = None
    responsibilities: List[str] = []
    day_in_the_life: str = ""
    salary_breakdown: List[SalaryBreakdownRequest] = []
    top_companies: List[str] = []
    technologies: List[str] = []


class RoadmapTopicRequest(BaseModel):
    """A topic entry inside a milestone. Provide course links for auto-derived progress."""
    title: str = ""
    description: str = ""
    duration_minutes: int = 0
    linked_course_id: Optional[str] = None
    linked_module_id: Optional[str] = None
    linked_topic_id: Optional[str] = None


class MilestoneRequest(BaseModel):
    title: str
    description: str = ""
    step_order: Optional[int] = None
    topics: List[RoadmapTopicRequest] = []


class RoadmapCreateRequest(BaseModel):
    name: str
    tagline: str = ""
    description: str = ""
    icon: str = ""
    icon_bg: str = ""
    finish_attire: str = ""


class RoadmapUpdateRequest(BaseModel):
    name: Optional[str] = None
    tagline: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    icon_bg: Optional[str] = None
    finish_attire: Optional[str] = None
    career: Optional[CareerInfoRequest] = None


class MilestoneUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    step_order: Optional[int] = None


# ---------------------------------------------------------------------------
# Career sub-section request schemas (granular endpoints)
# ---------------------------------------------------------------------------

class CareerStatsUpdateRequest(BaseModel):
    job_growth: str = ""
    new_jobs_per_year: str = ""
    entry_salary: str = ""
    senior_salary: str = ""


class DayInLifeUpdateRequest(BaseModel):
    day_in_the_life: str


class AddResponsibilityRequest(BaseModel):
    responsibility: str


class AddTechnologyRequest(BaseModel):
    technology: str


class AddCompanyRequest(BaseModel):
    company: str


class SalaryRowRequest(BaseModel):
    level: str
    amount: str


class SalaryRowUpdateRequest(BaseModel):
    amount: str


class RoadmapTopicUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = None
    linked_course_id: Optional[str] = None
    linked_module_id: Optional[str] = None
    linked_topic_id: Optional[str] = None


# ---------------------------------------------------------------------------
# User action schemas
# ---------------------------------------------------------------------------

class MarkRoadmapTopicCompleteRequest(BaseModel):
    user_id: str


# ---------------------------------------------------------------------------
# Response: roadmap list item  (GET /api/roadmaps/)
# ---------------------------------------------------------------------------

class RoadmapListItem(BaseModel):
    roadmap_id: str
    name: str
    tagline: str = ""
    milestone_count: int = 0
    icon: str = ""
    icon_bg: str = ""


class RoadmapListResponse(BaseModel):
    total_count: int
    roadmaps: List[RoadmapListItem]


# ---------------------------------------------------------------------------
# Response: roadmap overview  (GET /api/roadmaps/{roadmap_id})
# Static data only — no per-user progress fields.
# ---------------------------------------------------------------------------

class MilestoneOverviewTopic(BaseModel):
    """Lightweight topic item for the static overview (no is_completed)."""
    roadmap_topic_id: str
    title: str = ""
    description: str = ""
    duration_minutes: int = 0
    course_id: Optional[str] = None
    module_id: Optional[str] = None
    topic_id: Optional[str] = None


class MilestoneOverview(BaseModel):
    milestone_id: str
    title: str
    description: str = ""
    step_order: int = 0
    duration_minutes: int = 0
    total_topics: int = 0
    topics: List[MilestoneOverviewTopic] = []


class RoadmapOverviewResponse(BaseModel):
    roadmap_id: str
    name: str
    tagline: str = ""
    description: str = ""
    icon: str = ""
    icon_bg: str = ""
    finish_attire: str = ""
    milestone_count: int = 0
    career: CareerInfo = CareerInfo()
    milestones: List[MilestoneOverview] = []


# ---------------------------------------------------------------------------
# Response: admin roadmap detail  (GET /api/roadmaps/admin/{roadmap_id})
# ---------------------------------------------------------------------------

class AdminRoadmapDetailResponse(RoadmapOverviewResponse):
    created_at: int = 0
    updated_at: int = 0


class AdminRoadmapListResponse(BaseModel):
    total_count: int
    roadmaps: List[RoadmapListItem]


# ---------------------------------------------------------------------------
# Response: user roadmap progress  (GET /api/roadmaps/{roadmap_id}/progress/{user_id})
# ---------------------------------------------------------------------------

class RoadmapTopicProgress(BaseModel):
    roadmap_topic_id: str
    title: str = ""
    description: str = ""
    duration_minutes: int = 0
    course_id: Optional[str] = None
    module_id: Optional[str] = None
    topic_id: Optional[str] = None
    is_completed: bool = False
    course_enrolled: bool = True          # False when user has not enrolled in the linked course
    enrollment_message: str = ""          # Populated when course_enrolled=False


class MilestoneProgress(BaseModel):
    milestone_id: str
    title: str
    description: str = ""
    step_order: int = 0
    duration_minutes: int = 0
    total_topics: int = 0
    completed_topics: int = 0
    progress_percentage: int = 0
    topics: List[RoadmapTopicProgress] = []


class UserRoadmapProgressResponse(BaseModel):
    roadmap_id: str
    name: str
    overall_progress_percentage: int = 0
    total_topics: int = 0
    completed_topics: int = 0
    milestones: List[MilestoneProgress] = []


# ---------------------------------------------------------------------------
# Generic status response
# ---------------------------------------------------------------------------

class RoadmapApiStatusResponse(BaseModel):
    status: str
    roadmap_id: Optional[str] = None
    milestone_id: Optional[str] = None
    roadmap_topic_id: Optional[str] = None
    message: str = ""
