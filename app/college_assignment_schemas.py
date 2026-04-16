"""
Schemas for College Assignments.

Re-uses question/section/submission types from assignment_schemas.
Adds college_id, due_date, deadline (hard cutoff).
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime

# Re-export shared types so routes only need one import
from app.assignment_schemas import (
    AssignmentSection,
    CreateSectionRequest,
    UpdateSectionRequest,
    SectionResponse,
    SectionListResponse,
    QuestionType,
    AddQuestionRequest,
    CodingTestCaseResult,
    CodingAnswer,
    MultipleChoiceAnswer,
    FillInBlankAnswer,
    AnswerType,
    SectionSubmission,
)


# ---------------------------------------------------------------------------
# Admin create / update
# ---------------------------------------------------------------------------

class CreateCollegeAssignmentRequest(BaseModel):
    college_id: str                                          # Required — which college owns this
    college_name: Optional[str] = None                       # Human-readable college name
    title: str
    description: str
    created_by: str                                          # instructor / admin ID
    course_id: Optional[str] = None
    course_name: Optional[str] = None
    instructor_name: Optional[str] = None
    due_date: Optional[datetime] = None                     # Informational due date shown to students
    deadline: Optional[datetime] = None                     # Hard cutoff — reject submissions after this
    is_locked: Optional[bool] = False
    level: Optional[Literal["beginner", "intermediate", "advanced"]] = "intermediate"
    max_attempts: Optional[int] = None                      # None = unlimited
    tags: Optional[List[str]] = []
    instructions: Optional[str] = None


class UpdateCollegeAssignmentRequest(BaseModel):
    title: Optional[str] = None
    college_name: Optional[str] = None
    description: Optional[str] = None
    course_id: Optional[str] = None
    course_name: Optional[str] = None
    instructor_name: Optional[str] = None
    due_date: Optional[datetime] = None
    deadline: Optional[datetime] = None
    is_locked: Optional[bool] = None
    level: Optional[Literal["beginner", "intermediate", "advanced"]] = None
    max_attempts: Optional[int] = None
    tags: Optional[List[str]] = None
    instructions: Optional[str] = None


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

class CollegeAssignmentResponse(BaseModel):
    assignment_id: str
    status: str
    created_at: datetime
    total_points: int
    total_time_minutes: int
    section_count: int


class CollegeAssignmentDetailResponse(BaseModel):
    assignment_id: str
    college_id: str
    college_name: Optional[str]
    title: str
    description: str
    created_by: str
    course_id: Optional[str]
    course_name: Optional[str]
    instructor_name: Optional[str]
    sections: List[AssignmentSection]
    total_points: int
    total_time_minutes: int
    due_date: Optional[datetime]
    deadline: Optional[datetime]
    is_locked: bool
    level: str
    max_attempts: Optional[int]
    tags: List[str]
    instructions: Optional[str]
    created_at: datetime
    updated_at: datetime


class CollegeAssignmentListResponse(BaseModel):
    college_id: str
    assignments: List[dict]
    total_count: int


# ---------------------------------------------------------------------------
# Student submission — section-by-section (reuses AnswerType from base)
# ---------------------------------------------------------------------------

class SubmitCollegeSectionRequest(BaseModel):
    answers: List[AnswerType]
    time_taken_minutes: Optional[int] = 0


class FinalizeCollegeAssignmentRequest(BaseModel):
    user_name: Optional[str] = ""


# ---------------------------------------------------------------------------
# Admin submission views
# ---------------------------------------------------------------------------

class CollegeSubmissionSummary(BaseModel):
    user_id: str
    user_name: Optional[str]
    score: int
    total_points: int
    percentage: float
    submitted_at: str
    attempts_count: int


class CollegeAssignmentSubmissionsResponse(BaseModel):
    assignment_id: str
    college_id: str
    submissions: List[CollegeSubmissionSummary]
    total_submissions: int


class CollegeAssignmentStatsResponse(BaseModel):
    assignment_id: str
    college_id: str
    total_submissions: int
    average_score: float
    average_percentage: float
    pass_rate: float                   # percentage scoring >= 60 %
    highest_score: int
    lowest_score: int
