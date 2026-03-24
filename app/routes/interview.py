from fastapi import APIRouter, HTTPException
from fastapi import UploadFile, File, Form
import uuid
from decimal import Decimal
from boto3.dynamodb.conditions import Key
from app.dynamo import table
import time
from app.schemas import (
    InterviewStartRequest,
    InterviewStartResponse,
    InterviewAnswerSubmission,
    InterviewQuotaCheckRequest,
    InterviewQuotaCheckResponse,
)

from app.services.question_service import generate_questions
from app.services.behavior_service import generate_behavior_feedback
from app.services.technical_evaluation_service import evaluate_all_answers
from app.utils import convert_floats
from datetime import datetime, timezone
import calendar


router = APIRouter()


def _parse_plan_start(plan_start: str) -> datetime:
    raw = str(plan_start or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="planStartDate is required")

    # Accept ISO date (YYYY-MM-DD) or datetime.
    try:
        if len(raw) == 10:
            parsed = datetime.strptime(raw, "%Y-%m-%d")
            return parsed.replace(tzinfo=timezone.utc)
        normalized = raw.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="planStartDate must be ISO format (YYYY-MM-DD or ISO datetime)",
        )


def _month_shift(year: int, month: int, delta: int) -> tuple[int, int]:
    month_index = (year * 12 + (month - 1)) + delta
    return month_index // 12, (month_index % 12) + 1


def _anchor_for_month(year: int, month: int, anchor_day: int) -> datetime:
    last_day = calendar.monthrange(year, month)[1]
    day = min(anchor_day, last_day)
    return datetime(year, month, day, tzinfo=timezone.utc)


def _resolve_cycle_window(plan_start_dt: datetime, now_dt: datetime) -> tuple[datetime, datetime]:
    anchor_day = plan_start_dt.day
    current_anchor = _anchor_for_month(now_dt.year, now_dt.month, anchor_day)

    if now_dt >= current_anchor:
        cycle_start = current_anchor
    else:
        prev_year, prev_month = _month_shift(now_dt.year, now_dt.month, -1)
        cycle_start = _anchor_for_month(prev_year, prev_month, anchor_day)

    next_year, next_month = _month_shift(cycle_start.year, cycle_start.month, 1)
    cycle_end = _anchor_for_month(next_year, next_month, anchor_day)
    return cycle_start, cycle_end


def _quota_period_key(cycle_start: datetime) -> str:
    return cycle_start.strftime("%Y-%m-%d")


def _to_int(value, default=0) -> int:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_subscription_status(status: str | None) -> str:
    return str(status or "ACTIVE").strip().upper()


def _compute_quota_state(user_id: str, limit: int, cycle_start: datetime):
    period = _quota_period_key(cycle_start)
    quota_pk = f"USER#{user_id}"
    quota_sk = f"INTERVIEW_QUOTA#{period}"

    existing = table.get_item(Key={"PK": quota_pk, "SK": quota_sk}).get("Item")
    used_count = _to_int(existing.get("used_interviews"), 0) if existing else 0
    remaining = max(0, limit - used_count)

    return {
        "period": period,
        "quota_pk": quota_pk,
        "quota_sk": quota_sk,
        "existing": existing,
        "used_count": used_count,
        "remaining": remaining,
    }


def _persist_quota(
    user_id: str,
    plan_type: str,
    subscription_status: str,
    interviews_limit: int,
    used_interviews: int,
    plan_start_date: str,
    period: str,
    cycle_start: str,
    renews_at: str,
    now_iso: str,
):
    quota_pk = f"USER#{user_id}"
    quota_sk = f"INTERVIEW_QUOTA#{period}"
    table.put_item(
        Item={
            "PK": quota_pk,
            "SK": quota_sk,
            "user_id": user_id,
            "plan_type": plan_type,
            "subscription_status": subscription_status,
            "period": period,
            "plan_start_date": plan_start_date,
            "cycle_start": cycle_start,
            "interviews_limit": interviews_limit,
            "used_interviews": used_interviews,
            "remaining_interviews": max(0, interviews_limit - used_interviews),
            "renews_at": renews_at,
            "updated_at": now_iso,
            "entity_type": "INTERVIEW_QUOTA",
        }
    )


def _store_quota_audit(user_id: str, period: str, event_type: str, payload: dict):
    ts = int(time.time() * 1000)
    table.put_item(
        Item={
            "PK": f"USER#{user_id}",
            "SK": f"INTERVIEW_QUOTA#{period}#EVENT#{ts}",
            "entity_type": "INTERVIEW_QUOTA_EVENT",
            "event_type": event_type,
            **payload,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )

def _to_decimal(value):
    """
    DynamoDB does not allow native float.
    Convert floats safely to Decimal.
    """
    if value is None:
        return Decimal("0")
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, bool):
        return value
    return value

def store_video_metrics(session_id: str, metrics: dict):

    item = {
        "PK": f"SESSION#{session_id}",
        "SK": "VIDEO_METRICS",

        # -----------------------
        # REQUIRED (existing backend compatibility)
        # -----------------------
        "eye_contact_score": metrics.get("eye_contact_score", 0),
        "head_movement_score": metrics.get("head_stability_score", 0),
        "hand_movement_score": metrics.get("hand_stability_score", 0),
        "confidence_score": metrics.get("overall_behavior_score", 0),

        "frames_sampled": metrics.get("frames_sampled", 0),

        # -----------------------
        # RICH BEHAVIORAL SIGNALS
        # -----------------------

        # Eye metrics
        "eye_open_ratio": _to_decimal(metrics.get("eye_open_ratio", 0)),
        "gaze_center_ratio": _to_decimal(metrics.get("gaze_center_ratio", 0)),
        "blink_count": metrics.get("blink_count", 0),
        "blink_rate_per_min": _to_decimal(metrics.get("blink_rate_per_min", 0)),
        "max_eye_closed_secs": _to_decimal(metrics.get("max_eye_closed_secs", 0)),

        # Head metrics
        "avg_yaw_abs_deg": _to_decimal(metrics.get("avg_yaw_abs_deg", 0)),
        "avg_pitch_abs_deg": _to_decimal(metrics.get("avg_pitch_abs_deg", 0)),
        "yaw_std_deg": _to_decimal(metrics.get("yaw_std_deg", 0)),
        "pitch_std_deg": _to_decimal(metrics.get("pitch_std_deg", 0)),

        # Hand metrics
        "hands_visible_ratio": _to_decimal(metrics.get("hands_visible_ratio", 0)),
        "avg_hand_motion": _to_decimal(metrics.get("avg_hand_motion", 0)),
        "hand_jitter_index": _to_decimal(metrics.get("hand_jitter_index", 0)),

        # Frame integrity
        "face_present_ratio": _to_decimal(metrics.get("face_present_ratio", 0)),
        "left_frame_ratio": _to_decimal(metrics.get("left_frame_ratio", 0)),

        # Multi-face / multi-person
        "multiple_face_detected": metrics.get("multiple_face_detected", False),
        "multiple_face_ratio": _to_decimal(metrics.get("multiple_face_ratio", 0)),
        "multiple_face_detected_count": metrics.get("multiple_face_detected_count", 0),
        "multiple_people_detected_count": metrics.get("multiple_people_detected_count", 0),
        "multiple_body_detected": metrics.get("multiple_body_detected", False),

        # Looking away / frame violations
        "looked_away_count": metrics.get("looked_away_count", 0),
        "face_not_in_frame_count": metrics.get("face_not_in_frame_count", 0),

        # Phone / device detection
        "phone_detected": metrics.get("phone_detected", False),
        "phone_detected_count": metrics.get("phone_detected_count", 0),
        "device_detected_count": metrics.get("device_detected_count", 0),

        # Smile / engagement
        "smile_score": _to_decimal(metrics.get("smile_score", 0)),

        # Warning severity
        "red_warnings_count": metrics.get("red_warnings_count", 0),
        "yellow_warnings_count": metrics.get("yellow_warnings_count", 0),

        # Nested violation summary (if exists)
        "violation_summary": {
            "face_not_in_frame_count": metrics.get("violation_summary", {}).get("face_not_in_frame_count", 0),
            "looked_away_count": metrics.get("violation_summary", {}).get("looked_away_count", 0),
            "device_detected_count": metrics.get("violation_summary", {}).get("device_detected_count", 0),
            "multiple_face_detected_count": metrics.get("violation_summary", {}).get("multiple_face_detected_count", 0),
            "multiple_people_detected_count": metrics.get("violation_summary", {}).get("multiple_people_detected_count", 0),
            "red_warnings_count": metrics.get("violation_summary", {}).get("red_warnings_count", 0),
            "yellow_warnings_count": metrics.get("violation_summary", {}).get("yellow_warnings_count", 0),
        },

        # Metadata
        "updated_at": int(time.time()),
    }



    table.put_item(Item=item)

# -----------------------------
# GET ALL SESSIONS FOR USER
# -----------------------------
@router.get("/user/{user_id}")
def get_user_sessions(user_id: str):

    response = table.query(
        IndexName="user-session-index",
        KeyConditionExpression=Key("user_id").eq(user_id)
    )

    items = response.get("Items", [])

    sessions = []

    for item in items:
        if item.get("SK") != "METADATA":
            continue

        session_id = item.get("session_id")

        # -----------------------------------
        # Fetch session partition data
        # -----------------------------------
        session_response = table.query(
            KeyConditionExpression=Key("PK").eq(f"SESSION#{session_id}")
        )

        session_items = session_response.get("Items", [])

        feedback_item = next(
            (i for i in session_items if i.get("SK") == "FEEDBACK"),
            None
        )

        video_item = next(
            (i for i in session_items if i.get("SK") == "VIDEO_METRICS"),
            None
        )

        # -----------------------------------
        # Extract overall score
        # -----------------------------------
        overall_score = None
        if feedback_item:
            overall_score = feedback_item.get("overall_score")

        # -----------------------------------
        # Detect violations
        # -----------------------------------
        violation_flag = False

        if video_item:
            phone_detected = video_item.get("phone_detected", False)
            multiple_face = video_item.get("multiple_face_detected", False)
            red_warnings = video_item.get("red_warnings_count", 0)

            if phone_detected or multiple_face or red_warnings > 0:
                violation_flag = True

        # -----------------------------------
        # Append session
        # -----------------------------------
        sessions.append({
            "session_id": session_id,
            "role": item.get("role"),
            "interview_type": item.get("interview_type"),
            "difficulty": item.get("difficulty"),
            "status": item.get("status"),
            "created_at": item.get("created_at"),

            # New fields
            "overall_score": overall_score,
            "violation_flag": violation_flag
        })

    return {
        "user_id": user_id,
        "sessions": sessions
    }


@router.post("/quota/check", response_model=InterviewQuotaCheckResponse)
def check_interview_quota(payload: InterviewQuotaCheckRequest):
    user_id = str(payload.user_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    interviews_limit = _to_int(payload.interviewsLimit, default=-1)
    if interviews_limit < 0:
        raise HTTPException(status_code=400, detail="interviewsLimit is required and must be >= 0")

    plan_type = str(payload.planType or "UNKNOWN").strip()
    subscription_status = _normalize_subscription_status(payload.status)
    plan_start_dt = _parse_plan_start(payload.planStartDate)
    if subscription_status not in {"ACTIVE", "TRIAL"}:
        raise HTTPException(
            status_code=403,
            detail=f"Subscription is not active (status={subscription_status}).",
        )

    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()
    cycle_start_dt, cycle_end_dt = _resolve_cycle_window(plan_start_dt, now_dt)
    period = _quota_period_key(cycle_start_dt)
    state = _compute_quota_state(user_id=user_id, limit=interviews_limit, cycle_start=cycle_start_dt)

    can_start = state["remaining"] > 0
    message = (
        "Interview can be started."
        if can_start
        else f"Interview limit reached for {plan_type}. Upgrade your subscription plan."
    )

    _persist_quota(
        user_id=user_id,
        plan_type=plan_type,
        subscription_status=subscription_status,
        interviews_limit=interviews_limit,
        used_interviews=state["used_count"],
        plan_start_date=payload.planStartDate,
        period=period,
        cycle_start=cycle_start_dt.isoformat(),
        renews_at=cycle_end_dt.isoformat(),
        now_iso=now_iso,
    )

    _store_quota_audit(
        user_id=user_id,
        period=period,
        event_type="CHECK",
        payload={
            "plan_type": plan_type,
            "subscription_status": subscription_status,
            "plan_start_date": payload.planStartDate,
            "cycle_start": cycle_start_dt.isoformat(),
            "renews_at": cycle_end_dt.isoformat(),
            "interviews_limit": interviews_limit,
            "used_interviews": state["used_count"],
            "remaining_interviews": state["remaining"],
            "can_start_interview": can_start,
        },
    )

    return InterviewQuotaCheckResponse(
        user_id=user_id,
        plan_type=plan_type,
        subscription_status=subscription_status,
        period=period,
        cycle_start=cycle_start_dt.isoformat(),
        renews_at=cycle_end_dt.isoformat(),
        interviews_limit=interviews_limit,
        used_interviews=state["used_count"],
        remaining_interviews=state["remaining"],
        can_start_interview=can_start,
        slot_consumed=False,
        message=message,
    )


@router.post("/quota/consume", response_model=InterviewQuotaCheckResponse)
def consume_interview_quota(payload: InterviewQuotaCheckRequest):
    user_id = str(payload.user_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    interviews_limit = _to_int(payload.interviewsLimit, default=-1)
    if interviews_limit < 0:
        raise HTTPException(status_code=400, detail="interviewsLimit is required and must be >= 0")

    plan_type = str(payload.planType or "UNKNOWN").strip()
    subscription_status = _normalize_subscription_status(payload.status)
    plan_start_dt = _parse_plan_start(payload.planStartDate)
    if subscription_status not in {"ACTIVE", "TRIAL"}:
        raise HTTPException(
            status_code=403,
            detail=f"Subscription is not active (status={subscription_status}).",
        )

    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()
    cycle_start_dt, cycle_end_dt = _resolve_cycle_window(plan_start_dt, now_dt)
    period = _quota_period_key(cycle_start_dt)
    state = _compute_quota_state(user_id=user_id, limit=interviews_limit, cycle_start=cycle_start_dt)

    if state["remaining"] <= 0:
        _persist_quota(
            user_id=user_id,
            plan_type=plan_type,
            subscription_status=subscription_status,
            interviews_limit=interviews_limit,
            used_interviews=state["used_count"],
            plan_start_date=payload.planStartDate,
            period=period,
            cycle_start=cycle_start_dt.isoformat(),
            renews_at=cycle_end_dt.isoformat(),
            now_iso=now_iso,
        )
        _store_quota_audit(
            user_id=user_id,
            period=period,
            event_type="BLOCKED",
            payload={
                "plan_type": plan_type,
                "subscription_status": subscription_status,
                "plan_start_date": payload.planStartDate,
                "cycle_start": cycle_start_dt.isoformat(),
                "renews_at": cycle_end_dt.isoformat(),
                "interviews_limit": interviews_limit,
                "used_interviews": state["used_count"],
                "remaining_interviews": 0,
                "can_start_interview": False,
            },
        )
        raise HTTPException(
            status_code=403,
            detail=f"Interview limit reached for {plan_type}. Upgrade your subscription plan.",
        )

    updated_used = state["used_count"] + 1
    remaining = max(0, interviews_limit - updated_used)

    _persist_quota(
        user_id=user_id,
        plan_type=plan_type,
        subscription_status=subscription_status,
        interviews_limit=interviews_limit,
        used_interviews=updated_used,
        plan_start_date=payload.planStartDate,
        period=period,
        cycle_start=cycle_start_dt.isoformat(),
        renews_at=cycle_end_dt.isoformat(),
        now_iso=now_iso,
    )

    _store_quota_audit(
        user_id=user_id,
        period=period,
        event_type="CONSUMED",
        payload={
            "plan_type": plan_type,
            "subscription_status": subscription_status,
            "plan_start_date": payload.planStartDate,
            "cycle_start": cycle_start_dt.isoformat(),
            "renews_at": cycle_end_dt.isoformat(),
            "interviews_limit": interviews_limit,
            "used_interviews": updated_used,
            "remaining_interviews": remaining,
            "can_start_interview": True,
        },
    )

    return InterviewQuotaCheckResponse(
        user_id=user_id,
        plan_type=plan_type,
        subscription_status=subscription_status,
        period=period,
        cycle_start=cycle_start_dt.isoformat(),
        renews_at=cycle_end_dt.isoformat(),
        interviews_limit=interviews_limit,
        used_interviews=updated_used,
        remaining_interviews=remaining,
        can_start_interview=True,
        slot_consumed=True,
        message="Interview slot reserved. You can start the interview.",
    )




# -----------------------------
# GET FULL SESSION FEEDBACK
# -----------------------------
@router.get("/{session_id}/full-feedback")
def get_full_feedback(session_id: str):

    response = table.query(
        KeyConditionExpression=Key("PK").eq(f"SESSION#{session_id}")
    )

    items = response.get("Items", [])

    metadata = next(
        (item for item in items if item["SK"] == "METADATA"),
        None
    )

    feedback_item = next(
        (item for item in items if item["SK"] == "FEEDBACK"),
        None
    )
    behavioral = feedback_item.get("behavioral_feedback", {}) or {}
    if not feedback_item:
        raise HTTPException(status_code=404, detail="Feedback not found")

    return {
        "session_id": session_id,
        "role": metadata.get("role") if metadata else None,
        "difficulty": metadata.get("difficulty") if metadata else None,
        "interview_type": metadata.get("interview_type") if metadata else None,
        "overall_score": feedback_item.get("overall_score", 0),
        "technical_score": feedback_item.get("technical_score", 0),
        "behavioral_score": feedback_item.get("behavioral_score", 0),

        # -------------------------
        # Technical Feedback
        # -------------------------
        "question_feedback": feedback_item.get("question_feedback", []),

        # -------------------------
        # Behavioral Feedback (Full Structured)
        # -------------------------
        "behavioral_feedback": behavioral,

        # Flattened for easy frontend access (optional but useful)
        "behavior_summary": behavioral.get("behavior_summary"),
        "strengths": behavioral.get("strengths", []),
        "areas_of_improvement": behavioral.get("areas_of_improvement", []),
        "nervousness_level": behavioral.get("nervousness_level"),
        "professionalism_score": behavioral.get("professionalism_score"),
        "confidence_assessment": behavioral.get("confidence_assessment"),
        "engagement_level": behavioral.get("engagement_level"),
        "integrity_risk_level": behavioral.get("integrity_risk_level"),
        "integrity_risk_score": behavioral.get("integrity_risk_score"),
        "violation_analysis": behavioral.get("violation_analysis"),
        "detailed_coaching_tips": behavioral.get("detailed_coaching_tips", []),
        "completed_at": feedback_item.get("updated_at")
    }


@router.get("/count/{user_id}")
def get_user_interview_count(user_id: str):
    from app.schemas import UserInterviewCountResponse
    
    response = table.query(
        IndexName="user-session-index",
        KeyConditionExpression=Key("user_id").eq(user_id)
    )

    items = response.get("Items", [])
    interview_count = 0

    for item in items:
        if item.get("SK") == "METADATA":
            interview_count += 1

    return UserInterviewCountResponse(
        user_id=user_id,
        interview_count=interview_count
    )


# -----------------------------------------
# START INTERVIEW
# -----------------------------------------
@router.post("/start", response_model=InterviewStartResponse)
def start_interview(request: InterviewStartRequest):

    session_id = str(uuid.uuid4())

    now = datetime.now(timezone.utc).isoformat()  # UTC timestamp

    questions = generate_questions(
        request.role,
        request.technologies,
        request.difficulty,
        request.number_of_questions
    )

    # Save metadata
    table.put_item(
       Item={
        "PK": f"SESSION#{session_id}",
        "SK": "METADATA",
        "session_id": session_id,  # 🔥 REQUIRED for GSI
        "user_id": request.user_id,
        "role": request.role,
        "interview_type": request.interview_type,
        "difficulty": request.difficulty,
        "status": "STARTED",
        "created_at": now,        # ✅ added
        "updated_at": now 
       }
    )


    # Save questions
    for idx, q in enumerate(questions):
        table.put_item(
            Item={
                "PK": f"SESSION#{session_id}",
                "SK": f"QUESTION#{idx}",
                "question_id": q["question_id"],
                "question_text": q["question_text"],
                "created_at": now,   # optional but good practice
                "updated_at": now
            }
        )

    return {
        "session_id": session_id,
        "status": "STARTED"
    }


# -----------------------------------------
# GET QUESTIONS
# -----------------------------------------
@router.get("/{session_id}/questions")
def get_questions(session_id: str):

    response = table.query(
        KeyConditionExpression=Key("PK").eq(f"SESSION#{session_id}")
    )

    items = response.get("Items", [])

    questions = [
        {
            "question_id": item["question_id"],
            "question_text": item["question_text"]
        }
        for item in items
        if item["SK"].startswith("QUESTION#")
    ]

    return {
        "session_id": session_id,
        "questions": questions
    }


# -----------------------------------------
# SUBMIT ANSWERS
# -----------------------------------------
@router.post("/{session_id}/submit")
def submit_answers(session_id: str, submission: InterviewAnswerSubmission):

    # -----------------------------------------
    # 1️⃣ Fetch session data
    # -----------------------------------------
    response = table.query(
        KeyConditionExpression=Key("PK").eq(f"SESSION#{session_id}")
    )

    items = response.get("Items", [])

    if not items:
        raise HTTPException(status_code=404, detail="Session not found")

    # Extract metadata
    metadata_item = next(
        (item for item in items if item["SK"] == "METADATA"),
        None
    )

    if not metadata_item:
        raise HTTPException(status_code=404, detail="Session metadata missing")

    role = metadata_item.get("role")
    difficulty = metadata_item.get("difficulty")

    # Extract questions properly
    questions = [
        {
            "question_id": item["question_id"],
            "question_text": item["question_text"]
        }
        for item in items
        if item["SK"].startswith("QUESTION#")
    ]

    if not questions:
        raise HTTPException(status_code=404, detail="Questions not found")

    # -----------------------------------------
    # 2️⃣ Store answers
    # -----------------------------------------
    for answer in submission.answers:
        table.put_item(
            Item={
                "PK": f"SESSION#{session_id}",
                "SK": f"ANSWER#{answer.question_id}",
                "question_id": answer.question_id,
                "answer_text": answer.answer_text
            }
        )


        # -----------------------------------------
    # 3️⃣ Store video metrics (merge violation_summary)
    # -----------------------------------------
    if submission.video_metrics:

        # Merge violation_summary into video_metrics
        merged_metrics = submission.video_metrics.copy()

        if submission.violation_summary:
            merged_metrics["violation_summary"] = submission.violation_summary

        # Now store everything together
        store_video_metrics(session_id, merged_metrics)

        # Refresh items so VIDEO_METRICS is included
        response = table.query(
            KeyConditionExpression=Key("PK").eq(f"SESSION#{session_id}")
        )
        items = response.get("Items", [])





    # -----------------------------------------
    # 3️⃣ Technical Evaluation (LLM)
    # -----------------------------------------
    technical_score, question_feedback = evaluate_all_answers(
        questions=questions,
        answers=submission.answers,
        role=role,
        difficulty=difficulty
    )

    # -----------------------------------------
    # 4️⃣ Behavioral Evaluation (If Video Exists)
    # -----------------------------------------
    video_item = next(
        (item for item in items if item["SK"] == "VIDEO_METRICS"),
        None
    )

    behavioral_feedback = None
    behavioral_score = None

    if video_item:
        behavioral_feedback = generate_behavior_feedback(video_item)
        behavioral_score = behavioral_feedback.get("professionalism_score", 0)

    # -----------------------------------------
    # 5️⃣ Combine Overall Score
    # -----------------------------------------
    # -----------------------------------------

    interview_type = metadata_item.get("interview_type")

    if interview_type == "video" and behavioral_score is not None:
       overall_score = int(
         (0.7 * technical_score) + (0.3 * behavioral_score)
        )
    else:
       # Text-based interview
        overall_score = int(technical_score)


    # -----------------------------------------
    # 6️⃣ Store Final Feedback
    # -----------------------------------------
    feedback_item = {
    "PK": f"SESSION#{session_id}",
    "SK": "FEEDBACK",
    "overall_score": overall_score,
    "technical_score": technical_score,
    "behavioral_score": behavioral_score,
    "question_feedback": question_feedback,
    "behavioral_feedback": behavioral_feedback
    }

    table.put_item(
        Item=convert_floats(feedback_item)
    )

    # -----------------------------------------
    # 7️⃣ Update Session Status
    # -----------------------------------------
    table.update_item(
        Key={
            "PK": f"SESSION#{session_id}",
            "SK": "METADATA"
        },
        UpdateExpression="SET #st = :s",
        ExpressionAttributeNames={"#st": "status"},
        ExpressionAttributeValues={":s": "COMPLETED"}
    )

    return {
        "status": "SUBMITTED",
        "overall_score": overall_score
    }

# -----------------------------------------
# GET FEEDBACK
# -----------------------------------------
@router.get("/{session_id}/feedback")
def get_feedback(session_id: str):

    response = table.query(
        KeyConditionExpression=Key("PK").eq(f"SESSION#{session_id}")
    )

    items = response.get("Items", [])

    feedback_item = next(
        (item for item in items if item["SK"] == "FEEDBACK"),
        None
    )

    if not feedback_item:
        raise HTTPException(status_code=404, detail="Feedback not available")

    behavioral = feedback_item.get("behavioral_feedback", {}) or {}

    return {
        "session_id": session_id,

        # -------------------------
        # Overall Scores
        # -------------------------
        "overall_score": feedback_item.get("overall_score", 0),
        "technical_score": feedback_item.get("technical_score", 0),
        "behavioral_score": feedback_item.get("behavioral_score", 0),

        # -------------------------
        # Technical Feedback
        # -------------------------
        "question_feedback": feedback_item.get("question_feedback", []),

        # -------------------------
        # Behavioral Feedback (Full Structured)
        # -------------------------
        "behavioral_feedback": behavioral,

        # Flattened for easy frontend access (optional but useful)
        "behavior_summary": behavioral.get("behavior_summary"),
        "strengths": behavioral.get("strengths", []),
        "areas_of_improvement": behavioral.get("areas_of_improvement", []),
        "nervousness_level": behavioral.get("nervousness_level"),
        "professionalism_score": behavioral.get("professionalism_score"),
        "confidence_assessment": behavioral.get("confidence_assessment"),
        "engagement_level": behavioral.get("engagement_level"),
        "integrity_risk_level": behavioral.get("integrity_risk_level"),
        "integrity_risk_score": behavioral.get("integrity_risk_score"),
        "violation_analysis": behavioral.get("violation_analysis"),
        "detailed_coaching_tips": behavioral.get("detailed_coaching_tips", [])
    }




# @router.post("/{session_id}/video-feedback")
# def generate_video_feedback(session_id: str):

#     # Fetch session items
#     response = table.query(
#         KeyConditionExpression=Key("PK").eq(f"SESSION#{session_id}")
#     )

#     items = response.get("Items", [])

#     # Check if feedback already exists
#     existing_feedback = next(
#         (item for item in items if item["SK"] == "FEEDBACK"),
#         None
#     )

#     if existing_feedback:
#        return {
#         "status": "FEEDBACK_ALREADY_EXISTS"
#     }


#     # -----------------------------
#     # Extract required items
#     # -----------------------------
#     metadata = next(
#         (item for item in items if item["SK"] == "METADATA"),
#         None
#     )

#     questions = [
#         item for item in items
#         if item["SK"].startswith("QUESTION#")
#     ]

#     answers = [
#         item for item in items
#         if item["SK"].startswith("ANSWER#")
#     ]

#     video_metrics = next(
#         (item for item in items if item["SK"] == "VIDEO_METRICS"),
#         None
#     )

#     # -----------------------------
#     # Validations
#     # -----------------------------
#     if not metadata:
#         raise HTTPException(status_code=404, detail="Session metadata not found")

#     if not answers:
#         raise HTTPException(
#             status_code=400,
#             detail="Answers not processed yet. Worker still running."
#         )

#     if not video_metrics:
#         raise HTTPException(
#             status_code=400,
#             detail="Video metrics not available yet."
#         )

#     # -----------------------------
#     # Extract role + difficulty
#     # -----------------------------
#     role = metadata.get("role")
#     difficulty = metadata.get("difficulty")

#     # -----------------------------
#     # Convert answers format
#     # -----------------------------
#     submission_answers = [
#         {
#             "question_id": a["question_id"],
#             "answer_text": a["answer_text"]
#         }
#         for a in answers
#     ]

#     # -----------------------------
#     # 1️⃣ Technical evaluation
#     # -----------------------------
#     technical_score, question_feedback = evaluate_all_answers(
#         questions=questions,
#         answers=submission_answers,
#         role=role,
#         difficulty=difficulty
#     )

#     # -----------------------------
#     # 2️⃣ Behavioral evaluation
#     # -----------------------------
#     behavioral_feedback = generate_behavior_feedback(video_metrics)
#     behavioral_score = behavioral_feedback.get("professionalism_score", 0)

#     # -----------------------------
#     # 3️⃣ Combine overall score
#     # -----------------------------
#     overall_score = int(
#         (0.7 * technical_score) + (0.3 * behavioral_score)
#     )

#     # -----------------------------
#     # 4️⃣ Store FEEDBACK
#     # -----------------------------
    
#     feedback_item = {
#             "PK": f"SESSION#{session_id}",
#             "SK": "FEEDBACK",
#             "overall_score": overall_score,
#             "technical_score": technical_score,
#             "behavioral_score": behavioral_score,
#             "question_feedback": question_feedback,
#             "behavioral_feedback": behavioral_feedback,
#             "feedback_type": "VIDEO",
#             "generated_at": int(time.time())
#         }
    

#     table.put_item(
#         Item=convert_floats(feedback_item)
#     )
#     # -----------------------------
#     # 5️⃣ Update status
#     # -----------------------------
#     table.update_item(
#         Key={
#             "PK": f"SESSION#{session_id}",
#             "SK": "METADATA"
#         },
#         UpdateExpression="""
#             SET #st = :s,
#             updated_at = :u
#         """,
#         ExpressionAttributeNames={
#             "#st": "status"
#         },
#         ExpressionAttributeValues={
#             ":s": "COMPLETED",
#             ":u": datetime.now(timezone.utc).isoformat()
#         }
#     )


#     return {
#         "status": "FEEDBACK_GENERATED",
#         "overall_score": overall_score
#     }
