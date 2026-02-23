from app.services.bedrock_client import call_bedrock
import uuid
import json
import re


def generate_questions(role, technologies, difficulty, number_of_questions):

    prompt = f"""
You are a professional technical interviewer.

Role: {role}
Technologies: {technologies}
Difficulty: {difficulty}

Generate exactly {number_of_questions} interview questions.

Return ONLY valid JSON in this exact format:

[
  {{
    "question_id": "1",
    "question_text": "Actual question here"
  }},
  {{
    "question_id": "2",
    "question_text": "Actual question here"
  }}
]

Do not include explanations.
Do not include markdown.
Do not include ```json.
Do not return text outside the JSON array.
"""

    result = call_bedrock(prompt, max_tokens=100)

    # -------------------------------
    # STRICT JSON PARSING
    # -------------------------------
    try:
        cleaned = re.sub(r"```json|```", "", result).strip()

        json_match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON array found")

        json_str = json_match.group()
        parsed = json.loads(json_str)

        validated_questions = []

        for q in parsed:
            if "question_text" in q and isinstance(q["question_text"], str):
                validated_questions.append({
                    "question_id": str(uuid.uuid4()),
                    "question_text": q["question_text"].strip()
                })

        if len(validated_questions) >= number_of_questions:
            return validated_questions[:number_of_questions]

        raise ValueError("Insufficient valid questions")

    except Exception as e:
        print("JSON parsing failed:", str(e))

    # ---------------------------------------
    # SAFE FALLBACK (only real questions)
    # ---------------------------------------

    lines = [
        line.strip()
        for line in result.split("\n")
        if line.strip()
        and "question_id" not in line.lower()
        and "question_text" not in line.lower()
        and len(line.strip()) > 15
        and line.strip().endswith("?")
    ]

    fallback = []

    for line in lines[:number_of_questions]:
        fallback.append({
            "question_id": str(uuid.uuid4()),
            "question_text": line.replace('"', '').replace(",", "")
        })

    return fallback
