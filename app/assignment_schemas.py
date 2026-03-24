from pydantic import BaseModel, Field
from typing import Annotated, Any, List, Optional, Union, Literal
from datetime import datetime


# Question Types
class TestCase(BaseModel):
    input: str
    expected_output: str
    points: int = Field(ge=0)
    is_hidden: Optional[bool] = False
    explanation: Optional[str] = None


class CodingQuestion(BaseModel):
    id: Optional[str] = None  # Auto-generated when omitted
    question_type: Literal["coding"] = "coding"
    title: str
    description: str
    default_code: Optional[str] = None
    sample_input: Optional[str] = None
    sample_output: Optional[str] = None
    test_cases: List[TestCase] = []
    points: int = Field(default=0, ge=0)
    time_limit_minutes: Optional[int] = None
    hints: Optional[str] = None


class Option(BaseModel):
    id: str
    text: str


class MultipleChoiceQuestion(BaseModel):
    id: Optional[str] = None  # Auto-generated when omitted
    question_type: Literal["multiple_choice"] = "multiple_choice"
    title: str
    description: str
    options: List[Option] = []
    correct_option_ids: List[str] = []  # Can be single or multiple for multi-select
    points: int = Field(default=0, ge=0)
    explanation: Optional[str] = None
    shuffle_options: Optional[bool] = False


class FillInBlankQuestion(BaseModel):
    id: Optional[str] = None  # Auto-generated when omitted
    question_type: Literal["fill_in_blank"] = "fill_in_blank"
    title: str
    description: str
    text_with_blanks: str  # Text with blanks marked as ___
    correct_answers: List[List[str]] = []  # Each blank can have multiple correct answers
    points: int = Field(default=0, ge=0)
    case_sensitive: Optional[bool] = False
    explanation: Optional[str] = None


# Union type for any question — uses Pydantic discriminator for precise parsing
QuestionType = Annotated[
    Union[CodingQuestion, MultipleChoiceQuestion, FillInBlankQuestion],
    Field(discriminator="question_type"),
]

# Alias used as the POST body for adding a single question
# (same discriminated union — client sends the native question shape)
AddQuestionRequest = QuestionType


# Section Schema - NEW
class AssignmentSection(BaseModel):
    section_id: str
    title: str
    description: Optional[str] = None
    questions: List[QuestionType]
    total_points: Optional[int] = None  # Auto-calculated from questions
    time_limit_minutes: Optional[int] = None  # Time limit for this section
    order: int = Field(default=1, ge=0)  # Section order in assignment
    instructions: Optional[str] = None


class CreateSectionRequest(BaseModel):
    title: str
    description: Optional[str] = None
    questions: List[QuestionType] = []
    time_limit_minutes: Optional[int] = None
    order: Optional[int] = None  # Auto-assigned if not provided
    instructions: Optional[str] = None


class UpdateSectionRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    questions: Optional[List[QuestionType]] = None
    time_limit_minutes: Optional[int] = None
    order: Optional[int] = None
    instructions: Optional[str] = None


class SectionResponse(BaseModel):
    section_id: str
    assignment_id: str
    status: str
    created_at: datetime
    total_points: int
    question_count: int


# Updated Assignment Schemas
class CreateAssignmentRequest(BaseModel):
    title: str
    course_id: Optional[str] = None
    course_name: Optional[str] = None
    description: str
    created_by: str  # instructor/admin ID
    instructor_name: Optional[str] = None
    # Removed direct questions - now handled via sections
    start_date: Optional[datetime] = None
    deadline: Optional[datetime] = None
    is_locked: Optional[bool] = False
    level: Optional[Literal["beginner", "intermediate", "advanced"]] = "intermediate"
    max_attempts: Optional[int] = None  # None = unlimited
    tags: Optional[List[str]] = []
    instructions: Optional[str] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class AssignmentResponse(BaseModel):
    assignment_id: str
    status: str
    created_at: datetime
    total_points: int
    total_time_minutes: int
    section_count: int


class UpdateAssignmentRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    course_id: Optional[str] = None
    course_name: Optional[str] = None
    instructor_name: Optional[str] = None
    start_date: Optional[datetime] = None
    deadline: Optional[datetime] = None
    is_locked: Optional[bool] = None
    level: Optional[Literal["beginner", "intermediate", "advanced"]] = None
    max_attempts: Optional[int] = None
    tags: Optional[List[str]] = None
    instructions: Optional[str] = None


class AssignmentListResponse(BaseModel):
    assignments: List[dict]
    total_count: int
    next_key: Optional[str] = None


class AssignmentDetailResponse(BaseModel):
    assignment_id: str
    title: str
    course_id: Optional[str]
    course_name: Optional[str]
    description: str
    created_by: str
    instructor_name: Optional[str]
    sections: List[AssignmentSection]  # Changed from questions to sections
    total_points: int
    total_time_minutes: int
    start_date: Optional[datetime]
    deadline: Optional[datetime]
    is_locked: bool
    level: str
    max_attempts: Optional[int]
    tags: List[str]
    instructions: Optional[str]
    created_at: datetime
    updated_at: datetime


# Section List Response
class SectionListResponse(BaseModel):
    assignment_id: str
    sections: List[dict]
    total_sections: int
    total_points: int
    total_time_minutes: int


# Submission Schemas (Updated for sections)
class CodingTestCaseResult(BaseModel):
    test_case_index: int
    passed: bool
    actual_output: Optional[str] = None
    status: Optional[str] = None        # e.g. "Accepted", "Wrong Answer", "Time Limit Exceeded"
    time: Optional[Any] = None          # Judge0 may return number or string
    memory: Optional[Any] = None        # Judge0 may return number or string


class CodingAnswer(BaseModel):
    question_id: str
    code: str
    language: Optional[str] = "python"
    test_case_results: Optional[List["CodingTestCaseResult"]] = None


class MultipleChoiceAnswer(BaseModel):
    question_id: str
    selected_option_ids: List[str]


class FillInBlankAnswer(BaseModel):
    question_id: str
    answers: List[str]  # One answer per blank


AnswerType = Union[CodingAnswer, MultipleChoiceAnswer, FillInBlankAnswer]


class SectionSubmission(BaseModel):
    section_id: str
    answers: List[AnswerType]


class SubmitAssignmentRequest(BaseModel):
    assignment_id: str
    user_id: str
    section_submissions: List[SectionSubmission]  # Changed to section-based


class AssignmentSubmissionResponse(BaseModel):
    submission_id: str
    assignment_id: str
    user_id: str
    score: int
    total_points: int
    percentage: float
    status: str
    submitted_at: datetime
    section_results: List[dict]  # Results per section


# Progress Tracking (Updated for sections)
class SectionProgress(BaseModel):
    section_id: str
    questions_completed: int
    total_questions: int
    score: int
    total_points: int
    time_spent_minutes: Optional[int]
    is_completed: bool


class AssignmentProgress(BaseModel):
    assignment_id: str
    user_id: str
    progress_percentage: float
    sections_completed: int
    total_sections: int
    section_progress: List[SectionProgress]
    total_score: int
    total_points: int
    attempts_used: int
    max_attempts: Optional[int]
    can_attempt: bool
    last_accessed: datetime
    total_time_spent_minutes: Optional[int]
    is_submitted: bool


# Additional Schemas
class ResetAttemptsRequest(BaseModel):
    assignment_id: str
    user_id: str
    reason: Optional[str] = None


class AssignmentStats(BaseModel):
    assignment_id: str
    total_students: int
    completed_submissions: int
    average_score: float
    highest_score: int
    lowest_score: int
    average_time_minutes: Optional[float]
    section_stats: List[dict]


# ── Pre-start overview (shown before student begins) ──────────────────────────

class PreStartSectionItem(BaseModel):
    section_id: str
    title: str
    description: Optional[str] = None
    question_count: int
    time_limit_minutes: int
    total_points: int
    order: int


class AssignmentPreStartResponse(BaseModel):
    assignment_id: str
    title: str
    description: str
    course_id: Optional[str] = None
    course_name: Optional[str] = None
    instructor_name: Optional[str] = None
    level: str
    # Top stat bar
    section_count: int
    question_count: int
    total_time_minutes: int
    total_points: int
    # Attempt info
    max_attempts: Optional[int]        # None = unlimited
    attempts_used: int                 # how many times this user has already submitted
    attempts_left: Optional[int]       # None = unlimited; 0 = no more attempts
    can_attempt: bool
    # Dates
    start_date: Optional[str] = None
    deadline: Optional[str] = None
    # Sections overview list
    sections: List[PreStartSectionItem]
    # Instructions bullet list (split by newline)
    instructions: Optional[str] = None
    instructions_list: List[str] = []
    tags: List[str] = []


# AddQuestionRequest is the QuestionType discriminated union (defined above).
# Clients send the native question body:
#
#  coding        -> { "question_type": "coding", "title": ..., "test_cases": [...], ... }
#  multiple_choice -> { "question_type": "multiple_choice", "options": [...], ... }
#  fill_in_blank  -> { "question_type": "fill_in_blank", "correct_answers": [[...]], ... }
#
# "id" is always optional — a unique question_id is generated server-side when absent.


class UpdateQuestionRequest(BaseModel):
    """All fields optional — send only what you want to change."""
    title: Optional[str] = None
    description: Optional[str] = None
    points: Optional[int] = Field(default=None, ge=0)
    order: Optional[int] = None
    # coding
    default_code: Optional[str] = None
    sample_input: Optional[str] = None
    sample_output: Optional[str] = None
    test_cases: Optional[List[TestCase]] = None
    time_limit_minutes: Optional[int] = None
    hints: Optional[str] = None
    # multiple_choice
    options: Optional[List[Option]] = None
    correct_option_ids: Optional[List[str]] = None
    explanation: Optional[str] = None
    shuffle_options: Optional[bool] = None
    # fill_in_blank
    text_with_blanks: Optional[str] = None
    correct_answers: Optional[List[List[str]]] = None
    case_sensitive: Optional[bool] = None


class QuestionAddedResponse(BaseModel):
    question_id: str
    section_id: str
    assignment_id: str
    status: str
    created_at: str


class QuestionListResponse(BaseModel):
    section_id: str
    assignment_id: str
    questions: List[dict]
    total_questions: int
    total_points: int


# ── User submission input ─────────────────────────────────────────────────────

class UserSubmitAssignmentRequest(BaseModel):
    """Payload sent by a user when submitting an assignment."""
    user_id: str
    user_name: Optional[str] = None
    time_taken_minutes: int = Field(default=0, ge=0)
    section_submissions: List[SectionSubmission]


# ── Section-wise submission ───────────────────────────────────────────────────

class SubmitSectionRequest(BaseModel):
    """Payload for submitting a single section's answers."""
    user_id: str
    time_taken_minutes: int = Field(default=0, ge=0)
    answers: List[AnswerType]


class SectionSubmissionResult(BaseModel):
    assignment_id: str
    section_id: str
    user_id: str
    score: int
    total_points: int
    percentage: float
    time_taken_minutes: int
    submitted_at: str
    question_results: List[dict]
    # How many sections are done vs total
    sections_submitted: int
    sections_total: int
    all_sections_done: bool
    # Populated only when all_sections_done=True
    final_submission: Optional["UserSubmissionResponse"] = None


class AssignmentProgressResponse(BaseModel):
    assignment_id: str
    user_id: str
    sections_total: int
    sections_submitted: int
    sections_pending: int
    all_sections_done: bool
    is_finalized: bool          # True if final assignment submission exists
    section_statuses: List[dict]  # [{section_id, title, submitted, score, ...}]
    total_score_so_far: int
    total_points: int


# ── Run code (live test execution) ──────────────────────────────────────────

class RunSampleRequest(BaseModel):
    """Payload for running code against a single custom input (scratchpad run)."""
    language_id: int = Field(..., description="Judge0 language ID (e.g. 71=Python, 63=JS, 62=Java, 54=C++, 50=C)")
    source_code: str
    stdin: Optional[str] = Field(default="", description="Custom stdin to feed to the program")


class RunSampleResponse(BaseModel):
    status: str                         # e.g. "Accepted", "Compilation Error", "Runtime Error"
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    compile_output: Optional[str] = None
    time: Optional[Any] = None          # Judge0 may return number or string
    memory: Optional[Any] = None        # Judge0 may return number or string


class RunCodeRequest(BaseModel):
    """Payload for running code against all test cases."""
    language_id: int = Field(..., description="Judge0 language ID (e.g. 71=Python, 63=JS, 62=Java, 54=C++, 50=C)")
    source_code: str


class RunCodeTestResult(BaseModel):
    index: int
    passed: bool
    status: str                         # e.g. "Accepted", "Wrong Answer", "Time Limit Exceeded"
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    compile_output: Optional[str] = None
    time: Optional[Any] = None          # Judge0 may return number or string
    memory: Optional[Any] = None        # Judge0 may return number or string
    is_hidden: bool = False
    # Only populated for visible test cases
    input: Optional[str] = None
    expected_output: Optional[str] = None


class RunCodeResponse(BaseModel):
    question_id: str
    status: str                         # "COMPLETED" or "JUDGE0_UNAVAILABLE"
    passed_count: int
    total_count: int
    points_earned: int
    total_points: int
    compile_output: Optional[str] = None
    results: List[RunCodeTestResult]


# ── User submission response ──────────────────────────────────────────────────

class QuestionResult(BaseModel):
    question_id: str
    question_type: Optional[str] = None
    is_correct: bool
    points_earned: int
    points_possible: int
    submitted_answer: Optional[dict] = None  # the answer the user submitted


class SectionResult(BaseModel):
    section_id: str
    section_title: str = ""
    score: int
    total_points: int
    question_results: List[QuestionResult]


class UserSubmissionResponse(BaseModel):
    assignment_id: str
    user_id: str
    user_name: Optional[str] = None
    score: int
    total_points: int
    percentage: float
    attempts_count: int
    time_taken_minutes: int
    submitted_at: str
    status: str
    section_results: List[dict]


class FinalizeSubmissionRequest(BaseModel):
    """Payload for the explicit finalize/complete endpoint."""
    user_id: str
    user_name: Optional[str] = None


# ── User assignments listing ──────────────────────────────────────────────────

class UserAssignmentItem(BaseModel):
    assignment_id: str
    title: str
    course_id: Optional[str] = None
    course_name: Optional[str] = None
    total_points: int = 0
    total_time_minutes: int = 0
    section_count: int = 0
    level: str = "intermediate"
    start_date: Optional[str] = None
    deadline: Optional[str] = None
    is_locked: bool = False
    # "to_do" | "upcoming" | "past" | "completed"
    status: str = "to_do"
    # User-specific progress
    has_submitted: bool = False
    user_score: Optional[int] = None
    user_percentage: Optional[float] = None
    attempts_count: int = 0
    time_taken_minutes: Optional[int] = None
    last_submitted_at: Optional[str] = None


class UserAssignmentsResponse(BaseModel):
    user_id: str
    total_count: int
    assignments: List[UserAssignmentItem]


class UserAssignmentCategoryResponse(BaseModel):
    user_id: str
    category: str
    total_count: int
    assignments: List[UserAssignmentItem]


class UserAssignmentsDashboardResponse(BaseModel):
    user_id: str
    to_do: List[UserAssignmentItem]       # unlocked, deadline not passed
    upcoming: List[UserAssignmentItem]    # locked (not yet released)
    past: List[UserAssignmentItem]        # deadline passed OR overdue
    completed: List[UserAssignmentItem]   # submitted and deadline passed
    total_count: int


# ── Enrolled courses (simple) ─────────────────────────────────────────────────

class AllSubmissionsResponse(BaseModel):
    assignment_id: str
    total_count: int
    submissions: List[UserSubmissionResponse]


class SimpleEnrolledCourseItem(BaseModel):
    course_id: str
    course_name: str


class SimpleEnrolledCoursesResponse(BaseModel):
    user_id: str
    total_count: int
    courses: List[SimpleEnrolledCourseItem]