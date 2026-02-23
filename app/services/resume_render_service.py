from jinja2 import Environment, FileSystemLoader, TemplateNotFound
import os


def normalize_resume_data(resume_data: dict) -> dict:
    """
    Normalize resume data to template-compatible format
    Handles both nested and flat data structures
    """
    normalized = dict(resume_data)
    
    # Ensure personal section exists (handle both personal and personalInfo)
    if "personal" not in normalized and "personalInfo" in normalized:
        normalized["personal"] = normalized["personalInfo"]
    elif "personal" not in normalized:
        normalized["personal"] = {
            "fullName": resume_data.get("fullName") or resume_data.get("name"),
            "email": resume_data.get("email"),
            "phone": resume_data.get("phone"),
            "location": resume_data.get("location"),
            "linkedin": resume_data.get("linkedin"),
            "website": resume_data.get("website"),
            "profession": resume_data.get("profession")
        }
    
    # Ensure personalInfo also exists for backward compatibility
    if "personalInfo" not in normalized:
        normalized["personalInfo"] = normalized.get("personal", {})
    
    # Normalize experience
    if "experience" in normalized and isinstance(normalized["experience"], list):
        normalized["experience"] = [
            {
                "jobTitle": exp.get("jobTitle") or exp.get("position") or exp.get("title"),
                "company": exp.get("company") or exp.get("employer"),
                "startDate": exp.get("startDate") or exp.get("start"),
                "endDate": exp.get("endDate") or exp.get("end"),
                "currentlyWorking": exp.get("currentlyWorking", False),
                "description": exp.get("description") or exp.get("details")
            }
            for exp in normalized["experience"]
        ]
    
    # Normalize education
    if "education" in normalized and isinstance(normalized["education"], list):
        normalized["education"] = [
            {
                "degree": edu.get("degree") or edu.get("qualification"),
                "institution": edu.get("institution") or edu.get("school") or edu.get("university"),
                "startDate": edu.get("startDate") or edu.get("start"),
                "endDate": edu.get("endDate") or edu.get("end"),
                "graduationYear": edu.get("graduationYear") or edu.get("year") or edu.get("endDate"),
                "gpa": edu.get("gpa"),
                "details": edu.get("details"),
                "currentlyStudying": edu.get("currentlyStudying", False)
            }
            for edu in normalized["education"]
        ]
    
    # Handle skills - support both skill.technical and technicalSkills structures
    if "skill" in normalized and isinstance(normalized["skill"], dict):
        if "technical" in normalized["skill"] and isinstance(normalized["skill"]["technical"], list):
            # Normalize technical skills: map subheading to category
            normalized["skill"]["technical"] = [
                {
                    "category": skill.get("category") or skill.get("subheading"),
                    "skills": skill.get("skills", []),
                    "id": skill.get("id")
                }
                for skill in normalized["skill"]["technical"]
            ]
            if not normalized.get("technicalSkills"):
                normalized["technicalSkills"] = normalized["skill"]["technical"]
    
    # Normalize projects
    if "projects" in normalized and isinstance(normalized["projects"], list):
        normalized["projects"] = [
            {
                "title": proj.get("title") or proj.get("name"),
                "name": proj.get("name") or proj.get("title"),
                "description": proj.get("description") or proj.get("details"),
                "techStack": proj.get("techStack"),
                "points": proj.get("points", [])
            }
            for proj in normalized["projects"]
        ]
    
    # Normalize certifications
    if "certifications" in normalized and isinstance(normalized["certifications"], list):
        normalized["certifications"] = [
            {
                "title": cert.get("title") or cert.get("name"),
                "name": cert.get("name") or cert.get("title"),
                "date": cert.get("date") or cert.get("issuedDate"),
                "issuer": cert.get("issuer") or cert.get("organization"),
                "description": cert.get("description")
            }
            for cert in normalized["certifications"]
        ]
    
    return normalized


def render_resume_html(template_name: str, resume_data: dict, profile_image: str = None):
    """
    Render resume HTML from template with resume data
    
    Args:
        template_name: Name of the template file (without .html extension)
        resume_data: Dictionary containing resume information
        profile_image: Optional base64 encoded profile image data URL
    
    Returns:
        Rendered HTML string
    """
    try:
        template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
        env = Environment(loader=FileSystemLoader(template_dir))
        template = env.get_template(f"{template_name}.html")
        
        # Normalize resume data to ensure compatibility
        normalized_data = normalize_resume_data(resume_data)
        
        html_content = template.render(
            resume=normalized_data,
            profile_image=profile_image
        )
        return html_content
    except TemplateNotFound:
        raise Exception(f"Template '{template_name}.html' not found")
    except Exception as e:
        raise Exception(f"Template rendering failed: {str(e)}")