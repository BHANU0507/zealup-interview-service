"""
College Assignment Service  — TABLE8 (CollegeAssignments)

DynamoDB key patterns used (all in TABLE8):
  Assignment          PK=cassign_{id}                    SK=ASSIGNMENT
  Section             PK=csect_{id}                      SK=SECTION
  Question            PK=csect_{id}                      SK=QUESTION#{qid}
  User final sub      PK=cusub#{user_id}                 SK=CASSIGNMENT#{assignment_id}
  User section sub    PK=cusub#{user_id}                 SK=CSECT_SUB#{assignment_id}#{section_id}
  College list index  PK=COLLEGE_ASSIGN_LIST#{college_id} SK=CASSIGNMENT#{assignment_id}
  Admin subs index    PK=CASSIGN_SUBS#{assignment_id}    SK=USER#{user_id}
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from boto3.dynamodb.conditions import Attr, Key
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dynamo import college_assignments_table

# Grading helpers are stateless pure functions — safe to import directly
from app.services.assignment_service import (
    _grade_section_answers,
    _sanitize_for_dynamo,
    _normalize_datetime,
    _now_dt,
    _parse_dt_aware,
    _post_judge0,
    _normalize_output,
    JUDGE0_BASE_URL,
)


# ---------------------------------------------------------------------------
# Table accessor (raises 503 if table not configured)
# ---------------------------------------------------------------------------

def _cat():
    if college_assignments_table is None:
        raise HTTPException(
            status_code=503,
            detail="CollegeAssignments table is not configured (DYNAMODB_TABLE8 missing)",
        )
    return college_assignments_table


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------

def _cassign_pk(assignment_id: str) -> str:
    return assignment_id  # already "cassign_..."


def _csub_pk(user_id: str) -> str:
    return f"cusub#{user_id}"


def _csect_sub_sk(assignment_id: str, section_id: str) -> str:
    return f"CSECT_SUB#{assignment_id}#{section_id}"


def _college_list_pk(college_id: str) -> str:
    return f"COLLEGE_ASSIGN_LIST#{college_id}"


def _admin_subs_pk(assignment_id: str) -> str:
    return f"CASSIGN_SUBS#{assignment_id}"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_cassignment_item(assignment_id: str) -> Dict[str, Any]:
    resp = _cat().get_item(Key={"PK": assignment_id, "SK": "ASSIGNMENT"})
    item = resp.get("Item")
    if not item:
        raise HTTPException(status_code=404, detail=f"College assignment '{assignment_id}' not found")
    return item


def _decimal_to_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _load_sections_for_assignment(assignment_id: str) -> List[Dict[str, Any]]:
    """Fetch all sections + their questions for a given assignment."""
    resp = _cat().scan(
        FilterExpression=Attr("entity_type").eq("c_section") & Attr("assignment_id").eq(assignment_id)
    )
    sections = resp.get("Items", [])

    for section in sections:
        sid = section.get("section_id", "")
        q_resp = _cat().query(
            KeyConditionExpression=Key("PK").eq(sid) & Key("SK").begins_with("QUESTION#")
        )
        questions = q_resp.get("Items", [])
        for q in questions:
            q.pop("PK", None)
            q.pop("SK", None)
            for k, v in q.items():
                if isinstance(v, Decimal):
                    try:
                        q[k] = int(v)
                    except Exception:
                        pass
        questions.sort(key=lambda x: _decimal_to_int(x.get("order", 0)))
        section["questions"] = questions
        section.pop("PK", None)
        section.pop("SK", None)

    sections.sort(key=lambda x: _decimal_to_int(x.get("order", 0)))
    return sections


def _recalculate_assignment_totals(assignment_id: str) -> Tuple[int, int, int]:
    """Return (total_points, total_time_minutes, section_count) from live section data."""
    sections = _load_sections_for_assignment(assignment_id)
    total_points = sum(_decimal_to_int(s.get("total_points", 0)) for s in sections)
    total_time = sum(_decimal_to_int(s.get("time_limit_minutes", 0)) for s in sections)
    return total_points, total_time, len(sections)


def _update_assignment_totals(assignment_id: str) -> None:
    total_points, total_time, section_count = _recalculate_assignment_totals(assignment_id)
    now = _now_dt().isoformat()
    vals = {
        ":tp": total_points,
        ":tt": total_time,
        ":sc": section_count,
        ":ua": now,
    }
    # Update main assignment item
    _cat().update_item(
        Key={"PK": assignment_id, "SK": "ASSIGNMENT"},
        UpdateExpression="SET total_points = :tp, total_time_minutes = :tt, section_count = :sc, updated_at = :ua",
        ExpressionAttributeValues=vals,
    )
    # Keep list index item in sync so list API reflects live totals
    try:
        meta = _get_cassignment_item(assignment_id)
        college_id = str(meta.get("college_id", ""))
        if college_id:
            _cat().update_item(
                Key={"PK": _college_list_pk(college_id), "SK": f"CASSIGNMENT#{assignment_id}"},
                UpdateExpression="SET total_points = :tp, total_time_minutes = :tt, section_count = :sc, updated_at = :ua",
                ExpressionAttributeValues=vals,
            )
    except Exception:
        pass  # list item sync failure should never block section operations


def _get_all_section_subs(user_id: str, assignment_id: str) -> List[Dict[str, Any]]:
    resp = _cat().query(
        KeyConditionExpression=(
            Key("PK").eq(_csub_pk(user_id))
            & Key("SK").begins_with(f"CSECT_SUB#{assignment_id}#")
        )
    )
    return resp.get("Items", [])


def _get_user_final_sub(user_id: str, assignment_id: str) -> Optional[Dict[str, Any]]:
    resp = _cat().get_item(
        Key={"PK": _csub_pk(user_id), "SK": f"CASSIGNMENT#{assignment_id}"}
    )
    return resp.get("Item")


def _enrich_assignment(item: Dict[str, Any]) -> Dict[str, Any]:
    """Load sections, recalculate totals, coerce types for response."""
    item.pop("PK", None)
    item.pop("SK", None)
    sections = _load_sections_for_assignment(item["assignment_id"])
    item["sections"] = sections
    item["total_points"] = sum(_decimal_to_int(s.get("total_points", 0)) for s in sections)
    item["total_time_minutes"] = sum(_decimal_to_int(s.get("time_limit_minutes", 0)) for s in sections)
    item["section_count"] = len(sections)
    for f in ("max_attempts",):
        if item.get(f) is not None:
            item[f] = _decimal_to_int(item[f])
    for dt_field in ("due_date", "deadline", "created_at", "updated_at"):
        val = item.get(dt_field)
        if val and isinstance(val, str):
            try:
                item[dt_field] = datetime.fromisoformat(val)
            except ValueError:
                pass
    return item


# ---------------------------------------------------------------------------
# Assignment CRUD
# ---------------------------------------------------------------------------

def create_college_assignment(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not payload.get("college_id"):
        raise HTTPException(status_code=400, detail="college_id is required")
    if not payload.get("title"):
        raise HTTPException(status_code=400, detail="title is required")
    if not payload.get("description"):
        raise HTTPException(status_code=400, detail="description is required")
    if not payload.get("created_by"):
        raise HTTPException(status_code=400, detail="created_by is required")

    # Validate deadline
    due_date = payload.get("due_date")
    deadline = payload.get("deadline")
    if due_date and deadline:
        dd = _parse_dt_aware(due_date)
        dl = _parse_dt_aware(deadline)
        if dd and dl and dl < dd:
            raise HTTPException(status_code=400, detail="deadline cannot be before due_date")

    assignment_id = f"cassign_{uuid.uuid4().hex[:8]}"
    now = _now_dt()
    college_id = payload["college_id"]

    item = {
        "PK": assignment_id,
        "SK": "ASSIGNMENT",
        "assignment_id": assignment_id,
        "college_id": college_id,
        "college_name": payload.get("college_name"),
        "entity_type": "c_assignment",
        "title": payload["title"],
        "description": payload["description"],
        "created_by": payload["created_by"],
        "course_id": payload.get("course_id"),
        "course_name": payload.get("course_name"),
        "instructor_name": payload.get("instructor_name"),
        "total_points": 0,
        "total_time_minutes": 0,
        "section_count": 0,
        "due_date": _normalize_datetime(due_date),
        "deadline": _normalize_datetime(deadline),
        "is_locked": payload.get("is_locked", False),
        "level": payload.get("level", "intermediate"),
        "max_attempts": payload.get("max_attempts"),
        "tags": payload.get("tags") or [],
        "instructions": payload.get("instructions"),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    # College list index item (for fast college → assignments query)
    list_item = {
        "PK": _college_list_pk(college_id),
        "SK": f"CASSIGNMENT#{assignment_id}",
        "assignment_id": assignment_id,
        "college_id": college_id,
        "college_name": payload.get("college_name"),
        "entity_type": "c_assignment_list",
        "title": payload["title"],
        "due_date": _normalize_datetime(due_date),
        "deadline": _normalize_datetime(deadline),
        "level": payload.get("level", "intermediate"),
        "total_points": 0,
        "total_time_minutes": 0,
        "section_count": 0,
        "created_at": now.isoformat(),
    }

    try:
        _cat().put_item(Item=item)
        _cat().put_item(Item=list_item)
        return {
            "assignment_id": assignment_id,
            "status": "created",
            "created_at": now,
            "total_points": 0,
            "total_time_minutes": 0,
            "section_count": 0,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create college assignment: {e}")


def get_college_assignment(assignment_id: str) -> Dict[str, Any]:
    try:
        item = _get_cassignment_item(assignment_id)
        return _enrich_assignment(item)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get college assignment: {e}")


def list_college_assignments(college_id: str) -> Dict[str, Any]:
    try:
        resp = _cat().query(
            KeyConditionExpression=(
                Key("PK").eq(_college_list_pk(college_id))
                & Key("SK").begins_with("CASSIGNMENT#")
            )
        )
        items = resp.get("Items", [])
        for item in items:
            item.pop("PK", None)
            item.pop("SK", None)
        return {"college_id": college_id, "assignments": items, "total_count": len(items)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list college assignments: {e}")


def update_college_assignment(assignment_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    item = _get_cassignment_item(assignment_id)
    college_id = str(item.get("college_id", ""))
    now = _now_dt().isoformat()

    expr = "SET updated_at = :ua"
    vals: Dict[str, Any] = {":ua": now}
    names: Dict[str, str] = {}

    plain = ["title", "description", "course_id", "course_name", "instructor_name",
             "is_locked", "max_attempts", "tags", "instructions"]
    reserved = {"level": "#lvl"}

    for f in plain:
        if f in payload and payload[f] is not None:
            expr += f", {f} = :{f}"
            vals[f":{f}"] = payload[f]

    for f, alias in reserved.items():
        if f in payload and payload[f] is not None:
            expr += f", {alias} = :{f}"
            names[alias] = f
            vals[f":{f}"] = payload[f]

    if "due_date" in payload:
        expr += ", due_date = :dd"
        vals[":dd"] = _normalize_datetime(payload["due_date"])

    if "deadline" in payload:
        expr += ", deadline = :dl"
        vals[":dl"] = _normalize_datetime(payload["deadline"])

    kwargs: Dict[str, Any] = {
        "Key": {"PK": assignment_id, "SK": "ASSIGNMENT"},
        "UpdateExpression": expr,
        "ExpressionAttributeValues": vals,
    }
    if names:
        kwargs["ExpressionAttributeNames"] = names

    try:
        _cat().update_item(**kwargs)

        # Keep college list item in sync (title, due_date, deadline)
        list_vals: Dict[str, Any] = {":ua": now}
        list_expr = "SET updated_at = :ua"
        for f, placeholder in [("title", ":t"), ("due_date", ":dd"), ("deadline", ":dl"), ("level", ":lv")]:
            if f in payload and payload[f] is not None:
                list_expr += f", {f} = {placeholder}"
                list_vals[placeholder] = (
                    _normalize_datetime(payload[f]) if f in ("due_date", "deadline") else payload[f]
                )
        _cat().update_item(
            Key={"PK": _college_list_pk(college_id), "SK": f"CASSIGNMENT#{assignment_id}"},
            UpdateExpression=list_expr,
            ExpressionAttributeValues=list_vals,
        )
        return {"status": "updated", "assignment_id": assignment_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update college assignment: {e}")


def delete_college_assignment(assignment_id: str) -> Dict[str, Any]:
    item = _get_cassignment_item(assignment_id)
    college_id = str(item.get("college_id", ""))

    # Delete sections + questions
    sections = _load_sections_for_assignment(assignment_id)
    for section in sections:
        sid = section.get("section_id", "")
        # Delete questions for this section
        q_resp = _cat().query(
            KeyConditionExpression=Key("PK").eq(sid) & Key("SK").begins_with("QUESTION#")
        )
        for q_item in q_resp.get("Items", []):
            _cat().delete_item(Key={"PK": q_item["PK"], "SK": q_item["SK"]})
        # Delete section record
        _cat().delete_item(Key={"PK": sid, "SK": "SECTION"})

    # Delete college list index + main assignment item
    try:
        _cat().delete_item(Key={"PK": _college_list_pk(college_id), "SK": f"CASSIGNMENT#{assignment_id}"})
        _cat().delete_item(Key={"PK": assignment_id, "SK": "ASSIGNMENT"})
        return {"status": "deleted", "assignment_id": assignment_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete college assignment: {e}")


# ---------------------------------------------------------------------------
# Section CRUD
# ---------------------------------------------------------------------------

def add_college_section(assignment_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    _get_cassignment_item(assignment_id)  # 404 guard

    section_id = f"csect_{uuid.uuid4().hex[:8]}"
    now = _now_dt().isoformat()
    questions = payload.get("questions") or []
    total_points = sum(int(q.get("points", 0)) for q in questions)

    # Auto-assign order
    existing = _load_sections_for_assignment(assignment_id)
    order = payload.get("order") if payload.get("order") is not None else len(existing) + 1

    section_item = {
        "PK": section_id,
        "SK": "SECTION",
        "section_id": section_id,
        "assignment_id": assignment_id,
        "entity_type": "c_section",
        "title": payload.get("title", ""),
        "description": payload.get("description"),
        "order": order,
        "time_limit_minutes": payload.get("time_limit_minutes"),
        "total_points": total_points,
        "question_count": len(questions),
        "instructions": payload.get("instructions"),
        "created_at": now,
        "updated_at": now,
    }
    _cat().put_item(Item=section_item)

    # Store questions
    for i, q in enumerate(questions):
        qid = q.get("id") or f"q_{uuid.uuid4().hex[:8]}"
        q_item = {**q, "PK": section_id, "SK": f"QUESTION#{qid}", "id": qid,
                  "section_id": section_id, "assignment_id": assignment_id,
                  "order": q.get("order", i + 1)}
        _cat().put_item(Item=_sanitize_for_dynamo(q_item))

    _update_assignment_totals(assignment_id)

    return {
        "section_id": section_id,
        "assignment_id": assignment_id,
        "status": "created",
        "created_at": now,
        "total_points": total_points,
        "question_count": len(questions),
    }


def list_college_sections(assignment_id: str) -> Dict[str, Any]:
    _get_cassignment_item(assignment_id)
    sections = _load_sections_for_assignment(assignment_id)
    total_points = sum(_decimal_to_int(s.get("total_points", 0)) for s in sections)
    total_time = sum(_decimal_to_int(s.get("time_limit_minutes", 0)) for s in sections)
    return {
        "assignment_id": assignment_id,
        "sections": sections,
        "total_sections": len(sections),
        "total_points": total_points,
        "total_time_minutes": total_time,
    }


def get_college_section(assignment_id: str, section_id: str) -> Dict[str, Any]:
    resp = _cat().get_item(Key={"PK": section_id, "SK": "SECTION"})
    item = resp.get("Item")
    if not item or item.get("assignment_id") != assignment_id:
        raise HTTPException(status_code=404, detail="Section not found")
    item.pop("PK", None)
    item.pop("SK", None)
    q_resp = _cat().query(
        KeyConditionExpression=Key("PK").eq(section_id) & Key("SK").begins_with("QUESTION#")
    )
    item["questions"] = q_resp.get("Items", [])
    return item


def update_college_section(assignment_id: str, section_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    existing = get_college_section(assignment_id, section_id)
    now = _now_dt().isoformat()
    expr = "SET updated_at = :ua"
    vals: Dict[str, Any] = {":ua": now}
    names: Dict[str, str] = {}

    # Plain fields (not reserved keywords)
    for f in ["title", "description", "time_limit_minutes", "instructions"]:
        if f in payload and payload[f] is not None:
            expr += f", {f} = :{f}"
            vals[f":{f}"] = payload[f]

    # `order` is a DynamoDB reserved keyword — must use expression attribute name alias
    if "order" in payload and payload["order"] is not None:
        expr += ", #ord = :order"
        names["#ord"] = "order"
        vals[":order"] = payload["order"]

    # If questions are being replaced, recalculate totals
    if "questions" in payload and payload["questions"] is not None:
        questions = payload["questions"]
        total_points = sum(int(q.get("points", 0)) for q in questions)
        expr += ", total_points = :tp, question_count = :qc"
        vals[":tp"] = total_points
        vals[":qc"] = len(questions)

        # Delete old questions and re-insert
        old_q_resp = _cat().query(
            KeyConditionExpression=Key("PK").eq(section_id) & Key("SK").begins_with("QUESTION#")
        )
        for old_q in old_q_resp.get("Items", []):
            _cat().delete_item(Key={"PK": old_q["PK"], "SK": old_q["SK"]})

        for i, q in enumerate(questions):
            qid = q.get("id") or f"q_{uuid.uuid4().hex[:8]}"
            q_item = {**q, "PK": section_id, "SK": f"QUESTION#{qid}", "id": qid,
                      "section_id": section_id, "assignment_id": assignment_id,
                      "order": q.get("order", i + 1)}
            _cat().put_item(Item=_sanitize_for_dynamo(q_item))

    update_kwargs: Dict[str, Any] = {
        "Key": {"PK": section_id, "SK": "SECTION"},
        "UpdateExpression": expr,
        "ExpressionAttributeValues": vals,
    }
    if names:
        update_kwargs["ExpressionAttributeNames"] = names

    _cat().update_item(**update_kwargs)
    _update_assignment_totals(assignment_id)
    return {"status": "updated", "section_id": section_id}


def delete_college_section(assignment_id: str, section_id: str) -> Dict[str, Any]:
    get_college_section(assignment_id, section_id)  # 404 guard
    q_resp = _cat().query(
        KeyConditionExpression=Key("PK").eq(section_id) & Key("SK").begins_with("QUESTION#")
    )
    for q_item in q_resp.get("Items", []):
        _cat().delete_item(Key={"PK": q_item["PK"], "SK": q_item["SK"]})
    _cat().delete_item(Key={"PK": section_id, "SK": "SECTION"})
    _update_assignment_totals(assignment_id)
    return {"status": "deleted", "section_id": section_id}


# ---------------------------------------------------------------------------
# Question CRUD
# ---------------------------------------------------------------------------

def add_college_question(assignment_id: str, section_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    get_college_section(assignment_id, section_id)  # 404 guard
    qid = payload.get("id") or f"q_{uuid.uuid4().hex[:8]}"
    now = _now_dt().isoformat()

    # Count existing questions for auto-order
    q_resp = _cat().query(
        KeyConditionExpression=Key("PK").eq(section_id) & Key("SK").begins_with("QUESTION#")
    )
    order = payload.get("order", len(q_resp.get("Items", [])) + 1)

    # For coding questions: auto-calculate points from test cases
    if payload.get("question_type") == "coding":
        test_cases = payload.get("test_cases") or []
        payload["points"] = sum(int(tc.get("points", 0)) for tc in test_cases)

    q_item = {
        **payload,
        "PK": section_id,
        "SK": f"QUESTION#{qid}",
        "id": qid,
        "question_id": qid,
        "section_id": section_id,
        "assignment_id": assignment_id,
        "order": order,
        "created_at": now,
        "updated_at": now,
    }
    _cat().put_item(Item=_sanitize_for_dynamo(q_item))

    # Recalculate section total_points
    all_q = _cat().query(
        KeyConditionExpression=Key("PK").eq(section_id) & Key("SK").begins_with("QUESTION#")
    ).get("Items", [])
    total_pts = sum(_decimal_to_int(q.get("points", 0)) for q in all_q)
    _cat().update_item(
        Key={"PK": section_id, "SK": "SECTION"},
        UpdateExpression="SET total_points = :tp, question_count = :qc, updated_at = :ua",
        ExpressionAttributeValues={":tp": total_pts, ":qc": len(all_q), ":ua": now},
    )
    _update_assignment_totals(assignment_id)

    return {"question_id": qid, "section_id": section_id, "status": "created"}


def list_college_questions(assignment_id: str, section_id: str) -> Dict[str, Any]:
    get_college_section(assignment_id, section_id)
    q_resp = _cat().query(
        KeyConditionExpression=Key("PK").eq(section_id) & Key("SK").begins_with("QUESTION#")
    )
    questions = q_resp.get("Items", [])
    for q in questions:
        q.pop("PK", None)
        q.pop("SK", None)
    questions.sort(key=lambda x: _decimal_to_int(x.get("order", 0)))
    return {"section_id": section_id, "questions": questions, "total_questions": len(questions)}


def get_college_question(assignment_id: str, section_id: str, question_id: str) -> Dict[str, Any]:
    resp = _cat().get_item(Key={"PK": section_id, "SK": f"QUESTION#{question_id}"})
    item = resp.get("Item")
    if not item or item.get("assignment_id") != assignment_id:
        raise HTTPException(status_code=404, detail="Question not found")
    item.pop("PK", None)
    item.pop("SK", None)
    return item


def update_college_question(assignment_id: str, section_id: str, question_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    get_college_question(assignment_id, section_id, question_id)
    now = _now_dt().isoformat()
    payload_clean = {k: v for k, v in payload.items() if v is not None and k not in ("id", "question_id", "section_id", "assignment_id")}
    payload_clean["updated_at"] = now

    # For coding questions: re-derive points from test_cases
    q_type = payload_clean.get("question_type")
    if q_type == "coding" or (q_type is None and "test_cases" in payload_clean):
        existing_q = get_college_question(assignment_id, section_id, question_id)
        if existing_q.get("question_type") == "coding" or q_type == "coding":
            test_cases = payload_clean.get("test_cases") or existing_q.get("test_cases") or []
            payload_clean["points"] = sum(int(tc.get("points", 0)) for tc in test_cases)

    # DynamoDB reserved keywords that need aliasing
    _reserved = {"order", "status", "name", "level", "type", "values", "key"}

    expr_parts: list = []
    vals: Dict[str, Any] = {}
    names: Dict[str, str] = {}

    for k, v in payload_clean.items():
        if k in _reserved:
            alias = f"#{k}"
            expr_parts.append(f"{alias} = :{k}")
            names[alias] = k
        else:
            expr_parts.append(f"{k} = :{k}")
        vals[f":{k}"] = v

    expr = "SET " + ", ".join(expr_parts)

    update_kwargs: Dict[str, Any] = {
        "Key": {"PK": section_id, "SK": f"QUESTION#{question_id}"},
        "UpdateExpression": expr,
        "ExpressionAttributeValues": _sanitize_for_dynamo(vals),
    }
    if names:
        update_kwargs["ExpressionAttributeNames"] = names

    _cat().update_item(**update_kwargs)

    if "points" in payload_clean or "test_cases" in payload_clean:
        all_q = _cat().query(
            KeyConditionExpression=Key("PK").eq(section_id) & Key("SK").begins_with("QUESTION#")
        ).get("Items", [])
        total_pts = sum(_decimal_to_int(q.get("points", 0)) for q in all_q)
        _cat().update_item(
            Key={"PK": section_id, "SK": "SECTION"},
            UpdateExpression="SET total_points = :tp, updated_at = :ua",
            ExpressionAttributeValues={":tp": total_pts, ":ua": now},
        )
        _update_assignment_totals(assignment_id)

    return {"status": "updated", "question_id": question_id}


def delete_college_question(assignment_id: str, section_id: str, question_id: str) -> Dict[str, Any]:
    get_college_question(assignment_id, section_id, question_id)
    _cat().delete_item(Key={"PK": section_id, "SK": f"QUESTION#{question_id}"})

    all_q = _cat().query(
        KeyConditionExpression=Key("PK").eq(section_id) & Key("SK").begins_with("QUESTION#")
    ).get("Items", [])
    total_pts = sum(_decimal_to_int(q.get("points", 0)) for q in all_q)
    now = _now_dt().isoformat()
    _cat().update_item(
        Key={"PK": section_id, "SK": "SECTION"},
        UpdateExpression="SET total_points = :tp, question_count = :qc, updated_at = :ua",
        ExpressionAttributeValues={":tp": total_pts, ":qc": len(all_q), ":ua": now},
    )
    _update_assignment_totals(assignment_id)
    return {"status": "deleted", "question_id": question_id}


# ---------------------------------------------------------------------------
# Student — pre-start info & availability
# ---------------------------------------------------------------------------

def college_assignment_availability(assignment_id: str, user_id: str) -> Dict[str, Any]:
    assignment = get_college_assignment(assignment_id)
    now = _now_dt()

    if assignment.get("is_locked", False):
        return {"can_start": False, "reason": "Assignment is locked"}

    deadline = assignment.get("deadline")
    if deadline:
        dl = _parse_dt_aware(deadline) if isinstance(deadline, str) else deadline
        if dl and dl.tzinfo is None:
            dl = dl.replace(tzinfo=timezone.utc)
        if dl and dl < now:
            return {"can_start": False, "reason": "Submission deadline has passed"}

    max_attempts = assignment.get("max_attempts")
    if max_attempts is not None:
        existing = _get_user_final_sub(user_id, assignment_id)
        attempts = _decimal_to_int(existing.get("attempts_count", 0)) if existing else 0
        if attempts >= int(max_attempts):
            return {"can_start": False, "reason": f"Maximum attempts ({max_attempts}) reached"}

    return {"can_start": True, "reason": ""}


def college_assignment_prestart(assignment_id: str, user_id: str) -> Dict[str, Any]:
    assignment = get_college_assignment(assignment_id)
    availability = college_assignment_availability(assignment_id, user_id)

    existing = _get_user_final_sub(user_id, assignment_id)
    attempts_used = _decimal_to_int(existing.get("attempts_count", 0)) if existing else 0

    sections_overview = []
    for s in assignment.get("sections", []):
        sections_overview.append({
            "section_id": s.get("section_id"),
            "title": s.get("title"),
            "order": s.get("order"),
            "question_count": len(s.get("questions", [])),
            "total_points": s.get("total_points", 0),
            "time_limit_minutes": s.get("time_limit_minutes"),
        })

    return {
        "assignment_id": assignment_id,
        "title": assignment.get("title"),
        "description": assignment.get("description"),
        "instructions": assignment.get("instructions"),
        "level": assignment.get("level"),
        "total_points": assignment.get("total_points", 0),
        "total_time_minutes": assignment.get("total_time_minutes", 0),
        "due_date": assignment.get("due_date"),
        "deadline": assignment.get("deadline"),
        "max_attempts": assignment.get("max_attempts"),
        "attempts_used": attempts_used,
        "can_start": availability["can_start"],
        "availability_reason": availability.get("reason", ""),
        "sections": sections_overview,
    }


# ---------------------------------------------------------------------------
# Student — section-by-section submission
# ---------------------------------------------------------------------------

def submit_college_section(user_id: str, assignment_id: str, section_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    assignment = get_college_assignment(assignment_id)

    if assignment.get("is_locked", False):
        raise HTTPException(status_code=400, detail="Assignment is locked")

    now_dt = _now_dt()
    deadline = assignment.get("deadline")
    if deadline:
        dl = _parse_dt_aware(deadline) if isinstance(deadline, str) else deadline
        if dl:
            if dl.tzinfo is None:
                dl = dl.replace(tzinfo=timezone.utc)
            if dl < now_dt:
                raise HTTPException(status_code=400, detail="Submission deadline has passed")

    max_attempts = assignment.get("max_attempts")
    existing_final = _get_user_final_sub(user_id, assignment_id)
    if max_attempts is not None:
        current_attempts = _decimal_to_int(existing_final.get("attempts_count", 0)) if existing_final else 0
        if current_attempts >= int(max_attempts):
            raise HTTPException(status_code=400, detail=f"Maximum attempts ({max_attempts}) already reached")

    # On a retake: if the student already has a finalized submission, any section
    # subs still on record belong to the previous attempt. Wipe them all so that
    # finalize() can only aggregate section subs from this new attempt.
    if existing_final:
        last_final_at = str(existing_final.get("submitted_at", ""))
        old_subs = _get_all_section_subs(user_id, assignment_id)
        for old_sub in old_subs:
            sub_ts = str(old_sub.get("submitted_at", ""))
            if sub_ts <= last_final_at:
                # This section sub is from the previous attempt — delete it
                _cat().delete_item(
                    Key={"PK": _csub_pk(user_id), "SK": _csect_sub_sk(assignment_id, old_sub["section_id"])}
                )

    target_section = next(
        (s for s in assignment.get("sections", []) if s.get("section_id") == section_id), None
    )
    if not target_section:
        raise HTTPException(status_code=404, detail="Section not found in this assignment")

    answers = payload.get("answers", [])
    section_result, sec_score = _grade_section_answers(target_section, answers)
    time_taken = int(payload.get("time_taken_minutes", 0))

    sect_item = _sanitize_for_dynamo({
        "PK": _csub_pk(user_id),
        "SK": _csect_sub_sk(assignment_id, section_id),
        "entity_type": "c_section_submission",
        "user_id": user_id,
        "assignment_id": assignment_id,
        "college_id": assignment.get("college_id", ""),
        "section_id": section_id,
        "score": sec_score,
        "total_points": _decimal_to_int(target_section.get("total_points", 0)),
        "time_taken_minutes": time_taken,
        "submitted_at": now_dt.isoformat(),
        "question_results": section_result["question_results"],
    })
    _cat().put_item(Item=sect_item)

    all_sections = assignment.get("sections", [])
    all_section_ids = {s.get("section_id") for s in all_sections}
    submitted_items = _get_all_section_subs(user_id, assignment_id)
    submitted_ids = {item.get("section_id") for item in submitted_items}

    return {
        "assignment_id": assignment_id,
        "section_id": section_id,
        "user_id": user_id,
        "score": sec_score,
        "total_points": _decimal_to_int(target_section.get("total_points", 0)),
        "percentage": round(sec_score / _decimal_to_int(target_section.get("total_points", 0)) * 100, 2)
                      if _decimal_to_int(target_section.get("total_points", 0)) > 0 else 0.0,
        "time_taken_minutes": time_taken,
        "submitted_at": now_dt.isoformat(),
        "question_results": section_result["question_results"],
        "sections_submitted": len(submitted_ids),
        "sections_total": len(all_section_ids),
        "all_sections_done": all_section_ids.issubset(submitted_ids),
    }


def finalize_college_assignment(user_id: str, assignment_id: str, user_name: str = "") -> Dict[str, Any]:
    assignment = get_college_assignment(assignment_id)
    all_sections = assignment.get("sections", [])
    if not all_sections:
        raise HTTPException(status_code=400, detail="Assignment has no sections")

    submitted_items = _get_all_section_subs(user_id, assignment_id)
    if not submitted_items:
        raise HTTPException(status_code=400, detail="No section submissions found. Submit all sections first.")

    submitted_map = {item.get("section_id"): item for item in submitted_items}
    missing = [s.get("section_id") for s in all_sections if s.get("section_id") not in submitted_map]
    if missing:
        raise HTTPException(status_code=400, detail=f"Sections not yet submitted: {missing}")

    section_results: List[Dict[str, Any]] = []
    total_score = 0
    total_time = 0
    for s in all_sections:
        sid = s.get("section_id", "")
        sub = submitted_map[sid]
        sr = {
            "section_id": sid,
            "section_title": s.get("title", ""),
            "score": _decimal_to_int(sub.get("score", 0)),
            "total_points": _decimal_to_int(sub.get("total_points", 0)),
            "time_taken_minutes": _decimal_to_int(sub.get("time_taken_minutes", 0)),
            "submitted_at": str(sub.get("submitted_at", "")),
            "question_results": sub.get("question_results", []),
        }
        section_results.append(sr)
        total_score += sr["score"]
        total_time += sr["time_taken_minutes"]

    total_points = _decimal_to_int(assignment.get("total_points", 0))
    percentage = round(total_score / total_points * 100, 2) if total_points > 0 else 0.0
    now_dt = _now_dt()
    college_id = str(assignment.get("college_id", ""))

    existing = _get_user_final_sub(user_id, assignment_id)
    current_attempts = _decimal_to_int(existing.get("attempts_count", 0)) if existing else 0
    new_attempts = current_attempts + 1

    final_item = _sanitize_for_dynamo({
        "PK": _csub_pk(user_id),
        "SK": f"CASSIGNMENT#{assignment_id}",
        "entity_type": "c_user_submission",
        "user_id": user_id,
        "user_name": str(user_name or "").strip(),
        "assignment_id": assignment_id,
        "college_id": college_id,
        "score": total_score,
        "total_points": total_points,
        "percentage": percentage,
        "attempts_count": new_attempts,
        "time_taken_minutes": total_time,
        "submitted_at": now_dt.isoformat(),
        "status": "submitted",
        "section_results": section_results,
    })
    _cat().put_item(Item=final_item)

    # Write/overwrite admin subs index item so colleges can list all submissions
    admin_idx_item = _sanitize_for_dynamo({
        "PK": _admin_subs_pk(assignment_id),
        "SK": f"USER#{user_id}",
        "entity_type": "c_subs_index",
        "user_id": user_id,
        "user_name": str(user_name or "").strip(),
        "assignment_id": assignment_id,
        "college_id": college_id,
        "score": total_score,
        "total_points": total_points,
        "percentage": percentage,
        "attempts_count": new_attempts,
        "submitted_at": now_dt.isoformat(),
        "status": "submitted",
    })
    _cat().put_item(Item=admin_idx_item)

    return {
        "assignment_id": assignment_id,
        "user_id": user_id,
        "score": total_score,
        "total_points": total_points,
        "percentage": percentage,
        "attempts_count": new_attempts,
        "time_taken_minutes": total_time,
        "submitted_at": now_dt,
        "status": "submitted",
        "section_results": section_results,
    }


def get_college_assignment_progress(user_id: str, assignment_id: str) -> Dict[str, Any]:
    assignment = get_college_assignment(assignment_id)
    all_sections = assignment.get("sections", [])
    submitted_items = _get_all_section_subs(user_id, assignment_id)
    submitted_map = {item.get("section_id"): item for item in submitted_items}

    sections_progress = []
    total_score = 0
    for s in all_sections:
        sid = s.get("section_id", "")
        sub = submitted_map.get(sid)
        sp = {
            "section_id": sid,
            "title": s.get("title", ""),
            "is_submitted": sub is not None,
            "score": _decimal_to_int(sub.get("score", 0)) if sub else 0,
            "total_points": _decimal_to_int(s.get("total_points", 0)),
            "submitted_at": sub.get("submitted_at") if sub else None,
        }
        sections_progress.append(sp)
        if sub:
            total_score += sp["score"]

    return {
        "assignment_id": assignment_id,
        "user_id": user_id,
        "sections_submitted": len(submitted_map),
        "sections_total": len(all_sections),
        "current_score": total_score,
        "total_points": _decimal_to_int(assignment.get("total_points", 0)),
        "sections": sections_progress,
    }


def get_college_user_submission(user_id: str, assignment_id: str) -> Dict[str, Any]:
    item = _get_user_final_sub(user_id, assignment_id)
    if not item:
        raise HTTPException(status_code=404, detail="No submission found for this user")
    item.pop("PK", None)
    item.pop("SK", None)
    return item


# ---------------------------------------------------------------------------
# Admin — view all submissions for an assignment
# ---------------------------------------------------------------------------

def admin_list_college_submissions(assignment_id: str) -> Dict[str, Any]:
    assignment_item = _get_cassignment_item(assignment_id)
    college_id = str(assignment_item.get("college_id", ""))

    resp = _cat().query(
        KeyConditionExpression=(
            Key("PK").eq(_admin_subs_pk(assignment_id))
            & Key("SK").begins_with("USER#")
        )
    )
    items = resp.get("Items", [])
    submissions = []
    for item in items:
        submissions.append({
            "user_id": str(item.get("user_id", "")),
            "user_name": str(item.get("user_name", "")),
            "score": _decimal_to_int(item.get("score", 0)),
            "total_points": _decimal_to_int(item.get("total_points", 0)),
            "percentage": float(item.get("percentage", 0)),
            "submitted_at": str(item.get("submitted_at", "")),
            "attempts_count": _decimal_to_int(item.get("attempts_count", 0)),
        })

    return {
        "assignment_id": assignment_id,
        "college_id": college_id,
        "submissions": submissions,
        "total_submissions": len(submissions),
    }


def admin_college_assignment_stats(assignment_id: str) -> Dict[str, Any]:
    result = admin_list_college_submissions(assignment_id)
    submissions = result["submissions"]

    if not submissions:
        return {
            "assignment_id": assignment_id,
            "college_id": result["college_id"],
            "total_submissions": 0,
            "average_score": 0.0,
            "average_percentage": 0.0,
            "pass_rate": 0.0,
            "highest_score": 0,
            "lowest_score": 0,
        }

    scores = [s["score"] for s in submissions]
    percentages = [s["percentage"] for s in submissions]
    pass_count = sum(1 for p in percentages if p >= 60)

    return {
        "assignment_id": assignment_id,
        "college_id": result["college_id"],
        "total_submissions": len(submissions),
        "average_score": round(sum(scores) / len(scores), 2),
        "average_percentage": round(sum(percentages) / len(percentages), 2),
        "pass_rate": round(pass_count / len(submissions) * 100, 2),
        "highest_score": max(scores),
        "lowest_score": min(scores),
    }


# ---------------------------------------------------------------------------
# Latest college assignment snapshot (for dashboard widget)
# ---------------------------------------------------------------------------

def get_latest_college_assignment_snapshot(college_id: str, db: Session, branch_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Return the most recently created assignment for the college together with
    college-wide submission statistics (participants, avg, top, least score,
    and absent = total_students - participants).

    When branch_id is provided, total_students and absent are scoped to that branch.
    If no assignment exists yet returns an empty snapshot.
    """
    # 1. Fetch all assignments for this college sorted by created_at descending
    resp = _cat().query(
        KeyConditionExpression=(
            Key("PK").eq(f"COLLEGE_ASSIGN_LIST#{college_id}")
            & Key("SK").begins_with("CASSIGNMENT#")
        ),
        ScanIndexForward=False,          # newest SK first (lexicographic on CASSIGNMENT#)
    )
    items = resp.get("Items", [])

    if not items:
        return {
            "college_id": college_id,
            "has_assignment": False,
            "assignment": None,
        }

    # Sort by created_at string descending to get the true latest
    items.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    latest = items[0]
    assignment_id = str(latest.get("assignment_id", ""))

    # 2. Fetch all submissions from the admin subs index
    subs_resp = _cat().query(
        KeyConditionExpression=(
            Key("PK").eq(f"CASSIGN_SUBS#{assignment_id}")
            & Key("SK").begins_with("USER#")
        )
    )
    subs = subs_resp.get("Items", [])

    # 3. If branch_id filter is active, resolve eligible user_ids from MySQL first
    if branch_id:
        try:
            branch_rows = db.execute(
                text(
                    """
                    SELECT id FROM users
                    WHERE  college_id    = :college_id
                      AND  user_type     = 'COLLEGE_STUDENT'
                      AND  account_status = 'ACTIVE'
                      AND  branch_id     = :branch_id
                    """
                ),
                {"college_id": college_id, "branch_id": branch_id},
            ).fetchall()
            eligible_ids = {str(r.id) for r in branch_rows}
        except Exception:
            eligible_ids = set()
        subs = [
            s for s in subs
            if str(s.get("SK", ""))[len("USER#"):] in eligible_ids
        ]

    # 4. Compute stats
    scores = [_decimal_to_int(s.get("score", 0)) for s in subs]
    participants = len(scores)
    avg_score = round(sum(scores) / participants, 2) if participants else 0.0
    top_score = max(scores) if scores else 0
    least_score = min(scores) if scores else 0

    # 5. Total students (MySQL) → absent = total - participants
    total_students = 0
    try:
        branch_clause = "AND branch_id = :branch_id" if branch_id else ""
        params: dict = {"college_id": college_id}
        if branch_id:
            params["branch_id"] = branch_id
        row = db.execute(
            text(
                f"""
                SELECT COUNT(*) AS cnt
                FROM   users
                WHERE  college_id    = :college_id
                  AND  user_type     = 'COLLEGE_STUDENT'
                  AND  account_status = 'ACTIVE'
                  {branch_clause}
                """
            ),
            params,
        ).fetchone()
        if row:
            total_students = int(row.cnt)
    except Exception:
        total_students = 0

    absent = max(0, total_students - participants)

    return {
        "college_id": college_id,
        "branch_filter": branch_id,
        "has_assignment": True,
        "assignment": {
            "assignment_id": assignment_id,
            "title": str(latest.get("title", "")),
            "level": str(latest.get("level") or ""),
            "total_points": _decimal_to_int(latest.get("total_points", 0)),
            "total_time_minutes": _decimal_to_int(latest.get("total_time_minutes", 0)),
            "section_count": _decimal_to_int(latest.get("section_count", 0)),
            "due_date": str(latest.get("due_date") or ""),
            "deadline": str(latest.get("deadline") or ""),
            "created_at": str(latest.get("created_at") or ""),
            "stats": {
                "participants": participants,
                "absent":       absent,
                "total_students": total_students,
                "avg_score":    avg_score,
                "top_score":    top_score,
                "least_score":  least_score,
            },
        },
    }


# ---------------------------------------------------------------------------
# College-wide attendance trend (monthly participation)
# ---------------------------------------------------------------------------

_MONTH_NAMES = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def get_college_attendance_trend(
    college_id: str,
    year: int,
    month: Optional[int],
    db: Session,
    branch_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Return monthly attendance (participation) trend for a college.

    Attendance for a month = unique students who submitted at least one
    college assignment whose due_date falls in that month, divided by the
    total active college students (scoped to branch when branch_id provided).

    Args:
        college_id : the college to query
        year       : calendar year (e.g. 2026)
        month      : 1-12 for a specific month, or None for all 12 months
        db         : SQLAlchemy session for MySQL total-student count
        branch_id  : optional branch filter
    """
    # 1. Total active students from MySQL (optionally scoped to branch)
    total_students = 0
    eligible_user_ids: Optional[set] = None
    try:
        branch_clause = "AND branch_id = :branch_id" if branch_id else ""
        params: dict = {"college_id": college_id}
        if branch_id:
            params["branch_id"] = branch_id
        rows = db.execute(
            text(
                f"""
                SELECT id
                FROM   users
                WHERE  college_id    = :college_id
                  AND  user_type     = 'COLLEGE_STUDENT'
                  AND  account_status = 'ACTIVE'
                  {branch_clause}
                """
            ),
            params,
        ).fetchall()
        total_students = len(rows)
        if branch_id:
            eligible_user_ids = {str(r.id) for r in rows}
    except Exception:
        total_students = 0

    # 2. All assignments for the college from DynamoDB list index
    resp = _cat().query(
        KeyConditionExpression=(
            Key("PK").eq(f"COLLEGE_ASSIGN_LIST#{college_id}")
            & Key("SK").begins_with("CASSIGNMENT#")
        ),
        ProjectionExpression="assignment_id, due_date, created_at",
    )
    assignments = resp.get("Items", [])

    # 3. For each assignment that falls in the target period, collect
    #    unique participant user IDs grouped by month.
    month_participants: Dict[int, set] = {}

    for a in assignments:
        date_str = str(a.get("due_date") or a.get("created_at") or "").strip()
        if not date_str:
            continue
        try:
            dt = datetime.fromisoformat(date_str[:19])
        except ValueError:
            continue

        if dt.year != year:
            continue
        if month is not None and dt.month != month:
            continue

        assignment_id = str(a.get("assignment_id", "")).strip()
        if not assignment_id:
            continue

        # Fetch all submission records for this assignment (only SK needed)
        subs_resp = _cat().query(
            KeyConditionExpression=(
                Key("PK").eq(f"CASSIGN_SUBS#{assignment_id}")
                & Key("SK").begins_with("USER#")
            ),
            ProjectionExpression="SK",
        )
        for sub in subs_resp.get("Items", []):
            sk = str(sub.get("SK", ""))
            user_id = sk[len("USER#"):] if sk.startswith("USER#") else sk
            if user_id:
                # Apply branch filter if active
                if eligible_user_ids is not None and user_id not in eligible_user_ids:
                    continue
                month_participants.setdefault(dt.month, set()).add(user_id)

    # 4. Build the response data points
    target_months = [month] if month is not None else list(range(1, 13))
    data = []
    for m in target_months:
        participants = len(month_participants.get(m, set()))
        att_pct = (
            round(participants / total_students * 100, 2)
            if total_students > 0
            else 0.0
        )
        data.append(
            {
                "month":          m,
                "month_name":     _MONTH_NAMES[m - 1],
                "participants":   participants,
                "attendance_pct": att_pct,
            }
        )

    return {
        "college_id":     college_id,
        "branch_filter":  branch_id,
        "year":           year,
        "month":          month,
        "total_students": total_students,
        "data":           data,
    }


# ---------------------------------------------------------------------------
# Student dashboard — active / completed / missed  (shared helper)
# ---------------------------------------------------------------------------

def _build_student_assignment_cards(
    college_id: str, user_id: str
) -> tuple:
    """
    Returns (active_list, completed_list, missed_list) — each a list of card dicts.
    Does all DynamoDB work in exactly 2 queries regardless of which bucket is needed.
    """
    resp = _cat().query(
        KeyConditionExpression=(
            Key("PK").eq(_college_list_pk(college_id))
            & Key("SK").begins_with("CASSIGNMENT#")
        )
    )
    assignments = resp.get("Items", [])

    if not assignments:
        return [], [], []

    # Fetch all final submissions for this user in one query
    subs_resp = _cat().query(
        KeyConditionExpression=(
            Key("PK").eq(_csub_pk(user_id))
            & Key("SK").begins_with("CASSIGNMENT#")
        )
    )
    sub_map: Dict[str, Dict[str, Any]] = {}
    for sub in subs_resp.get("Items", []):
        sk = str(sub.get("SK", ""))
        aid = sk.replace("CASSIGNMENT#", "", 1)
        if aid:
            sub_map[aid] = sub

    now_dt = _now_dt()
    active: List[Dict[str, Any]] = []
    completed: List[Dict[str, Any]] = []
    missed: List[Dict[str, Any]] = []

    for a in assignments:
        a.pop("PK", None)
        a.pop("SK", None)

        assignment_id = str(a.get("assignment_id", ""))
        max_attempts_raw = a.get("max_attempts")
        max_attempts: Optional[int] = _decimal_to_int(max_attempts_raw) if max_attempts_raw is not None else None

        deadline_str = a.get("deadline")
        due_date_str = a.get("due_date")
        deadline_dt: Optional[datetime] = None
        if deadline_str:
            try:
                deadline_dt = _parse_dt_aware(deadline_str)
            except Exception:
                pass

        sub = sub_map.get(assignment_id)

        card: Dict[str, Any] = {
            "assignment_id": assignment_id,
            "title": a.get("title", ""),
            "description": a.get("description", ""),
            "level": a.get("level"),
            "total_points": _decimal_to_int(a.get("total_points", 0)),
            "total_time_minutes": _decimal_to_int(a.get("total_time_minutes", 0)),
            "section_count": _decimal_to_int(a.get("section_count", 0)),
            "due_date": due_date_str,
            "deadline": deadline_str,
            "max_attempts": max_attempts,
            "is_locked": bool(a.get("is_locked", False)),
        }

        if sub:
            attempts_count = _decimal_to_int(sub.get("attempts_count", 0))
            attempts_remaining: Optional[int] = None
            if max_attempts is not None:
                attempts_remaining = max(0, max_attempts - attempts_count)
            card.update({
                "score": _decimal_to_int(sub.get("score", 0)),
                "percentage": float(sub.get("percentage", 0)),
                "attempts_count": attempts_count,
                "attempts_remaining": attempts_remaining,
                "can_retake": (attempts_remaining is None or attempts_remaining > 0),
                "submitted_at": str(sub.get("submitted_at", "")),
                "status": "completed",
            })
            completed.append(card)
        else:
            is_past_deadline = deadline_dt is not None and now_dt > deadline_dt
            if is_past_deadline:
                card["status"] = "missed"
                missed.append(card)
            else:
                card["status"] = "active"
                active.append(card)

    def _dl_key(c: Dict[str, Any]) -> str:
        return str(c.get("deadline") or "9999-12-31")

    active.sort(key=_dl_key)
    missed.sort(key=_dl_key)
    completed.sort(key=lambda c: str(c.get("submitted_at") or ""), reverse=True)

    return active, completed, missed


def get_student_active_assignments(college_id: str, user_id: str) -> Dict[str, Any]:
    """Assignments the student has NOT submitted yet and deadline has not passed."""
    active, _, _ = _build_student_assignment_cards(college_id, user_id)
    return {
        "college_id": college_id,
        "user_id": user_id,
        "status": "active",
        "assignments": active,
        "total_count": len(active),
    }


def get_student_completed_assignments(college_id: str, user_id: str) -> Dict[str, Any]:
    """Assignments the student has finalized at least once."""
    _, completed, _ = _build_student_assignment_cards(college_id, user_id)
    return {
        "college_id": college_id,
        "user_id": user_id,
        "status": "completed",
        "assignments": completed,
        "total_count": len(completed),
    }


def get_student_missed_assignments(college_id: str, user_id: str) -> Dict[str, Any]:
    """Assignments whose deadline has passed and student never submitted."""
    _, _, missed = _build_student_assignment_cards(college_id, user_id)
    return {
        "college_id": college_id,
        "user_id": user_id,
        "status": "missed",
        "assignments": missed,
        "total_count": len(missed),
    }


# ---------------------------------------------------------------------------
# Code execution (Judge0) — run sample & run tests
# ---------------------------------------------------------------------------

def run_college_sample(
    assignment_id: str, section_id: str, question_id: str,
    language_id: int, source_code: str, stdin: str = ""
) -> Dict[str, Any]:
    """Execute source_code with a single custom stdin via Judge0 (scratchpad)."""
    if not JUDGE0_BASE_URL:
        raise HTTPException(status_code=503, detail="Code execution is not configured on this server.")

    question = get_college_question(assignment_id, section_id, question_id)
    if question.get("question_type") != "coding":
        raise HTTPException(status_code=400, detail="Run code is only supported for coding questions")

    result = _post_judge0({
        "language_id": language_id,
        "source_code": source_code,
        "stdin": stdin or "",
    })
    return {
        "status": result.get("status", {}).get("description", "Unknown"),
        "stdout": result.get("stdout"),
        "stderr": result.get("stderr"),
        "compile_output": result.get("compile_output"),
        "time": result.get("time"),
        "memory": result.get("memory"),
    }


def run_college_tests(
    assignment_id: str, section_id: str, question_id: str,
    language_id: int, source_code: str
) -> Dict[str, Any]:
    """Run source_code against all test cases via Judge0."""
    if not JUDGE0_BASE_URL:
        raise HTTPException(status_code=503, detail="Code execution is not configured on this server.")

    question = get_college_question(assignment_id, section_id, question_id)
    if question.get("question_type") != "coding":
        raise HTTPException(status_code=400, detail="Run code is only supported for coding questions")

    test_cases: List[Dict[str, Any]] = question.get("test_cases") or []
    if not test_cases:
        raise HTTPException(status_code=400, detail="This question has no test cases configured")

    total_points: int = _decimal_to_int(question.get("points", 0))
    points_per_case: float = total_points / len(test_cases)

    results: List[Dict[str, Any]] = []
    passed_count: int = 0
    earned_points: float = 0.0
    compile_output: Optional[str] = None

    for index, tc in enumerate(test_cases, start=1):
        is_hidden = bool(tc.get("is_hidden"))
        judge_result = _post_judge0({
            "language_id": language_id,
            "source_code": source_code,
            "stdin": tc.get("input", ""),
            "expected_output": tc.get("expected_output", ""),
        })

        stdout = _normalize_output(judge_result.get("stdout"))
        expected = _normalize_output(tc.get("expected_output"))
        status_desc: str = judge_result.get("status", {}).get("description", "Unknown")
        passed = stdout == expected and status_desc == "Accepted"

        if not compile_output and judge_result.get("compile_output"):
            compile_output = judge_result["compile_output"]

        if passed:
            passed_count += 1
            earned_points += points_per_case

        result_item: Dict[str, Any] = {
            "index": index,
            "passed": passed,
            "status": status_desc,
            "stdout": judge_result.get("stdout"),
            "stderr": judge_result.get("stderr"),
            "compile_output": judge_result.get("compile_output"),
            "time": judge_result.get("time"),
            "memory": judge_result.get("memory"),
            "is_hidden": is_hidden,
        }
        if not is_hidden:
            result_item["input"] = tc.get("input")
            result_item["expected_output"] = tc.get("expected_output")

        results.append(result_item)

    return {
        "question_id": question_id,
        "status": "COMPLETED",
        "passed_count": passed_count,
        "total_count": len(test_cases),
        "points_earned": int(round(earned_points)),
        "total_points": total_points,
        "compile_output": compile_output,
        "results": results,
    }
