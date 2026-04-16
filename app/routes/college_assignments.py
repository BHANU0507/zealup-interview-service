from fastapi import APIRouter, Depends, Query
from typing import Optional

from sqlalchemy.orm import Session

from app.mysql_db import get_db

from app.college_assignment_schemas import (
    CreateCollegeAssignmentRequest,
    UpdateCollegeAssignmentRequest,
    CreateSectionRequest,
    UpdateSectionRequest,
    AddQuestionRequest,
    SubmitCollegeSectionRequest,
    FinalizeCollegeAssignmentRequest,
)
from app.assignment_schemas import RunSampleRequest, RunSampleResponse, RunCodeRequest, RunCodeResponse
from app.services.college_assignment_service import (
    create_college_assignment,
    get_college_assignment,
    list_college_assignments,
    update_college_assignment,
    delete_college_assignment,
    add_college_section,
    list_college_sections,
    get_college_section,
    update_college_section,
    delete_college_section,
    add_college_question,
    list_college_questions,
    get_college_question,
    update_college_question,
    delete_college_question,
    college_assignment_availability,
    college_assignment_prestart,
    submit_college_section,
    finalize_college_assignment,
    get_college_assignment_progress,
    get_college_user_submission,
    admin_list_college_submissions,
    admin_college_assignment_stats,
    run_college_sample,
    run_college_tests,
    get_student_active_assignments,
    get_student_completed_assignments,
    get_student_missed_assignments,
    get_latest_college_assignment_snapshot,
    get_college_attendance_trend,
)

router = APIRouter()


# ===========================================================================
# College dashboard — latest assignment snapshot
# ===========================================================================

@router.get("/latest-snapshot/{college_id}")
def latest_assignment_snapshot_endpoint(
    college_id: str,
    branch_id: Optional[str] = Query(None, description="Filter stats to this branch; omit for whole college"),
    db: Session = Depends(get_db),
):
    """
    Returns the most recently created assignment for the college along with
    college-wide submission statistics:
      - participants    (total who submitted)
      - absent          (total_students - participants)
      - total_students  (active COLLEGE_STUDENT rows, scoped to branch when branch_id provided)
      - avg_score
      - top_score
      - least_score

    Returns has_assignment=false when no assignment has been created yet.
    """
    return get_latest_college_assignment_snapshot(college_id, db, branch_id)


@router.get("/attendance-trend/{college_id}")
def college_attendance_trend(
    college_id: str,
    year: int,
    month: Optional[int] = None,
    branch_id: Optional[str] = Query(None, description="Filter to this branch; omit for whole college"),
    db: Session = Depends(get_db),
):
    """
    College-wide monthly attendance trend.

    Attendance = unique students who submitted at least one college assignment
    whose due_date falls in the given month / total active students × 100.

    Query params:
      - year      (required) : e.g. 2026
      - month     (optional) : 1-12 for a single month; omit for all 12 months
      - branch_id (optional) : restrict to a specific branch

    Response fields per data point:
      month | month_name | participants | attendance_pct
    """
    if month is not None and not (1 <= month <= 12):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="month must be between 1 and 12")
    return get_college_attendance_trend(college_id, year, month, db, branch_id)


# ===========================================================================
# Assignment CRUD (admin / instructor)
# ===========================================================================

@router.post("/")
def create_assignment_endpoint(payload: CreateCollegeAssignmentRequest):
    """Admin: create a new college assignment (sections added separately)."""
    return create_college_assignment(payload.model_dump())


@router.get("/list/{college_id}")
def list_assignments_endpoint(college_id: str):
    """Admin/Student: list all assignments for a college."""
    return list_college_assignments(college_id)


@router.get("/{assignment_id}")
def get_assignment_endpoint(assignment_id: str):
    """Get full college assignment detail (with sections & questions)."""
    return get_college_assignment(assignment_id)


@router.put("/{assignment_id}")
def update_assignment_endpoint(assignment_id: str, payload: UpdateCollegeAssignmentRequest):
    """Admin: update college assignment metadata."""
    return update_college_assignment(assignment_id, payload.model_dump(exclude_none=True))


@router.delete("/{assignment_id}")
def delete_assignment_endpoint(assignment_id: str):
    """Admin: delete college assignment and all its sections/questions."""
    return delete_college_assignment(assignment_id)


# ===========================================================================
# Section CRUD
# ===========================================================================

@router.post("/{assignment_id}/sections")
def add_section_endpoint(assignment_id: str, payload: CreateSectionRequest):
    return add_college_section(assignment_id, payload.model_dump())


@router.get("/{assignment_id}/sections")
def list_sections_endpoint(assignment_id: str):
    return list_college_sections(assignment_id)


@router.get("/{assignment_id}/sections/{section_id}")
def get_section_endpoint(assignment_id: str, section_id: str):
    return get_college_section(assignment_id, section_id)


@router.put("/{assignment_id}/sections/{section_id}")
def update_section_endpoint(assignment_id: str, section_id: str, payload: UpdateSectionRequest):
    return update_college_section(assignment_id, section_id, payload.model_dump(exclude_none=True))


@router.delete("/{assignment_id}/sections/{section_id}")
def delete_section_endpoint(assignment_id: str, section_id: str):
    return delete_college_section(assignment_id, section_id)


# ===========================================================================
# Question CRUD
# ===========================================================================

@router.post("/{assignment_id}/sections/{section_id}/questions")
def add_question_endpoint(assignment_id: str, section_id: str, payload: AddQuestionRequest):
    return add_college_question(assignment_id, section_id, payload.model_dump())


@router.get("/{assignment_id}/sections/{section_id}/questions")
def list_questions_endpoint(assignment_id: str, section_id: str):
    return list_college_questions(assignment_id, section_id)


@router.get("/{assignment_id}/sections/{section_id}/questions/{question_id}")
def get_question_endpoint(assignment_id: str, section_id: str, question_id: str):
    return get_college_question(assignment_id, section_id, question_id)


@router.put("/{assignment_id}/sections/{section_id}/questions/{question_id}")
def update_question_endpoint(assignment_id: str, section_id: str, question_id: str, payload: AddQuestionRequest):
    return update_college_question(assignment_id, section_id, question_id, payload.model_dump(exclude_none=True))


@router.delete("/{assignment_id}/sections/{section_id}/questions/{question_id}")
def delete_question_endpoint(assignment_id: str, section_id: str, question_id: str):
    return delete_college_question(assignment_id, section_id, question_id)


# ===========================================================================
# Student — availability & pre-start
# ===========================================================================

@router.get("/{assignment_id}/availability")
def availability_endpoint(assignment_id: str, user_id: str = Query(...)):
    """Check whether a student can start an assignment."""
    return college_assignment_availability(assignment_id, user_id)


@router.get("/{assignment_id}/prestart")
def prestart_endpoint(assignment_id: str, user_id: str = Query(...)):
    """Pre-start overview: sections list, due date, attempt info."""
    return college_assignment_prestart(assignment_id, user_id)


# ===========================================================================
# Student — section-by-section submission
# ===========================================================================

@router.post("/{assignment_id}/sections/{section_id}/submit")
def submit_section_endpoint(assignment_id: str, section_id: str, user_id: str = Query(...), payload: SubmitCollegeSectionRequest = ...):
    """Submit answers for one section. Graded immediately; returns instant results."""
    return submit_college_section(user_id, assignment_id, section_id, payload.model_dump())


@router.get("/{assignment_id}/progress/{user_id}")
def progress_endpoint(assignment_id: str, user_id: str):
    """Get student's section-by-section submission progress."""
    return get_college_assignment_progress(user_id, assignment_id)


@router.post("/{assignment_id}/finalize")
def finalize_endpoint(assignment_id: str, user_id: str = Query(...), payload: FinalizeCollegeAssignmentRequest = ...):
    """Finalize: aggregate all section submissions into a final graded submission."""
    return finalize_college_assignment(user_id, assignment_id, payload.user_name or "")


@router.get("/{assignment_id}/submission/{user_id}")
def get_submission_endpoint(assignment_id: str, user_id: str):
    """Get a student's final submission for this assignment."""
    return get_college_user_submission(user_id, assignment_id)


# ===========================================================================
# Admin — submissions & stats
# ===========================================================================

# ===========================================================================
# Student — active / completed / missed assignment lists
# ===========================================================================

@router.get("/student/{college_id}/{user_id}/active")
def student_active_endpoint(college_id: str, user_id: str):
    """Assignments the student has NOT submitted yet and deadline has not passed."""
    return get_student_active_assignments(college_id, user_id)


@router.get("/student/{college_id}/{user_id}/completed")
def student_completed_endpoint(college_id: str, user_id: str):
    """Assignments the student has finalized at least once."""
    return get_student_completed_assignments(college_id, user_id)


@router.get("/student/{college_id}/{user_id}/missed")
def student_missed_endpoint(college_id: str, user_id: str):
    """Assignments whose deadline has passed and student never submitted."""
    return get_student_missed_assignments(college_id, user_id)


# ===========================================================================
# Admin — submissions & stats
# ===========================================================================

@router.get("/{assignment_id}/submissions")
def admin_submissions_endpoint(assignment_id: str):
    """Admin/Branch Admin: list all student submissions for a college assignment."""
    return admin_list_college_submissions(assignment_id)


@router.get("/{assignment_id}/stats")
def admin_stats_endpoint(assignment_id: str):
    """Admin: analytics — avg score, pass rate, highest/lowest score."""
    return admin_college_assignment_stats(assignment_id)


# ===========================================================================
# Code execution (Judge0)
# ===========================================================================

@router.post("/{assignment_id}/sections/{section_id}/questions/{question_id}/run",
             response_model=RunSampleResponse)
def run_sample_endpoint(assignment_id: str, section_id: str, question_id: str, request: RunSampleRequest):
    """
    Run code with a **single custom input** (scratchpad).
    Executes via Judge0 and returns raw stdout — does not compare against test cases.
    """
    return run_college_sample(
        assignment_id=assignment_id,
        section_id=section_id,
        question_id=question_id,
        language_id=request.language_id,
        source_code=request.source_code,
        stdin=request.stdin or "",
    )


@router.post("/{assignment_id}/sections/{section_id}/questions/{question_id}/run-tests",
             response_model=RunCodeResponse)
def run_tests_endpoint(assignment_id: str, section_id: str, question_id: str, request: RunCodeRequest):
    """
    Run code against **all test cases**.
    Hidden test cases only show pass/fail. Pass results as `test_case_results`
    in CodingAnswer when submitting to avoid re-running Judge0 server-side.
    """
    return run_college_tests(
        assignment_id=assignment_id,
        section_id=section_id,
        question_id=question_id,
        language_id=request.language_id,
        source_code=request.source_code,
    )
