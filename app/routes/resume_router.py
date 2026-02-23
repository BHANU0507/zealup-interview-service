from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from app.resume_schemas import CreateResumeRequest, CreateResumeResponse, ResumeListResponse, ResumeAIRequest
from app.services.resume_service import create_resume_draft , get_user_resumes ,save_resume_data ,fetch_resume
from app.services.resume_ai_service import optimize_resume_with_ai
from app.services.resume_render_service import render_resume_html
from app.services.pdf_service import generate_pdf
from app.services.profile_service import fetch_profile_photo

resume_router = APIRouter()


@resume_router.post("/new", response_model=CreateResumeResponse)
def create_new_resume(request: CreateResumeRequest):
    try:
        return create_resume_draft(
            user_id=request.user_id,
            resume_name=request.resume_name,
            tenant_id=request.tenant_id,
            role=request.role,
            email_or_phone=request.emailOrPhone
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    

@resume_router.get("/user/{user_id}", response_model=ResumeListResponse)
def list_user_resumes(user_id: str):
    return get_user_resumes(user_id)


@resume_router.put("/{resume_id}/save")
def save_resume(resume_id: str, payload: dict):

    user_id = payload.get("userId")

    if not user_id:
        raise HTTPException(status_code=400, detail="userId required")

    return save_resume_data(user_id, resume_id, payload)


@resume_router.get("/{user_id}/{resume_id}")
def get_resume(user_id: str, resume_id: str):
    return fetch_resume(user_id, resume_id)


@resume_router.post("/ask-ai")
def ask_ai_resume_optimizer(request: ResumeAIRequest):
    return optimize_resume_with_ai(
        user_id=request.user_id,
        resume_id=request.resume_id,
        user_description =request.user_description,
        target_jd=request.target_job_description

    )


@resume_router.get("/{user_id}/{resume_id}/download/pdf")
def download_resume_pdf(user_id: str, resume_id: str, request: Request):
    """
    Download resume as PDF file
    
    Args:
        user_id: User ID
        resume_id: Resume ID
        
    Returns:
        PDF file response for download
    """
    try:
        # Available templates
        AVAILABLE_TEMPLATES = {
            "classic-latex",
            "professional-blue",
            "centered-classic",
            "minimal"
        }
        
        # Fetch resume from database
        resume_response = fetch_resume(user_id, resume_id)
        
        if not resume_response:
            raise HTTPException(status_code=404, detail="Resume not found")
        
        resume_data = resume_response.get("resume_data", {})
        resume_name = resume_data.get("name") or resume_data.get("personal", {}).get("fullName") or "resume"
        
        # Extract template name from resume data, default to classic-latex
        template_name = resume_data.get("template", "classic-latex").lower()
        
        # Validate template exists
        if template_name not in AVAILABLE_TEMPLATES:
            template_name = "classic-latex"
        
        # Fetch profile photo if needed. Forward Authorization and resume fields.
        profile_image = None
        if resume_data.get("includeProfileImage"):
            auth_header = request.headers.get("authorization") or request.headers.get("Authorization")

            tenant_id = (
                resume_data.get("tenantId")
                or resume_data.get("tenant_id")
                or resume_data.get("tenant")
            )
            role = resume_data.get("role")
            email_or_phone = (
                resume_data.get("emailOrPhone")
                or resume_data.get("email")
                or resume_data.get("emailOrPhone")
            )

            profile_image = fetch_profile_photo(
                user_id,
                tenant_id=tenant_id,
                role=role,
                email_or_phone=email_or_phone,
                auth_token=auth_header,
            )
        
        # Render HTML from selected template with resume data
        html_content = render_resume_html(
            template_name=template_name,
            resume_data=resume_data,
            profile_image=profile_image
        )
        
        # Generate PDF from HTML
        pdf_bytes = generate_pdf(html_content)
        
        # Return as downloadable file
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={resume_name}.pdf"
            }
        )
    
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {str(e)}")



