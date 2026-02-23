# app/services/template_registry.py

from app.services.resume_render_service import render_resume_html


def render_classic_latex(resume_data: dict, profile_image: str = None) -> str:
    return render_resume_html(
        template_name="classic-latex",
        resume_data=resume_data,
        profile_image=profile_image
    )


def render_modern_minimal(resume_data: dict, profile_image: str = None) -> str:
    return render_resume_html(
        template_name="modern-minimal",
        resume_data=resume_data,
        profile_image=profile_image
    )


def render_ats_clean(resume_data: dict, profile_image: str = None) -> str:
    return render_resume_html(
        template_name="ats-clean",
        resume_data=resume_data,
        profile_image=profile_image
    )


TEMPLATE_REGISTRY = {
    "classic-latex": render_classic_latex,
    "modern-minimal": render_modern_minimal,
    "ats-clean": render_ats_clean,
}


def render_by_template(template_name: str, resume_data: dict, profile_image: str = None) -> str:
    renderer = TEMPLATE_REGISTRY.get(template_name)

    if not renderer:
        raise ValueError(f"Template '{template_name}' not supported")

    return renderer(resume_data, profile_image)
