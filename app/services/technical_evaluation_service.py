from app.services.bedrock_client import call_bedrock
import json
import re


def evaluate_single_answer(question, answer, role, difficulty):

    prompt = f"""
You are a senior technical interviewer.

Role: {role}
Difficulty: {difficulty}

Question:
{question}

Candidate Answer:
{answer}

Evaluate the answer strictly.

Return ONLY valid JSON in this format:

{{
  "score": 0-10,
  "skill_gaps": "...",
  "what_was_missing": "...",
  "correct_answer": "...",
  "real_life_example": "...",
  "improvement_advice": "..."
}}

Do not include markdown.
Do not include explanations outside JSON.
"""

    result = call_bedrock(prompt, max_tokens=400)

    try:
        cleaned = re.sub(r"```json|```", "", result).strip()
        json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)

        if not json_match:
            raise ValueError("No JSON found")

        return json.loads(json_match.group())

    except Exception as e:
        print("Technical evaluation parsing failed:", str(e))

        return {
            "score": 0,
            "skill_gaps": "Unable to evaluate.",
            "what_was_missing": "Parsing error.",
            "correct_answer": "Unavailable",
            "real_life_example": "Unavailable",
            "improvement_advice": "Try structuring answers more clearly."
        }




def evaluate_all_answers(questions, answers, role, difficulty):

    question_feedback = []
    total_score = 0

    
    print(answers)

    #answer_map = {a["question_id"]: a["answer_text"] for a in answers}
    answer_map = {a.question_id: a.answer_text for a in answers}


    for q in questions:
        qid = q["question_id"]
        question_text = q["question_text"]

        candidate_answer = answer_map.get(qid, "")

        evaluation = evaluate_single_answer(
            question_text,
            candidate_answer,
            role,
            difficulty
        )

        question_feedback.append({
            "question_id": qid,
            "question_text": question_text,
            "candidate_answer": candidate_answer,   # ✅ Added here
            "evaluation": evaluation
        })

        total_score += evaluation.get("score", 0)

    average_score = round(total_score / len(questions), 2) if questions else 0

    return average_score, question_feedback
