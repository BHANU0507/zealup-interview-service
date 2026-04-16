from fastapi import APIRouter, Query

from app.services.dashboard_service import (
    get_college_student_dashboard,
    get_individual_student_dashboard,
    get_college_student_todo,
    get_individual_weak_areas,
    get_college_weak_areas,
    get_user_roadmap_progress,
)
from app.services.course_service import get_user_enrollments

router = APIRouter()


@router.get("/college-student/{user_id}")
def college_student_dashboard(
    user_id: str,
    college_id: str = Query(..., alias="collegeId"),
):
    """
    Dashboard stats for a college student.

    Returns:
    - courses_enrolled
    - interview_stats  (avg_score, total_interviews, total_score)
    - college_assignment_stats (avg_score, total_assignments, total_score)
    - challenge_rank   (rank, total_score, total_users_in_college)
    """
    return get_college_student_dashboard(user_id, college_id)


@router.get("/individual-student/{user_id}")
def individual_student_dashboard(user_id: str):
    """
    Dashboard stats for an individual (non-college) student.

    Returns:
    - courses_enrolled
    - interview_stats  (avg_score, total_interviews, total_score)
    - assignment_stats (avg_score, total_assignments, total_score)
    - challenge_rank   (rank, total_score, total_individual_users)
    """
    return get_individual_student_dashboard(user_id)


@router.get("/college-student/{user_id}/courses")
def college_student_courses(
    user_id: str,
    college_id: str = Query(..., alias="collegeId"),
):
    """
    Enrolled courses with name and progress bar for a college student.

    Returns a list of courses with title and progress_percentage (0-100).
    """
    data = get_user_enrollments(user_id)
    return {
        "user_id": user_id,
        "college_id": college_id,
        "enrolled_count": data["enrolled_count"],
        "courses": [
            {
                "course_id": c["course_id"],
                "title": c["title"],
                "progress_percentage": c["progress_percentage"],
                "status": c["status"],
            }
            for c in data["enrolled_courses"]
        ],
    }


@router.get("/individual-student/{user_id}/courses")
def individual_student_courses(user_id: str):
    """
    Enrolled courses with name and progress bar for an individual student.

    Returns a list of courses with title and progress_percentage (0-100).
    """
    data = get_user_enrollments(user_id)
    return {
        "user_id": user_id,
        "enrolled_count": data["enrolled_count"],
        "courses": [
            {
                "course_id": c["course_id"],
                "title": c["title"],
                "progress_percentage": c["progress_percentage"],
                "status": c["status"],
            }
            for c in data["enrolled_courses"]
        ],
    }


@router.get("/college-student/{user_id}/todo")
def college_student_todo(
    user_id: str,
    college_id: str = Query(..., alias="collegeId"),
):
    """
    Pending (todo) assignments for a college student.

    Returns assignments that are:
    - Active (not locked)
    - Deadline not yet passed (or no deadline)
    - Not yet submitted by the student

    Each item includes days_remaining and an urgency label:
      due_today | urgent (≤2 days) | this_week (≤7 days) | upcoming | no_deadline
    """
    return get_college_student_todo(user_id, college_id)


@router.get("/college-student/{user_id}/weak-areas")
def college_student_weak_areas(
    user_id: str,
    college_id: str = Query(..., alias="collegeId"),
):
    """
    Weak areas for a college student, derived from:
    - Interview question feedback (skill_gaps where AI score < 5/10)
    - College assignment section scores (sections where score < 60%)

    Returns:
    - interview_weak_areas: grouped by skill_gap, sorted by frequency then worst score
    - college_assignment_weak_areas: per-section breakdown sorted by lowest score %
    - thresholds: the cutoff values used
    """
    return get_college_weak_areas(user_id, college_id)


@router.get("/individual-student/{user_id}/weak-areas")
def individual_student_weak_areas(user_id: str):
    """
    Weak areas for an individual student, derived from:
    - Interview question feedback (skill_gaps where AI score < 5/10)
    - General assignment section scores (sections where score < 60%)

    Returns:
    - interview_weak_areas: grouped by skill_gap, sorted by frequency then worst score
    - assignment_weak_areas: per-section breakdown sorted by lowest score %
    - thresholds: the cutoff values used
    """
    return get_individual_weak_areas(user_id)


@router.get("/college-student/{user_id}/roadmap-progress")
def college_student_roadmap_progress(
    user_id: str,
    college_id: str = Query(..., alias="collegeId"),
):
    """
    Roadmap overall progress for a college student.
    Only returns roadmaps the student has started (begun their journey on).

    Each item includes:
    - roadmap name
    - overall_progress_percentage (0-100)
    - total_stages  (total topics across all milestones)
    - completed_stages
    """
    return get_user_roadmap_progress(user_id)


@router.get("/individual-student/{user_id}/roadmap-progress")
def individual_student_roadmap_progress(user_id: str):
    """
    Roadmap overall progress for an individual student.
    Only returns roadmaps the student has started (begun their journey on).

    Each item includes:
    - roadmap name
    - overall_progress_percentage (0-100)
    - total_stages  (total topics across all milestones)
    - completed_stages
    """
    return get_user_roadmap_progress(user_id)

