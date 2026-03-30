from fastapi import APIRouter

from app.roadmap_schemas import (
    AdminRoadmapDetailResponse,
    AdminRoadmapListResponse,
    CareerStatsUpdateRequest,
    DayInLifeUpdateRequest,
    MarkRoadmapTopicCompleteRequest,
    MilestoneRequest,
    MilestoneUpdateRequest,
    RoadmapApiStatusResponse,
    RoadmapCreateRequest,
    RoadmapListResponse,
    RoadmapOverviewResponse,
    RoadmapTopicRequest,
    RoadmapTopicUpdateRequest,
    RoadmapUpdateRequest,
    AddResponsibilityRequest,
    AddTechnologyRequest,
    AddCompanyRequest,
    SalaryRowRequest,
    SalaryRowUpdateRequest,
    UserRoadmapProgressResponse,
)
from app.services.roadmap_service import (
    admin_add_milestone,
    admin_add_milestone_topic,
    admin_create_roadmap,
    admin_delete_milestone,
    admin_delete_milestone_topic,
    admin_delete_roadmap,
    admin_get_roadmap,
    admin_list_roadmaps,
    admin_update_milestone,
    admin_update_milestone_topic,
    admin_update_roadmap,
    admin_update_career_stats,
    admin_update_day_in_life,
    admin_add_responsibility,
    admin_delete_responsibility,
    admin_add_technology,
    admin_delete_technology,
    admin_add_top_company,
    admin_delete_top_company,
    admin_add_salary_row,
    admin_update_salary_row,
    admin_delete_salary_row,
    user_get_roadmap_overview,
    user_get_roadmap_progress,
    user_list_roadmaps,
    user_mark_topic_complete,
)

router = APIRouter()


# ===========================================================================
# User — Public roadmap listing
# ===========================================================================

@router.get("/", response_model=RoadmapListResponse)
def list_roadmaps():
    """List all roadmaps (id, name, tagline, milestone_count, icon, icon_bg)."""
    return user_list_roadmaps()


# ===========================================================================
# User — Roadmap overview (static career info + milestone structure)
# ===========================================================================

@router.get("/{roadmap_id}", response_model=RoadmapOverviewResponse)
def get_roadmap_overview(roadmap_id: str):
    """
    Public roadmap overview: career stats, salary breakdown, technologies,
    responsibilities, finish_attire, and milestone list (no user progress).
    """
    return user_get_roadmap_overview(roadmap_id)


# ===========================================================================
# User — Roadmap progress (per-milestone, per-topic completion)
# ===========================================================================

@router.get("/{roadmap_id}/progress/{user_id}", response_model=UserRoadmapProgressResponse)
def get_roadmap_progress(roadmap_id: str, user_id: str):
    """
    User roadmap progress: per-milestone duration, completed/total topics,
    progress_percentage, and per-topic is_completed derived from course progress.
    """
    return user_get_roadmap_progress(roadmap_id, user_id)


# ===========================================================================
# User — Mark unlinked topic complete (manual)
# ===========================================================================

@router.post(
    "/{roadmap_id}/milestones/{milestone_id}/topics/{roadmap_topic_id}/complete",
    response_model=RoadmapApiStatusResponse,
)
def mark_topic_complete(
    roadmap_id: str,
    milestone_id: str,
    roadmap_topic_id: str,
    payload: MarkRoadmapTopicCompleteRequest,
):
    """Mark a standalone (non-linked) roadmap topic as complete for a user."""
    return user_mark_topic_complete(roadmap_id, milestone_id, roadmap_topic_id, payload.user_id)


# ===========================================================================
# Admin — Roadmap CRUD
# ===========================================================================

@router.post("/admin", response_model=RoadmapApiStatusResponse)
def admin_create_roadmap_endpoint(payload: RoadmapCreateRequest):
    """Admin: create a new roadmap with optional milestones and topics."""
    return admin_create_roadmap(payload.model_dump())


@router.get("/admin/all", response_model=AdminRoadmapListResponse)
def admin_list_roadmaps_endpoint():
    """Admin: list all roadmaps."""
    return admin_list_roadmaps()


@router.get("/admin/{roadmap_id}", response_model=AdminRoadmapDetailResponse)
def admin_get_roadmap_endpoint(roadmap_id: str):
    """Admin: get full roadmap detail with all milestones and topics."""
    return admin_get_roadmap(roadmap_id)


@router.put("/admin/{roadmap_id}", response_model=RoadmapApiStatusResponse)
def admin_update_roadmap_endpoint(roadmap_id: str, payload: RoadmapUpdateRequest):
    """Admin: update roadmap metadata (name, tagline, description, icon, career)."""
    return admin_update_roadmap(roadmap_id, payload.model_dump(exclude_none=True))


@router.delete("/admin/{roadmap_id}", response_model=RoadmapApiStatusResponse)
def admin_delete_roadmap_endpoint(roadmap_id: str):
    """Admin: permanently delete a roadmap."""
    return admin_delete_roadmap(roadmap_id)


# ===========================================================================
# Admin — Career: Stats
# ===========================================================================

@router.put("/admin/{roadmap_id}/career/stats", response_model=RoadmapApiStatusResponse)
def admin_update_career_stats_endpoint(roadmap_id: str, payload: CareerStatsUpdateRequest):
    """Admin: set all 4 career stat fields (job_growth, new_jobs_per_year, entry_salary, senior_salary)."""
    return admin_update_career_stats(roadmap_id, payload.model_dump())


# ===========================================================================
# Admin — Career: Day in the Life
# ===========================================================================

@router.put("/admin/{roadmap_id}/career/day-in-life", response_model=RoadmapApiStatusResponse)
def admin_update_day_in_life_endpoint(roadmap_id: str, payload: DayInLifeUpdateRequest):
    """Admin: update the 'A Day in the Life' text."""
    return admin_update_day_in_life(roadmap_id, payload.day_in_the_life)


# ===========================================================================
# Admin — Career: Responsibilities
# ===========================================================================

@router.post("/admin/{roadmap_id}/career/responsibilities", response_model=RoadmapApiStatusResponse)
def admin_add_responsibility_endpoint(roadmap_id: str, payload: AddResponsibilityRequest):
    """Admin: add a responsibility bullet."""
    return admin_add_responsibility(roadmap_id, payload.responsibility)


@router.delete("/admin/{roadmap_id}/career/responsibilities", response_model=RoadmapApiStatusResponse)
def admin_delete_responsibility_endpoint(roadmap_id: str, payload: AddResponsibilityRequest):
    """Admin: remove a responsibility bullet by exact value."""
    return admin_delete_responsibility(roadmap_id, payload.responsibility)


# ===========================================================================
# Admin — Career: Technologies
# ===========================================================================

@router.post("/admin/{roadmap_id}/career/technologies", response_model=RoadmapApiStatusResponse)
def admin_add_technology_endpoint(roadmap_id: str, payload: AddTechnologyRequest):
    """Admin: add a technology."""
    return admin_add_technology(roadmap_id, payload.technology)


@router.delete("/admin/{roadmap_id}/career/technologies", response_model=RoadmapApiStatusResponse)
def admin_delete_technology_endpoint(roadmap_id: str, payload: AddTechnologyRequest):
    """Admin: remove a technology by exact value."""
    return admin_delete_technology(roadmap_id, payload.technology)


# ===========================================================================
# Admin — Career: Top Companies
# ===========================================================================

@router.post("/admin/{roadmap_id}/career/top-companies", response_model=RoadmapApiStatusResponse)
def admin_add_top_company_endpoint(roadmap_id: str, payload: AddCompanyRequest):
    """Admin: add a top company."""
    return admin_add_top_company(roadmap_id, payload.company)


@router.delete("/admin/{roadmap_id}/career/top-companies", response_model=RoadmapApiStatusResponse)
def admin_delete_top_company_endpoint(roadmap_id: str, payload: AddCompanyRequest):
    """Admin: remove a top company by exact value."""
    return admin_delete_top_company(roadmap_id, payload.company)


# ===========================================================================
# Admin — Career: Salary Breakdown
# ===========================================================================

@router.post("/admin/{roadmap_id}/career/salary-breakdown", response_model=RoadmapApiStatusResponse)
def admin_add_salary_row_endpoint(roadmap_id: str, payload: SalaryRowRequest):
    """Admin: add a salary row (level + amount)."""
    return admin_add_salary_row(roadmap_id, payload.level, payload.amount)


@router.put("/admin/{roadmap_id}/career/salary-breakdown/{level}", response_model=RoadmapApiStatusResponse)
def admin_update_salary_row_endpoint(roadmap_id: str, level: str, payload: SalaryRowUpdateRequest):
    """Admin: update the amount for an existing salary level."""
    return admin_update_salary_row(roadmap_id, level, payload.amount)


@router.delete("/admin/{roadmap_id}/career/salary-breakdown/{level}", response_model=RoadmapApiStatusResponse)
def admin_delete_salary_row_endpoint(roadmap_id: str, level: str):
    """Admin: remove a salary row by its level name."""
    return admin_delete_salary_row(roadmap_id, level)


# ===========================================================================
# Admin — Milestone CRUD
# ===========================================================================

@router.post("/admin/{roadmap_id}/milestones", response_model=RoadmapApiStatusResponse)
def admin_add_milestone_endpoint(roadmap_id: str, payload: MilestoneRequest):
    """Admin: add a new milestone to a roadmap."""
    return admin_add_milestone(roadmap_id, payload.model_dump())


@router.put(
    "/admin/{roadmap_id}/milestones/{milestone_id}",
    response_model=RoadmapApiStatusResponse,
)
def admin_update_milestone_endpoint(
    roadmap_id: str, milestone_id: str, payload: MilestoneUpdateRequest
):
    """Admin: update a milestone's title, description, or step_order."""
    return admin_update_milestone(roadmap_id, milestone_id, payload.model_dump(exclude_none=True))


@router.delete(
    "/admin/{roadmap_id}/milestones/{milestone_id}",
    response_model=RoadmapApiStatusResponse,
)
def admin_delete_milestone_endpoint(roadmap_id: str, milestone_id: str):
    """Admin: remove a milestone (and all its topics) from a roadmap."""
    return admin_delete_milestone(roadmap_id, milestone_id)


# ===========================================================================
# Admin — Milestone topic CRUD
# ===========================================================================

@router.post(
    "/admin/{roadmap_id}/milestones/{milestone_id}/topics",
    response_model=RoadmapApiStatusResponse,
)
def admin_add_milestone_topic_endpoint(
    roadmap_id: str, milestone_id: str, payload: RoadmapTopicRequest
):
    """Admin: add a topic to a milestone. Link it to a course topic for auto progress."""
    return admin_add_milestone_topic(roadmap_id, milestone_id, payload.model_dump())


@router.put(
    "/admin/{roadmap_id}/milestones/{milestone_id}/topics/{roadmap_topic_id}",
    response_model=RoadmapApiStatusResponse,
)
def admin_update_milestone_topic_endpoint(
    roadmap_id: str,
    milestone_id: str,
    roadmap_topic_id: str,
    payload: RoadmapTopicUpdateRequest,
):
    """Admin: update or re-link a milestone topic."""
    return admin_update_milestone_topic(
        roadmap_id, milestone_id, roadmap_topic_id, payload.model_dump(exclude_none=True)
    )


@router.delete(
    "/admin/{roadmap_id}/milestones/{milestone_id}/topics/{roadmap_topic_id}",
    response_model=RoadmapApiStatusResponse,
)
def admin_delete_milestone_topic_endpoint(
    roadmap_id: str, milestone_id: str, roadmap_topic_id: str
):
    """Admin: remove a topic from a milestone."""
    return admin_delete_milestone_topic(roadmap_id, milestone_id, roadmap_topic_id)
