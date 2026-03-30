import time
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from boto3.dynamodb.conditions import Key
from fastapi import HTTPException

from app.dynamo import (
    roadmaps_table as _rm_tbl,
    courses_table as _courses_tbl,
    course_enrollments_table as _enroll_tbl,
)


# ---------------------------------------------------------------------------
# Table guards
# ---------------------------------------------------------------------------

def _rmt():
    if _rm_tbl is None:
        raise HTTPException(
            status_code=500,
            detail="Roadmaps table not configured. Set DYNAMODB_TABLE7 or DYNAMODB_ROADMAPS_TABLE.",
        )
    return _rm_tbl


def _ct():
    if _courses_tbl is None:
        raise HTTPException(status_code=500, detail="Courses table not configured")
    return _courses_tbl


def _et():
    if _enroll_tbl is None:
        raise HTTPException(status_code=500, detail="Enrollments table not configured")
    return _enroll_tbl


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------

def _now() -> int:
    return int(time.time() * 1000)


def _roadmap_pk(roadmap_id: str) -> str:
    return f"ROADMAP#{roadmap_id}"


def _user_pk(user_id: str) -> str:
    return f"USER#{user_id}"


def _user_course_pk(user_id: str, course_id: str) -> str:
    return f"USER#{user_id}#COURSE#{course_id}"


def _roadmap_progress_sk(roadmap_id: str) -> str:
    return f"ROADMAP_PROGRESS#{roadmap_id}"


# ---------------------------------------------------------------------------
# DynamoDB record builders
# ---------------------------------------------------------------------------

def _build_roadmap_topic(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "roadmap_topic_id": f"rtopic_{uuid.uuid4().hex[:8]}",
        "title": str(data.get("title") or ""),
        "description": str(data.get("description") or ""),
        "duration_minutes": int(data.get("duration_minutes") or 0),
        "linked_course_id": data.get("linked_course_id") or None,
        "linked_module_id": data.get("linked_module_id") or None,
        "linked_topic_id": data.get("linked_topic_id") or None,
    }


def _build_milestone(data: Dict[str, Any], order: int) -> Dict[str, Any]:
    topics = [_build_roadmap_topic(t) for t in data.get("topics", [])]
    return {
        "milestone_id": f"mile_{uuid.uuid4().hex[:8]}",
        "step_order": int(data.get("step_order") or order),
        "title": str(data.get("title") or "").strip(),
        "description": str(data.get("description") or ""),
        "topics": topics,
    }


def _career_from_payload(career_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not career_data:
        return {
            "stats": {"job_growth": "", "new_jobs_per_year": "", "entry_salary": "", "senior_salary": ""},
            "responsibilities": [],
            "day_in_the_life": "",
            "salary_breakdown": [],
            "top_companies": [],
            "technologies": [],
        }
    stats_raw = career_data.get("stats") or {}
    return {
        "stats": {
            "job_growth": str(stats_raw.get("job_growth") or ""),
            "new_jobs_per_year": str(stats_raw.get("new_jobs_per_year") or ""),
            "entry_salary": str(stats_raw.get("entry_salary") or ""),
            "senior_salary": str(stats_raw.get("senior_salary") or ""),
        },
        "responsibilities": list(career_data.get("responsibilities") or []),
        "day_in_the_life": str(career_data.get("day_in_the_life") or ""),
        "salary_breakdown": [
            {"level": str(s.get("level") or ""), "amount": str(s.get("amount") or "")}
            for s in (career_data.get("salary_breakdown") or [])
        ],
        "top_companies": list(career_data.get("top_companies") or []),
        "technologies": list(career_data.get("technologies") or []),
    }


# ---------------------------------------------------------------------------
# Fetch topic detail from courses table (live)
# ---------------------------------------------------------------------------

def _fetch_course_topic(course_id: str, module_id: str, topic_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a single topic item from the Courses table."""
    try:
        resp = _ct().get_item(
            Key={
                "PK": f"COURSE#{course_id}",
                "SK": f"MODULE#{module_id}#TOPIC#{topic_id}",
            }
        )
        return resp.get("Item")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Build enriched milestone list with optional user progress
# ---------------------------------------------------------------------------

def _build_milestones_enriched(
    milestones: List[Dict[str, Any]],
    user_id: Optional[str] = None,
    manual_completed_ids: Optional[Set[str]] = None,
    include_progress: bool = False,
) -> Tuple[List[Dict[str, Any]], int, int]:
    """
    Returns (enriched_milestones, grand_total_topics, grand_completed_topics).

    When user_id is given and include_progress=True, each topic gets is_completed
    derived live from the enrollments table. Topics linked to a course use
    TOPIC_PROGRESS records; unlinked topics fall back to manual_completed_ids.

    Batches progress queries per (course_id, module_id) pair.
    """
    # Collect unique (course_id, module_id) pairs and unique course IDs
    # Also collect courses whose topics have no module_id — need a full-course scan
    course_module_pairs: Set[Tuple[str, str]] = set()
    no_module_course_ids: Set[str] = set()   # courses where at least one topic has no module_id
    unique_course_ids: Set[str] = set()
    if user_id and include_progress:
        for m in milestones:
            for t in m.get("topics", []):
                cid = t.get("linked_course_id")
                mid = t.get("linked_module_id")
                if cid and mid:
                    course_module_pairs.add((cid, mid))
                elif cid:
                    no_module_course_ids.add(cid)
                if cid:
                    unique_course_ids.add(cid)

    # Check which courses this user is enrolled in
    enrolled_courses: Set[str] = set()
    for cid in unique_course_ids:
        try:
            resp = _et().get_item(
                Key={"PK": _user_pk(user_id), "SK": f"ENROLLMENT#COURSE#{cid}"}
            )
            if resp.get("Item"):
                enrolled_courses.add(cid)
        except Exception:
            pass

    # Fetch progress maps per (course_id, module_id) — only for enrolled courses
    # progress_cache[(cid, mid)][topic_id] = status string
    progress_cache: Dict[Tuple[str, str], Dict[str, str]] = {}
    for cid, mid in course_module_pairs:
        if cid not in enrolled_courses:
            continue  # skip — user not enrolled, no point querying progress
        try:
            resp = _et().query(
                KeyConditionExpression=(
                    Key("PK").eq(_user_course_pk(user_id, cid))
                    & Key("SK").begins_with(f"TOPIC_PROGRESS#MODULE#{mid}#TOPIC#")
                )
            )
            prog_map: Dict[str, str] = {}
            for item in resp.get("Items", []):
                sk = str(item.get("SK") or "")
                if "#TOPIC#" in sk:
                    tid = sk.split("#TOPIC#")[-1]
                    prog_map[tid] = str(item.get("status") or "").upper()
            progress_cache[(cid, mid)] = prog_map
        except Exception:
            progress_cache[(cid, mid)] = {}

    # For topics with no module_id, fetch ALL topic progress for the course (all modules)
    # no_module_cache[cid][topic_id] = status string
    no_module_cache: Dict[str, Dict[str, str]] = {}
    for cid in no_module_course_ids:
        if cid not in enrolled_courses:
            continue
        try:
            resp = _et().query(
                KeyConditionExpression=(
                    Key("PK").eq(_user_course_pk(user_id, cid))
                    & Key("SK").begins_with("TOPIC_PROGRESS#MODULE#")
                )
            )
            flat_map: Dict[str, str] = {}
            for item in resp.get("Items", []):
                sk = str(item.get("SK") or "")
                if "#TOPIC#" in sk:
                    tid = sk.split("#TOPIC#")[-1]
                    status = str(item.get("status") or "").upper()
                    # Keep the best status if the same topic appears in multiple modules
                    existing = flat_map.get(tid, "")
                    if status in {"ENDED", "COMPLETED"} or not existing:
                        flat_map[tid] = status
            no_module_cache[cid] = flat_map
        except Exception:
            no_module_cache[cid] = {}

    # Collect unique (course_id, module_id, topic_id) for topic detail fetch
    topic_keys: Set[Tuple[str, str, str]] = set()
    for m in milestones:
        for t in m.get("topics", []):
            cid = t.get("linked_course_id")
            mid = t.get("linked_module_id")
            tid = t.get("linked_topic_id")
            if cid and mid and tid:
                topic_keys.add((cid, mid, tid))

    # Fetch topic details from courses table
    topic_detail_cache: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for cid, mid, tid in topic_keys:
        item = _fetch_course_topic(cid, mid, tid)
        topic_detail_cache[(cid, mid, tid)] = item or {}

    # Build enriched milestones sorted by step_order
    enriched: List[Dict[str, Any]] = []
    grand_total = 0
    grand_completed = 0

    for milestone in sorted(milestones, key=lambda x: int(x.get("step_order") or 0)):
        topics_raw = milestone.get("topics", [])
        total_duration = 0
        completed_count = 0
        enriched_topics: List[Dict[str, Any]] = []

        for t in topics_raw:
            rtopic_id = str(t.get("roadmap_topic_id") or "")
            cid = t.get("linked_course_id")
            mid = t.get("linked_module_id")
            tid = t.get("linked_topic_id")

            # Prefer live course data; fall back to stored values
            title = str(t.get("title") or "")
            description = str(t.get("description") or "")
            duration_minutes = int(t.get("duration_minutes") or 0)

            if cid and mid and tid:
                detail = topic_detail_cache.get((cid, mid, tid), {})
                if detail:
                    title = str(detail.get("title") or title)
                    description = str(detail.get("description") or description)
                    duration_minutes = int(detail.get("duration_minutes") or duration_minutes)

            is_completed = False
            course_enrolled = True
            enrollment_message = ""

            if include_progress and user_id:
                if cid and tid:
                    if cid not in enrolled_courses:
                        # User has not enrolled in the linked course
                        course_enrolled = False
                        enrollment_message = "Enroll in this course to complete this topic"
                    elif mid:
                        # Normal path — module_id is known
                        status = progress_cache.get((cid, mid), {}).get(tid, "")
                        is_completed = status in {"ENDED", "COMPLETED"}
                    else:
                        # module_id not stored on roadmap topic — scan all modules
                        status = no_module_cache.get(cid, {}).get(tid, "")
                        is_completed = status in {"ENDED", "COMPLETED"}
                elif manual_completed_ids:
                    is_completed = rtopic_id in manual_completed_ids

            total_duration += duration_minutes
            if is_completed:
                completed_count += 1

            enriched_topics.append({
                "roadmap_topic_id": rtopic_id,
                "title": title,
                "description": description,
                "duration_minutes": duration_minutes,
                "course_id": cid,
                "module_id": mid,
                "topic_id": tid,
                "is_completed": is_completed,
                "course_enrolled": course_enrolled,
                "enrollment_message": enrollment_message,
            })

        total = len(topics_raw)
        pct = round(completed_count / total * 100) if total > 0 else 0

        grand_total += total
        grand_completed += completed_count

        milestone_out: Dict[str, Any] = {
            "milestone_id": str(milestone.get("milestone_id") or ""),
            "title": str(milestone.get("title") or ""),
            "description": str(milestone.get("description") or ""),
            "step_order": int(milestone.get("step_order") or 0),
            "duration_minutes": total_duration,
            "total_topics": total,
            "topics": enriched_topics,
        }
        if include_progress:
            milestone_out["completed_topics"] = completed_count
            milestone_out["progress_percentage"] = pct

        enriched.append(milestone_out)

    return enriched, grand_total, grand_completed


def _build_overview_milestones(milestones: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build simplified milestone list for the static overview response."""
    enriched, _, _ = _build_milestones_enriched(milestones, include_progress=False)
    return enriched


# ---------------------------------------------------------------------------
# Persist milestones helper
# ---------------------------------------------------------------------------

def _persist_milestones(roadmap_id: str, milestones: List[Dict[str, Any]]) -> None:
    count = len(milestones)
    now = _now()
    _rmt().update_item(
        Key={"PK": _roadmap_pk(roadmap_id), "SK": "META"},
        UpdateExpression="SET milestones = :m, milestone_count = :c, updated_at = :t",
        ExpressionAttributeValues={":m": milestones, ":c": count, ":t": now},
    )
    _rmt().update_item(
        Key={"PK": "ROADMAP_LIST", "SK": f"ROADMAP#{roadmap_id}"},
        UpdateExpression="SET milestone_count = :c",
        ExpressionAttributeValues={":c": count},
    )


# ===========================================================================
# Admin — Roadmap CRUD
# ===========================================================================

def admin_create_roadmap(payload: Dict[str, Any]) -> Dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    roadmap_id = f"rm_{uuid.uuid4().hex[:10]}"
    now = _now()

    empty_career = _career_from_payload(None)

    meta: Dict[str, Any] = {
        "PK": _roadmap_pk(roadmap_id),
        "SK": "META",
        "roadmap_id": roadmap_id,
        "name": name,
        "tagline": str(payload.get("tagline") or ""),
        "description": str(payload.get("description") or ""),
        "icon": str(payload.get("icon") or ""),
        "icon_bg": str(payload.get("icon_bg") or ""),
        "finish_attire": str(payload.get("finish_attire") or ""),
        "career": empty_career,
        "milestones": [],
        "milestone_count": 0,
        "created_at": now,
        "updated_at": now,
    }

    list_item: Dict[str, Any] = {
        "PK": "ROADMAP_LIST",
        "SK": f"ROADMAP#{roadmap_id}",
        "roadmap_id": roadmap_id,
        "name": name,
        "tagline": str(payload.get("tagline") or ""),
        "icon": str(payload.get("icon") or ""),
        "icon_bg": str(payload.get("icon_bg") or ""),
        "milestone_count": 0,
        "created_at": now,
    }

    _rmt().put_item(Item=meta)
    _rmt().put_item(Item=list_item)

    return {"status": "CREATED", "roadmap_id": roadmap_id, "message": "Roadmap created successfully"}


def admin_list_roadmaps() -> Dict[str, Any]:
    resp = _rmt().query(KeyConditionExpression=Key("PK").eq("ROADMAP_LIST"))
    items = resp.get("Items", [])
    roadmaps = [
        {
            "roadmap_id": str(i.get("roadmap_id") or ""),
            "name": str(i.get("name") or ""),
            "tagline": str(i.get("tagline") or ""),
            "icon": str(i.get("icon") or ""),
            "icon_bg": str(i.get("icon_bg") or ""),
            "milestone_count": int(i.get("milestone_count") or 0),
        }
        for i in items
    ]
    return {"total_count": len(roadmaps), "roadmaps": roadmaps}


def admin_get_roadmap(roadmap_id: str) -> Dict[str, Any]:
    meta = _get_roadmap_meta(roadmap_id)
    milestones = _build_overview_milestones(meta.get("milestones") or [])
    career_raw = meta.get("career") or {}
    return {
        "roadmap_id": roadmap_id,
        "name": str(meta.get("name") or ""),
        "tagline": str(meta.get("tagline") or ""),
        "description": str(meta.get("description") or ""),
        "icon": str(meta.get("icon") or ""),
        "icon_bg": str(meta.get("icon_bg") or ""),
        "finish_attire": str(meta.get("finish_attire") or ""),
        "milestone_count": int(meta.get("milestone_count") or 0),
        "career": _normalise_career(career_raw),
        "milestones": milestones,
        "created_at": int(meta.get("created_at") or 0),
        "updated_at": int(meta.get("updated_at") or 0),
    }


def admin_update_roadmap(roadmap_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    _get_roadmap_meta(roadmap_id)  # 404 if missing

    set_parts = ["updated_at = :t"]
    expr_vals: Dict[str, Any] = {":t": _now()}

    simple_fields = ["name", "tagline", "description", "icon", "icon_bg", "finish_attire"]
    for field in simple_fields:
        if field in updates and updates[field] is not None:
            set_parts.append(f"{field} = :{field}")
            expr_vals[f":{field}"] = str(updates[field])

    if "career" in updates and updates["career"] is not None:
        set_parts.append("career = :career")
        expr_vals[":career"] = _career_from_payload(updates["career"])

    if len(set_parts) == 1:
        return {"status": "NO_CHANGE", "roadmap_id": roadmap_id, "message": "Nothing to update"}

    _rmt().update_item(
        Key={"PK": _roadmap_pk(roadmap_id), "SK": "META"},
        UpdateExpression="SET " + ", ".join(set_parts),
        ExpressionAttributeValues=expr_vals,
    )

    # Sync name to list item if name changed
    if "name" in updates:
        _rmt().update_item(
            Key={"PK": "ROADMAP_LIST", "SK": f"ROADMAP#{roadmap_id}"},
            UpdateExpression="SET #n = :name",
            ExpressionAttributeNames={"#n": "name"},
            ExpressionAttributeValues={":name": str(updates["name"])},
        )

    return {"status": "UPDATED", "roadmap_id": roadmap_id, "message": "Roadmap updated"}


def admin_delete_roadmap(roadmap_id: str) -> Dict[str, Any]:
    _get_roadmap_meta(roadmap_id)
    _rmt().delete_item(Key={"PK": _roadmap_pk(roadmap_id), "SK": "META"})
    _rmt().delete_item(Key={"PK": "ROADMAP_LIST", "SK": f"ROADMAP#{roadmap_id}"})
    return {"status": "DELETED", "roadmap_id": roadmap_id, "message": "Roadmap deleted"}


# ===========================================================================
# Admin — Career sub-section helpers
# ===========================================================================

def _get_career(roadmap_id: str) -> Dict[str, Any]:
    meta = _get_roadmap_meta(roadmap_id)
    return dict(meta.get("career") or _career_from_payload(None))


def _save_career(roadmap_id: str, career: Dict[str, Any]) -> None:
    _rmt().update_item(
        Key={"PK": _roadmap_pk(roadmap_id), "SK": "META"},
        UpdateExpression="SET career = :c, updated_at = :t",
        ExpressionAttributeValues={":c": career, ":t": _now()},
    )


# Career stats — PUT (replace all 4 fields)
def admin_update_career_stats(roadmap_id: str, stats: Dict[str, Any]) -> Dict[str, Any]:
    career = _get_career(roadmap_id)
    career["stats"] = {
        "job_growth": str(stats.get("job_growth") or ""),
        "new_jobs_per_year": str(stats.get("new_jobs_per_year") or ""),
        "entry_salary": str(stats.get("entry_salary") or ""),
        "senior_salary": str(stats.get("senior_salary") or ""),
    }
    _save_career(roadmap_id, career)
    return {"status": "UPDATED", "roadmap_id": roadmap_id, "message": "Career stats updated"}


# Day in the life — PUT
def admin_update_day_in_life(roadmap_id: str, text: str) -> Dict[str, Any]:
    career = _get_career(roadmap_id)
    career["day_in_the_life"] = str(text or "")
    _save_career(roadmap_id, career)
    return {"status": "UPDATED", "roadmap_id": roadmap_id, "message": "Day in the life updated"}


# Responsibilities — add / delete by value
def admin_add_responsibility(roadmap_id: str, value: str) -> Dict[str, Any]:
    career = _get_career(roadmap_id)
    items: List[str] = list(career.get("responsibilities") or [])
    if value in items:
        raise HTTPException(status_code=400, detail="Responsibility already exists")
    items.append(value)
    career["responsibilities"] = items
    _save_career(roadmap_id, career)
    return {"status": "CREATED", "roadmap_id": roadmap_id, "message": "Responsibility added"}


def admin_delete_responsibility(roadmap_id: str, value: str) -> Dict[str, Any]:
    career = _get_career(roadmap_id)
    items: List[str] = [r for r in (career.get("responsibilities") or []) if r != value]
    career["responsibilities"] = items
    _save_career(roadmap_id, career)
    return {"status": "DELETED", "roadmap_id": roadmap_id, "message": "Responsibility removed"}


# Technologies — add / delete by value
def admin_add_technology(roadmap_id: str, value: str) -> Dict[str, Any]:
    career = _get_career(roadmap_id)
    items: List[str] = list(career.get("technologies") or [])
    if value in items:
        raise HTTPException(status_code=400, detail="Technology already exists")
    items.append(value)
    career["technologies"] = items
    _save_career(roadmap_id, career)
    return {"status": "CREATED", "roadmap_id": roadmap_id, "message": "Technology added"}


def admin_delete_technology(roadmap_id: str, value: str) -> Dict[str, Any]:
    career = _get_career(roadmap_id)
    items: List[str] = [t for t in (career.get("technologies") or []) if t != value]
    career["technologies"] = items
    _save_career(roadmap_id, career)
    return {"status": "DELETED", "roadmap_id": roadmap_id, "message": "Technology removed"}


# Top companies — add / delete by value
def admin_add_top_company(roadmap_id: str, value: str) -> Dict[str, Any]:
    career = _get_career(roadmap_id)
    items: List[str] = list(career.get("top_companies") or [])
    if value in items:
        raise HTTPException(status_code=400, detail="Company already exists")
    items.append(value)
    career["top_companies"] = items
    _save_career(roadmap_id, career)
    return {"status": "CREATED", "roadmap_id": roadmap_id, "message": "Company added"}


def admin_delete_top_company(roadmap_id: str, value: str) -> Dict[str, Any]:
    career = _get_career(roadmap_id)
    items: List[str] = [c for c in (career.get("top_companies") or []) if c != value]
    career["top_companies"] = items
    _save_career(roadmap_id, career)
    return {"status": "DELETED", "roadmap_id": roadmap_id, "message": "Company removed"}


# Salary breakdown — add / update by level / delete by level
def admin_add_salary_row(roadmap_id: str, level: str, amount: str) -> Dict[str, Any]:
    career = _get_career(roadmap_id)
    rows: List[Dict[str, str]] = list(career.get("salary_breakdown") or [])
    if any(r.get("level") == level for r in rows):
        raise HTTPException(status_code=400, detail=f"Salary row for '{level}' already exists")
    rows.append({"level": level, "amount": amount})
    career["salary_breakdown"] = rows
    _save_career(roadmap_id, career)
    return {"status": "CREATED", "roadmap_id": roadmap_id, "message": "Salary row added"}


def admin_update_salary_row(roadmap_id: str, level: str, amount: str) -> Dict[str, Any]:
    career = _get_career(roadmap_id)
    rows: List[Dict[str, str]] = list(career.get("salary_breakdown") or [])
    idx = next((i for i, r in enumerate(rows) if r.get("level") == level), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"Salary row for '{level}' not found")
    rows[idx]["amount"] = amount
    career["salary_breakdown"] = rows
    _save_career(roadmap_id, career)
    return {"status": "UPDATED", "roadmap_id": roadmap_id, "message": "Salary row updated"}


def admin_delete_salary_row(roadmap_id: str, level: str) -> Dict[str, Any]:
    career = _get_career(roadmap_id)
    rows: List[Dict[str, str]] = [r for r in (career.get("salary_breakdown") or []) if r.get("level") != level]
    career["salary_breakdown"] = rows
    _save_career(roadmap_id, career)
    return {"status": "DELETED", "roadmap_id": roadmap_id, "message": "Salary row removed"}


# ===========================================================================
# Admin — Milestone CRUD
# ===========================================================================

def admin_add_milestone(roadmap_id: str, milestone_data: Dict[str, Any]) -> Dict[str, Any]:
    meta = _get_roadmap_meta(roadmap_id)
    milestones = list(meta.get("milestones") or [])
    max_order = max((int(m.get("step_order") or 0) for m in milestones), default=0)
    new_milestone = _build_milestone(milestone_data, order=max_order + 1)
    milestones.append(new_milestone)
    _persist_milestones(roadmap_id, milestones)
    return {
        "status": "CREATED",
        "roadmap_id": roadmap_id,
        "milestone_id": new_milestone["milestone_id"],
        "message": "Milestone added",
    }


def admin_update_milestone(
    roadmap_id: str, milestone_id: str, updates: Dict[str, Any]
) -> Dict[str, Any]:
    meta = _get_roadmap_meta(roadmap_id)
    milestones = list(meta.get("milestones") or [])
    idx = next((i for i, m in enumerate(milestones) if m.get("milestone_id") == milestone_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Milestone not found")
    for field in ["title", "description", "step_order"]:
        if field in updates and updates[field] is not None:
            milestones[idx][field] = updates[field]
    _persist_milestones(roadmap_id, milestones)
    return {"status": "UPDATED", "roadmap_id": roadmap_id, "milestone_id": milestone_id, "message": "Milestone updated"}


def admin_delete_milestone(roadmap_id: str, milestone_id: str) -> Dict[str, Any]:
    meta = _get_roadmap_meta(roadmap_id)
    milestones = [m for m in (meta.get("milestones") or []) if m.get("milestone_id") != milestone_id]
    if len(milestones) == len(meta.get("milestones") or []):
        raise HTTPException(status_code=404, detail="Milestone not found")
    _persist_milestones(roadmap_id, milestones)
    return {"status": "DELETED", "roadmap_id": roadmap_id, "milestone_id": milestone_id, "message": "Milestone deleted"}


# ===========================================================================
# Admin — Milestone topic CRUD
# ===========================================================================

def admin_add_milestone_topic(
    roadmap_id: str, milestone_id: str, topic_data: Dict[str, Any]
) -> Dict[str, Any]:
    meta = _get_roadmap_meta(roadmap_id)
    milestones = list(meta.get("milestones") or [])
    idx = next((i for i, m in enumerate(milestones) if m.get("milestone_id") == milestone_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Milestone not found")
    new_topic = _build_roadmap_topic(topic_data)
    milestones[idx].setdefault("topics", []).append(new_topic)
    _persist_milestones(roadmap_id, milestones)
    return {
        "status": "CREATED",
        "roadmap_id": roadmap_id,
        "milestone_id": milestone_id,
        "roadmap_topic_id": new_topic["roadmap_topic_id"],
        "message": "Topic added to milestone",
    }


def admin_update_milestone_topic(
    roadmap_id: str, milestone_id: str, roadmap_topic_id: str, updates: Dict[str, Any]
) -> Dict[str, Any]:
    meta = _get_roadmap_meta(roadmap_id)
    milestones = list(meta.get("milestones") or [])
    idx = next((i for i, m in enumerate(milestones) if m.get("milestone_id") == milestone_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Milestone not found")
    topics = list(milestones[idx].get("topics") or [])
    tidx = next((i for i, t in enumerate(topics) if t.get("roadmap_topic_id") == roadmap_topic_id), None)
    if tidx is None:
        raise HTTPException(status_code=404, detail="Topic not found in milestone")
    for field in ["title", "description", "duration_minutes", "linked_course_id", "linked_module_id", "linked_topic_id"]:
        if field in updates and updates[field] is not None:
            topics[tidx][field] = updates[field]
    milestones[idx]["topics"] = topics
    _persist_milestones(roadmap_id, milestones)
    return {
        "status": "UPDATED",
        "roadmap_id": roadmap_id,
        "milestone_id": milestone_id,
        "roadmap_topic_id": roadmap_topic_id,
        "message": "Topic updated",
    }


def admin_delete_milestone_topic(
    roadmap_id: str, milestone_id: str, roadmap_topic_id: str
) -> Dict[str, Any]:
    meta = _get_roadmap_meta(roadmap_id)
    milestones = list(meta.get("milestones") or [])
    idx = next((i for i, m in enumerate(milestones) if m.get("milestone_id") == milestone_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Milestone not found")
    topics = [t for t in (milestones[idx].get("topics") or []) if t.get("roadmap_topic_id") != roadmap_topic_id]
    milestones[idx]["topics"] = topics
    _persist_milestones(roadmap_id, milestones)
    return {
        "status": "DELETED",
        "roadmap_id": roadmap_id,
        "milestone_id": milestone_id,
        "roadmap_topic_id": roadmap_topic_id,
        "message": "Topic removed from milestone",
    }


# ===========================================================================
# User — List all roadmaps (public)
# ===========================================================================

def user_list_roadmaps() -> Dict[str, Any]:
    resp = _rmt().query(KeyConditionExpression=Key("PK").eq("ROADMAP_LIST"))
    items = resp.get("Items", [])
    roadmaps = [
        {
            "roadmap_id": str(i.get("roadmap_id") or ""),
            "name": str(i.get("name") or ""),
            "tagline": str(i.get("tagline") or ""),
            "milestone_count": int(i.get("milestone_count") or 0),
            "icon": str(i.get("icon") or ""),
            "icon_bg": str(i.get("icon_bg") or ""),
        }
        for i in items
    ]
    return {"total_count": len(roadmaps), "roadmaps": roadmaps}


# ===========================================================================
# User — Roadmap overview (static, no user progress)
# ===========================================================================

def user_get_roadmap_overview(roadmap_id: str) -> Dict[str, Any]:
    meta = _get_roadmap_meta(roadmap_id)
    milestones = _build_overview_milestones(meta.get("milestones") or [])
    career_raw = meta.get("career") or {}
    return {
        "roadmap_id": roadmap_id,
        "name": str(meta.get("name") or ""),
        "tagline": str(meta.get("tagline") or ""),
        "description": str(meta.get("description") or ""),
        "icon": str(meta.get("icon") or ""),
        "icon_bg": str(meta.get("icon_bg") or ""),
        "finish_attire": str(meta.get("finish_attire") or ""),
        "milestone_count": int(meta.get("milestone_count") or 0),
        "career": _normalise_career(career_raw),
        "milestones": milestones,
    }


# ===========================================================================
# User — Get roadmap progress (per-milestone)
# ===========================================================================

def user_get_roadmap_progress(roadmap_id: str, user_id: str) -> Dict[str, Any]:
    meta = _get_roadmap_meta(roadmap_id)

    enroll = _et().get_item(
        Key={"PK": _user_pk(user_id), "SK": _roadmap_progress_sk(roadmap_id)}
    ).get("Item")
    manual_ids: Set[str] = set(enroll.get("completed_topic_ids") or []) if enroll else set()

    milestones_raw = meta.get("milestones") or []
    enriched, grand_total, grand_completed = _build_milestones_enriched(
        milestones_raw, user_id=user_id, manual_completed_ids=manual_ids, include_progress=True
    )

    pct = round(grand_completed / grand_total * 100) if grand_total > 0 else 0

    return {
        "roadmap_id": roadmap_id,
        "name": str(meta.get("name") or ""),
        "overall_progress_percentage": pct,
        "total_topics": grand_total,
        "completed_topics": grand_completed,
        "milestones": enriched,
    }


# ===========================================================================
# User — Mark unlinked topic complete (manual)
# ===========================================================================

def user_mark_topic_complete(
    roadmap_id: str, milestone_id: str, roadmap_topic_id: str, user_id: str
) -> Dict[str, Any]:
    meta = _get_roadmap_meta(roadmap_id)
    milestones = meta.get("milestones") or []

    # Validate milestone + topic exist
    milestone = next((m for m in milestones if m.get("milestone_id") == milestone_id), None)
    if milestone is None:
        raise HTTPException(status_code=404, detail="Milestone not found")

    topic = next((t for t in (milestone.get("topics") or []) if t.get("roadmap_topic_id") == roadmap_topic_id), None)
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found in milestone")

    if topic.get("linked_course_id"):
        raise HTTPException(
            status_code=400,
            detail="Topic is linked to a course; completion is derived automatically from course progress.",
        )

    # Upsert enrollment record and add to completed_topic_ids
    enroll_key = {"PK": _user_pk(user_id), "SK": _roadmap_progress_sk(roadmap_id)}
    existing = _et().get_item(Key=enroll_key).get("Item")
    if existing:
        ids: Set[str] = set(existing.get("completed_topic_ids") or [])
        ids.add(roadmap_topic_id)
        _et().update_item(
            Key=enroll_key,
            UpdateExpression="SET completed_topic_ids = :ids",
            ExpressionAttributeValues={":ids": list(ids)},
        )
    else:
        _et().put_item(
            Item={
                "PK": _user_pk(user_id),
                "SK": _roadmap_progress_sk(roadmap_id),
                "user_id": user_id,
                "roadmap_id": roadmap_id,
                "enrolled_at": _now(),
                "completed_topic_ids": [roadmap_topic_id],
            }
        )

    return {"status": "COMPLETED", "roadmap_id": roadmap_id, "message": "Topic marked as complete"}


# ===========================================================================
# Internal helpers
# ===========================================================================

def _get_roadmap_meta(roadmap_id: str) -> Dict[str, Any]:
    resp = _rmt().get_item(Key={"PK": _roadmap_pk(roadmap_id), "SK": "META"})
    item = resp.get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Roadmap not found")
    return item


def _normalise_career(career_raw: Any) -> Dict[str, Any]:
    if not isinstance(career_raw, dict):
        career_raw = {}
    stats_raw = career_raw.get("stats") or {}
    return {
        "stats": {
            "job_growth": str(stats_raw.get("job_growth") or ""),
            "new_jobs_per_year": str(stats_raw.get("new_jobs_per_year") or ""),
            "entry_salary": str(stats_raw.get("entry_salary") or ""),
            "senior_salary": str(stats_raw.get("senior_salary") or ""),
        },
        "responsibilities": list(career_raw.get("responsibilities") or []),
        "day_in_the_life": str(career_raw.get("day_in_the_life") or ""),
        "salary_breakdown": [
            {"level": str(s.get("level") or ""), "amount": str(s.get("amount") or "")}
            for s in (career_raw.get("salary_breakdown") or [])
        ],
        "top_companies": list(career_raw.get("top_companies") or []),
        "technologies": list(career_raw.get("technologies") or []),
    }


# ===========================================================================
# Hook called by course_service after a topic is marked complete.
# For linked topics, progress is derived live — nothing to store here.
# ===========================================================================

def auto_complete_linked_roadmap_topics(
    user_id: str, course_id: str, module_id: str, topic_id: str
) -> None:
    """No-op: linked roadmap topic progress is derived live from course topic progress."""
    pass
