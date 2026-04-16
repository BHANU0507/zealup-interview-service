from pydantic import BaseModel
from typing import List, Literal, Optional


class TestCase(BaseModel):
    input: str
    expected_output: str
    points: int
    is_hidden: Optional[bool] = False
    explanation: Optional[str] = None


class AptitudeQuestion(BaseModel):
    text: str
    options: List[str]
    correct_answers: List[str]  # Can be single or multiple
    points: int
    explanation: Optional[str] = None


class AptitudeSection(BaseModel):
    name: str
    description: Optional[str] = None
    questions: List[AptitudeQuestion]


class CreateChallengeRequest(BaseModel):
    title: str
    description: str
    challenge_type: Literal["coding", "aptitude"]
    difficulty: Literal["easy", "medium", "hard"]
    points: Optional[int] = None  # Auto-calculated from test cases for coding challenges
    tags: Optional[List[str]] = None
    created_by: Optional[str] = None
    college_id: Optional[str] = None  # Set if created by a college student
    time_limit_minutes: Optional[int] = None  # For aptitude challenges

    # Aptitude fields (old format - single question)
    question: Optional[str] = None
    options: Optional[List[str]] = None
    correct_answer: Optional[str] = None
    answer_explanation: Optional[str] = None

    # Aptitude fields (new format - multiple sections with questions)
    sections: Optional[List[AptitudeSection]] = None

    # Coding fields
    default_code: Optional[str] = None
    sample_input: Optional[str] = None
    sample_input_explanation: Optional[str] = None
    sample_output: Optional[str] = None
    sample_output_explanation: Optional[str] = None
    hints: Optional[str] = None
    test_cases: Optional[List[TestCase]] = None


class CreateChallengeResponse(BaseModel):
    challenge_id: str
    status: str
    created_at: int


class UpdateChallengeRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    difficulty: Optional[Literal["easy", "medium", "hard"]] = None
    points: Optional[int] = None
    tags: Optional[List[str]] = None
    time_limit_minutes: Optional[int] = None

    # Aptitude fields
    question: Optional[str] = None
    options: Optional[List[str]] = None
    correct_answer: Optional[str] = None
    answer_explanation: Optional[str] = None
    sections: Optional[List[AptitudeSection]] = None

    # Coding fields
    default_code: Optional[str] = None
    sample_input: Optional[str] = None
    sample_input_explanation: Optional[str] = None
    sample_output: Optional[str] = None
    sample_output_explanation: Optional[str] = None
    hints: Optional[str] = None
    test_cases: Optional[List[TestCase]] = None


class UpdateChallengeResponse(BaseModel):
    challenge_id: str
    status: str
    updated_at: int


class BulkDeleteRequest(BaseModel):
    challenge_ids: List[str]


class BulkDeleteResponse(BaseModel):
    deleted_count: int
    failed_count: int
    deleted_ids: List[str]
    failed_ids: List[str]
    errors: Optional[List[dict]] = None


class ChallengeSummary(BaseModel):
    challenge_id: str
    title: str
    challenge_type: str
    difficulty: str
    points: int
    tags: List[str]
    created_at: int
    created_by: Optional[str] = None
    college_id: Optional[str] = None
    solved: Optional[bool] = None
    user_score: Optional[int] = None
    time_taken_seconds: Optional[int] = None


class ChallengeListResponse(BaseModel):
    challenges: List[ChallengeSummary]
    next_key: Optional[str] = None
    total_solved: Optional[int] = None


class ChallengeDetailResponse(BaseModel):
    challenge_id: str
    title: str
    description: str
    challenge_type: str
    difficulty: str
    points: int
    tags: List[str]
    created_at: int
    created_by: Optional[str] = None
    solved: Optional[bool] = None
    time_limit_minutes: Optional[int] = None

    # Aptitude
    question: Optional[str] = None
    options: Optional[List[str]] = None
    answer_explanation: Optional[str] = None
    sections: Optional[List[AptitudeSection]] = None

    # Coding
    default_code: Optional[str] = None
    sample_input: Optional[str] = None
    sample_input_explanation: Optional[str] = None
    sample_output: Optional[str] = None
    sample_output_explanation: Optional[str] = None
    hints: Optional[str] = None
    test_cases_count: Optional[int] = None
    visible_test_cases: Optional[List[TestCase]] = None
    hidden_test_cases: Optional[List[TestCase]] = None


class QuestionAnswer(BaseModel):
    question_index: int
    selected_answers: List[str]  # Can be single or multiple


class SectionAnswers(BaseModel):
    section_index: int
    question_answers: List[QuestionAnswer]


class ChallengeSubmitRequest(BaseModel):
    user_id: str
    college_id: Optional[str] = None  # Set if the submitting user is a college student
    selected_answer: Optional[str] = None  # For single-question aptitude
    language_id: Optional[int] = None
    source_code: Optional[str] = None
    section_answers: Optional[List[SectionAnswers]] = None  # For multi-section aptitude
    time_taken_seconds: Optional[int] = None


class ChallengeSubmitResponse(BaseModel):
    submission_id: str
    challenge_id: str
    status: str
    score: int
    passed_count: Optional[int] = None
    total_count: Optional[int] = None
    results: Optional[List[dict]] = None
    time_taken_seconds: Optional[int] = None


class SubmissionDetailResponse(BaseModel):
    submission_id: str
    challenge_id: str
    challenge_title: Optional[str] = None
    challenge_type: str
    user_id: str
    score: int
    created_at: int
    
    # Aptitude
    selected_answer: Optional[str] = None
    is_correct: Optional[bool] = None
    section_answers: Optional[List[SectionAnswers]] = None
    time_taken_seconds: Optional[int] = None
    
    # Coding
    language_id: Optional[int] = None
    source_code: Optional[str] = None
    passed_count: Optional[int] = None
    total_count: Optional[int] = None
    results: Optional[List[dict]] = None


class RunCodeRequest(BaseModel):
    language_id: int
    source_code: str
    stdin: Optional[str] = None


class RunCodeResponse(BaseModel):
    status: str
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    compile_output: Optional[str] = None
    time: Optional[str] = None
    memory: Optional[int] = None


class RunTestsRequest(BaseModel):
    language_id: int
    source_code: str


class RunTestsResponse(BaseModel):
    status: str
    passed_count: int
    total_count: int
    score: int
    total_points: int
    compile_output: Optional[str] = None
    results: List[dict]


class ScoreboardEntry(BaseModel):
    user_id: str
    best_score: int
    submissions: int
    last_submission_at: int


class ScoreboardResponse(BaseModel):
    challenge_id: str
    entries: List[ScoreboardEntry]


class CollegeRankResponse(BaseModel):
    user_id: str
    college_id: str
    rank: int
    total_score: int
    total_users: int


class GlobalRankResponse(BaseModel):
    user_id: str
    rank: int
    total_score: int
    total_users: int


class UserSubmissionSummary(BaseModel):
    submission_id: str
    challenge_id: str
    challenge_title: Optional[str] = None
    challenge_type: str
    score: int
    passed_count: Optional[int] = None
    total_count: Optional[int] = None
    language_id: Optional[int] = None
    selected_answer: Optional[str] = None
    is_correct: Optional[bool] = None
    time_taken_seconds: Optional[int] = None
    created_at: int


class UserSubmissionListResponse(BaseModel):
    user_id: str
    submissions: List[UserSubmissionSummary]
    next_key: Optional[str] = None
