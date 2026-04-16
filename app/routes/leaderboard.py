from fastapi import APIRouter, Depends, Query
from typing import Optional
from sqlalchemy.orm import Session

from app.mysql_db import get_db
from app.services.leaderboard_service import (
    get_college_leaderboard,
    get_college_department_stats,
    get_college_activity_stats,
    get_college_overview,
    get_low_engagement_students,
    get_academic_support_students,
    get_top_performers,
    search_college_students,
)

router = APIRouter()


@router.get("/college/{college_id}")
def college_leaderboard(
    college_id: str,
    branch_id: Optional[str] = Query(None, description="Filter by branch; omit for all branches"),
    db: Session = Depends(get_db),
):
    """
    College student leaderboard ranked by avg college-assignment score %.

    Student profile data (name, student_id, branch, year_of_study) is pulled
    from the MySQL zealup_db.users table.

    Score is the student's average percentage across all submitted college
    assignments stored in DynamoDB (TABLE8).

    Response:
        rank | name | student_id | branch | year_of_study | score_pct | score_display
    """
    return get_college_leaderboard(college_id, db, branch_id)


@router.get("/college/{college_id}/departments")
def college_department_stats(
    college_id: str,
    branch_id: Optional[str] = Query(None, description="Filter by branch; omit for all branches"),
    db: Session = Depends(get_db),
):
    """
    Department-wise analytics for a college.

    For each branch/department returns:
    - branch              : department name
    - student_count       : number of active students
    - avg_score_pct       : average assignment score % across all students in the dept
    - avg_attendance_pct  : average attendance % (submitted assignments / total college assignments * 100)
    """
    return get_college_department_stats(college_id, db, branch_id)


@router.get("/college/{college_id}/activity-stats")
def college_activity_stats(
    college_id: str,
    branch_id: Optional[str] = Query(None, description="Filter by branch; omit for all branches"),
    db: Session = Depends(get_db),
):
    """
    Aggregate interview and resume counts for all active college students.

    Returns:
      - total_students   : number of active college students
      - total_interviews : total interview sessions taken across all college students
      - total_resumes    : total resumes created across all college students
    """
    return get_college_activity_stats(college_id, db, branch_id)


@router.get("/college/{college_id}/overview")
def college_overview(
    college_id: str,
    branch_id: Optional[str] = Query(None, description="Filter by branch; omit for all branches"),
    db: Session = Depends(get_db),
):
    """
    Single-call college overview card.

    Returns:
      - total_students        : number of active students
      - active_departments    : number of distinct branches with ≥ 1 student
      - overall_avg_score_pct : college-wide average assignment score %
      - overall_attendance_pct: college-wide average attendance %
    """
    return get_college_overview(college_id, db, branch_id)


@router.get("/college/{college_id}/insights/low-engagement")
def college_low_engagement(
    college_id: str,
    branch_id: Optional[str] = Query(None, description="Filter by branch name; omit for all branches"),
    attendance_threshold: float = Query(60.0, description="Attendance % below this value is flagged"),
    db: Session = Depends(get_db),
):
    """
    Low Engagement / Absentees — students whose attendance % is below the threshold.

    Query params:
      - branch_id            : branch name to filter (optional, default = all)
      - attendance_threshold : flag students below this % (default 60)

    Response per student: name | student_id | branch | attendance_pct | absent_count | attendance_metric
    """
    return get_low_engagement_students(college_id, branch_id, attendance_threshold, db)


@router.get("/college/{college_id}/insights/academic-support")
def college_academic_support(
    college_id: str,
    branch_id: Optional[str] = Query(None, description="Filter by branch name; omit for all branches"),
    score_threshold: float = Query(50.0, description="Avg score % below this value is flagged"),
    db: Session = Depends(get_db),
):
    """
    Academic Support Needed — students whose avg assignment score % is below the threshold.

    Query params:
      - branch_id       : branch name to filter (optional, default = all)
      - score_threshold : flag students below this % (default 50)

    Response per student: name | student_id | branch | avg_score_pct | performance_metric
    """
    return get_academic_support_students(college_id, branch_id, score_threshold, db)


@router.get("/college/{college_id}/insights/top-performers")
def college_top_performers(
    college_id: str,
    branch_id: Optional[str] = Query(None, description="Filter by branch name; omit for all branches"),
    score_threshold: float = Query(80.0, description="Avg score % at or above this value qualifies"),
    db: Session = Depends(get_db),
):
    """
    Top Performers — students whose avg assignment score % is at or above the threshold.

    Query params:
      - branch_id       : branch name to filter (optional, default = all)
      - score_threshold : minimum % to qualify as top performer (default 80)

    Response per student: name | student_id | branch | avg_score_pct | performance_metric
    """
    return get_top_performers(college_id, branch_id, score_threshold, db)


@router.get("/college/{college_id}/search")
def student_search(
    college_id: str,
    q: str = Query(..., min_length=1, description="Name or student ID (partial match)"),
    branch_id: Optional[str] = Query(None, description="Restrict search to this branch"),
    db: Session = Depends(get_db),
):
    """
    Search students in a college by name or student ID (partial / prefix match).

    Query params:
      - q         : search term (required, min 1 character)
      - branch_id : restrict to a specific branch (optional)

    Returns up to 50 matches: user_id | name | student_id | email | branch | year_of_study
    """
    return search_college_students(college_id, q, branch_id, db)
