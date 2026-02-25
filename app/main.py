from fastapi import FastAPI
from app.routes.interview import router as interview_router
#from app.routes.video import router as video_router
from app.routes.resume_router import resume_router
from app.routes.challenges import router as challenges_router
app = FastAPI(
    title="ZealUp Mock Interview API",
    description="""
API for conducting AI-powered mock interviews.

Flow:
1. Start interview
2. Fetch generated questions
3. Submit all answers
4. Get detailed feedback
""",
    version="1.0.0"
)

app.include_router(interview_router, prefix="/api/interview")
# app.include_router(video_router, prefix="/api/video_interview")
app.include_router(resume_router, prefix="/api/resume")
app.include_router(challenges_router, prefix="/api/challenges")