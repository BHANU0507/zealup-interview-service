from app.services.bedrock_client import call_bedrock
import json
import re


# def generate_behavior_feedback(metrics: dict):

#     prompt = f"""
# You are an expert behavioral interview coach.

# Analyze the candidate's video behavioral metrics below.

# Respond ONLY with valid JSON.

# Metrics:

# Eye Metrics:
# - Eye Contact Score: {metrics.get("eye_contact_score")}
# - Eye Open Ratio: {metrics.get("eye_open_ratio")}
# - Gaze Center Ratio: {metrics.get("gaze_center_ratio")}
# - Blink Rate Per Minute: {metrics.get("blink_rate_per_min")}
# - Max Eye Closed Seconds: {metrics.get("max_eye_closed_secs")}

# Head Metrics:
# - Head Movement Score: {metrics.get("head_movement_score")}
# - Avg Yaw (degrees): {metrics.get("avg_yaw_abs_deg")}
# - Avg Pitch (degrees): {metrics.get("avg_pitch_abs_deg")}
# - Yaw Std Dev: {metrics.get("yaw_std_deg")}
# - Pitch Std Dev: {metrics.get("pitch_std_deg")}

# Hand Metrics:
# - Hand Movement Score: {metrics.get("hand_movement_score")}
# - Hands Visible Ratio: {metrics.get("hands_visible_ratio")}
# - Avg Hand Motion: {metrics.get("avg_hand_motion")}
# - Hand Jitter Index: {metrics.get("hand_jitter_index")}

# Presence Metrics:
# - Face Present Ratio: {metrics.get("face_present_ratio")}
# - Left Frame Ratio: {metrics.get("left_frame_ratio")}
# - Multiple Face Detected: {metrics.get("multiple_face_detected")}
# - Multiple Face Ratio: {metrics.get("multiple_face_ratio")}

# Overall Confidence Score: {metrics.get("confidence_score")}

# Based on these values:

# 1. Interpret behavioral patterns (nervousness, stability, confidence, posture).
# 2. Identify strengths.
# 3. Identify specific improvement areas.
# 4. Give professional interview advice.

# Return JSON in this format:

# {{
#   "behavior_summary": "...",
#   "strengths": ["...", "..."],
#   "areas_of_improvement": ["...", "..."],
#   "nervousness_level": "Low | Moderate | High",
#   "professionalism_score": 0-100,
#   "confidence_assessment": "...",
#   "detailed_coaching_tips": ["...", "..."]
# }}

# Do not include explanations or markdown.
# Only JSON.
# """

#     result = call_bedrock(prompt, max_tokens=1200)

#     try:
#         cleaned = re.sub(r"```json|```", "", result).strip()
#         json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)

#         if not json_match:
#             raise ValueError("No JSON detected")

#         return json.loads(json_match.group())

#     except Exception as e:
#         print("Behavior parsing failed:", str(e))

#         return {
#             "behavior_summary": "Behavioral analysis unavailable.",
#             "strengths": [],
#             "areas_of_improvement": [],
#             "nervousness_level": "Unknown",
#             "professionalism_score": 0,
#             "confidence_assessment": "Unable to assess",
#             "detailed_coaching_tips": []
#         }
def generate_behavior_feedback(metrics: dict):

    prompt = f"""
You are an expert behavioral interview evaluator and integrity assessor.

Analyze the candidate’s video behavioral and integrity metrics below.

Respond ONLY with valid JSON.

-------------------------------------
BEHAVIORAL METRICS
-------------------------------------

Eye Metrics:
- Eye Contact Score: {metrics.get("eye_contact_score")}
- Eye Open Ratio: {metrics.get("eye_open_ratio")}
- Gaze Center Ratio: {metrics.get("gaze_center_ratio")}
- Blink Rate Per Minute: {metrics.get("blink_rate_per_min")}
- Max Eye Closed Seconds: {metrics.get("max_eye_closed_secs")}
- Looked Away Count: {metrics.get("looked_away_count")}

Head Metrics:
- Head Movement Score: {metrics.get("head_movement_score")}
- Avg Yaw (degrees): {metrics.get("avg_yaw_abs_deg")}
- Avg Pitch (degrees): {metrics.get("avg_pitch_abs_deg")}
- Yaw Std Dev: {metrics.get("yaw_std_deg")}
- Pitch Std Dev: {metrics.get("pitch_std_deg")}

Hand Metrics:
- Hand Movement Score: {metrics.get("hand_movement_score")}
- Hands Visible Ratio: {metrics.get("hands_visible_ratio")}
- Avg Hand Motion: {metrics.get("avg_hand_motion")}
- Hand Jitter Index: {metrics.get("hand_jitter_index")}

Presence & Engagement:
- Face Present Ratio: {metrics.get("face_present_ratio")}
- Left Frame Ratio: {metrics.get("left_frame_ratio")}
- Smile Score: {metrics.get("smile_score")}
- Confidence Score: {metrics.get("confidence_score")}

-------------------------------------
INTEGRITY / VIOLATION METRICS
-------------------------------------

- Multiple Face Detected: {metrics.get("multiple_face_detected")}
- Multiple Face Count: {metrics.get("multiple_face_detected_count")}
- Multiple People Count: {metrics.get("multiple_people_detected_count")}
- Phone Detected: {metrics.get("phone_detected")}
- Phone Detected Count: {metrics.get("phone_detected_count")}
- Device Detected Count: {metrics.get("device_detected_count")}
- Face Not In Frame Count: {metrics.get("face_not_in_frame_count")}
- Red Warnings: {metrics.get("red_warnings_count")}
- Yellow Warnings: {metrics.get("yellow_warnings_count")}

-------------------------------------

Instructions:

1. Interpret behavioral stability, confidence, engagement.
2. Detect nervousness patterns (excess blinking, high yaw/pitch variance, jitter).
3. Evaluate professionalism.
4. Assess potential integrity risks (multiple people, phone usage, red warnings).
5. Provide separate behavioral score and integrity risk score.
6. Provide actionable coaching advice.
7. Be objective and data-driven.
8. If red warnings or phone/multiple people detected, increase integrity risk.

-------------------------------------

Return JSON in this format:

{{
  "behavior_summary": "...",
  "strengths": ["...", "..."],
  "areas_of_improvement": ["...", "..."],
  "nervousness_level": "Low | Moderate | High",
  "professionalism_score": 0-100,
  "confidence_assessment": "...",
  "engagement_level": "Low | Moderate | High",
  "integrity_risk_level": "Low | Moderate | High",
  "integrity_risk_score": 0-100,
  "violation_analysis": "...",
  "detailed_coaching_tips": ["...", "..."]
}}

Only JSON.
No markdown.
No explanation.
"""

    result = call_bedrock(prompt, max_tokens=300)

    try:
        cleaned = re.sub(r"```json|```", "", result).strip()
        json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)

        if not json_match:
            raise ValueError("No JSON detected")

        return json.loads(json_match.group())

    except Exception as e:
        print("Behavior parsing failed:", str(e))

        return {
            "behavior_summary": "Behavioral analysis unavailable.",
            "strengths": [],
            "areas_of_improvement": [],
            "nervousness_level": "Unknown",
            "professionalism_score": 0,
            "confidence_assessment": "Unable to assess",
            "engagement_level": "Unknown",
            "integrity_risk_level": "Unknown",
            "integrity_risk_score": 0,
            "violation_analysis": "Unavailable",
            "detailed_coaching_tips": []
        }
