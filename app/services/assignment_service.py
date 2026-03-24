import json
import os
import time
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException
from boto3.dynamodb.conditions import Attr, Key

from app.dynamo import assignments_table, course_enrollments_table, courses_table as courses_tbl


JUDGE0_BASE_URL = os.getenv("JUDGE0_BASE_URL")
JUDGE0_API_KEY = os.getenv("JUDGE0_API_KEY")


def _normalize_datetime(value):
    """Convert datetime to ISO format string for DynamoDB storage"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        # Validate and normalize the string format
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return dt.isoformat()
        except ValueError:
            return value  # Return as-is if parsing fails
    return str(value)


def _now_ts() -> int:
    """Current timestamp as integer"""
    return int(time.time())


def _now_dt() -> datetime:
    """Current UTC-aware datetime"""
    return datetime.now(timezone.utc)


def _parse_dt_aware(value) -> "datetime | None":
    """Parse a date string or datetime to a UTC-aware datetime. Returns None on failure."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
    elif isinstance(value, datetime):
        dt = value
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _calculate_total_points_from_sections(assignment_id: str) -> int:
    """Calculate total points from all sections in assignment"""
    try:
        response = assignments_table.scan(
            FilterExpression=Attr("entity_type").eq("section") & 
                           Attr("assignment_id").eq(assignment_id)
        )
        sections = response.get("Items", [])
        total = sum(int(section.get("total_points", 0) or 0) for section in sections)
        return total
    except:
        return 0


def _calculate_total_time_from_sections(assignment_id: str) -> int:
    """Calculate total time from all sections in assignment"""
    try:
        response = assignments_table.scan(
            FilterExpression=Attr("entity_type").eq("section") & 
                           Attr("assignment_id").eq(assignment_id)
        )
        sections = response.get("Items", [])
        total = sum(int(section.get("time_limit_minutes", 0) or 0) for section in sections)
        return total
    except:
        return 0


def _calculate_section_points(questions: List[Dict[str, Any]]) -> int:
    """Calculate total points from questions in a section"""
    total = 0
    for question in questions:
        total += question.get("points", 0)
    return total


def _update_assignment_totals(assignment_id: str):
    """Update assignment total points and time from sections"""
    try:
        total_points = _calculate_total_points_from_sections(assignment_id)
        total_time = _calculate_total_time_from_sections(assignment_id)
        
        assignments_table.update_item(
            Key={"PK": assignment_id, "SK": "ASSIGNMENT"},
            UpdateExpression="SET total_points = :points, total_time_minutes = :time, updated_at = :updated_at",
            ExpressionAttributeValues={
                ":points": total_points,
                ":time": total_time,
                ":updated_at": _now_dt().isoformat()
            }
        )
    except Exception as e:
        # Log error but don't fail the operation
        print(f"Warning: Failed to update assignment totals: {e}")


def _calculate_total_points(questions: List[Dict[str, Any]]) -> int:
    """Calculate total points from all questions (legacy function)"""
    total = 0
    for question in questions:
        total += question.get("points", 0)
    return total


# ── Per-question DynamoDB helpers ─────────────────────────────────────────────

def _clean_question_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Strip internal DynamoDB keys and coerce Decimal to int."""
    item = dict(item)
    item.pop("PK", None)
    item.pop("SK", None)
    item.pop("entity_type", None)
    for int_field in ("points", "order", "time_limit_minutes"):
        if item.get(int_field) is not None:
            item[int_field] = int(item[int_field])
    for tc in item.get("test_cases") or []:
        if isinstance(tc, dict) and tc.get("points") is not None:
            tc["points"] = int(tc["points"])
    return item


def _load_section_questions(section_id: str) -> List[Dict[str, Any]]:
    """Query all question items for a section, sorted by order."""
    try:
        resp = assignments_table.query(
            KeyConditionExpression=Key("PK").eq(section_id) & Key("SK").begins_with("QUESTION#"),
            ScanIndexForward=True,
        )
        questions = [_clean_question_item(dict(q)) for q in resp.get("Items", [])]
        questions.sort(key=lambda q: q.get("order", 999))
        return questions
    except Exception:
        return []


def _recalculate_section_points_from_questions(section_id: str) -> int:
    """Sum points of all question items stored for a section."""
    try:
        resp = assignments_table.query(
            KeyConditionExpression=Key("PK").eq(section_id) & Key("SK").begins_with("QUESTION#")
        )
        return sum(int(q.get("points", 0)) for q in resp.get("Items", []))
    except Exception:
        return 0


def _sync_section_total_points(section_id: str, assignment_id: str):
    """Recalculate section total_points/question_count from question items and roll up."""
    try:
        resp = assignments_table.query(
            KeyConditionExpression=Key("PK").eq(section_id) & Key("SK").begins_with("QUESTION#")
        )
        items = resp.get("Items", [])
        total = sum(int(q.get("points", 0)) for q in items)
        qcount = len(items)
        assignments_table.update_item(
            Key={"PK": section_id, "SK": "SECTION"},
            UpdateExpression="SET total_points = :tp, question_count = :qc, updated_at = :ua",
            ExpressionAttributeValues={
                ":tp": total,
                ":qc": qcount,
                ":ua": _now_dt().isoformat(),
            },
        )
        _update_assignment_totals(assignment_id)
    except Exception as e:
        print(f"Warning: _sync_section_total_points failed: {e}")


def _post_judge0(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Submit code to Judge0 for execution"""
    url = f"{JUDGE0_BASE_URL}/submissions?base64_encoded=false&wait=true"
    headers = {"Content-Type": "application/json"}
    
    if JUDGE0_API_KEY:
        headers["X-RapidAPI-Key"] = JUDGE0_API_KEY
    
    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=20)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Judge0 request failed: {exc}")

    if response.status_code >= 400:
        error_detail = f"Judge0 error: {response.status_code}"
        try:
            error_body = response.json()
            error_detail += f" - {error_body}"
        except:
            error_detail += f" - {response.text}"
        raise HTTPException(status_code=502, detail=error_detail)

    return response.json()


# Assignment CRUD Operations
def create_assignment(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new assignment (sections will be added separately)"""
    assignment_id = f"assign_{uuid.uuid4().hex[:8]}"
    now = _now_dt()
    
    # Validate required fields
    if not payload.get("title"):
        raise HTTPException(status_code=400, detail="Title is required")
    if not payload.get("description"):
        raise HTTPException(status_code=400, detail="Description is required")
    if not payload.get("created_by"):
        raise HTTPException(status_code=400, detail="created_by is required")
    
    # Validate availability window
    start_date = payload.get("start_date")
    deadline = payload.get("deadline")
    
    if start_date and deadline:
        start_dt = _parse_dt_aware(start_date)
        deadline_dt = _parse_dt_aware(deadline)
        if start_dt and deadline_dt and start_dt >= deadline_dt:
            raise HTTPException(
                status_code=400,
                detail="start_date must be before deadline"
            )
    
    assignment_data = {
        "PK": assignment_id,
        "SK": "ASSIGNMENT",
        "assignment_id": assignment_id,
        "entity_type": "assignment",
        "title": payload["title"],
        "course_id": payload.get("course_id"),
        "course_name": payload.get("course_name"),
        "description": payload["description"],
        "created_by": payload["created_by"],
        "instructor_name": payload.get("instructor_name"),
        "total_points": 0,  # Will be calculated from sections
        "total_time_minutes": 0,  # Will be calculated from sections
        "section_count": 0,
        "start_date": _normalize_datetime(payload.get("start_date")),
        "deadline": _normalize_datetime(payload.get("deadline")),
        "is_locked": payload.get("is_locked", False),
        "level": payload.get("level", "intermediate"),
        "max_attempts": payload.get("max_attempts"),  # None = unlimited
        "tags": payload.get("tags", []),
        "instructions": payload.get("instructions"),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    
    try:
        assignments_table.put_item(Item=assignment_data)
        return {
            "assignment_id": assignment_id,
            "status": "created",
            "created_at": now,
            "total_points": 0,
            "total_time_minutes": 0,
            "section_count": 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create assignment: {str(e)}")


# Section CRUD Operations
def create_section(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new section within an assignment"""
    assignment_id = payload.get("assignment_id")
    if not assignment_id:
        raise HTTPException(status_code=400, detail="assignment_id is required")
    
    # Check if assignment exists
    try:
        get_assignment(assignment_id)
    except HTTPException:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    section_id = f"sect_{uuid.uuid4().hex[:8]}"
    now = _now_dt()
    
    # Validate required fields
    if not payload.get("title"):
        raise HTTPException(status_code=400, detail="Section title is required")
    
    questions = payload.get("questions", [])
    section_points = _calculate_section_points(questions)
    
    # Auto-assign order if not provided
    order = payload.get("order")
    if order is None:
        # Get highest order + 1
        try:
            response = assignments_table.scan(
                FilterExpression=Attr("entity_type").eq("section") & 
                               Attr("assignment_id").eq(assignment_id)
            )
            sections = response.get("Items", [])
            max_order = max([s.get("order", 0) for s in sections]) if sections else 0
            order = max_order + 1
        except:
            order = 1
    
    section_data = {
        "PK": section_id,
        "SK": "SECTION",
        "section_id": section_id,
        "assignment_id": assignment_id,
        "entity_type": "section",
        "title": payload["title"],
        "description": payload.get("description"),
        "questions": [],  # Questions are stored as separate items
        "question_count": 0,
        "total_points": 0,
        "time_limit_minutes": payload.get("time_limit_minutes"),
        "order": order,
        "instructions": payload.get("instructions"),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    try:
        assignments_table.put_item(Item=section_data)

        # Store each question as a separate DynamoDB item
        for idx, q in enumerate(questions):
            q_dict = q if isinstance(q, dict) else (q.dict() if hasattr(q, "dict") else dict(q))
            if not q_dict.get("order"):
                q_dict = dict(q_dict)
                q_dict["order"] = idx + 1
            _store_question_for_section(section_id, assignment_id, q_dict)

        # Update assignment section count and recalculate totals from stored question items
        _update_assignment_section_count(assignment_id)
        _sync_section_total_points(section_id, assignment_id)

        final_points = _recalculate_section_points_from_questions(section_id)
        return {
            "section_id": section_id,
            "assignment_id": assignment_id,
            "status": "created",
            "created_at": now.isoformat(),
            "total_points": final_points,
            "question_count": len(questions)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create section: {str(e)}")


def _update_assignment_section_count(assignment_id: str):
    """Update the section count for an assignment"""
    try:
        response = assignments_table.scan(
            FilterExpression=Attr("entity_type").eq("section") & 
                           Attr("assignment_id").eq(assignment_id)
        )
        section_count = len(response.get("Items", []))
        
        assignments_table.update_item(
            Key={"PK": assignment_id, "SK": "ASSIGNMENT"},
            UpdateExpression="SET section_count = :count",
            ExpressionAttributeValues={":count": section_count}
        )
    except Exception as e:
        print(f"Warning: Failed to update section count: {e}")


def get_section(section_id: str) -> Dict[str, Any]:
    """Get section by ID, loading questions from separate items."""
    try:
        response = assignments_table.get_item(Key={"PK": section_id, "SK": "SECTION"})

        if "Item" not in response:
            raise HTTPException(status_code=404, detail="Section not found")

        section = dict(response["Item"])

        # Load questions from separate items (new storage format)
        questions = _load_section_questions(section_id)

        # Backward compat: fall back to inline questions for old data
        if not questions and isinstance(section.get("questions"), list) and section["questions"]:
            questions = [
                dict(q) if not isinstance(q, dict) else q for q in section["questions"]
            ]

        section["questions"] = questions
        section["question_count"] = len(questions)

        # Clean internal fields and coerce Decimal
        section.pop("PK", None)
        section.pop("SK", None)
        section.pop("entity_type", None)
        for int_field in ("total_points", "time_limit_minutes", "order"):
            if section.get(int_field) is not None:
                section[int_field] = int(section[int_field])
        if section.get("order", 0) < 1:
            section["order"] = 1

        return section
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get section: {str(e)}")


def update_section(section_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Update an existing section"""
    # Check if section exists
    existing_section = get_section(section_id)
    assignment_id = existing_section["assignment_id"]
    
    # Build update expression
    update_expression = "SET updated_at = :updated_at"
    expression_values = {":updated_at": _now_dt().isoformat()}
    
    if "title" in payload:
        update_expression += ", title = :title"
        expression_values[":title"] = payload["title"]
    
    if "description" in payload:
        update_expression += ", description = :description"
        expression_values[":description"] = payload["description"]
    
    # 'questions' are managed via the dedicated /questions endpoint
    if "time_limit_minutes" in payload:
        update_expression += ", time_limit_minutes = :time_limit_minutes"
        expression_values[":time_limit_minutes"] = payload["time_limit_minutes"]
        
    if "order" in payload:
        update_expression += ", #order = :order"
        expression_values[":order"] = payload["order"]
        # Add ExpressionAttributeNames for reserved word
        expression_names = {"#order": "order"}
    else:
        expression_names = None
        
    if "instructions" in payload:
        update_expression += ", instructions = :instructions"
        expression_values[":instructions"] = payload["instructions"]

    try:
        update_kwargs = {
            "Key": {"PK": section_id, "SK": "SECTION"},
            "UpdateExpression": update_expression,
            "ExpressionAttributeValues": expression_values,
        }
        if expression_names:
            update_kwargs["ExpressionAttributeNames"] = expression_names
            
        assignments_table.update_item(**update_kwargs)
        
        # Update assignment totals
        _update_assignment_totals(assignment_id)
        
        return {"status": "updated", "section_id": section_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update section: {str(e)}")


def delete_section(section_id: str) -> Dict[str, Any]:
    """Delete a section"""
    # Check if section exists and get assignment_id
    section = get_section(section_id)
    assignment_id = section["assignment_id"]
    
    try:
        # Cascade-delete all question items for this section
        q_resp = assignments_table.query(
            KeyConditionExpression=Key("PK").eq(section_id) & Key("SK").begins_with("QUESTION#")
        )
        with assignments_table.batch_writer() as batch:
            for q in q_resp.get("Items", []):
                batch.delete_item(Key={"PK": section_id, "SK": q["SK"]})

        assignments_table.delete_item(Key={"PK": section_id, "SK": "SECTION"})

        # Update assignment section count and totals
        _update_assignment_section_count(assignment_id)
        _update_assignment_totals(assignment_id)

        return {"status": "deleted", "section_id": section_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete section: {str(e)}")


def list_sections(assignment_id: str) -> Dict[str, Any]:
    """List all sections for an assignment, with questions loaded from separate items."""
    try:
        response = assignments_table.scan(
            FilterExpression=Attr("entity_type").eq("section") &
                           Attr("assignment_id").eq(assignment_id)
        )

        sections = response.get("Items", [])

        # Sort by order
        sections.sort(key=lambda x: x.get("order", 999))

        cleaned: List[Dict[str, Any]] = []
        for section in sections:
            s = dict(section)
            s.pop("PK", None)
            s.pop("SK", None)
            s.pop("entity_type", None)

            # Coerce DynamoDB Decimal → int
            for int_field in ("total_points", "time_limit_minutes", "order"):
                if s.get(int_field) is not None:
                    s[int_field] = int(s[int_field])
            if s.get("order", 0) < 1:
                s["order"] = 1

            # Load questions from separate items (fall back to inline for old data)
            sid = s.get("section_id", "")
            if sid:
                qs = _load_section_questions(sid)
                if qs:
                    s["questions"] = qs
                elif isinstance(s.get("questions"), list):
                    pass  # keep inline questions for backward-compat
                else:
                    s["questions"] = []
            else:
                s["questions"] = []

            s["question_count"] = len(s.get("questions", []))
            cleaned.append(s)

        total_points = sum(int(s.get("total_points", 0)) for s in cleaned)
        total_time = sum(int(s.get("time_limit_minutes", 0) or 0) for s in cleaned)

        return {
            "assignment_id": assignment_id,
            "sections": cleaned,
            "total_sections": len(cleaned),
            "total_points": total_points,
            "total_time_minutes": total_time,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list sections: {str(e)}")


def get_assignment(assignment_id: str) -> Dict[str, Any]:
    """Get assignment by ID with all sections"""
    try:
        response = assignments_table.get_item(Key={"PK": assignment_id, "SK": "ASSIGNMENT"})
        
        if "Item" not in response:
            raise HTTPException(status_code=404, detail="Assignment not found")
        
        assignment = response["Item"]
        
        # Get all sections for this assignment
        sections_response = assignments_table.scan(
            FilterExpression=Attr("entity_type").eq("section") & 
                           Attr("assignment_id").eq(assignment_id)
        )
        
        sections = sections_response.get("Items", [])
        
        # Sort sections by order
        sections.sort(key=lambda x: x.get("order", 999))
        
        # Clean up section data and coerce Decimal -> int/float for JSON serialisation
        for section in sections:
            section.pop("PK", None)
            section.pop("SK", None)
            section.pop("entity_type", None)
            # DynamoDB returns numbers as Decimal — convert to plain Python types
            for int_field in ("total_points", "time_limit_minutes", "order"):
                if section.get(int_field) is not None:
                    section[int_field] = int(section[int_field])
            # Ensure order is at least 1 for data stored before the constraint existed
            if section.get("order", 0) < 1:
                section["order"] = 1
            # Load questions from separate items (with inline fallback for old data)
            sid = section.get("section_id", "")
            if sid:
                qs = _load_section_questions(sid)
                if qs:
                    section["questions"] = qs
                elif not isinstance(section.get("questions"), list):
                    section["questions"] = []

        # Add sections to assignment
        assignment["sections"] = sections

        # Recompute totals live from the loaded sections (always accurate)
        assignment["total_points"] = sum(s.get("total_points", 0) for s in sections)
        assignment["total_time_minutes"] = sum(s.get("time_limit_minutes", 0) or 0 for s in sections)
        assignment["section_count"] = len(sections)

        # Coerce other Decimal fields on the assignment item itself
        for int_field in ("max_attempts",):
            if assignment.get(int_field) is not None:
                try:
                    assignment[int_field] = int(assignment[int_field])
                except (TypeError, ValueError):
                    pass
        
        # Parse dates back to datetime objects if needed
        if assignment.get("start_date"):
            try:
                assignment["start_date"] = datetime.fromisoformat(assignment["start_date"])
            except ValueError:
                pass
        
        if assignment.get("deadline"):
            try:
                assignment["deadline"] = datetime.fromisoformat(assignment["deadline"])
            except ValueError:
                pass
                
        if assignment.get("created_at"):
            try:
                assignment["created_at"] = datetime.fromisoformat(assignment["created_at"])
            except ValueError:
                pass
                
        if assignment.get("updated_at"):
            try:
                assignment["updated_at"] = datetime.fromisoformat(assignment["updated_at"])
            except ValueError:
                pass
        
        return assignment
    except Exception as e:
        if "Assignment not found" in str(e):
            raise e
        raise HTTPException(status_code=500, detail=f"Failed to get assignment: {str(e)}")


def update_assignment(assignment_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Update an existing assignment (sections updated separately)"""
    # Check if assignment exists
    get_assignment(assignment_id)

    # Build update expression
    # Some field names are DynamoDB reserved keywords and must be aliased via
    # ExpressionAttributeNames: level, status, name, ...
    update_expression = "SET updated_at = :updated_at"
    expression_values: Dict[str, Any] = {":updated_at": _now_dt().isoformat()}
    expression_names: Dict[str, str] = {}

    plain_fields = [
        "title", "description", "course_id", "course_name",
        "instructor_name", "is_locked", "max_attempts", "tags", "instructions",
    ]
    # Fields that are DynamoDB reserved keywords -> must use #alias
    reserved_fields = {"level": "#lvl", "status": "#sts", "name": "#nm"}

    for field in plain_fields:
        if field in payload:
            update_expression += f", {field} = :{field}"
            expression_values[f":{field}"] = payload[field]

    for field, alias in reserved_fields.items():
        if field in payload:
            update_expression += f", {alias} = :{field}"
            expression_names[alias] = field
            expression_values[f":{field}"] = payload[field]

    if "start_date" in payload:
        update_expression += ", start_date = :start_date"
        expression_values[":start_date"] = _normalize_datetime(payload["start_date"])

    if "deadline" in payload:
        update_expression += ", deadline = :deadline"
        expression_values[":deadline"] = _normalize_datetime(payload["deadline"])

    update_kwargs: Dict[str, Any] = {
        "Key": {"PK": assignment_id, "SK": "ASSIGNMENT"},
        "UpdateExpression": update_expression,
        "ExpressionAttributeValues": expression_values,
    }
    if expression_names:
        update_kwargs["ExpressionAttributeNames"] = expression_names

    try:
        assignments_table.update_item(**update_kwargs)
        return {"status": "updated", "assignment_id": assignment_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update assignment: {str(e)}")


def delete_assignment(assignment_id: str) -> Dict[str, Any]:
    """Delete an assignment"""
    # Check if assignment exists
    get_assignment(assignment_id)
    
    try:
        assignments_table.delete_item(Key={"PK": assignment_id, "SK": "ASSIGNMENT"})
        return {"status": "deleted", "assignment_id": assignment_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete assignment: {str(e)}")


def list_assignments(
    course_id: Optional[str] = None,
    created_by: Optional[str] = None,
    level: Optional[str] = None,
    is_locked: Optional[bool] = None,
    limit: int = 20,
    next_key: Optional[str] = None
) -> Dict[str, Any]:
    """List assignments with filtering"""
    try:
        scan_kwargs = {
            "FilterExpression": Attr("entity_type").eq("assignment"),
            "Limit": limit
        }
        
        if next_key:
            scan_kwargs["ExclusiveStartKey"] = {"PK": next_key, "SK": "ASSIGNMENT"}
        
        # Add filters
        filter_expressions = [Attr("entity_type").eq("assignment")]
        
        if course_id:
            filter_expressions.append(Attr("course_id").eq(course_id))
        if created_by:
            filter_expressions.append(Attr("created_by").eq(created_by))
        if level:
            filter_expressions.append(Attr("level").eq(level))
        if is_locked is not None:
            filter_expressions.append(Attr("is_locked").eq(is_locked))
        
        # Combine filters
        if len(filter_expressions) > 1:
            combined_filter = filter_expressions[0]
            for expr in filter_expressions[1:]:
                combined_filter = combined_filter & expr
            scan_kwargs["FilterExpression"] = combined_filter
        
        response = assignments_table.scan(**scan_kwargs)
        assignments = response.get("Items", [])
        
        # Clean up the response
        for assignment in assignments:
            # Remove DynamoDB internal fields
            assignment.pop("PK", None)
            assignment.pop("SK", None)
            assignment.pop("entity_type", None)
            # Coerce Decimal → int for numeric fields
            for int_field in ("total_points", "total_time_minutes", "section_count", "max_attempts"):
                if assignment.get(int_field) is not None:
                    try:
                        assignment[int_field] = int(assignment[int_field])
                    except (TypeError, ValueError):
                        pass
        
        result = {
            "assignments": assignments,
            "total_count": len(assignments),
        }
        
        if "LastEvaluatedKey" in response:
            result["next_key"] = response["LastEvaluatedKey"]["PK"]
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list assignments: {str(e)}")


def get_assignment_prestart(assignment_id: str, user_id: str) -> Dict[str, Any]:
    """
    Return all metadata a student needs to see before starting an assignment:
    section overview, attempt info, instructions, deadline, totals.
    """
    assignment = get_assignment(assignment_id)
    sections_raw = assignment.get("sections", [])

    # Build lightweight section summaries
    section_items = []
    total_questions = 0
    for s in sections_raw:
        qs = s.get("questions", [])
        qcount = len(qs)
        total_questions += qcount
        section_items.append({
            "section_id": s.get("section_id", ""),
            "title": s.get("title", ""),
            "description": s.get("description"),
            "question_count": qcount,
            "time_limit_minutes": int(s.get("time_limit_minutes", 0) or 0),
            "total_points": int(s.get("total_points", 0)),
            "order": int(s.get("order", 1)),
        })
    section_items.sort(key=lambda x: x["order"])

    # Attempt info
    max_attempts = assignment.get("max_attempts")
    if max_attempts is not None:
        max_attempts = int(max_attempts)

    submission = _get_user_submission_internal(user_id, assignment_id)
    attempts_used = int(submission.get("attempts_count", 0)) if submission else 0

    if max_attempts is None:
        attempts_left = None   # unlimited
        can_attempt = True
    else:
        attempts_left = max(0, max_attempts - attempts_used)
        can_attempt = attempts_left > 0

    # Instructions as both raw string and split list
    instructions_raw = assignment.get("instructions") or ""
    instructions_list = [
        line.strip() for line in instructions_raw.splitlines() if line.strip()
    ]

    # Date strings
    def _dt_str(val):
        if val is None:
            return None
        if hasattr(val, "isoformat"):
            return val.isoformat()
        return str(val)

    return {
        "assignment_id": assignment_id,
        "title": str(assignment.get("title", "")),
        "description": str(assignment.get("description", "")),
        "course_id": assignment.get("course_id"),
        "course_name": assignment.get("course_name"),
        "instructor_name": assignment.get("instructor_name"),
        "level": str(assignment.get("level", "intermediate")),
        "section_count": len(section_items),
        "question_count": total_questions,
        "total_time_minutes": int(assignment.get("total_time_minutes", 0)),
        "total_points": int(assignment.get("total_points", 0)),
        "max_attempts": max_attempts,
        "attempts_used": attempts_used,
        "attempts_left": attempts_left,
        "can_attempt": can_attempt,
        "start_date": _dt_str(assignment.get("start_date")),
        "deadline": _dt_str(assignment.get("deadline")),
        "sections": section_items,
        "instructions": instructions_raw or None,
        "instructions_list": instructions_list,
        "tags": list(assignment.get("tags") or []),
    }


def check_assignment_availability(assignment_id: str) -> Dict[str, Any]:
    """Check if assignment is available for taking"""
    assignment = get_assignment(assignment_id)
    
    # Check if locked
    if assignment.get("is_locked", False):
        raise HTTPException(status_code=400, detail="Assignment is currently locked")
    
    # Check availability window (start_date to deadline)
    now_dt = _now_dt()
    start_date = assignment.get("start_date")
    deadline = assignment.get("deadline")
    
    # Check if assignment has started
    if start_date:
        start_dt = _parse_dt_aware(start_date)
        if start_dt and start_dt > now_dt:
            raise HTTPException(
                status_code=400,
                detail=f"Assignment is not yet available. It starts on {start_date}"
            )

    # Check if assignment deadline has passed
    if deadline:
        deadline_dt = _parse_dt_aware(deadline)
        if deadline_dt and deadline_dt < now_dt:
            # Auto-mark assignment as overdue
            try:
                update_assignment(assignment_id, {"status": "overdue"})
            except Exception:
                pass  # best-effort; don't block the error response
            raise HTTPException(status_code=400, detail="Assignment deadline has passed")

    return {"available": True, "message": "Assignment is available"}


def get_assignment_stats(assignment_id: str) -> Dict[str, Any]:
    """Get statistics for an assignment"""
    # Load assignment and build section_id -> title map
    assignment = get_assignment(assignment_id)
    section_title_map: Dict[str, str] = {
        s.get("section_id", ""): str(s.get("title", ""))
        for s in assignment.get("sections", [])
        if s.get("section_id")
    }

    try:
        # Query all submissions for this assignment
        response = assignments_table.scan(
            FilterExpression=Attr("entity_type").eq("user_submission") & 
                           Attr("assignment_id").eq(assignment_id)
        )
        
        submissions = response.get("Items", [])
        
        if not submissions:
            return {
                "assignment_id": assignment_id,
                "total_students": 0,
                "completed_submissions": 0,
                "average_score": 0.0,
                "highest_score": 0,
                "lowest_score": 0,
                "average_time_minutes": None,
                "section_stats": [],
            }

        scores = [int(sub.get("score", 0)) for sub in submissions]
        completed_count = len([sub for sub in submissions if sub.get("status") == "submitted"])

        # Per-section stats: aggregate across all submissions
        section_score_map: Dict[str, List[int]] = {}
        for sub in submissions:
            for sec_res in sub.get("section_results", []):
                sid = sec_res.get("section_id", "")
                s_score = int(sec_res.get("score", 0))
                section_score_map.setdefault(sid, []).append(s_score)

        section_stats = [
            {
                "section_id": sid,
                "section_title": section_title_map.get(sid, ""),
                "average_score": round(sum(sc) / len(sc), 2) if sc else 0.0,
                "highest_score": max(sc) if sc else 0,
                "lowest_score": min(sc) if sc else 0,
                "total_submissions": len(sc),
            }
            for sid, sc in section_score_map.items()
        ]

        times = [
            float(sub["time_taken_minutes"])
            for sub in submissions
            if sub.get("time_taken_minutes") is not None
        ]

        stats = {
            "assignment_id": assignment_id,
            "total_students": len(set(sub.get("user_id") for sub in submissions)),
            "completed_submissions": completed_count,
            "average_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
            "highest_score": max(scores) if scores else 0,
            "lowest_score": min(scores) if scores else 0,
            "average_time_minutes": round(sum(times) / len(times), 2) if times else None,
            "section_stats": section_stats,
        }

        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get assignment stats: {str(e)}")


# ── Grading helpers ───────────────────────────────────────────────────────────

def _sanitize_for_dynamo(obj: Any) -> Any:
    """Recursively convert floats to Decimal for DynamoDB storage."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _sanitize_for_dynamo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_dynamo(item) for item in obj]
    return obj


def _grade_mcq(question: Dict[str, Any], selected_ids: List[str]) -> int:
    """Full points only when the exact set of option IDs matches."""
    correct = set(question.get("correct_option_ids", []))
    selected = set(selected_ids)
    if correct == selected:
        return int(question.get("points", 0))
    return 0


def _grade_fill_in_blank(question: Dict[str, Any], user_answers: List[str]) -> int:
    """Award proportional points per blank answered correctly."""
    correct_per_blank: List[List[str]] = question.get("correct_answers", [])
    if not correct_per_blank:
        return 0
    case_sensitive: bool = question.get("case_sensitive", False)
    total_points: int = int(question.get("points", 0))
    points_per_blank: float = total_points / len(correct_per_blank)
    earned: float = 0.0
    for i, user_ans in enumerate(user_answers):
        if i >= len(correct_per_blank):
            break
        acceptable = correct_per_blank[i]
        ua = user_ans if case_sensitive else user_ans.lower()
        acc = acceptable if case_sensitive else [a.lower() for a in acceptable]
        if ua in acc:
            earned += points_per_blank
    return int(round(earned))


def _grade_coding(
    question: Dict[str, Any],
    code: str,
    language: str,
    test_case_results: Optional[List[Dict[str, Any]]] = None,
) -> int:
    """Calculate earned points for a coding question.

    When *test_case_results* are supplied (UI ran Judge0 itself), use them
    directly.  Otherwise fall back to running Judge0 server-side.
    """
    test_cases: List[Dict[str, Any]] = question.get("test_cases", [])
    if not test_cases:
        return 0
    total_points: int = int(question.get("points", 0))
    points_per_case: float = total_points / len(test_cases)

    # ── Use client-provided results ──────────────────────────────────────────
    if test_case_results:
        earned: float = sum(
            points_per_case
            for r in test_case_results
            if r.get("passed") is True
        )
        return int(round(earned))

    # ── Fall back to server-side Judge0 ──────────────────────────────────────
    if not JUDGE0_BASE_URL or not code:
        return 0
    lang_map = {"python": 71, "javascript": 63, "java": 62, "cpp": 54, "c": 50}
    lang_id = lang_map.get(language.lower(), 71)
    earned = 0.0
    for tc in test_cases:
        try:
            result = _post_judge0({
                "source_code": code,
                "language_id": lang_id,
                "stdin": tc.get("input", ""),
                "expected_output": tc.get("expected_output", ""),
            })
            if result.get("status", {}).get("id") == 3:  # 3 = Accepted
                earned += points_per_case
        except Exception:
            pass
    return int(round(earned))


# ── Run code (live test execution) ──────────────────────────────────────────

def _normalize_output(text: Optional[str]) -> str:
    """Strip trailing whitespace/newlines for reliable comparison."""
    if not text:
        return ""
    return text.strip()


def run_assignment_sample(
    assignment_id: str, section_id: str, question_id: str,
    language_id: int, source_code: str, stdin: str = ""
) -> Dict[str, Any]:
    """Execute *source_code* with a single custom *stdin* via Judge0.

    Does NOT compare against test cases — just returns the raw output so the
    user can verify their logic before running the full test suite.
    """
    if not JUDGE0_BASE_URL:
        raise HTTPException(status_code=503, detail="Code execution is not configured on this server.")

    # Validate the question exists and belongs to this assignment
    question = get_question_item(section_id, question_id)
    if question.get("assignment_id") != assignment_id:
        raise HTTPException(status_code=404, detail="Question not found in this assignment")
    if question.get("question_type") != "coding":
        raise HTTPException(status_code=400, detail="Run code is only supported for coding questions")

    payload = {
        "language_id": language_id,
        "source_code": source_code,
        "stdin": stdin or "",
    }
    result = _post_judge0(payload)
    return {
        "status": result.get("status", {}).get("description", "Unknown"),
        "stdout": result.get("stdout"),
        "stderr": result.get("stderr"),
        "compile_output": result.get("compile_output"),
        "time": result.get("time"),
        "memory": result.get("memory"),
    }


def run_assignment_code(
    assignment_id: str, section_id: str, question_id: str, language_id: int, source_code: str
) -> Dict[str, Any]:
    """Run *source_code* against the question's test cases via Judge0.

    Visible test cases include input / expected_output in the result.
    Hidden test cases only reveal pass/fail status.
    """
    if not JUDGE0_BASE_URL:
        raise HTTPException(status_code=503, detail="Code execution is not configured on this server.")

    # Fetch question and validate it belongs to this assignment/section
    question = get_question_item(section_id, question_id)
    if question.get("assignment_id") != assignment_id:
        raise HTTPException(status_code=404, detail="Question not found in this assignment")
    if question.get("question_type") != "coding":
        raise HTTPException(status_code=400, detail="Run code is only supported for coding questions")

    test_cases: List[Dict[str, Any]] = question.get("test_cases") or []
    if not test_cases:
        raise HTTPException(status_code=400, detail="This question has no test cases configured")

    total_points: int = int(question.get("points", 0))
    points_per_case: float = total_points / len(test_cases)

    results: List[Dict[str, Any]] = []
    passed_count: int = 0
    earned_points: float = 0.0
    compile_output: Optional[str] = None

    for index, tc in enumerate(test_cases, start=1):
        is_hidden = bool(tc.get("is_hidden"))
        payload = {
            "language_id": language_id,
            "source_code": source_code,
            "stdin": tc.get("input", ""),
            "expected_output": tc.get("expected_output", ""),
        }
        judge_result = _post_judge0(payload)

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


# ── User submission CRUD ──────────────────────────────────────────────────────

def _get_user_submission_internal(user_id: str, assignment_id: str) -> Optional[Dict[str, Any]]:
    """Return the stored submission item or None if it doesn't exist."""
    try:
        resp = assignments_table.get_item(
            Key={"PK": f"usub#{user_id}", "SK": f"ASSIGNMENT#{assignment_id}"}
        )
        return resp.get("Item")
    except Exception:
        return None


# ── Section-wise submission helpers ──────────────────────────────────────────

def _section_sub_sk(assignment_id: str, section_id: str) -> str:
    return f"SECT_SUB#{assignment_id}#{section_id}"


def _get_section_submission_internal(user_id: str, assignment_id: str, section_id: str) -> Optional[Dict[str, Any]]:
    """Return a stored per-section submission item or None."""
    try:
        resp = assignments_table.get_item(
            Key={"PK": f"usub#{user_id}", "SK": _section_sub_sk(assignment_id, section_id)}
        )
        return resp.get("Item")
    except Exception:
        return None


def _get_all_section_submissions(user_id: str, assignment_id: str) -> List[Dict[str, Any]]:
    """Return all per-section submission items for a user+assignment."""
    try:
        resp = assignments_table.query(
            KeyConditionExpression=Key("PK").eq(f"usub#{user_id}") &
                                   Key("SK").begins_with(f"SECT_SUB#{assignment_id}#")
        )
        return resp.get("Items", [])
    except Exception:
        return []


def _grade_section_answers(section: Dict[str, Any], answers: List[Dict[str, Any]]) -> tuple:
    """
    Grade answers for a single section.
    Returns (section_result_dict, section_score).
    """
    question_map: Dict[str, Dict[str, Any]] = {}
    for q in section.get("questions", []):
        qid = q.get("id") or q.get("question_id", "")
        if qid:
            question_map[qid] = q

    sec_score: int = 0
    q_results: List[Dict[str, Any]] = []

    for answer in answers:
        qid = answer.get("question_id", "")
        question = question_map.get(qid)
        if not question:
            q_results.append({
                "question_id": qid,
                "question_type": None,
                "is_correct": False,
                "points_earned": 0,
                "points_possible": 0,
                "error": "Question not found",
                "submitted_answer": {},
            })
            continue

        q_type = question.get("question_type", "")
        pts_possible: int = int(question.get("points", 0))
        pts_earned: int = 0

        if q_type == "multiple_choice":
            pts_earned = _grade_mcq(question, answer.get("selected_option_ids", []))
            submitted_answer = {"selected_option_ids": answer.get("selected_option_ids", [])}
        elif q_type == "fill_in_blank":
            pts_earned = _grade_fill_in_blank(question, answer.get("answers", []))
            submitted_answer = {"answers": answer.get("answers", [])}
        elif q_type == "coding":
            tcr = answer.get("test_case_results") or []
            pts_earned = _grade_coding(
                question,
                answer.get("code", ""),
                answer.get("language", "python"),
                test_case_results=tcr if tcr else None,
            )
            submitted_answer = {
                "code": answer.get("code", ""),
                "language": answer.get("language", "python"),
                "test_case_results": tcr,
            }
        else:
            submitted_answer = {}

        is_correct = pts_earned >= pts_possible and pts_possible > 0
        sec_score += pts_earned
        q_results.append({
            "question_id": qid,
            "question_type": q_type,
            "is_correct": is_correct,
            "points_earned": pts_earned,
            "points_possible": pts_possible,
            "submitted_answer": submitted_answer,
        })

    section_result = {
        "section_id": section.get("section_id", ""),
        "section_title": section.get("title", ""),
        "score": sec_score,
        "total_points": int(section.get("total_points", 0)),
        "question_results": q_results,
    }
    return section_result, sec_score


def submit_section_for_user(
    user_id: str, assignment_id: str, section_id: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Submit answers for one section.
    - Grades immediately and stores the result.
    - If this is the last section, auto-finalizes the full assignment submission.
    """
    assignment = get_assignment(assignment_id)

    # Availability checks
    if assignment.get("is_locked", False):
        raise HTTPException(status_code=400, detail="Assignment is locked")

    now_dt = _now_dt()
    raw_deadline = assignment.get("deadline")
    if raw_deadline:
        dl = _parse_dt_aware(raw_deadline)
        if dl and dl < now_dt:
            raise HTTPException(status_code=400, detail="Assignment deadline has passed")

    # Attempt-limit check (based on final assignment submission count)
    max_attempts = assignment.get("max_attempts")
    existing_final = _get_user_submission_internal(user_id, assignment_id)
    current_attempts: int = int(existing_final.get("attempts_count", 0)) if existing_final else 0
    if max_attempts is not None and current_attempts >= int(max_attempts):
        raise HTTPException(
            status_code=400,
            detail=f"Maximum attempts ({max_attempts}) already reached",
        )

    # Find the target section
    target_section = None
    for s in assignment.get("sections", []):
        if s.get("section_id") == section_id:
            target_section = s
            break
    if not target_section:
        raise HTTPException(status_code=404, detail="Section not found in this assignment")

    # Grade this section
    answers = payload.get("answers", [])
    section_result, sec_score = _grade_section_answers(target_section, answers)

    time_taken: int = int(payload.get("time_taken_minutes", 0))

    # Store the per-section submission (overwrite if resubmitting)
    sect_item = _sanitize_for_dynamo({
        "PK": f"usub#{user_id}",
        "SK": _section_sub_sk(assignment_id, section_id),
        "entity_type": "section_submission",
        "user_id": user_id,
        "assignment_id": assignment_id,
        "section_id": section_id,
        "score": sec_score,
        "total_points": int(target_section.get("total_points", 0)),
        "time_taken_minutes": time_taken,
        "submitted_at": now_dt.isoformat(),
        "question_results": section_result["question_results"],
    })
    try:
        assignments_table.put_item(Item=sect_item)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store section submission: {str(e)}")

    # Check if all sections are now submitted (for informational response only)
    all_sections = assignment.get("sections", [])
    all_section_ids = {s.get("section_id") for s in all_sections}
    submitted_items = _get_all_section_submissions(user_id, assignment_id)
    submitted_ids = {item.get("section_id") for item in submitted_items}
    all_done = all_section_ids.issubset(submitted_ids)

    return {
        "assignment_id": assignment_id,
        "section_id": section_id,
        "user_id": user_id,
        "score": sec_score,
        "total_points": int(target_section.get("total_points", 0)),
        "percentage": round(sec_score / int(target_section.get("total_points", 0)) * 100, 2)
                      if int(target_section.get("total_points", 0)) > 0 else 0.0,
        "time_taken_minutes": time_taken,
        "submitted_at": now_dt.isoformat(),
        "question_results": section_result["question_results"],
        "sections_submitted": len(submitted_ids),
        "sections_total": len(all_section_ids),
        "all_sections_done": all_done,
        "final_submission": None,
    }


def finalize_assignment_submission(user_id: str, assignment_id: str, user_name: str = "") -> Dict[str, Any]:
    """
    Explicitly finalize an assignment submission by aggregating all submitted
    section results. Use this after the user has submitted every section.

    - Sums scores and time_taken_minutes from all section submissions.
    - Overwrites any existing final submission record.
    - Returns the complete UserSubmissionResponse payload.
    """
    assignment = get_assignment(assignment_id)
    all_sections = assignment.get("sections", [])
    if not all_sections:
        raise HTTPException(status_code=400, detail="Assignment has no sections")

    submitted_items = _get_all_section_submissions(user_id, assignment_id)
    if not submitted_items:
        raise HTTPException(
            status_code=400,
            detail="No section submissions found. Submit all sections before finalizing.",
        )

    submitted_map = {item.get("section_id"): item for item in submitted_items}
    all_section_ids = [s.get("section_id") for s in all_sections]
    missing = [sid for sid in all_section_ids if sid not in submitted_map]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"The following sections have not been submitted yet: {missing}",
        )

    # Aggregate results
    section_results: List[Dict[str, Any]] = []
    total_score: int = 0
    total_time: int = 0
    for s in all_sections:
        sid = s.get("section_id", "")
        item = submitted_map[sid]
        sr = {
            "section_id": sid,
            "section_title": s.get("title", ""),
            "score": int(item.get("score", 0)),
            "total_points": int(item.get("total_points", 0)),
            "time_taken_minutes": int(item.get("time_taken_minutes", 0)),
            "submitted_at": str(item.get("submitted_at", "")),
            "question_results": item.get("question_results", []),
        }
        section_results.append(sr)
        total_score += int(item.get("score", 0))
        total_time += int(item.get("time_taken_minutes", 0))

    total_points: int = int(assignment.get("total_points", 0))
    percentage: float = round(total_score / total_points * 100, 2) if total_points > 0 else 0.0
    now_dt = _now_dt()

    # Determine attempt count (increment from existing if any)
    existing = _get_user_submission_internal(user_id, assignment_id)
    current_attempts: int = int(existing.get("attempts_count", 0)) if existing else 0
    new_attempts = current_attempts + 1

    resolved_name = str(user_name or "").strip()

    final_item = _sanitize_for_dynamo({
        "PK": f"usub#{user_id}",
        "SK": f"ASSIGNMENT#{assignment_id}",
        "entity_type": "user_submission",
        "user_id": user_id,
        "user_name": resolved_name,
        "assignment_id": assignment_id,
        "score": total_score,
        "total_points": total_points,
        "percentage": percentage,
        "attempts_count": new_attempts,
        "time_taken_minutes": total_time,
        "submitted_at": now_dt.isoformat(),
        "status": "submitted",
        "section_results": section_results,
    })
    try:
        assignments_table.put_item(Item=final_item)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save final submission: {str(e)}")

    return {
        "assignment_id": assignment_id,
        "user_id": user_id,
        "user_name": resolved_name or None,
        "score": total_score,
        "total_points": total_points,
        "percentage": percentage,
        "attempts_count": new_attempts,
        "time_taken_minutes": total_time,
        "submitted_at": now_dt.isoformat(),
        "status": "submitted",
        "section_results": section_results,
    }


def get_assignment_progress(user_id: str, assignment_id: str) -> Dict[str, Any]:
    """
    Return per-section submission status for a user:
    which sections are done, scores so far, and whether finalized.
    """
    assignment = get_assignment(assignment_id)
    all_sections = assignment.get("sections", [])
    submitted_items = _get_all_section_submissions(user_id, assignment_id)
    submitted_map = {item.get("section_id"): item for item in submitted_items}

    section_statuses = []
    total_score_so_far = 0
    for s in all_sections:
        sid = s.get("section_id", "")
        sub = submitted_map.get(sid)
        status_entry = {
            "section_id": sid,
            "title": s.get("title", ""),
            "order": int(s.get("order", 1)),
            "total_points": int(s.get("total_points", 0)),
            "submitted": sub is not None,
            "score": int(sub.get("score", 0)) if sub else None,
            "submitted_at": str(sub.get("submitted_at", "")) if sub else None,
            "time_taken_minutes": int(sub.get("time_taken_minutes", 0)) if sub else None,
        }
        if sub:
            total_score_so_far += int(sub.get("score", 0))
        section_statuses.append(status_entry)

    sections_submitted = len(submitted_map)
    sections_total = len(all_sections)
    all_done = sections_submitted == sections_total
    is_finalized = _get_user_submission_internal(user_id, assignment_id) is not None

    return {
        "assignment_id": assignment_id,
        "user_id": user_id,
        "sections_total": sections_total,
        "sections_submitted": sections_submitted,
        "sections_pending": sections_total - sections_submitted,
        "all_sections_done": all_done,
        "is_finalized": is_finalized,
        "section_statuses": section_statuses,
        "total_score_so_far": total_score_so_far,
        "total_points": int(assignment.get("total_points", 0)),
    }


def submit_assignment_for_user(
    user_id: str, assignment_id: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Grade and store a user's assignment submission.
    Only the *latest* submission is kept — previous data is overwritten.
    The attempt counter increments on every call.
    """
    # 1. Load assignment (validates it exists)
    assignment = get_assignment(assignment_id)

    # 2. Availability checks
    if assignment.get("is_locked", False):
        raise HTTPException(status_code=400, detail="Assignment is locked")

    now_dt = _now_dt()
    raw_deadline = assignment.get("deadline")
    if raw_deadline:
        dl = _parse_dt_aware(raw_deadline)
        if dl and dl < now_dt:
            raise HTTPException(status_code=400, detail="Assignment deadline has passed")

    # 3. Attempt-limit check
    max_attempts = assignment.get("max_attempts")
    existing = _get_user_submission_internal(user_id, assignment_id)
    current_attempts: int = int(existing.get("attempts_count", 0)) if existing else 0
    if max_attempts is not None and current_attempts >= int(max_attempts):
        raise HTTPException(
            status_code=400,
            detail=f"Maximum attempts ({max_attempts}) already reached",
        )

    # 4. Build question-id → question map from sections
    question_map: Dict[str, Dict[str, Any]] = {}
    section_meta: Dict[str, Dict[str, Any]] = {}
    for section in assignment.get("sections", []):
        sid = section.get("section_id") or section.get("id", "")
        section_meta[sid] = {
            "title": section.get("title", ""),
            "total_points": int(section.get("total_points", 0)),
        }
        for q in section.get("questions", []):
            qid = q.get("id") or q.get("question_id", "")
            if qid:
                question_map[qid] = q

    # 5. Grade each answer
    section_results: List[Dict[str, Any]] = []
    total_score: int = 0

    for sec_sub in payload.get("section_submissions", []):
        sid = sec_sub.get("section_id", "")
        sec_info = section_meta.get(sid, {"title": "", "total_points": 0})
        sec_score: int = 0
        q_results: List[Dict[str, Any]] = []

        for answer in sec_sub.get("answers", []):
            qid = answer.get("question_id", "")
            question = question_map.get(qid)
            if not question:
                q_results.append({
                    "question_id": qid,
                    "question_type": None,
                    "is_correct": False,
                    "points_earned": 0,
                    "points_possible": 0,
                    "error": "Question not found",
                })
                continue

            q_type = question.get("question_type", "")
            pts_possible: int = int(question.get("points", 0))
            pts_earned: int = 0

            if q_type == "multiple_choice":
                pts_earned = _grade_mcq(question, answer.get("selected_option_ids", []))
                submitted_answer = {"selected_option_ids": answer.get("selected_option_ids", [])}
            elif q_type == "fill_in_blank":
                pts_earned = _grade_fill_in_blank(question, answer.get("answers", []))
                submitted_answer = {"answers": answer.get("answers", [])}
            elif q_type == "coding":
                tcr = answer.get("test_case_results") or []
                pts_earned = _grade_coding(
                    question,
                    answer.get("code", ""),
                    answer.get("language", "python"),
                    test_case_results=tcr if tcr else None,
                )
                submitted_answer = {
                    "code": answer.get("code", ""),
                    "language": answer.get("language", "python"),
                    "test_case_results": tcr,
                }
            else:
                submitted_answer = {}

            is_correct = pts_earned >= pts_possible and pts_possible > 0
            sec_score += pts_earned
            q_results.append({
                "question_id": qid,
                "question_type": q_type,
                "is_correct": is_correct,
                "points_earned": pts_earned,
                "points_possible": pts_possible,
                "submitted_answer": submitted_answer,
            })

        section_results.append({
            "section_id": sid,
            "section_title": sec_info["title"],
            "score": sec_score,
            "total_points": sec_info["total_points"],
            "question_results": q_results,
        })
        total_score += sec_score

    # 6. Calculate score percentage
    total_points: int = int(assignment.get("total_points", 0))
    percentage: float = round(total_score / total_points * 100, 2) if total_points > 0 else 0.0

    # 7. Persist latest submission (overwrites any previous)
    new_attempts = current_attempts + 1
    time_taken: int = int(payload.get("time_taken_minutes", 0))

    user_name_val = str(payload.get("user_name") or "").strip()

    submission_item = _sanitize_for_dynamo({
        "PK": f"usub#{user_id}",
        "SK": f"ASSIGNMENT#{assignment_id}",
        "entity_type": "user_submission",
        "user_id": user_id,
        "user_name": user_name_val,
        "assignment_id": assignment_id,
        "score": total_score,
        "total_points": total_points,
        "percentage": percentage,
        "attempts_count": new_attempts,
        "time_taken_minutes": time_taken,
        "submitted_at": now_dt.isoformat(),
        "status": "submitted",
        "section_results": section_results,
    })

    try:
        assignments_table.put_item(Item=submission_item)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store submission: {str(e)}")

    return {
        "assignment_id": assignment_id,
        "user_id": user_id,
        "user_name": user_name_val or None,
        "score": total_score,
        "total_points": total_points,
        "percentage": percentage,
        "attempts_count": new_attempts,
        "time_taken_minutes": time_taken,
        "submitted_at": now_dt.isoformat(),
        "status": "submitted",
        "section_results": section_results,
    }


def get_user_submission(user_id: str, assignment_id: str) -> Dict[str, Any]:
    """Return the user's latest submission for an assignment."""
    item = _get_user_submission_internal(user_id, assignment_id)
    if not item:
        raise HTTPException(
            status_code=404,
            detail="No submission found for this user and assignment",
        )
    # Deserialise section_results if stored as string (legacy)
    section_results = item.get("section_results", [])
    if isinstance(section_results, str):
        try:
            section_results = json.loads(section_results)
        except Exception:
            section_results = []

    return {
        "assignment_id": assignment_id,
        "user_id": user_id,
        "user_name": str(item.get("user_name") or "") or None,
        "score": int(item.get("score", 0)),
        "total_points": int(item.get("total_points", 0)),
        "percentage": float(item.get("percentage", 0)),
        "attempts_count": int(item.get("attempts_count", 0)),
        "time_taken_minutes": int(item.get("time_taken_minutes", 0)),
        "submitted_at": str(item.get("submitted_at", "")),
        "status": str(item.get("status", "submitted")),
        "section_results": section_results,
    }


# ── All submissions for an assignment ────────────────────────────────────────

def get_all_submissions(assignment_id: str) -> Dict[str, Any]:
    """Return all user submissions for a given assignment."""
    # Verify assignment exists
    get_assignment(assignment_id)

    try:
        response = assignments_table.scan(
            FilterExpression=Attr("entity_type").eq("user_submission") &
                             Attr("assignment_id").eq(assignment_id)
        )
        items = response.get("Items", [])

        submissions = []
        for item in items:
            section_results = item.get("section_results", [])
            if isinstance(section_results, str):
                try:
                    section_results = json.loads(section_results)
                except Exception:
                    section_results = []

            submissions.append({
                "assignment_id": assignment_id,
                "user_id": str(item.get("user_id", "")),
                "user_name": str(item.get("user_name") or "") or None,
                "score": int(item.get("score", 0)),
                "total_points": int(item.get("total_points", 0)),
                "percentage": float(item.get("percentage", 0)),
                "attempts_count": int(item.get("attempts_count", 0)),
                "time_taken_minutes": int(item.get("time_taken_minutes", 0)),
                "submitted_at": str(item.get("submitted_at", "")),
                "status": str(item.get("status", "submitted")),
                "section_results": section_results,
            })

        # Sort by submitted_at descending (most recent first)
        submissions.sort(key=lambda x: x.get("submitted_at", ""), reverse=True)

        return {
            "assignment_id": assignment_id,
            "total_count": len(submissions),
            "submissions": submissions,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get submissions: {str(e)}")


# ── User assignments listing ──────────────────────────────────────────────────

def get_user_assignments(user_id: str) -> Dict[str, Any]:
    """
    Return all assignments that belong to courses the user is enrolled in,
    enriched with the user's own submission data (score, attempts, time).
    """
    if course_enrollments_table is None:
        raise HTTPException(
            status_code=500,
            detail="Course enrollments table is not configured",
        )

    # 1. Fetch enrolled course IDs
    try:
        resp = course_enrollments_table.query(
            KeyConditionExpression=Key("PK").eq(f"USER#{user_id}")
            & Key("SK").begins_with("ENROLLMENT#COURSE#"),
        )
        enrollments = resp.get("Items", [])
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch enrollments: {str(e)}"
        )

    enrolled_course_ids: List[str] = [
        str(e["course_id"]) for e in enrollments if e.get("course_id")
    ]

    if not enrolled_course_ids:
        return {"user_id": user_id, "total_count": 0, "assignments": []}

    # 2. Build course_id → course_name map
    course_name_map: Dict[str, str] = {}
    if courses_tbl:
        for cid in enrolled_course_ids:
            try:
                item = courses_tbl.get_item(
                    Key={"PK": "COURSE_LIST", "SK": f"COURSE#{cid}"}
                ).get("Item")
                if item:
                    course_name_map[cid] = str(item.get("title", ""))
            except Exception:
                pass

    # 3. Scan assignments table for assignments belonging to enrolled courses
    try:
        base_filter = Attr("entity_type").eq("assignment")
        if len(enrolled_course_ids) == 1:
            course_filter = Attr("course_id").eq(enrolled_course_ids[0])
        else:
            course_filter = Attr("course_id").is_in(enrolled_course_ids)

        scan_resp = assignments_table.scan(FilterExpression=base_filter & course_filter)
        raw_assignments: List[Dict[str, Any]] = scan_resp.get("Items", [])
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch assignments: {str(e)}"
        )

    # 4. Attach user-specific submission data to each assignment
    now = _now_dt()
    result: List[Dict[str, Any]] = []
    for a in raw_assignments:
        aid = str(a.get("assignment_id") or a.get("PK", ""))
        cid = str(a.get("course_id", "") or "")
        submission = _get_user_submission_internal(user_id, aid)

        is_locked = bool(a.get("is_locked", False))
        deadline_raw = a.get("deadline")
        deadline_dt = _parse_dt_aware(deadline_raw)
        deadline_passed = deadline_dt is not None and deadline_dt < now

        start_date_raw = a.get("start_date")
        start_dt = _parse_dt_aware(start_date_raw)
        not_started_yet = start_dt is not None and start_dt > now

        has_submitted = submission is not None

        # Categorise:
        # - completed: user already submitted (regardless of deadline)
        # - past: deadline passed and user never submitted
        # - upcoming: start_date is in the future OR is_locked
        # - to_do: deadline not passed, not locked, not submitted yet
        if has_submitted:
            status = "completed"
        elif deadline_passed:
            status = "past"
        elif not_started_yet or is_locked:
            status = "upcoming"
        else:
            status = "to_do"

        item: Dict[str, Any] = {
            "assignment_id": aid,
            "title": str(a.get("title", "")),
            "course_id": cid,
            "course_name": course_name_map.get(cid, str(a.get("course_name", "") or "")),
            "total_points": int(a.get("total_points", 0)),
            "total_time_minutes": int(a.get("total_time_minutes", 0)),
            "section_count": int(a.get("section_count", 0)),
            "level": str(a.get("level", "intermediate")),
            "start_date": str(a.get("start_date", "") or "") or None,
            "deadline": str(deadline_raw or "") or None,
            "is_locked": is_locked,
            "status": status,
            "has_submitted": has_submitted,
            "user_score": None,
            "user_percentage": None,
            "attempts_count": 0,
            "time_taken_minutes": None,
            "last_submitted_at": None,
        }

        if submission:
            item["user_score"] = int(submission.get("score", 0))
            item["user_percentage"] = float(submission.get("percentage", 0))
            item["attempts_count"] = int(submission.get("attempts_count", 0))
            item["time_taken_minutes"] = int(submission.get("time_taken_minutes", 0))
            item["last_submitted_at"] = str(submission.get("submitted_at", ""))

        result.append(item)

    return {"user_id": user_id, "total_count": len(result), "assignments": result}


def get_user_assignments_by_category(user_id: str, category: str) -> Dict[str, Any]:
    """
    Return only assignments matching the given category for a user.
    category: 'to_do' | 'upcoming' | 'past' | 'completed'
    """
    valid = {"to_do", "upcoming", "past", "completed"}
    if category not in valid:
        raise HTTPException(status_code=400, detail=f"category must be one of: {', '.join(sorted(valid))}")

    flat = get_user_assignments(user_id)
    assignments = [a for a in flat.get("assignments", []) if a["status"] == category]

    def _sort_key(a):
        return a.get("deadline") or "9999"

    if category in ("to_do", "upcoming"):
        assignments.sort(key=_sort_key)
    elif category == "past":
        assignments.sort(key=_sort_key, reverse=True)
    else:  # completed
        assignments.sort(key=lambda a: a.get("last_submitted_at") or "", reverse=True)

    return {"user_id": user_id, "category": category, "total_count": len(assignments), "assignments": assignments}


def get_user_assignments_dashboard(user_id: str) -> Dict[str, Any]:
    """
    Return assignments grouped into to_do / upcoming / past / completed
    for the student dashboard view.
    """
    flat = get_user_assignments(user_id)
    assignments = flat.get("assignments", [])

    to_do = [a for a in assignments if a["status"] == "to_do"]
    upcoming = [a for a in assignments if a["status"] == "upcoming"]
    past = [a for a in assignments if a["status"] == "past"]
    completed = [a for a in assignments if a["status"] == "completed"]

    # Sort to_do by deadline ascending (nearest first); upcoming by deadline asc
    def _sort_key(a):
        return a.get("deadline") or "9999"

    to_do.sort(key=_sort_key)
    upcoming.sort(key=_sort_key)
    past.sort(key=_sort_key, reverse=True)       # most recently expired first
    completed.sort(key=lambda a: a.get("last_submitted_at") or "", reverse=True)

    return {
        "user_id": user_id,
        "to_do": to_do,
        "upcoming": upcoming,
        "past": past,
        "completed": completed,
        "total_count": len(assignments),
    }


# ── Per-question CRUD ─────────────────────────────────────────────────────────

def _store_question_for_section(
    section_id: str, assignment_id: str, q_dict: Dict[str, Any]
) -> str:
    """Persist a single question dict as PK=section_id / SK=QUESTION#{question_id}.
    Returns the question_id used."""
    q_id = (
        q_dict.get("id")
        or q_dict.get("question_id")
        or f"q_{uuid.uuid4().hex[:10]}"
    )
    now_str = _now_dt().isoformat()
    q_item: Dict[str, Any] = {
        "PK": section_id,
        "SK": f"QUESTION#{q_id}",
        "entity_type": "question",
        "question_id": q_id,
        "section_id": section_id,
        "assignment_id": assignment_id,
        "question_type": q_dict.get("question_type"),
        "title": q_dict.get("title", ""),
        "description": q_dict.get("description", ""),
        "points": int(q_dict.get("points", 0)),
        "order": int(q_dict.get("order") or 1),
        "created_at": q_dict.get("created_at", now_str),
        "updated_at": now_str,
    }
    q_type = q_dict.get("question_type")
    if q_type == "coding":
        q_item.update({
            "default_code": q_dict.get("default_code"),
            "sample_input": q_dict.get("sample_input"),
            "sample_output": q_dict.get("sample_output"),
            "test_cases": q_dict.get("test_cases") or [],
            "time_limit_minutes": q_dict.get("time_limit_minutes"),
            "hints": q_dict.get("hints"),
        })
    elif q_type == "multiple_choice":
        q_item.update({
            "options": q_dict.get("options") or [],
            "correct_option_ids": q_dict.get("correct_option_ids") or [],
            "explanation": q_dict.get("explanation"),
            "shuffle_options": bool(q_dict.get("shuffle_options", False)),
        })
    elif q_type == "fill_in_blank":
        q_item.update({
            "text_with_blanks": q_dict.get("text_with_blanks"),
            "correct_answers": q_dict.get("correct_answers") or [],
            "case_sensitive": bool(q_dict.get("case_sensitive", False)),
            "explanation": q_dict.get("explanation"),
        })
    assignments_table.put_item(Item=_sanitize_for_dynamo(q_item))
    return q_id


def add_question_to_section(
    section_id: str, assignment_id: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    """Add a new question, stored as a dedicated DynamoDB item."""
    section = get_section(section_id)
    if section.get("assignment_id") != assignment_id:
        raise HTTPException(status_code=404, detail="Section not found in this assignment")
    if not payload.get("question_type"):
        raise HTTPException(status_code=400, detail="question_type is required")
    if not payload.get("title"):
        raise HTTPException(status_code=400, detail="title is required")

    # Auto-assign order (append to end)
    if payload.get("order") is None:
        try:
            resp = assignments_table.query(
                KeyConditionExpression=Key("PK").eq(section_id) & Key("SK").begins_with("QUESTION#")
            )
            max_order = max((int(q.get("order", 0)) for q in resp.get("Items", [])), default=0)
            payload = dict(payload)
            payload["order"] = max_order + 1
        except Exception:
            payload = dict(payload)
            payload["order"] = 1

    now = _now_dt()
    q_id = _store_question_for_section(section_id, assignment_id, payload)
    _sync_section_total_points(section_id, assignment_id)
    return {
        "question_id": q_id,
        "section_id": section_id,
        "assignment_id": assignment_id,
        "status": "created",
        "created_at": now.isoformat(),
    }


def get_question_item(section_id: str, question_id: str) -> Dict[str, Any]:
    """Fetch a single question by section_id + question_id."""
    try:
        resp = assignments_table.get_item(Key={"PK": section_id, "SK": f"QUESTION#{question_id}"})
        if "Item" not in resp:
            raise HTTPException(status_code=404, detail="Question not found")
        return _clean_question_item(dict(resp["Item"]))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get question: {str(e)}")


def list_section_questions_from_db(
    section_id: str, assignment_id: str
) -> Dict[str, Any]:
    """Return all questions for a section, loading from separate question items."""
    section = get_section(section_id)
    if section.get("assignment_id") != assignment_id:
        raise HTTPException(status_code=404, detail="Section not found in this assignment")

    questions = _load_section_questions(section_id)
    # Fallback: inline questions for data created before this migration
    if not questions:
        inline = section.get("questions") or []
        questions = [dict(q) if not isinstance(q, dict) else q for q in inline]

    return {
        "section_id": section_id,
        "assignment_id": assignment_id,
        "questions": questions,
        "total_questions": len(questions),
        "total_points": sum(int(q.get("points", 0)) for q in questions),
    }


def update_question_item(
    section_id: str, question_id: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    """Partially update a question — only provided fields are modified."""
    question = get_question_item(section_id, question_id)
    assignment_id = str(question.get("assignment_id", ""))
    now = _now_dt()

    update_expr = "SET updated_at = :ua"
    expr_vals: Dict[str, Any] = {":ua": now.isoformat()}
    expr_names: Dict[str, str] = {}

    simple_str_fields = [
        "title", "description", "default_code", "sample_input", "sample_output",
        "hints", "explanation", "text_with_blanks",
    ]
    simple_bool_fields = ["shuffle_options", "case_sensitive"]
    list_fields = ["test_cases", "options", "correct_option_ids", "correct_answers"]

    for f in simple_str_fields:
        if f in payload:
            update_expr += f", {f} = :{f}"
            expr_vals[f":{f}"] = payload[f]
    for f in simple_bool_fields:
        if f in payload:
            update_expr += f", {f} = :{f}"
            expr_vals[f":{f}"] = bool(payload[f])
    for f in list_fields:
        if f in payload:
            update_expr += f", {f} = :{f}"
            expr_vals[f":{f}"] = payload[f]
    if "points" in payload:
        update_expr += ", points = :points"
        expr_vals[":points"] = int(payload["points"])
    if "time_limit_minutes" in payload:
        update_expr += ", time_limit_minutes = :tlm"
        expr_vals[":tlm"] = int(payload["time_limit_minutes"])
    if "order" in payload:
        update_expr += ", #ord = :order_val"
        expr_names["#ord"] = "order"
        expr_vals[":order_val"] = int(payload["order"])

    update_kwargs: Dict[str, Any] = {
        "Key": {"PK": section_id, "SK": f"QUESTION#{question_id}"},
        "UpdateExpression": update_expr,
        "ExpressionAttributeValues": _sanitize_for_dynamo(expr_vals),
    }
    if expr_names:
        update_kwargs["ExpressionAttributeNames"] = expr_names

    try:
        assignments_table.update_item(**update_kwargs)
        if assignment_id:
            _sync_section_total_points(section_id, assignment_id)
        return {"status": "updated", "question_id": question_id, "section_id": section_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update question: {str(e)}")


def delete_question_item(section_id: str, question_id: str) -> Dict[str, Any]:
    """Delete a question and resync the section's total points."""
    question = get_question_item(section_id, question_id)
    assignment_id = str(question.get("assignment_id", ""))
    try:
        assignments_table.delete_item(Key={"PK": section_id, "SK": f"QUESTION#{question_id}"})
        if assignment_id:
            _sync_section_total_points(section_id, assignment_id)
        return {"status": "deleted", "question_id": question_id, "section_id": section_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete question: {str(e)}")