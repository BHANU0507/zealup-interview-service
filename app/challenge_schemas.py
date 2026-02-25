from pydantic import BaseModel
from typing import List, Literal, Optional


class TestCase(BaseModel):
    input: str
    expected_output: str
    is_hidden: Optional[bool] = False


class CreateChallengeRequest(BaseModel):
    title: str
    description: str
    challenge_type: Literal["coding", "aptitude"]
    difficulty: Literal["easy", "medium", "hard"]
    points: int
    tags: Optional[List[str]] = None
    created_by: Optional[str] = None

    # Aptitude fields
    question: Optional[str] = None
    options: Optional[List[str]] = None
    correct_answer: Optional[str] = None
    answer_explanation: Optional[str] = None

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


class ChallengeSummary(BaseModel):
    challenge_id: str
    title: str
    challenge_type: str
    difficulty: str
    points: int
    tags: List[str]
    created_at: int
    created_by: Optional[str] = None


class ChallengeListResponse(BaseModel):
    challenges: List[ChallengeSummary]
    next_key: Optional[str] = None


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

    # Aptitude
    question: Optional[str] = None
    options: Optional[List[str]] = None
    answer_explanation: Optional[str] = None

    # Coding
    default_code: Optional[str] = None
    sample_input: Optional[str] = None
    sample_input_explanation: Optional[str] = None
    sample_output: Optional[str] = None
    sample_output_explanation: Optional[str] = None
    hints: Optional[str] = None
    test_cases_count: Optional[int] = None


class ChallengeSubmitRequest(BaseModel):
    user_id: str
    selected_answer: Optional[str] = None
    language_id: Optional[int] = None
    source_code: Optional[str] = None


class ChallengeSubmitResponse(BaseModel):
    submission_id: str
    challenge_id: str
    status: str
    score: int
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


class ScoreboardEntry(BaseModel):
    user_id: str
    best_score: int
    submissions: int
    last_submission_at: int


class ScoreboardResponse(BaseModel):
    challenge_id: str
    entries: List[ScoreboardEntry]


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
    created_at: int


class UserSubmissionListResponse(BaseModel):
    user_id: str
    submissions: List[UserSubmissionSummary]
    next_key: Optional[str] = None
