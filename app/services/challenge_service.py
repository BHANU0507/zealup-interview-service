import base64
import csv
import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional

import httpx
from fastapi import HTTPException
from boto3.dynamodb.conditions import Attr, Key

from app.dynamo import table2


JUDGE0_BASE_URL = os.getenv("JUDGE0_BASE_URL")
JUDGE0_API_KEY = os.getenv("JUDGE0_API_KEY")


def _now_ts() -> int:
    return int(time.time())


def _normalize_output(value: Optional[str]) -> str:
    if value is None:
        return ""
    return value.strip()


def _post_judge0(payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{JUDGE0_BASE_URL}/submissions?base64_encoded=false&wait=true"
    headers = {"Content-Type": "application/json"}
    
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


def _encode_key(key: Optional[Dict[str, Any]]) -> Optional[str]:
    if not key:
        return None
    raw = json.dumps(key).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8")


def _decode_key(token: Optional[str]) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    try:
        raw = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        return json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Invalid start_key")


def get_languages() -> List[Dict[str, Any]]:
    url = f"{JUDGE0_BASE_URL}/languages"
    try:
        response = httpx.get(url, timeout=10)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Judge0 request failed: {exc}")

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Judge0 error: {response.status_code} {response.text}"
        )

    languages = response.json()

    allowed = ["java", "python", "javascript", "c"]
    filtered = []

    for lang in languages:
        name = (lang.get("name") or "").strip().lower()
        # Check if any allowed keyword appears in the language name
        for keyword in allowed:
            if keyword in name:
                filtered.append(lang)
                break  # Only add once even if multiple keywords match

    return filtered


def create_challenge(payload: Dict[str, Any]) -> Dict[str, Any]:
    challenge_id = f"chal_{uuid.uuid4()}"
    now = _now_ts()

    challenge_type = payload.get("challenge_type")
    if challenge_type not in {"coding", "aptitude"}:
        raise HTTPException(status_code=400, detail="Invalid challenge_type")

    title = (payload.get("title") or "").strip()
    description = (payload.get("description") or "").strip()
    if not title or not description:
        raise HTTPException(status_code=400, detail="title and description are required")

    if challenge_type == "aptitude":
        sections = payload.get("sections") or []
        if sections:
            total_points = 0
            for section in sections:
                section_name = (section.get("name") or "").strip()
                questions = section.get("questions") or []
                if not section_name or not questions:
                    raise HTTPException(
                        status_code=400,
                        detail="Each section must have a name and at least one question"
                    )
                for question in questions:
                    text = (question.get("text") or "").strip()
                    options = question.get("options") or []
                    correct_answers = question.get("correct_answers") or []
                    points = question.get("points")
                    if not text or not options or not correct_answers:
                        raise HTTPException(
                            status_code=400,
                            detail="Each question must have text, options, and correct_answers"
                        )
                    if points is None:
                        raise HTTPException(
                            status_code=400,
                            detail="Each question must have points"
                        )
                    total_points += int(points)

            if total_points > 0:
                payload["points"] = total_points
        else:
            question = (payload.get("question") or "").strip()
            options = payload.get("options") or []
            correct_answer = (payload.get("correct_answer") or "").strip()
            if not question or not options or not correct_answer:
                raise HTTPException(
                    status_code=400,
                    detail="question, options, and correct_answer are required for aptitude"
                )

    if challenge_type == "coding":
        test_cases = payload.get("test_cases") or []
        if not test_cases:
            raise HTTPException(
                status_code=400,
                detail="test_cases are required for coding"
            )
        # Auto-calculate total points from test cases
        total_points = sum(case.get("points", 0) for case in test_cases)
        if total_points > 0:
            payload["points"] = total_points

    metadata_item = {
        "PK": f"CHALLENGE#{challenge_id}",
        "SK": "METADATA",
        "challenge_id": challenge_id,
        "title": title,
        "description": description,
        "challenge_type": challenge_type,
        "difficulty": payload.get("difficulty"),
        "points": int(payload.get("points") or 0),
        "tags": payload.get("tags") or [],
        "created_by": payload.get("created_by"),
        "created_at": now,
        "updated_at": now,
        "status": "ACTIVE",
        "time_limit_minutes": payload.get("time_limit_minutes"),
        "question": payload.get("question"),
        "options": payload.get("options"),
        "correct_answer": payload.get("correct_answer"),
        "answer_explanation": payload.get("answer_explanation"),
        "sections": payload.get("sections"),
        "default_code": payload.get("default_code"),
        "sample_input": payload.get("sample_input"),
        "sample_input_explanation": payload.get("sample_input_explanation"),
        "sample_output": payload.get("sample_output"),
        "sample_output_explanation": payload.get("sample_output_explanation"),
        "hints": payload.get("hints"),
        "test_cases": payload.get("test_cases"),
    }
    # Only store college_id when present — omitting it ensures not_exists() filter works
    if payload.get("college_id"):
        metadata_item["college_id"] = payload["college_id"]

    tags = payload.get("tags") or []
    list_item = {
        "PK": "CHALLENGE_LIST",
        "SK": f"CHALLENGE#{challenge_id}",
        "challenge_id": challenge_id,
        "title": title,
        "challenge_type": challenge_type,
        "difficulty": payload.get("difficulty"),
        "points": int(payload.get("points") or 0),
        "tags": tags,
        "created_by": payload.get("created_by"),
        "created_at": now,
        "status": "ACTIVE",
    }
    if payload.get("college_id"):
        list_item["college_id"] = payload["college_id"]

    table2.put_item(Item=metadata_item)
    table2.put_item(Item=list_item)

    return {
        "challenge_id": challenge_id,
        "status": "CREATED",
        "created_at": now,
    }


def update_challenge(challenge_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    response = table2.get_item(
        Key={
            "PK": f"CHALLENGE#{challenge_id}",
            "SK": "METADATA",
        }
    )

    item = response.get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Challenge not found")

    now = _now_ts()
    update_expr_parts = ["updated_at = :updated"]
    expr_values = {":updated": now}
    expr_names = {}

    if "title" in payload and payload["title"]:
        update_expr_parts.append("title = :title")
        expr_values[":title"] = payload["title"].strip()

    if "description" in payload and payload["description"]:
        update_expr_parts.append("description = :description")
        expr_values[":description"] = payload["description"].strip()

    if "difficulty" in payload and payload["difficulty"]:
        update_expr_parts.append("difficulty = :difficulty")
        expr_values[":difficulty"] = payload["difficulty"]

    if "points" in payload and payload["points"] is not None:
        update_expr_parts.append("points = :points")
        expr_values[":points"] = int(payload["points"])

    if "tags" in payload:
        update_expr_parts.append("tags = :tags")
        expr_values[":tags"] = payload["tags"] or []

    if "question" in payload:
        update_expr_parts.append("question = :question")
        expr_values[":question"] = payload["question"]

    if "options" in payload:
        update_expr_parts.append("#opts = :options")
        expr_values[":options"] = payload["options"]
        expr_names["#opts"] = "options"

    if "correct_answer" in payload:
        update_expr_parts.append("correct_answer = :correct_answer")
        expr_values[":correct_answer"] = payload["correct_answer"]

    if "answer_explanation" in payload:
        update_expr_parts.append("answer_explanation = :answer_explanation")
        expr_values[":answer_explanation"] = payload["answer_explanation"]

    if "default_code" in payload:
        update_expr_parts.append("default_code = :default_code")
        expr_values[":default_code"] = payload["default_code"]

    if "sample_input" in payload:
        update_expr_parts.append("sample_input = :sample_input")
        expr_values[":sample_input"] = payload["sample_input"]

    if "sample_input_explanation" in payload:
        update_expr_parts.append("sample_input_explanation = :sample_input_explanation")
        expr_values[":sample_input_explanation"] = payload["sample_input_explanation"]

    if "sample_output" in payload:
        update_expr_parts.append("sample_output = :sample_output")
        expr_values[":sample_output"] = payload["sample_output"]

    if "sample_output_explanation" in payload:
        update_expr_parts.append("sample_output_explanation = :sample_output_explanation")
        expr_values[":sample_output_explanation"] = payload["sample_output_explanation"]

    if "hints" in payload:
        update_expr_parts.append("hints = :hints")
        expr_values[":hints"] = payload["hints"]

    if "test_cases" in payload:
        update_expr_parts.append("test_cases = :test_cases")
        expr_values[":test_cases"] = payload["test_cases"]

    update_args: Dict[str, Any] = {
        "Key": {
            "PK": f"CHALLENGE#{challenge_id}",
            "SK": "METADATA",
        },
        "UpdateExpression": "SET " + ", ".join(update_expr_parts),
        "ExpressionAttributeValues": expr_values,
    }
    if expr_names:
        update_args["ExpressionAttributeNames"] = expr_names

    table2.update_item(**update_args)

    if "title" in payload or "difficulty" in payload or "points" in payload or "tags" in payload:
        list_update_parts = []
        list_values = {}
        list_names = {}

        if "title" in payload and payload["title"]:
            list_update_parts.append("title = :title")
            list_values[":title"] = payload["title"].strip()

        if "difficulty" in payload and payload["difficulty"]:
            list_update_parts.append("difficulty = :difficulty")
            list_values[":difficulty"] = payload["difficulty"]

        if "points" in payload and payload["points"] is not None:
            list_update_parts.append("points = :points")
            list_values[":points"] = int(payload["points"])

        if "tags" in payload:
            list_update_parts.append("tags = :tags")
            list_values[":tags"] = payload["tags"] or []

        if list_update_parts:
            list_update_args: Dict[str, Any] = {
                "Key": {
                    "PK": "CHALLENGE_LIST",
                    "SK": f"CHALLENGE#{challenge_id}",
                },
                "UpdateExpression": "SET " + ", ".join(list_update_parts),
                "ExpressionAttributeValues": list_values,
            }
            if list_names:
                list_update_args["ExpressionAttributeNames"] = list_names

            table2.update_item(**list_update_args)

    return {
        "challenge_id": challenge_id,
        "status": "UPDATED",
        "updated_at": now,
    }


def delete_challenge(challenge_id: str) -> Dict[str, Any]:
    response = table2.get_item(
        Key={
            "PK": f"CHALLENGE#{challenge_id}",
            "SK": "METADATA",
        }
    )

    item = response.get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Challenge not found")

    table2.delete_item(
        Key={
            "PK": f"CHALLENGE#{challenge_id}",
            "SK": "METADATA",
        }
    )

    table2.delete_item(
        Key={
            "PK": "CHALLENGE_LIST",
            "SK": f"CHALLENGE#{challenge_id}",
        }
    )

    return {
        "challenge_id": challenge_id,
        "status": "DELETED",
    }


def bulk_delete_challenges(challenge_ids: List[str]) -> Dict[str, Any]:
    deleted_ids = []
    failed_ids = []
    errors = []

    for challenge_id in challenge_ids:
        try:
            # Check if challenge exists
            response = table2.get_item(
                Key={
                    "PK": f"CHALLENGE#{challenge_id}",
                    "SK": "METADATA",
                }
            )

            if not response.get("Item"):
                failed_ids.append(challenge_id)
                errors.append({
                    "challenge_id": challenge_id,
                    "error": "Challenge not found"
                })
                continue

            # Delete metadata
            table2.delete_item(
                Key={
                    "PK": f"CHALLENGE#{challenge_id}",
                    "SK": "METADATA",
                }
            )

            # Delete from list
            table2.delete_item(
                Key={
                    "PK": "CHALLENGE_LIST",
                    "SK": f"CHALLENGE#{challenge_id}",
                }
            )

            deleted_ids.append(challenge_id)

        except Exception as e:
            failed_ids.append(challenge_id)
            errors.append({
                "challenge_id": challenge_id,
                "error": str(e)
            })

    return {
        "deleted_count": len(deleted_ids),
        "failed_count": len(failed_ids),
        "deleted_ids": deleted_ids,
        "failed_ids": failed_ids,
        "errors": errors if errors else None,
    }


def _build_challenge_filters(
    challenge_type: Optional[str],
    difficulty: Optional[str],
    tag: Optional[str],
    created_by: Optional[str],
    college_id: Optional[str] = None,
) -> Optional[Any]:
    filters = []

    if challenge_type:
        filters.append(Attr("challenge_type").eq(challenge_type))
    if difficulty:
        filters.append(Attr("difficulty").eq(difficulty))
    if created_by:
        filters.append(Attr("created_by").eq(created_by))
    if tag:
        filters.append(Attr("tags").contains(tag))

    # Show college challenges for this college + public challenges (no college_id)
    if college_id:
        filters.append(Attr("college_id").eq(college_id))
    else:
        # No college context: show only public challenges (no college_id stored)
        # Handle both truly-missing attribute and legacy NULL-stored values
        filters.append(
            Attr("college_id").not_exists() | Attr("college_id").eq(None)
        )

    if not filters:
        return None

    expression = filters[0]
    for expr in filters[1:]:
        expression = expression & expr
    return expression


def _matches_keyword(item: Dict[str, Any], keyword: str) -> bool:
    title = (item.get("title") or "").lower()
    tags = item.get("tags") or []
    tags_text = " ".join([str(tag).lower() for tag in tags])
    return keyword in title or keyword in tags_text


def _get_user_solved_challenges(user_id: str) -> Dict[str, Dict[str, Any]]:
    solved = {}  # challenge_id -> {score, time_taken_seconds} mapping
    last_key: Optional[Dict[str, Any]] = None

    while True:
        query_args: Dict[str, Any] = {
            "KeyConditionExpression": Key("PK").eq(f"USER#{user_id}"),
            "ScanIndexForward": False,
        }
        if last_key:
            query_args["ExclusiveStartKey"] = last_key

        response = table2.query(**query_args)
        items = response.get("Items", [])

        for item in items:
            challenge_id = item.get("challenge_id")
            if challenge_id:
                score = item.get("score", 0)
                time_taken = item.get("time_taken_seconds")
                solved[challenge_id] = {
                    "score": score,
                    "time_taken_seconds": time_taken
                }

        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break

    return solved


def list_challenges(
    challenge_type: Optional[str] = None,
    difficulty: Optional[str] = None,
    tag: Optional[str] = None,
    keyword: Optional[str] = None,
    created_by: Optional[str] = None,
    user_id: Optional[str] = None,
    college_id: Optional[str] = None,
    page_size: int = 10,
    start_key: Optional[str] = None,
) -> Dict[str, Any]:
    if page_size <= 0:
        raise HTTPException(status_code=400, detail="page_size must be > 0")

    filter_expression = _build_challenge_filters(
        challenge_type=challenge_type,
        difficulty=difficulty,
        tag=tag,
        created_by=created_by,
        college_id=college_id,
    )

    decoded_key = _decode_key(start_key)
    items: List[Dict[str, Any]] = []
    last_key = decoded_key
    keyword_value = (keyword or "").strip().lower()
    solved_dict = _get_user_solved_challenges(user_id) if user_id else {}

    while len(items) < page_size:
        query_args: Dict[str, Any] = {
            "KeyConditionExpression": Key("PK").eq("CHALLENGE_LIST"),
            "Limit": max(1, page_size - len(items)),
            "ScanIndexForward": False,
        }
        if last_key:
            query_args["ExclusiveStartKey"] = last_key
        if filter_expression is not None:
            query_args["FilterExpression"] = filter_expression

        response = table2.query(**query_args)
        batch = response.get("Items", [])

        if keyword_value:
            batch = [item for item in batch if _matches_keyword(item, keyword_value)]

        items.extend(batch)

        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break

    challenges_list = []
    for item in items:
        challenge_id = item.get("challenge_id")
        user_data = solved_dict.get(challenge_id) if user_id and challenge_id in solved_dict else None
        challenge_data = {
            "challenge_id": challenge_id,
            "title": item.get("title"),
            "challenge_type": item.get("challenge_type"),
            "difficulty": item.get("difficulty"),
            "points": item.get("points", 0),
            "tags": item.get("tags", []),
            "created_by": item.get("created_by"),
            "college_id": item.get("college_id"),
            "created_at": item.get("created_at", 0),
            "solved": challenge_id in solved_dict if user_id else None,
            "user_score": user_data.get("score") if user_data else None,
            "time_taken_seconds": user_data.get("time_taken_seconds") if user_data else None,
        }
        challenges_list.append(challenge_data)

    return {
        "challenges": challenges_list,
        "next_key": _encode_key(last_key),
        "total_solved": len(solved_dict) if user_id else None,
    }


def get_challenge(challenge_id: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    response = table2.get_item(
        Key={
            "PK": f"CHALLENGE#{challenge_id}",
            "SK": "METADATA",
        }
    )

    item = response.get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Challenge not found")

    test_cases = item.get("test_cases") or []
    visible_cases = [case for case in test_cases if not case.get("is_hidden")]
    hidden_cases = [case for case in test_cases if case.get("is_hidden")]
    solved = None
    if user_id:
        solved_check = table2.get_item(
            Key={
                "PK": f"USER#{user_id}",
                "SK": f"SUBMISSION#{challenge_id}",
            }
        )
        solved = bool(solved_check.get("Item"))

    return {
        "challenge_id": challenge_id,
        "title": item.get("title"),
        "description": item.get("description"),
        "challenge_type": item.get("challenge_type"),
        "difficulty": item.get("difficulty"),
        "points": item.get("points", 0),
        "tags": item.get("tags", []),
        "created_by": item.get("created_by"),
        "created_at": item.get("created_at", 0),
        "solved": solved,
        "time_limit_minutes": item.get("time_limit_minutes"),
        "question": item.get("question"),
        "options": item.get("options"),
        "answer_explanation": item.get("answer_explanation"),
        "sections": item.get("sections"),
        "default_code": item.get("default_code"),
        "sample_input": item.get("sample_input"),
        "sample_input_explanation": item.get("sample_input_explanation"),
        "sample_output": item.get("sample_output"),
        "sample_output_explanation": item.get("sample_output_explanation"),
        "hints": item.get("hints"),
        "test_cases_count": len(test_cases),
        "visible_test_cases": visible_cases,
        "hidden_test_cases": hidden_cases,
    }


def run_code(language_id: int, source_code: str, stdin: Optional[str]) -> Dict[str, Any]:
    payload = {
        "language_id": language_id,
        "source_code": source_code,
        "stdin": stdin or "",
    }

    result = _post_judge0(payload)

    return {
        "status": result.get("status", {}).get("description", "UNKNOWN"),
        "stdout": result.get("stdout"),
        "stderr": result.get("stderr"),
        "compile_output": result.get("compile_output"),
        "time": result.get("time"),
        "memory": result.get("memory"),
    }


def run_visible_tests(challenge_id: str, language_id: int, source_code: str) -> Dict[str, Any]:
    response = table2.get_item(
        Key={
            "PK": f"CHALLENGE#{challenge_id}",
            "SK": "METADATA",
        }
    )

    item = response.get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Challenge not found")

    test_cases = item.get("test_cases") or []
    
    compile_output = None

    results: List[Dict[str, Any]] = []
    passed_count = 0
    earned_score = 0

    for index, case in enumerate(test_cases, start=1):
        is_hidden = bool(case.get("is_hidden"))
        test_case_points = int(case.get("points", 0))
        
        payload = {
            "language_id": int(language_id),
            "source_code": source_code,
            "stdin": case.get("input", ""),
            "expected_output": case.get("expected_output", ""),
        }

        judge_result = _post_judge0(payload)
        stdout = _normalize_output(judge_result.get("stdout"))
        expected = _normalize_output(case.get("expected_output"))
        status_desc = judge_result.get("status", {}).get("description", "UNKNOWN")
        is_passed = stdout == expected and status_desc == "Accepted"
        
        if not compile_output and judge_result.get("compile_output"):
            compile_output = judge_result.get("compile_output")

        if is_passed:
            passed_count += 1
            earned_score += test_case_points

        result_item = {
            "index": index,
            "status": status_desc,
            "passed": is_passed,
            "points": test_case_points,
            "earned_points": test_case_points if is_passed else 0,
            "stdout": judge_result.get("stdout"),
            "stderr": judge_result.get("stderr"),
            "compile_output": judge_result.get("compile_output"),
            "time": judge_result.get("time"),
            "memory": judge_result.get("memory"),
            "is_hidden": is_hidden,
        }
        
        if not is_hidden:
            result_item["input"] = case.get("input")
            result_item["expected_output"] = case.get("expected_output")
        
        results.append(result_item)

    total_points = sum(case.get("points", 0) for case in test_cases)

    return {
        "status": "COMPLETED",
        "passed_count": passed_count,
        "total_count": len(test_cases),
        "score": earned_score,
        "total_points": total_points,
        "compile_output": compile_output,
        "results": results,
    }


def _update_college_rank(user_id: str, college_id: str, challenge_id: str, new_score: int) -> None:
    """Update a college student's cumulative score in the college rank table."""
    from decimal import Decimal

    # Get the previous score for this challenge from the user's submission record
    prev_item = table2.get_item(
        Key={
            "PK": f"USER#{user_id}",
            "SK": f"SUBMISSION#{challenge_id}",
        }
    ).get("Item")

    old_score = int(prev_item.get("score", 0)) if prev_item else 0
    delta = new_score - old_score

    # Atomically update (or create) the college rank entry
    table2.update_item(
        Key={
            "PK": f"COLLEGE_RANK#{college_id}",
            "SK": f"USER#{user_id}",
        },
        UpdateExpression="SET user_id = :uid, college_id = :cid, #ts = if_not_exists(#ts, :zero) + :delta",
        ExpressionAttributeNames={"#ts": "total_score"},
        ExpressionAttributeValues={
            ":uid": user_id,
            ":cid": college_id,
            ":zero": Decimal("0"),
            ":delta": Decimal(str(delta)),
        },
    )


def _update_global_rank(user_id: str, challenge_id: str, new_score: int) -> None:
    """Update an individual (non-college) user's cumulative score in the global rank table."""
    from decimal import Decimal

    prev_item = table2.get_item(
        Key={
            "PK": f"USER#{user_id}",
            "SK": f"SUBMISSION#{challenge_id}",
        }
    ).get("Item")

    old_score = int(prev_item.get("score", 0)) if prev_item else 0
    delta = new_score - old_score

    table2.update_item(
        Key={
            "PK": "GLOBAL_RANK",
            "SK": f"USER#{user_id}",
        },
        UpdateExpression="SET user_id = :uid, #ts = if_not_exists(#ts, :zero) + :delta",
        ExpressionAttributeNames={"#ts": "total_score"},
        ExpressionAttributeValues={
            ":uid": user_id,
            ":zero": Decimal("0"),
            ":delta": Decimal(str(delta)),
        },
    )


def submit_challenge(challenge_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    response = table2.get_item(
        Key={
            "PK": f"CHALLENGE#{challenge_id}",
            "SK": "METADATA",
        }
    )

    item = response.get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Challenge not found")

    challenge_type = item.get("challenge_type")
    user_id = payload.get("user_id")
    college_id = payload.get("college_id") or None
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    submission_id = f"{challenge_id}#{user_id}"
    now = _now_ts()
    
    # Check if submission already exists
    existing_submission = table2.get_item(
        Key={
            "PK": f"SUBMISSION#{submission_id}",
            "SK": "DETAIL",
        }
    )
    is_update = bool(existing_submission.get("Item"))

    if challenge_type == "aptitude":
        sections = item.get("sections") or []
        if sections:
            section_answers = payload.get("section_answers") or []
            if not section_answers:
                raise HTTPException(
                    status_code=400,
                    detail="section_answers are required for aptitude sections"
                )

            answers_by_section = {
                int(section.get("section_index")): section.get("question_answers") or []
                for section in section_answers
                if section.get("section_index") is not None
            }

            results = []
            total_questions = 0
            correct_count = 0
            score = 0

            for section_index, section in enumerate(sections):
                questions = section.get("questions") or []
                total_questions += len(questions)
                question_answers = answers_by_section.get(section_index, [])
                answers_by_question = {
                    int(answer.get("question_index")): answer.get("selected_answers") or []
                    for answer in question_answers
                    if answer.get("question_index") is not None
                }

                for question_index, question in enumerate(questions):
                    correct_answers = question.get("correct_answers") or []
                    selected_answers = answers_by_question.get(question_index, [])

                    normalized_correct = {str(value).strip() for value in correct_answers}
                    normalized_selected = {str(value).strip() for value in selected_answers}

                    is_correct = normalized_selected == normalized_correct
                    points = int(question.get("points", 0))
                    earned_points = points if is_correct else 0

                    if is_correct:
                        correct_count += 1
                        score += points

                    results.append({
                        "section_index": section_index,
                        "question_index": question_index,
                        "is_correct": is_correct,
                        "points": points,
                        "earned_points": earned_points,
                        "selected_answers": selected_answers,
                    })

            submission_item = {
                "PK": f"CHALLENGE#{challenge_id}",
                "SK": f"SUBMISSION#{user_id}",
                "submission_id": submission_id,
                "challenge_id": challenge_id,
                "challenge_type": challenge_type,
                "user_id": user_id,
                "college_id": college_id,
                "section_answers": section_answers,
                "time_taken_seconds": payload.get("time_taken_seconds"),
                "score": int(score),
                "passed_count": correct_count,
                "total_count": total_questions,
                "results": results,
                "created_at": now,
            }

            if college_id:
                _update_college_rank(user_id, college_id, challenge_id, int(score))
            else:
                _update_global_rank(user_id, challenge_id, int(score))

            table2.put_item(Item=submission_item)

            user_item = {
                "PK": f"USER#{user_id}",
                "SK": f"SUBMISSION#{challenge_id}",
                "submission_id": submission_id,
                "challenge_id": challenge_id,
                "challenge_title": item.get("title"),
                "challenge_type": challenge_type,
                "score": int(score),
                "college_id": college_id,
                "passed_count": correct_count,
                "total_count": total_questions,
                "time_taken_seconds": payload.get("time_taken_seconds"),
                "created_at": now,
            }
            table2.put_item(Item=user_item)

            detail_item = {
                "PK": f"SUBMISSION#{submission_id}",
                "SK": "DETAIL",
                "submission_id": submission_id,
                "challenge_id": challenge_id,
                "challenge_title": item.get("title"),
                "challenge_type": challenge_type,
                "user_id": user_id,
                "college_id": college_id,
                "section_answers": section_answers,
                "time_taken_seconds": payload.get("time_taken_seconds"),
                "score": int(score),
                "passed_count": correct_count,
                "total_count": total_questions,
                "results": results,
                "created_at": now,
            }
            table2.put_item(Item=detail_item)

            return {
                "submission_id": submission_id,
                "challenge_id": challenge_id,
                "status": "COMPLETED",
                "score": int(score),
                "passed_count": correct_count,
                "total_count": total_questions,
                "results": results,
                "time_taken_seconds": payload.get("time_taken_seconds"),
            }

        selected = (payload.get("selected_answer") or "").strip()
        correct = (item.get("correct_answer") or "").strip()
        is_correct = selected == correct
        score = item.get("points", 0) if is_correct else 0

        submission_item = {
            "PK": f"CHALLENGE#{challenge_id}",
            "SK": f"SUBMISSION#{user_id}",
            "submission_id": submission_id,
            "challenge_id": challenge_id,
            "challenge_type": challenge_type,
            "user_id": user_id,
            "college_id": college_id,
            "selected_answer": selected,
            "is_correct": is_correct,
            "score": int(score),
            "time_taken_seconds": payload.get("time_taken_seconds"),
            "created_at": now,
        }

        if college_id:
            _update_college_rank(user_id, college_id, challenge_id, int(score))
        else:
            _update_global_rank(user_id, challenge_id, int(score))

        table2.put_item(Item=submission_item)

        user_item = {
            "PK": f"USER#{user_id}",
            "SK": f"SUBMISSION#{challenge_id}",
            "submission_id": submission_id,
            "challenge_id": challenge_id,
            "challenge_title": item.get("title"),
            "challenge_type": challenge_type,
            "score": int(score),
            "college_id": college_id,
            "selected_answer": selected,
            "is_correct": is_correct,
            "time_taken_seconds": payload.get("time_taken_seconds"),
            "created_at": now,
        }
        table2.put_item(Item=user_item)

        detail_item = {
            "PK": f"SUBMISSION#{submission_id}",
            "SK": "DETAIL",
            "submission_id": submission_id,
            "challenge_id": challenge_id,
            "challenge_title": item.get("title"),
            "challenge_type": challenge_type,
            "user_id": user_id,
            "college_id": college_id,
            "selected_answer": selected,
            "is_correct": is_correct,
            "score": int(score),
            "time_taken_seconds": payload.get("time_taken_seconds"),
            "created_at": now,
        }
        table2.put_item(Item=detail_item)

        return {
            "submission_id": submission_id,
            "challenge_id": challenge_id,
            "status": "COMPLETED",
            "score": int(score),
            "passed_count": 1 if is_correct else 0,
            "total_count": 1,
            "results": [
                {
                    "is_correct": is_correct,
                    "selected_answer": selected,
                }
            ],
            "time_taken_seconds": payload.get("time_taken_seconds"),
        }

    if challenge_type != "coding":
        raise HTTPException(status_code=400, detail="Unsupported challenge type")

    language_id = payload.get("language_id")
    source_code = payload.get("source_code")
    if language_id is None or not source_code:
        raise HTTPException(
            status_code=400,
            detail="language_id and source_code are required for coding submissions"
        )

    test_cases = item.get("test_cases") or []
    if not test_cases:
        raise HTTPException(status_code=400, detail="No test cases configured")

    results: List[Dict[str, Any]] = []
    passed_count = 0
    earned_score = 0

    for index, case in enumerate(test_cases, start=1):
        payload = {
            "language_id": int(language_id),
            "source_code": source_code,
            "stdin": case.get("input", ""),
            "expected_output": case.get("expected_output", ""),
        }

        judge_result = _post_judge0(payload)
        stdout = _normalize_output(judge_result.get("stdout"))
        expected = _normalize_output(case.get("expected_output"))
        status_desc = judge_result.get("status", {}).get("description", "UNKNOWN")
        is_passed = stdout == expected and status_desc == "Accepted"
        test_case_points = int(case.get("points", 0))

        if is_passed:
            passed_count += 1
            earned_score += test_case_points

        result_item = {
            "index": index,
            "status": status_desc,
            "passed": is_passed,
            "points": test_case_points,
            "earned_points": test_case_points if is_passed else 0,
            "stdout": judge_result.get("stdout"),
            "stderr": judge_result.get("stderr"),
            "compile_output": judge_result.get("compile_output"),
            "time": judge_result.get("time"),
            "memory": judge_result.get("memory"),
            "is_hidden": bool(case.get("is_hidden")),
        }

        if not case.get("is_hidden"):
            result_item["input"] = case.get("input")
            result_item["expected_output"] = case.get("expected_output")

        results.append(result_item)

    total_count = len(test_cases)
    score = earned_score

    submission_item = {
        "PK": f"CHALLENGE#{challenge_id}",
        "SK": f"SUBMISSION#{user_id}",
        "submission_id": submission_id,
        "challenge_id": challenge_id,
        "challenge_type": challenge_type,
        "user_id": user_id,
        "college_id": college_id,
        "score": score,
        "passed_count": passed_count,
        "total_count": total_count,
        "language_id": int(language_id),
        "source_code": source_code,
        "results": results,
        "created_at": now,
    }

    if college_id:
        _update_college_rank(user_id, college_id, challenge_id, score)
    else:
        _update_global_rank(user_id, challenge_id, score)

    table2.put_item(Item=submission_item)

    user_item = {
        "PK": f"USER#{user_id}",
        "SK": f"SUBMISSION#{challenge_id}",
        "submission_id": submission_id,
        "challenge_id": challenge_id,
        "challenge_title": item.get("title"),
        "challenge_type": challenge_type,
        "score": score,
        "college_id": college_id,
        "passed_count": passed_count,
        "total_count": total_count,
        "language_id": int(language_id),
        "created_at": now,
    }
    table2.put_item(Item=user_item)

    detail_item = {
        "PK": f"SUBMISSION#{submission_id}",
        "SK": "DETAIL",
        "submission_id": submission_id,
        "challenge_id": challenge_id,
        "challenge_title": item.get("title"),
        "challenge_type": challenge_type,
        "user_id": user_id,
        "college_id": college_id,
        "language_id": int(language_id),
        "source_code": source_code,
        "score": score,
        "passed_count": passed_count,
        "total_count": total_count,
        "results": results,
        "created_at": now,
    }
    table2.put_item(Item=detail_item)

    return {
        "submission_id": submission_id,
        "challenge_id": challenge_id,
        "status": "COMPLETED",
        "score": score,
        "passed_count": passed_count,
        "total_count": total_count,
        "results": results,
    }


def get_submission_detail(submission_id: str) -> Dict[str, Any]:
    response = table2.get_item(
        Key={
            "PK": f"SUBMISSION#{submission_id}",
            "SK": "DETAIL",
        }
    )

    item = response.get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Submission not found")

    return {
        "submission_id": submission_id,
        "challenge_id": item.get("challenge_id"),
        "challenge_title": item.get("challenge_title"),
        "challenge_type": item.get("challenge_type"),
        "user_id": item.get("user_id"),
        "score": int(item.get("score", 0)),
        "created_at": int(item.get("created_at", 0)),
        "selected_answer": item.get("selected_answer"),
        "is_correct": item.get("is_correct"),
        "section_answers": item.get("section_answers"),
        "time_taken_seconds": item.get("time_taken_seconds"),
        "language_id": item.get("language_id"),
        "source_code": item.get("source_code"),
        "passed_count": item.get("passed_count"),
        "total_count": item.get("total_count"),
        "results": item.get("results"),
    }


def get_scoreboard(challenge_id: str, limit: int = 10) -> Dict[str, Any]:
    response = table2.query(
        KeyConditionExpression=Key("PK").eq(f"CHALLENGE#{challenge_id}")
    )

    items = response.get("Items", [])
    submissions = [item for item in items if item.get("SK", "").startswith("SUBMISSION#")]

    user_best: Dict[str, Dict[str, Any]] = {}

    for sub in submissions:
        user_id = sub.get("user_id")
        score = int(sub.get("score", 0))
        created_at = int(sub.get("created_at", 0))

        if user_id not in user_best:
            user_best[user_id] = {
                "user_id": user_id,
                "best_score": score,
                "submissions": 1,
                "last_submission_at": created_at,
            }
            continue

        entry = user_best[user_id]
        entry["submissions"] += 1
        if score > entry["best_score"]:
            entry["best_score"] = score
        if created_at > entry["last_submission_at"]:
            entry["last_submission_at"] = created_at

    entries = sorted(
        user_best.values(),
        key=lambda x: (x["best_score"], x["last_submission_at"]),
        reverse=True,
    )

    return {
        "challenge_id": challenge_id,
        "entries": entries[:limit],
    }


def list_user_submissions(
    user_id: str,
    challenge_id: Optional[str] = None,
    page_size: int = 10,
    start_key: Optional[str] = None,
) -> Dict[str, Any]:
    if page_size <= 0:
        raise HTTPException(status_code=400, detail="page_size must be > 0")

    decoded_key = _decode_key(start_key)
    items: List[Dict[str, Any]] = []
    last_key = decoded_key

    while len(items) < page_size:
        query_args: Dict[str, Any] = {
            "KeyConditionExpression": Key("PK").eq(f"USER#{user_id}"),
            "Limit": max(1, page_size - len(items)),
            "ScanIndexForward": False,
        }
        if last_key:
            query_args["ExclusiveStartKey"] = last_key

        response = table2.query(**query_args)
        batch = response.get("Items", [])

        if challenge_id:
            batch = [item for item in batch if item.get("challenge_id") == challenge_id]

        items.extend(batch)

        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break

    return {
        "user_id": user_id,
        "submissions": [
            {
                "submission_id": item.get("submission_id"),
                "challenge_id": item.get("challenge_id"),
                "challenge_title": item.get("challenge_title"),
                "challenge_type": item.get("challenge_type"),
                "score": int(item.get("score", 0)),
                "passed_count": item.get("passed_count"),
                "total_count": item.get("total_count"),
                "language_id": item.get("language_id"),
                "selected_answer": item.get("selected_answer"),
                "is_correct": item.get("is_correct"),
                "time_taken_seconds": item.get("time_taken_seconds"),
                "created_at": int(item.get("created_at", 0)),
            }
            for item in items
        ],
        "next_key": _encode_key(last_key),
    }


def get_college_rank(user_id: str, college_id: str) -> Dict[str, Any]:
    """Calculate the rank of a user among all students of their college."""
    all_entries: List[Dict[str, Any]] = []
    last_key = None

    while True:
        query_args: Dict[str, Any] = {
            "KeyConditionExpression": Key("PK").eq(f"COLLEGE_RANK#{college_id}"),
        }
        if last_key:
            query_args["ExclusiveStartKey"] = last_key

        response = table2.query(**query_args)
        all_entries.extend(response.get("Items", []))

        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break

    # Sort by total_score descending (higher score = better rank)
    sorted_entries = sorted(
        all_entries,
        key=lambda x: int(x.get("total_score", 0)),
        reverse=True,
    )

    user_entry = next(
        (e for e in sorted_entries if e.get("user_id") == user_id),
        None,
    )
    if not user_entry:
        raise HTTPException(
            status_code=404,
            detail="User has no submissions for this college"
        )

    rank = next(
        (idx + 1 for idx, e in enumerate(sorted_entries) if e.get("user_id") == user_id),
        None,
    )

    return {
        "user_id": user_id,
        "college_id": college_id,
        "rank": rank,
        "total_score": int(user_entry.get("total_score", 0)),
        "total_users": len(sorted_entries),
    }


def get_global_rank(user_id: str) -> Dict[str, Any]:
    """Calculate the rank of an individual (non-college) user among all individual users."""
    all_entries: List[Dict[str, Any]] = []
    last_key = None

    while True:
        query_args: Dict[str, Any] = {
            "KeyConditionExpression": Key("PK").eq("GLOBAL_RANK"),
        }
        if last_key:
            query_args["ExclusiveStartKey"] = last_key

        response = table2.query(**query_args)
        all_entries.extend(response.get("Items", []))

        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break

    sorted_entries = sorted(
        all_entries,
        key=lambda x: int(x.get("total_score", 0)),
        reverse=True,
    )

    user_entry = next(
        (e for e in sorted_entries if e.get("user_id") == user_id),
        None,
    )
    if not user_entry:
        raise HTTPException(
            status_code=404,
            detail="User has no individual submissions"
        )

    rank = next(
        (idx + 1 for idx, e in enumerate(sorted_entries) if e.get("user_id") == user_id),
        None,
    )

    return {
        "user_id": user_id,
        "rank": rank,
        "total_score": int(user_entry.get("total_score", 0)),
        "total_users": len(sorted_entries),
    }


def _parse_list(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_options(value: Optional[str]) -> List[str]:
    if not value:
        return []
    text = value.strip()
    if text.startswith("["):
        parsed = json.loads(text)
        return [str(item).strip() for item in parsed if str(item).strip()]
    if "|" in text:
        parts = text.split("|")
    else:
        parts = text.split(",")
    return [part.strip() for part in parts if part.strip()]


def _parse_test_cases(value: Optional[str]) -> List[Dict[str, Any]]:
    if not value:
        return []
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError("test_cases must be a JSON array")
    return parsed


def bulk_create_challenges_from_csv(csv_text: str) -> Dict[str, Any]:
    reader = csv.DictReader(csv_text.splitlines())
    created: List[str] = []
    errors: List[Dict[str, Any]] = []

    for index, row in enumerate(reader, start=2):
        try:
            payload = {
                "title": (row.get("title") or "").strip(),
                "description": (row.get("description") or "").strip(),
                "challenge_type": (row.get("challenge_type") or "").strip(),
                "difficulty": (row.get("difficulty") or "").strip(),
                "points": int(row.get("points") or 0),
                "tags": _parse_list(row.get("tags")),
                "created_by": (row.get("created_by") or "").strip() or None,
                "question": (row.get("question") or "").strip() or None,
                "options": _parse_options(row.get("options")),
                "correct_answer": (row.get("correct_answer") or "").strip() or None,
                "answer_explanation": (row.get("answer_explanation") or "").strip() or None,
                "default_code": row.get("default_code"),
                "sample_input": row.get("sample_input"),
                "sample_input_explanation": row.get("sample_input_explanation"),
                "sample_output": row.get("sample_output"),
                "sample_output_explanation": row.get("sample_output_explanation"),
                "hints": row.get("hints"),
            }

            test_cases_text = row.get("test_cases")
            if test_cases_text:
                payload["test_cases"] = _parse_test_cases(test_cases_text)

            result = create_challenge(payload)
            created.append(result["challenge_id"])
        except Exception as exc:
            errors.append({"row": index, "error": str(exc)})

    return {
        "created": created,
        "created_count": len(created),
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# College challenge analytics (stats + leaderboard)
# ---------------------------------------------------------------------------

def get_college_challenge_stats(college_id: str, db: Any, branch_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Return high-level challenge stats for a college:
    - challenges_created : total challenges tagged with this college_id
    - students_solved    : unique students who solved ≥ 1 challenge for this college
                           (filtered to branch when provided)
    """
    from boto3.dynamodb.conditions import Attr
    from sqlalchemy import text as sql_text

    # 1. Count challenges created for this college by scanning CHALLENGE_LIST
    challenges_created = 0
    last_key = None
    while True:
        scan_args: Dict[str, Any] = {
            "KeyConditionExpression": Key("PK").eq("CHALLENGE_LIST"),
            "FilterExpression": Attr("college_id").eq(college_id),
            "Select": "COUNT",
        }
        if last_key:
            scan_args["ExclusiveStartKey"] = last_key
        resp = table2.query(**scan_args)
        challenges_created += int(resp.get("Count", 0))
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break

    # 2. Count unique students who have a rank entry for this college
    #    If branch filter is active, first resolve eligible user_ids from MySQL
    all_rank_entries: List[Dict[str, Any]] = []
    last_key = None
    while True:
        query_args: Dict[str, Any] = {
            "KeyConditionExpression": Key("PK").eq(f"COLLEGE_RANK#{college_id}"),
            "ProjectionExpression": "user_id",
        }
        if last_key:
            query_args["ExclusiveStartKey"] = last_key
        resp = table2.query(**query_args)
        all_rank_entries.extend(resp.get("Items", []))
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break

    if branch_id:
        # Filter to only user_ids that belong to this branch
        rank_user_ids = [str(e.get("user_id", "")) for e in all_rank_entries if e.get("user_id")]
        students_solved = 0
        if rank_user_ids:
            try:
                placeholders = ", ".join(f":uid{i}" for i in range(len(rank_user_ids)))
                params = {f"uid{i}": uid for i, uid in enumerate(rank_user_ids)}
                params["branch_id"] = branch_id
                row = db.execute(
                    sql_text(
                        f"""
                        SELECT COUNT(*) AS cnt
                        FROM   users
                        WHERE  id IN ({placeholders})
                          AND  branch_id = :branch_id
                        """
                    ),
                    params,
                ).fetchone()
                students_solved = int(row.cnt) if row else 0
            except Exception:
                students_solved = 0
    else:
        students_solved = len(all_rank_entries)

    return {
        "college_id":         college_id,
        "branch_filter":      branch_id,
        "challenges_created": challenges_created,
        "students_solved":    students_solved,
    }


def get_college_challenge_leaderboard(college_id: str, db: Any, branch_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Return challenge leaderboard for a college ranked by total score descending.
    Enriches with MySQL profile (name, student_id, branch).
    Optionally filtered to a single branch.

    Response per entry: rank | name | student_id | branch | challenges_solved | avg_score | total_score
    """
    from boto3.dynamodb.conditions import Attr
    from sqlalchemy import text as sql_text
    from decimal import Decimal

    # 1. Fetch all COLLEGE_RANK entries for this college
    rank_entries: List[Dict[str, Any]] = []
    last_key = None
    while True:
        query_args: Dict[str, Any] = {
            "KeyConditionExpression": Key("PK").eq(f"COLLEGE_RANK#{college_id}"),
        }
        if last_key:
            query_args["ExclusiveStartKey"] = last_key
        resp = table2.query(**query_args)
        rank_entries.extend(resp.get("Items", []))
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break

    if not rank_entries:
        return {
            "college_id":     college_id,
            "total_students": 0,
            "leaderboard":    [],
        }

    # 2. Per-user: count challenges solved + compute avg score for this college
    def _user_challenge_stats(user_id: str) -> Dict[str, Any]:
        solved_count = 0
        score_sum    = 0
        last_k       = None
        while True:
            q: Dict[str, Any] = {
                "KeyConditionExpression": (
                    Key("PK").eq(f"USER#{user_id}")
                    & Key("SK").begins_with("SUBMISSION#")
                ),
                "FilterExpression": Attr("college_id").eq(college_id),
                "ProjectionExpression": "score",
            }
            if last_k:
                q["ExclusiveStartKey"] = last_k
            r = table2.query(**q)
            for item in r.get("Items", []):
                solved_count += 1
                raw = item.get("score", 0)
                score_sum += int(raw) if not isinstance(raw, Decimal) else int(raw)
            last_k = r.get("LastEvaluatedKey")
            if not last_k:
                break
        avg_score = round(score_sum / solved_count, 2) if solved_count else 0.0
        return {"challenges_solved": solved_count, "avg_score": avg_score}

    # 3. MySQL: bulk-fetch profiles for all user_ids in one query
    #    When branch filter is set, only include users from that branch
    user_ids = [str(e.get("user_id", "")) for e in rank_entries if e.get("user_id")]
    profiles: Dict[str, Dict[str, str]] = {}
    if user_ids:
        try:
            placeholders = ", ".join(f":uid{i}" for i in range(len(user_ids)))
            params = {f"uid{i}": uid for i, uid in enumerate(user_ids)}
            branch_clause = ""
            if branch_id:
                branch_clause = "AND branch_id = :branch_id"
                params["branch_id"] = branch_id
            rows = db.execute(
                sql_text(
                    f"""
                    SELECT id, name, student_id, branch
                    FROM   users
                    WHERE  id IN ({placeholders})
                    {branch_clause}
                    """
                ),
                params,
            ).fetchall()
            for row in rows:
                profiles[str(row.id)] = {
                    "name":       str(row.name or ""),
                    "student_id": str(row.student_id or ""),
                    "branch":     str(row.branch or ""),
                }
        except Exception:
            pass

    # 4. Sort by total_score descending — only include entries that have a profile
    #    (when branch filter is set, users not in that branch have no profile entry)
    rank_entries = [e for e in rank_entries if str(e.get("user_id", "")) in profiles]
    rank_entries.sort(
        key=lambda x: int(x.get("total_score", 0)),
        reverse=True,
    )

    # 5. Assemble leaderboard
    leaderboard: List[Dict[str, Any]] = []
    rank = 1
    for i, entry in enumerate(rank_entries):
        if i > 0 and int(entry.get("total_score", 0)) < int(rank_entries[i - 1].get("total_score", 0)):
            rank = i + 1
        user_id   = str(entry.get("user_id", ""))
        profile   = profiles.get(user_id, {})
        ch_stats  = _user_challenge_stats(user_id)
        total_score = int(entry.get("total_score", 0))
        leaderboard.append(
            {
                "rank":              rank,
                "name":              profile.get("name", ""),
                "student_id":        profile.get("student_id", ""),
                "branch":            profile.get("branch", ""),
                "challenges_solved": ch_stats["challenges_solved"],
                "avg_score":         ch_stats["avg_score"],
                "total_score":       total_score,
            }
        )

    return {
        "college_id":     college_id,
        "branch_filter":  branch_id,
        "total_students": len(leaderboard),
        "leaderboard":    leaderboard,
    }
