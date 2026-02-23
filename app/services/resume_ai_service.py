# app/services/resume_ai_service.py

import json
import re
from fastapi import HTTPException
from app.services.resume_service import fetch_resume
from app.services.bedrock_client import call_bedrock  # your existing function



def build_resume_optimizer_prompt(target_jd, user_description, resume_sections):

    job_context = target_jd if target_jd else "General Resume Optimization"

    return f"""
You are an enterprise ATS resume optimization engine.

Return ONLY valid JSON.

User Intent:
{user_description if user_description else "No additional context provided."}

Target Job Description:
{job_context}

Current Resume Sections:
{json.dumps(resume_sections, indent=2)}

IMPORTANT LOGIC:

1. If target job description is specific → optimize resume to match it.
2. If target job description is general or null → optimize resume for broad employability.
3. Use user description to adjust tone:
   - If fresher/campus → emphasize projects, internships, skills.
   - If experienced → emphasize impact metrics and leadership.
4. Do NOT regenerate sections unnecessarily.
5. Preserve structure.

Return JSON:

{{
  "ats_match_score_estimate": 0-100,
  "overall_alignment": "Strong | Moderate | Weak",

  "summary": {{
    "changed": true/false,
    "content": "..."
  }},

  "experience": {{
    "changed": true/false,
    "content": [...]
  }},

  "projects": {{
    "changed": true/false,
    "content": [...]
  }},

  "skill": {{
    "changed": true/false,
    "skillType": "technical",
    "technical": [
      {{
        "subheading": "Languages",
        "skills": ["..."]
      }}
    ]
  }},

  "missing_keywords": [],
  "suggested_keywords_to_insert": []
}}

Return only JSON.
"""

def optimize_resume_with_ai(user_id: str, resume_id: str, target_jd: str | None, user_description: str | None):

    # 1️⃣ Fetch Resume
    resume_record = fetch_resume(user_id, resume_id)

    if not resume_record:
        raise HTTPException(status_code=404, detail="Resume not found")

    resume_data = resume_record.get("resume_data", {})

    # 2️⃣ Extract Only Editable Sections
    editable_sections = {
        "summary": resume_data.get("summary"),
        "experience": resume_data.get("experience"),
        "projects": resume_data.get("projects"),
        "certifications": resume_data.get("certifications"),
        "keyAchievements": resume_data.get("keyAchievements"),
        "skills": resume_data.get("skill"),
        "languages": resume_data.get("languages"),
        "interests": resume_data.get("interests")
    }

    # 3️⃣ Build Prompt
    prompt = build_resume_optimizer_prompt(
        target_jd=target_jd,
        user_description=user_description,
        resume_sections=editable_sections
    )

    # 4️⃣ Call Bedrock
    result = call_bedrock(
        prompt=prompt,
        max_tokens=1000,
        temperature=0.3
    )

    # 5️⃣ Parse JSON Safely
    try:
        cleaned = re.sub(r"```json|```", "", result).strip()
        json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)

        if not json_match:
            raise ValueError("No JSON detected")

        return json.loads(json_match.group())

    except Exception as e:
        print("Resume AI parsing failed:", str(e))

        return {
            "status": "error",
            "message": "AI response parsing failed"
        }
    



    