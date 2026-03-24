from typing import Annotated, Optional
from fastapi import APIRouter, Body, HTTPException, Query

from app.assignment_schemas import (
    CreateAssignmentRequest,
    AssignmentResponse,
    RunSampleRequest,
    RunSampleResponse,
    RunCodeRequest,
    RunCodeResponse,
    FinalizeSubmissionRequest,
    UpdateAssignmentRequest,
    AssignmentListResponse,
    AssignmentDetailResponse,
    UserSubmitAssignmentRequest,
    UserSubmissionResponse,
    AllSubmissionsResponse,
    SubmitSectionRequest,
    SectionSubmissionResult,
    AssignmentProgressResponse,
    ResetAttemptsRequest,
    AssignmentStats,
    AssignmentPreStartResponse,
    CreateSectionRequest,
    UpdateSectionRequest,
    SectionResponse,
    SectionListResponse,
    UserAssignmentsResponse,
    UserAssignmentsDashboardResponse,
    UserAssignmentCategoryResponse,
    AddQuestionRequest,
    UpdateQuestionRequest,
    QuestionAddedResponse,
    QuestionListResponse,
)
from app.services.assignment_service import (
    create_assignment,
    get_assignment,
    update_assignment,
    delete_assignment,
    list_assignments,
    check_assignment_availability,
    get_assignment_prestart,
    get_assignment_stats,
    create_section,
    get_section,
    update_section,
    delete_section,
    list_sections,
    submit_assignment_for_user,
    submit_section_for_user,
    get_assignment_progress,
    get_user_submission,
    get_all_submissions,
    get_user_assignments,
    get_user_assignments_dashboard,
    get_user_assignments_by_category,
    add_question_to_section,
    get_question_item,
    list_section_questions_from_db,
    update_question_item,
    delete_question_item,
    run_assignment_code,
    run_assignment_sample,
    finalize_assignment_submission,
)

router = APIRouter()


@router.post("/", response_model=AssignmentResponse)
def create_assignment_endpoint(request: CreateAssignmentRequest):
    """
    Create a new assignment (sections and questions added separately).
    
    Features:
    - Create assignment with basic info
    - Add sections with mixed question types afterwards
    - Course association 
    - Time limits and deadlines
    - Lock/unlock functionality
    - Configurable attempt limits
    - Multiple difficulty levels
    """
    return create_assignment(request.dict())


# ===== SECTION MANAGEMENT ENDPOINTS =====

@router.post("/{assignment_id}/sections", response_model=SectionResponse)
def create_section_endpoint(assignment_id: str, request: CreateSectionRequest):
    """
    Create a new section within an assignment.
    
    Features:
    - Add questions to the section
    - Automatic point calculation from questions
    - Section-level time limits
    - Automatic ordering
    - Instructions per section
    """
    request_dict = request.dict()
    request_dict["assignment_id"] = assignment_id
    return create_section(request_dict)


@router.get("/{assignment_id}/sections", response_model=SectionListResponse)
def list_sections_endpoint(assignment_id: str):
    """
    List all sections for an assignment.
    
    Returns:
    - Sections ordered by their order field
    - Total points across all sections
    - Total time across all sections
    - Question counts per section
    """
    return list_sections(assignment_id)


@router.get("/{assignment_id}/sections/{section_id}")
def get_section_endpoint(assignment_id: str, section_id: str):
    """Get detailed section information including all questions"""
    section = get_section(section_id)
    if section.get("assignment_id") != assignment_id:
        raise HTTPException(status_code=404, detail="Section not found in this assignment")
    return section


@router.put("/{assignment_id}/sections/{section_id}")
def update_section_endpoint(assignment_id: str, section_id: str, request: UpdateSectionRequest):
    """
    Update section details, questions, or settings.
    
    Features:
    - Update questions and recalculate points
    - Change section order
    - Update time limits
    - Modify instructions
    """
    section = get_section(section_id)
    if section.get("assignment_id") != assignment_id:
        raise HTTPException(status_code=404, detail="Section not found in this assignment")
    return update_section(section_id, request.dict(exclude_unset=True))


@router.delete("/{assignment_id}/sections/{section_id}")
def delete_section_endpoint(assignment_id: str, section_id: str):
    """Delete a section from an assignment"""
    section = get_section(section_id)
    if section.get("assignment_id") != assignment_id:
        raise HTTPException(status_code=404, detail="Section not found in this assignment")
    return delete_section(section_id)


# ── Per-section question CRUD ────────────────────────────────────────────

@router.post(
    "/{assignment_id}/sections/{section_id}/questions",
    response_model=QuestionAddedResponse,
)
def add_question_endpoint(
    assignment_id: str,
    section_id: str,
    request: Annotated[AddQuestionRequest, Body()],
):
    """
    Add a single question to a section.

    Send the native question body — the shape is determined by **question_type**:

    **coding**
    ```json
    {
      "question_type": "coding",
      "title": "Fibonacci",
      "description": "...",
      "points": 35,
      "test_cases": [{"input": "5", "expected_output": "5", "points": 10}],
      "default_code": "def fib(n): pass",
      "hints": "..."
    }
    ```

    **multiple_choice**
    ```json
    {
      "question_type": "multiple_choice",
      "title": "Mutable types",
      "description": "...",
      "points": 20,
      "options": [{"id": "opt1", "text": "List"}, ...],
      "correct_option_ids": ["opt1", "opt3"],
      "shuffle_options": true
    }
    ```

    **fill_in_blank**
    ```json
    {
      "question_type": "fill_in_blank",
      "title": "Python Keywords",
      "description": "...",
      "points": 16,
      "text_with_blanks": "Use _____ to define a function.",
      "correct_answers": [["def"]],
      "case_sensitive": false
    }
    ```

    `id` is always optional — a unique `question_id` is generated when absent.
    Section and assignment `total_points` are recalculated automatically.
    """
    q_dict = request.dict() if hasattr(request, "dict") else request.model_dump()
    return add_question_to_section(section_id, assignment_id, q_dict)


@router.get(
    "/{assignment_id}/sections/{section_id}/questions",
    response_model=QuestionListResponse,
)
def list_questions_endpoint(assignment_id: str, section_id: str):
    """
    List all questions in a section.

    Returns questions sorted by their order field, with total points.
    Questions created via the section body (legacy) are also returned.
    """
    return list_section_questions_from_db(section_id, assignment_id)


@router.get("/{assignment_id}/sections/{section_id}/questions/{question_id}")
def get_question_endpoint(assignment_id: str, section_id: str, question_id: str):
    """Get a single question by ID."""
    q = get_question_item(section_id, question_id)
    if q.get("assignment_id") != assignment_id:
        raise HTTPException(status_code=404, detail="Question not found in this assignment")
    return q


@router.put("/{assignment_id}/sections/{section_id}/questions/{question_id}")
def update_question_endpoint(
    assignment_id: str,
    section_id: str,
    question_id: str,
    request: UpdateQuestionRequest,
):
    """
    Update a question.

    Send only the fields you want to change — all other fields remain untouched.
    Changing points automatically resyncs the section and assignment totals.
    """
    q = get_question_item(section_id, question_id)
    if q.get("assignment_id") != assignment_id:
        raise HTTPException(status_code=404, detail="Question not found in this assignment")
    return update_question_item(section_id, question_id, request.dict(exclude_unset=True))


@router.delete("/{assignment_id}/sections/{section_id}/questions/{question_id}")
def delete_question_endpoint(
    assignment_id: str, section_id: str, question_id: str
):
    """
    Delete a question from a section.

    Section and assignment point totals are recalculated automatically.
    """
    q = get_question_item(section_id, question_id)
    if q.get("assignment_id") != assignment_id:
        raise HTTPException(status_code=404, detail="Question not found in this assignment")
    return delete_question_item(section_id, question_id)


# ===== ASSIGNMENT MANAGEMENT ENDPOINTS ===== 


@router.get("/{assignment_id}", response_model=AssignmentDetailResponse)
def get_assignment_endpoint(assignment_id: str):
    """Get detailed assignment information including all questions"""
    return get_assignment(assignment_id)


@router.put("/{assignment_id}")
def update_assignment_endpoint(assignment_id: str, request: UpdateAssignmentRequest):
    """Update assignment details, questions, or settings"""
    return update_assignment(assignment_id, request.dict(exclude_unset=True))


@router.delete("/{assignment_id}")
def delete_assignment_endpoint(assignment_id: str):
    """Delete an assignment (instructor/admin only)"""
    return delete_assignment(assignment_id)


@router.get("/", response_model=AssignmentListResponse)
def list_assignments_endpoint(
    course_id: Optional[str] = Query(None, description="Filter by course ID"),
    created_by: Optional[str] = Query(None, description="Filter by instructor/creator"),
    level: Optional[str] = Query(None, description="Filter by difficulty level"),
    is_locked: Optional[bool] = Query(None, description="Filter by lock status"),
    limit: int = Query(20, ge=1, le=100, description="Number of results to return"),
    next_key: Optional[str] = Query(None, description="Pagination key for next page")
):
    """
    List assignments with filtering and pagination.
    
    Filters available:
    - course_id: Show assignments for specific course
    - created_by: Show assignments by specific instructor
    - level: beginner, intermediate, advanced  
    - is_locked: true/false for availability
    """
    return list_assignments(
        course_id=course_id,
        created_by=created_by,
        level=level,
        is_locked=is_locked,
        limit=limit,
        next_key=next_key
    )


@router.get("/{assignment_id}/availability")
def check_assignment_availability_endpoint(assignment_id: str):
    """
    Check if assignment is available for students to take.
    
    Checks:
    - Assignment is not locked
    - Assignment has started (past start_date)
    - Assignment deadline has not passed
    """
    return check_assignment_availability(assignment_id)


@router.get("/{assignment_id}/prestart", response_model=AssignmentPreStartResponse)
def get_assignment_prestart_endpoint(assignment_id: str, user_id: str = Query(..., description="The student's user ID")):
    """
    Pre-start overview page — all metadata a student needs before beginning.

    Returns:
    - **section_count / question_count / total_time_minutes / total_points** — top stat bar
    - **attempts_left / attempts_used / can_attempt** — attempt tracking per user
    - **sections** — list of sections with title, description, questions, time, points
    - **instructions_list** — instructions split into bullet points
    - **deadline / start_date** — displayed in the footer
    """
    return get_assignment_prestart(assignment_id, user_id)


@router.get("/{assignment_id}/stats", response_model=AssignmentStats)
def get_assignment_stats_endpoint(assignment_id: str):
    """
    Get assignment statistics and analytics.
    
    Returns:
    - Total students who attempted
    - Completion rate
    - Score statistics (avg, highest, lowest)
    - Time statistics
    """
    return get_assignment_stats(assignment_id)



# ── Section-wise submission endpoints ────────────────────────────────────────

@router.post(
    "/{assignment_id}/sections/{section_id}/questions/{question_id}/run",
    response_model=RunSampleResponse,
)
def run_sample_endpoint(assignment_id: str, section_id: str, question_id: str, request: RunSampleRequest):
    """
    Run code with a **single custom input** (scratchpad).

    - Executes the code with whatever `stdin` you provide.
    - Does **not** compare against test cases — just returns the raw output.
    - Use this so the user can quickly check their logic during coding.
    """
    return run_assignment_sample(
        assignment_id=assignment_id,
        section_id=section_id,
        question_id=question_id,
        language_id=request.language_id,
        source_code=request.source_code,
        stdin=request.stdin or "",
    )


@router.post(
    "/{assignment_id}/sections/{section_id}/questions/{question_id}/run-tests",
    response_model=RunCodeResponse,
)
def run_tests_endpoint(assignment_id: str, section_id: str, question_id: str, request: RunCodeRequest):
    """
    Run code against **all test cases**.

    - Executes code via Judge0 for every test case and returns per-case pass/fail.
    - **Visible** test cases include `input` and `expected_output` in the response.
    - **Hidden** test cases only show pass/fail (no input/expected exposed).
    - Use `points_earned` / `total_points` to show the user their live score.
    - When satisfied, send these results as `test_case_results` in `CodingAnswer`
      when submitting the section — the backend uses them directly to award points.
    """
    return run_assignment_code(
        assignment_id=assignment_id,
        section_id=section_id,
        question_id=question_id,
        language_id=request.language_id,
        source_code=request.source_code,
    )


@router.post("/{assignment_id}/sections/{section_id}/submit", response_model=SectionSubmissionResult)
def submit_section_endpoint(assignment_id: str, section_id: str, request: SubmitSectionRequest):
    """
    Submit answers for a **single section**.

    - Grades the section immediately and stores the result.
    - When **all sections** are submitted, the full assignment submission is
      **automatically finalized** (score, percentage, attempts updated).
    - Re-submitting a section overwrites the previous section result.
    - `all_sections_done=true` + `final_submission` in the response means the
      assignment is fully submitted.
    """
    return submit_section_for_user(
        user_id=request.user_id,
        assignment_id=assignment_id,
        section_id=section_id,
        payload=request.dict(),
    )


@router.get("/{assignment_id}/progress/{user_id}", response_model=AssignmentProgressResponse)
def get_assignment_progress_endpoint(assignment_id: str, user_id: str):
    """
    Get a student's section-by-section progress for an assignment.

    Shows which sections are submitted, scores so far, and whether the
    full assignment has been finalized.
    """
    return get_assignment_progress(user_id, assignment_id)


# ── User-facing submission endpoints ─────────────────────────────────────────

@router.post("/{assignment_id}/finalize", response_model=UserSubmissionResponse)
def finalize_assignment_endpoint(assignment_id: str, request: FinalizeSubmissionRequest):
    """
    Finalize an assignment after all sections have been submitted.

    Call this once the user has submitted every section via the section-submit API.
    - Aggregates scores and time taken from all section submissions.
    - Saves the final submission record (overwrites any incomplete one).
    - Returns the complete result with total score, percentage, and per-section breakdown.

    Returns **400** if any section has not been submitted yet.
    """
    return finalize_assignment_submission(
        user_id=request.user_id,
        assignment_id=assignment_id,
        user_name=request.user_name or "",
    )


@router.post("/{assignment_id}/submit", response_model=UserSubmissionResponse)
def submit_assignment_endpoint(assignment_id: str, request: UserSubmitAssignmentRequest):
    """
    Submit assignment answers.

    - Grades MCQ and fill-in-blank answers automatically.
    - Grades coding questions via Judge0 (if configured).
    - Only the **latest** submission is stored per user — previous results are
      overwritten. The attempt counter increments on every submission.
    - Returns score, percentage, per-question results, and attempt count.
    """
    return submit_assignment_for_user(
        user_id=request.user_id,
        assignment_id=assignment_id,
        payload=request.dict(),
    )


@router.get("/{assignment_id}/submissions", response_model=AllSubmissionsResponse)
def get_all_submissions_endpoint(assignment_id: str):
    """
    Get all user submissions for a specific assignment.

    Returns every user's latest submission, sorted by submitted_at descending.
    """
    return get_all_submissions(assignment_id)


@router.get("/{assignment_id}/submission/{user_id}", response_model=UserSubmissionResponse)
def get_user_submission_endpoint(assignment_id: str, user_id: str):
    """
    Get a specific user's latest submission for an assignment.

    Returns score, percentage, time taken, attempts count, and per-section results.
    """
    return get_user_submission(user_id, assignment_id)


# ── User listing endpoint ─────────────────────────────────────────────────────

@router.get("/users/{user_id}/assignments/to-do", response_model=UserAssignmentCategoryResponse)
def get_user_assignments_todo_endpoint(user_id: str):
    """Unlocked assignments with deadline not yet passed — open for submission."""
    return get_user_assignments_by_category(user_id, "to_do")


@router.get("/users/{user_id}/assignments/upcoming", response_model=UserAssignmentCategoryResponse)
def get_user_assignments_upcoming_endpoint(user_id: str):
    """Locked assignments — not yet released by the instructor."""
    return get_user_assignments_by_category(user_id, "upcoming")


@router.get("/users/{user_id}/assignments/past", response_model=UserAssignmentCategoryResponse)
def get_user_assignments_past_endpoint(user_id: str):
    """Assignments whose deadline has passed and the user did NOT submit."""
    return get_user_assignments_by_category(user_id, "past")


@router.get("/users/{user_id}/assignments/completed", response_model=UserAssignmentCategoryResponse)
def get_user_assignments_completed_endpoint(user_id: str):
    """Assignments the user submitted (deadline passed)."""
    return get_user_assignments_by_category(user_id, "completed")


@router.get("/users/{user_id}/assignments/dashboard", response_model=UserAssignmentsDashboardResponse)
def get_user_assignments_dashboard_endpoint(user_id: str):
    """
    Student dashboard view — assignments grouped by category:
    - **to_do**: unlocked, deadline not yet passed (open for submission)
    - **upcoming**: locked (not yet released by instructor)
    - **past**: deadline passed, user did NOT submit (missed)
    - **completed**: deadline passed AND user submitted

    Only includes assignments from courses the user is enrolled in.
    Sorted: to_do/upcoming by deadline ascending, past/completed by most recent first.
    """
    return get_user_assignments_dashboard(user_id)


@router.get("/users/{user_id}/assignments", response_model=UserAssignmentsResponse)
def get_user_assignments_endpoint(user_id: str):
    """
    Return all assignments that belong to the courses a user is enrolled in.

    Each assignment is enriched with the user's own progress:
    - user_score / user_percentage  – points and % earned on latest submission
    - attempts_count                – how many times the user has submitted
    - time_taken_minutes            – time spent on latest submission
    - last_submitted_at             – when the latest submission was made
    - has_submitted                 – False if the user hasn't attempted yet
    """
    return get_user_assignments(user_id)


# ── Admin / instructor management ────────────────────────────────────────────

@router.post("/{assignment_id}/reset-attempts")
def reset_user_attempts_endpoint(request: ResetAttemptsRequest):
    """Reset user's attempt count (instructor only) — not yet implemented."""
    raise HTTPException(status_code=501, detail="Reset attempts endpoint not yet implemented")


@router.get("/{assignment_id}/leaderboard")
def get_assignment_leaderboard_endpoint(assignment_id: str):
    """Get assignment leaderboard/scoreboard"""
    # TODO: Implement leaderboard functionality
    raise HTTPException(status_code=501, detail="Leaderboard endpoint not yet implemented")


@router.post("/{assignment_id}/duplicate")
def duplicate_assignment_endpoint(assignment_id: str, title: Optional[str] = None):
    """Duplicate an assignment with optional new title"""
    # TODO: Implement assignment duplication
    raise HTTPException(status_code=501, detail="Duplicate assignment endpoint not yet implemented")


@router.get("/courses/{course_id}")
def get_course_assignments_endpoint(course_id: str):
    """Get all assignments for a specific course"""
    return list_assignments(course_id=course_id)


@router.get("/instructors/{instructor_id}")
def get_instructor_assignments_endpoint(instructor_id: str):
    """Get all assignments created by specific instructor"""
    return list_assignments(created_by=instructor_id)