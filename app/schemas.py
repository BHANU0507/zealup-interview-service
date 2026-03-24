from pydantic import BaseModel
from typing import List, Literal, Optional

class InterviewStartRequest(BaseModel):
    user_id: str
    role: str
    technologies: List[str]
    interview_type: Literal["text", "video"]
    difficulty: Literal["easy", "medium", "hard"]
    number_of_questions: int

class InterviewStartResponse(BaseModel):
    session_id: str
    status: str

class InterviewQuestion(BaseModel):
    question_id: str
    question_text: str

class QuestionListResponse(BaseModel):
    session_id: str
    questions: List[InterviewQuestion]

class AnswerItem(BaseModel):
    question_id: str
    answer_text: str

class InterviewAnswerSubmission(BaseModel):
    answers: List[AnswerItem]
    video_metrics: Optional[dict] = None
    violation_summary: Optional[dict] = None

class QuestionFeedback(BaseModel):
    question_id: str
    score: int
    strengths: List[str]
    weaknesses: List[str]
    ideal_answer: str
    improvement_tips: List[str]

class InterviewFeedbackResponse(BaseModel):
    session_id: str
    overall_score: int
    summary: str
    question_feedback: List[QuestionFeedback]
    behavioral_feedback: Optional[dict] = None


class UserInterviewCountResponse(BaseModel):
    user_id: str
    interview_count: int


class InterviewQuotaCheckRequest(BaseModel):
    user_id: str
    planType: Optional[str] = None
    status: Optional[str] = "ACTIVE"
    interviewsLimit: int
    planStartDate: str


class InterviewQuotaCheckResponse(BaseModel):
    user_id: str
    plan_type: str
    subscription_status: str
    period: str
    cycle_start: str
    renews_at: str
    interviews_limit: int
    used_interviews: int
    remaining_interviews: int
    can_start_interview: bool
    slot_consumed: bool
    message: str
