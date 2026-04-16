"""
Dashboard Service

Aggregates stats for two student types:

College Student Dashboard:
  - courses_enrolled     (count)
  - avg_interview_score  (sum of all overall_score / count)
  - avg_college_assignment_score (sum of college assignment scores / count)
  - challenge_rank       (rank among students in the same college)

Individual Student Dashboard:
  - courses_enrolled     (count)
  - avg_interview_score  (sum of all overall_score / count)
  - avg_assignment_score (sum of general assignment scores / count)
  - challenge_rank       (global rank among individual students)
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional

from boto3.dynamodb.conditions import Key
from fastapi import HTTPException

from app.dynamo import (
    table,                      # TABLE1 — interview sessions
    assignments_table,          # TABLE4 — general assignments
    course_enrollments_table,   # TABLE6 — course enrollments
    college_assignments_table,  # TABLE8 — college assignments
)
from app.services.challenge_service import get_college_rank, get_global_rank
from app.services.assignment_service import _parse_dt_aware, _now_dt
from app.dynamo import roadmaps_table as _rm_tbl


# ---------------------------------------------------------------------------
# Type helpers
# ---------------------------------------------------------------------------

def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Courses enrolled
# ---------------------------------------------------------------------------

def _get_courses_enrolled_count(user_id: str) -> int:
    """Count how many courses the user is currently enrolled in."""
    if course_enrollments_table is None:
        return 0
    try:
        resp = course_enrollments_table.query(
            KeyConditionExpression=(
                Key("PK").eq(f"USER#{user_id}")
                & Key("SK").begins_with("ENROLLMENT#COURSE#")
            ),
            Select="COUNT",
        )
        return _to_int(resp.get("Count"), 0)
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Interview stats
# ---------------------------------------------------------------------------

def _get_interview_stats(user_id: str) -> Dict[str, Any]:
    """
    Return avg_score, total_interviews, total_score across all completed
    interview sessions for the user.

    Flow: query user-session-index GSI → filter SK=METADATA →
          for each session fetch FEEDBACK item → collect overall_score.
    """
    try:
        resp = table.query(
            IndexName="user-session-index",
            KeyConditionExpression=Key("user_id").eq(user_id),
        )
        metadata_items = [
            i for i in resp.get("Items", []) if i.get("SK") == "METADATA"
        ]
    except Exception:
        return {"avg_score": 0.0, "total_interviews": 0, "total_score": 0.0}

    scores: List[float] = []
    for meta in metadata_items:
        session_id = meta.get("session_id")
        if not session_id:
            continue
        try:
            session_resp = table.query(
                KeyConditionExpression=Key("PK").eq(f"SESSION#{session_id}")
            )
            feedback = next(
                (
                    i
                    for i in session_resp.get("Items", [])
                    if i.get("SK") == "FEEDBACK"
                ),
                None,
            )
            if feedback is not None and feedback.get("overall_score") is not None:
                scores.append(_to_float(feedback["overall_score"]))
        except Exception:
            continue

    total = sum(scores)
    count = len(scores)
    avg = round(total / count, 2) if count > 0 else 0.0

    return {
        "avg_score": avg,
        "total_interviews": count,
        "total_score": round(total, 2),
    }


# ---------------------------------------------------------------------------
# College assignment stats
# ---------------------------------------------------------------------------

def _get_college_assignment_stats(user_id: str) -> Dict[str, Any]:
    """
    Return avg_score, total_assignments, total_score for all finalized college
    assignment submissions made by the user.

    Key pattern: PK=cusub#{user_id}, SK begins_with CASSIGNMENT#
    """
    if college_assignments_table is None:
        return {"avg_score": 0.0, "total_assignments": 0, "total_score": 0.0}
    try:
        resp = college_assignments_table.query(
            KeyConditionExpression=(
                Key("PK").eq(f"cusub#{user_id}")
                & Key("SK").begins_with("CASSIGNMENT#")
            )
        )
        items = resp.get("Items", [])
    except Exception:
        return {"avg_score": 0.0, "total_assignments": 0, "total_score": 0.0}

    scores: List[float] = []
    for item in items:
        if str(item.get("status", "")).lower() == "submitted":
            scores.append(_to_float(item.get("score", 0)))

    total = sum(scores)
    count = len(scores)
    avg = round(total / count, 2) if count > 0 else 0.0

    return {
        "avg_score": avg,
        "total_assignments": count,
        "total_score": round(total, 2),
    }


# ---------------------------------------------------------------------------
# General (individual) assignment stats
# ---------------------------------------------------------------------------

def _get_assignment_stats(user_id: str) -> Dict[str, Any]:
    """
    Return avg_score, total_assignments, total_score for all finalized general
    assignment submissions made by the user.

    Key pattern: PK=usub#{user_id}, SK begins_with ASSIGNMENT#
    """
    if assignments_table is None:
        return {"avg_score": 0.0, "total_assignments": 0, "total_score": 0.0}
    try:
        resp = assignments_table.query(
            KeyConditionExpression=(
                Key("PK").eq(f"usub#{user_id}")
                & Key("SK").begins_with("ASSIGNMENT#")
            )
        )
        items = resp.get("Items", [])
    except Exception:
        return {"avg_score": 0.0, "total_assignments": 0, "total_score": 0.0}

    scores: List[float] = []
    for item in items:
        if str(item.get("status", "")).lower() == "submitted":
            scores.append(_to_float(item.get("score", 0)))

    total = sum(scores)
    count = len(scores)
    avg = round(total / count, 2) if count > 0 else 0.0

    return {
        "avg_score": avg,
        "total_assignments": count,
        "total_score": round(total, 2),
    }


# ---------------------------------------------------------------------------
# Challenge rank helpers (safe — returns None when user has no submissions)
# ---------------------------------------------------------------------------

def _get_college_rank_safe(user_id: str, college_id: str) -> Optional[Dict[str, Any]]:
    try:
        return get_college_rank(user_id, college_id)
    except HTTPException:
        return None


def _get_global_rank_safe(user_id: str) -> Optional[Dict[str, Any]]:
    try:
        return get_global_rank(user_id)
    except HTTPException:
        return None


# ---------------------------------------------------------------------------
# Public dashboard aggregators
# ---------------------------------------------------------------------------

def get_college_student_dashboard(user_id: str, college_id: str) -> Dict[str, Any]:
    """Aggregate dashboard stats for a college student."""
    courses_enrolled = _get_courses_enrolled_count(user_id)
    interview_stats = _get_interview_stats(user_id)
    college_assignment_stats = _get_college_assignment_stats(user_id)
    college_rank_data = _get_college_rank_safe(user_id, college_id)

    return {
        "user_id": user_id,
        "college_id": college_id,
        "courses_enrolled": courses_enrolled,
        "interview_stats": {
            "avg_score": interview_stats["avg_score"],
            "total_interviews": interview_stats["total_interviews"],
            "total_score": interview_stats["total_score"],
        },
        "college_assignment_stats": {
            "avg_score": college_assignment_stats["avg_score"],
            "total_assignments": college_assignment_stats["total_assignments"],
            "total_score": college_assignment_stats["total_score"],
        },
        "challenge_rank": {
            "rank": college_rank_data["rank"] if college_rank_data else None,
            "total_score": college_rank_data["total_score"] if college_rank_data else 0,
            "total_users_in_college": college_rank_data["total_users"] if college_rank_data else 0,
        },
    }


def get_individual_student_dashboard(user_id: str) -> Dict[str, Any]:
    """Aggregate dashboard stats for an individual (non-college) student."""
    courses_enrolled = _get_courses_enrolled_count(user_id)
    interview_stats = _get_interview_stats(user_id)
    assignment_stats = _get_assignment_stats(user_id)
    global_rank_data = _get_global_rank_safe(user_id)

    return {
        "user_id": user_id,
        "courses_enrolled": courses_enrolled,
        "interview_stats": {
            "avg_score": interview_stats["avg_score"],
            "total_interviews": interview_stats["total_interviews"],
            "total_score": interview_stats["total_score"],
        },
        "assignment_stats": {
            "avg_score": assignment_stats["avg_score"],
            "total_assignments": assignment_stats["total_assignments"],
            "total_score": assignment_stats["total_score"],
        },
        "challenge_rank": {
            "rank": global_rank_data["rank"] if global_rank_data else None,
            "total_score": global_rank_data["total_score"] if global_rank_data else 0,
            "total_individual_users": global_rank_data["total_users"] if global_rank_data else 0,
        },
    }


# ---------------------------------------------------------------------------
# College student — pending (todo) assignments
# ---------------------------------------------------------------------------

def get_college_student_todo(user_id: str, college_id: str) -> Dict[str, Any]:
    """
    Return all college assignments that are:
      1. Belong to the student's college
      2. NOT locked (is_locked != True)
      3. Deadline has NOT passed (or no deadline set)
      4. The student has NOT submitted yet

    Each item includes days_remaining so the frontend can show urgency.
    """
    if college_assignments_table is None:
        return {"user_id": user_id, "college_id": college_id, "todo_count": 0, "assignments": []}

    # 1. Fetch all assignments for this college from the list index
    try:
        resp = college_assignments_table.query(
            KeyConditionExpression=(
                Key("PK").eq(f"COLLEGE_ASSIGN_LIST#{college_id}")
                & Key("SK").begins_with("CASSIGNMENT#")
            )
        )
        all_assignments = resp.get("Items", [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch college assignments: {e}")

    # 2. Fetch all submission SKs for this user (O(1) query, not a scan)
    submitted_ids: set = set()
    try:
        sub_resp = college_assignments_table.query(
            KeyConditionExpression=(
                Key("PK").eq(f"cusub#{user_id}")
                & Key("SK").begins_with("CASSIGNMENT#")
            ),
            ProjectionExpression="SK",
        )
        for item in sub_resp.get("Items", []):
            sk = str(item.get("SK", ""))
            # SK format: CASSIGNMENT#{assignment_id}
            if sk.startswith("CASSIGNMENT#"):
                submitted_ids.add(sk[len("CASSIGNMENT#"):])
    except Exception:
        pass  # if this fails we still show all pending

    now = _now_dt()
    todo: List[Dict[str, Any]] = []

    for a in all_assignments:
        assignment_id = str(a.get("assignment_id", ""))

        # Skip already submitted
        if assignment_id in submitted_ids:
            continue

        # Skip locked assignments
        if a.get("is_locked"):
            continue

        # Skip if deadline has passed
        deadline_raw = a.get("deadline")
        deadline_dt = _parse_dt_aware(deadline_raw)
        if deadline_dt is not None and deadline_dt < now:
            continue

        # Calculate days remaining (None when no deadline set)
        days_remaining: Optional[int] = None
        if deadline_dt is not None:
            delta = deadline_dt - now
            days_remaining = max(0, delta.days)

        # Urgency label
        if days_remaining is None:
            urgency = "no_deadline"
        elif days_remaining == 0:
            urgency = "due_today"
        elif days_remaining <= 2:
            urgency = "urgent"
        elif days_remaining <= 7:
            urgency = "this_week"
        else:
            urgency = "upcoming"

        todo.append(
            {
                "assignment_id": assignment_id,
                "title": str(a.get("title", "")),
                "course_name": str(a.get("course_name") or ""),
                "instructor_name": str(a.get("instructor_name") or ""),
                "level": str(a.get("level") or ""),
                "total_points": _to_int(a.get("total_points", 0)),
                "total_time_minutes": _to_int(a.get("total_time_minutes", 0)),
                "section_count": _to_int(a.get("section_count", 0)),
                "due_date": str(a.get("due_date") or ""),
                "deadline": str(deadline_raw or ""),
                "days_remaining": days_remaining,
                "urgency": urgency,
            }
        )

    # Sort: soonest deadline first; no-deadline items go last
    todo.sort(
        key=lambda x: (
            x["days_remaining"] is None,
            x["days_remaining"] if x["days_remaining"] is not None else 0,
        )
    )

    return {
        "user_id": user_id,
        "college_id": college_id,
        "todo_count": len(todo),
        "assignments": todo,
    }


# ---------------------------------------------------------------------------
# Weak areas helpers
# ---------------------------------------------------------------------------

# A question is "weak" when its AI score (0-10) is below this value
_INTERVIEW_WEAK_THRESHOLD = 5
# A section is "weak" when the student scored below this percentage
_ASSIGNMENT_WEAK_PCT = 60.0


def _collect_interview_weak_areas(user_id: str) -> List[Dict[str, Any]]:
    """
    Walk every completed interview session for user_id, gather question-level
    evaluations that scored below the threshold, and group by skill_gap text.

    Returns a list sorted by (occurrences desc, avg_score asc):
      [{ skill_gap, occurrences, avg_score, roles, sample_advice }, ...]
    """
    try:
        resp = table.query(
            IndexName="user-session-index",
            KeyConditionExpression=Key("user_id").eq(user_id),
        )
        metadata_items = [i for i in resp.get("Items", []) if i.get("SK") == "METADATA"]
    except Exception:
        return []

    # skill_gap (normalised) -> {scores, roles, advice}
    gap_map: Dict[str, Dict[str, Any]] = {}

    for meta in metadata_items:
        session_id = meta.get("session_id")
        role = str(meta.get("role") or "").strip()
        if not session_id:
            continue
        try:
            s_resp = table.query(
                KeyConditionExpression=Key("PK").eq(f"SESSION#{session_id}")
            )
            feedback = next(
                (i for i in s_resp.get("Items", []) if i.get("SK") == "FEEDBACK"),
                None,
            )
        except Exception:
            continue

        if not feedback:
            continue

        for qf in feedback.get("question_feedback") or []:
            evaluation = qf.get("evaluation") or {}
            score = _to_float(evaluation.get("score"), default=10.0)
            if score >= _INTERVIEW_WEAK_THRESHOLD:
                continue  # not weak

            raw_gap = str(evaluation.get("skill_gaps") or "").strip()
            if not raw_gap:
                continue
            key = raw_gap.lower()

            advice = str(evaluation.get("improvement_advice") or "").strip()

            if key not in gap_map:
                gap_map[key] = {
                    "skill_gap": raw_gap,
                    "scores": [],
                    "roles": set(),
                    "sample_advice": advice,
                }
            entry = gap_map[key]
            entry["scores"].append(score)
            if role:
                entry["roles"].add(role)
            if advice and not entry["sample_advice"]:
                entry["sample_advice"] = advice

    result = []
    for entry in gap_map.values():
        scores = entry["scores"]
        result.append(
            {
                "skill_gap": entry["skill_gap"],
                "occurrences": len(scores),
                "avg_score": round(sum(scores) / len(scores), 2),
                "roles": sorted(entry["roles"]),
                "sample_advice": entry["sample_advice"],
            }
        )

    # Sort: most frequent first, then lowest score first (worst problem on top)
    result.sort(key=lambda x: (-x["occurrences"], x["avg_score"]))
    return result


def _collect_assignment_section_weak_areas(
    user_id: str,
    pk_prefix: str,        # "usub#" or "cusub#"
    sk_prefix: str,        # "ASSIGNMENT#" or "CASSIGNMENT#"
    dynamo_table,          # assignments_table or college_assignments_table
    assignment_sk: str,    # "ASSIGNMENT" — the SK to look up assignment title
) -> List[Dict[str, Any]]:
    """
    Scan all finalised assignment submissions for the user and return sections
    where score_percentage < _ASSIGNMENT_WEAK_PCT.
    """
    if dynamo_table is None:
        return []

    try:
        resp = dynamo_table.query(
            KeyConditionExpression=(
                Key("PK").eq(f"{pk_prefix}{user_id}")
                & Key("SK").begins_with(sk_prefix)
            )
        )
        submissions = resp.get("Items", [])
    except Exception:
        return []

    # Batch-resolve assignment titles (1 get per unique assignment_id)
    assignment_id_set = {str(s.get("assignment_id", "")) for s in submissions if s.get("assignment_id")}
    title_map: Dict[str, str] = {}
    for aid in assignment_id_set:
        try:
            item = dynamo_table.get_item(
                Key={"PK": aid, "SK": assignment_sk}
            ).get("Item")
            title_map[aid] = str(item.get("title", "")) if item else ""
        except Exception:
            title_map[aid] = ""

    weak: List[Dict[str, Any]] = []
    for sub in submissions:
        if str(sub.get("status", "")).lower() != "submitted":
            continue
        assignment_id = str(sub.get("assignment_id", ""))
        assignment_title = title_map.get(assignment_id, "")

        section_results = sub.get("section_results") or []
        if isinstance(section_results, str):
            import json as _json
            try:
                section_results = _json.loads(section_results)
            except Exception:
                section_results = []

        for sec in section_results:
            score = _to_float(sec.get("score", 0))
            total = _to_float(sec.get("total_points", 0))
            if total <= 0:
                continue
            pct = round(score / total * 100, 2)
            if pct >= _ASSIGNMENT_WEAK_PCT:
                continue  # not weak

            weak.append(
                {
                    "assignment_id": assignment_id,
                    "assignment_title": assignment_title,
                    "section_title": str(sec.get("section_title") or ""),
                    "score": int(score),
                    "total_points": int(total),
                    "score_percentage": pct,
                }
            )

    # Sort worst section first
    weak.sort(key=lambda x: x["score_percentage"])
    return weak


# ---------------------------------------------------------------------------
# Public weak-area aggregators
# ---------------------------------------------------------------------------

def get_individual_weak_areas(user_id: str) -> Dict[str, Any]:
    """Weak areas for an individual student."""
    interview_weak = _collect_interview_weak_areas(user_id)
    assignment_weak = _collect_assignment_section_weak_areas(
        user_id=user_id,
        pk_prefix="usub#",
        sk_prefix="ASSIGNMENT#",
        dynamo_table=assignments_table,
        assignment_sk="ASSIGNMENT",
    )
    return {
        "user_id": user_id,
        "interview_weak_areas": interview_weak,
        "assignment_weak_areas": assignment_weak,
        "thresholds": {
            "interview_weak_below_score": _INTERVIEW_WEAK_THRESHOLD,
            "assignment_weak_below_pct": _ASSIGNMENT_WEAK_PCT,
        },
    }


def get_college_weak_areas(user_id: str, college_id: str) -> Dict[str, Any]:
    """Weak areas for a college student."""
    interview_weak = _collect_interview_weak_areas(user_id)
    assignment_weak = _collect_assignment_section_weak_areas(
        user_id=user_id,
        pk_prefix="cusub#",
        sk_prefix="CASSIGNMENT#",
        dynamo_table=college_assignments_table,
        assignment_sk="ASSIGNMENT",
    )
    return {
        "user_id": user_id,
        "college_id": college_id,
        "interview_weak_areas": interview_weak,
        "college_assignment_weak_areas": assignment_weak,
        "thresholds": {
            "interview_weak_below_score": _INTERVIEW_WEAK_THRESHOLD,
            "assignment_weak_below_pct": _ASSIGNMENT_WEAK_PCT,
        },
    }


# ---------------------------------------------------------------------------
# Roadmap overall progress (only roadmaps the user has started)
# ---------------------------------------------------------------------------

def get_user_roadmap_progress(user_id: str) -> Dict[str, Any]:
    """
    Return one card per roadmap the user has started their journey on.

    A "started" roadmap = the user has a ROADMAP_PROGRESS# record in the
    course_enrollments_table (PK=USER#{user_id}).

    For each started roadmap we compute:
      - roadmap_id, name
      - overall_progress_percentage  (0-100)
      - total_stages   (total topics across all milestones)
      - completed_stages
    """
    if course_enrollments_table is None or _rm_tbl is None:
        return {"user_id": user_id, "roadmaps": []}

    # 1. Find all roadmaps the user has started
    try:
        resp = course_enrollments_table.query(
            KeyConditionExpression=(
                Key("PK").eq(f"USER#{user_id}")
                & Key("SK").begins_with("ROADMAP_PROGRESS#")
            )
        )
        progress_records = resp.get("Items", [])
    except Exception:
        return {"user_id": user_id, "roadmaps": []}

    if not progress_records:
        return {"user_id": user_id, "roadmaps": []}

    roadmaps: List[Dict[str, Any]] = []

    for record in progress_records:
        sk = str(record.get("SK", ""))
        # SK format: ROADMAP_PROGRESS#{roadmap_id}
        if not sk.startswith("ROADMAP_PROGRESS#"):
            continue
        roadmap_id = sk[len("ROADMAP_PROGRESS#"):]
        if not roadmap_id:
            continue

        # 2. Fetch roadmap metadata for name + milestones
        try:
            meta_resp = _rm_tbl.get_item(
                Key={"PK": f"ROADMAP#{roadmap_id}", "SK": "META"}
            )
            meta = meta_resp.get("Item")
        except Exception:
            meta = None

        if not meta:
            continue

        name = str(meta.get("name") or "")
        milestones_raw = meta.get("milestones") or []

        # 3. Count total and completed topics across all milestones
        #    Completion: enumerate every topic; check course progress if linked,
        #    fall back to manual_completed_ids from the progress record.
        manual_ids = set(record.get("completed_topic_ids") or [])

        total_stages = 0
        completed_stages = 0

        for milestone in milestones_raw:
            for topic in milestone.get("topics") or []:
                total_stages += 1
                cid = topic.get("linked_course_id")
                mid = topic.get("linked_module_id")
                tid = topic.get("linked_topic_id")
                rtid = str(topic.get("roadmap_topic_id") or "")

                if cid and mid and tid:
                    # Check live course topic progress
                    try:
                        prog_resp = course_enrollments_table.get_item(
                            Key={
                                "PK": f"USER#{user_id}#COURSE#{cid}",
                                "SK": f"TOPIC_PROGRESS#MODULE#{mid}#TOPIC#{tid}",
                            }
                        )
                        prog_item = prog_resp.get("Item")
                        status = str(prog_item.get("status", "") if prog_item else "").upper()
                        if status in {"ENDED", "COMPLETED"}:
                            completed_stages += 1
                    except Exception:
                        pass
                elif cid and tid:
                    # module_id unknown — scan all modules of this course for the topic
                    try:
                        scan_resp = course_enrollments_table.query(
                            KeyConditionExpression=(
                                Key("PK").eq(f"USER#{user_id}#COURSE#{cid}")
                                & Key("SK").begins_with("TOPIC_PROGRESS#MODULE#")
                            ),
                            FilterExpression=Key("SK").begins_with(
                                f"TOPIC_PROGRESS#MODULE#"  # broad match, filter below
                            ),
                            ProjectionExpression="SK, #s",
                            ExpressionAttributeNames={"#s": "status"},
                        )
                        for pi in scan_resp.get("Items", []):
                            if f"#TOPIC#{tid}" in str(pi.get("SK", "")):
                                if str(pi.get("status", "")).upper() in {"ENDED", "COMPLETED"}:
                                    completed_stages += 1
                                    break
                    except Exception:
                        pass
                else:
                    # No course link — rely on manual completion record
                    if rtid in manual_ids:
                        completed_stages += 1

        pct = round(completed_stages / total_stages * 100) if total_stages > 0 else 0

        roadmaps.append(
            {
                "roadmap_id": roadmap_id,
                "name": name,
                "overall_progress_percentage": pct,
                "total_stages": total_stages,
                "completed_stages": completed_stages,
            }
        )

    # Sort by progress descending (most advanced first)
    roadmaps.sort(key=lambda x: -x["overall_progress_percentage"])

    return {"user_id": user_id, "roadmaps": roadmaps}

