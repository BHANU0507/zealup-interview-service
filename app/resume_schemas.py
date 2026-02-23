from pydantic import BaseModel, Field
from typing import Optional , List


class ResumeListItem(BaseModel):
    resume_id: str
    resume_name: str
    status: str
    created_at: int


class ResumeListResponse(BaseModel):
    user_id: str
    resumes: List[ResumeListItem]


class CreateResumeRequest(BaseModel):
    user_id: str = Field(..., example="12e5a565-10de-4daf-b96d-90158542b0f3")
    resume_name: str = Field(..., example="Backend Developer - Amazon")
    tenant_id: str = Field(..., example="public")
    role: Optional[str] = Field(None, example="STUDENT")
    emailOrPhone: Optional[str] = Field(None, example="thudibhanuprasad4@gmail.com")



class CreateResumeResponse(BaseModel):
    resume_id: str
    resume_name: str
    status: str
    created_at: int


class ResumeAIRequest(BaseModel):
    user_id: str
    resume_id: str
    target_job_description: str | None = None
    user_description: str | None = None