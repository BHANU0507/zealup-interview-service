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


def _now_ts() -> int:
    return int(time.time())


def _normalize_output(value: Optional[str]) -> str:
    if value is None:
        return ""
    return value.strip()


def _post_judge0(payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{JUDGE0_BASE_URL}/submissions?base64_encoded=false&wait=true"
    try:
        response = httpx.post(url, json=payload, timeout=20)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Judge0 request failed: {exc}")

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Judge0 error: {response.status_code} {response.text}"
        )

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

    return response.json()


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
        "question": payload.get("question"),
        "options": payload.get("options"),
        "correct_answer": payload.get("correct_answer"),
        "answer_explanation": payload.get("answer_explanation"),
        "default_code": payload.get("default_code"),
        "sample_input": payload.get("sample_input"),
        "sample_input_explanation": payload.get("sample_input_explanation"),
        "sample_output": payload.get("sample_output"),
        "sample_output_explanation": payload.get("sample_output_explanation"),
        "hints": payload.get("hints"),
        "test_cases": payload.get("test_cases"),
    }

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

    table2.put_item(Item=metadata_item)
    table2.put_item(Item=list_item)

    return {
        "challenge_id": challenge_id,
        "status": "CREATED",
        "created_at": now,
    }


def _build_challenge_filters(
    challenge_type: Optional[str],
    difficulty: Optional[str],
    tag: Optional[str],
    created_by: Optional[str],
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


def list_challenges(
    challenge_type: Optional[str] = None,
    difficulty: Optional[str] = None,
    tag: Optional[str] = None,
    keyword: Optional[str] = None,
    created_by: Optional[str] = None,
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
    )

    decoded_key = _decode_key(start_key)
    items: List[Dict[str, Any]] = []
    last_key = decoded_key
    keyword_value = (keyword or "").strip().lower()

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

    return {
        "challenges": [
            {
                "challenge_id": item.get("challenge_id"),
                "title": item.get("title"),
                "challenge_type": item.get("challenge_type"),
                "difficulty": item.get("difficulty"),
                "points": item.get("points", 0),
                "tags": item.get("tags", []),
                "created_by": item.get("created_by"),
                "created_at": item.get("created_at", 0),
            }
            for item in items
        ],
        "next_key": _encode_key(last_key),
    }


def get_challenge(challenge_id: str) -> Dict[str, Any]:
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
        "question": item.get("question"),
        "options": item.get("options"),
        "answer_explanation": item.get("answer_explanation"),
        "default_code": item.get("default_code"),
        "sample_input": item.get("sample_input"),
        "sample_input_explanation": item.get("sample_input_explanation"),
        "sample_output": item.get("sample_output"),
        "sample_output_explanation": item.get("sample_output_explanation"),
        "hints": item.get("hints"),
        "test_cases_count": len(test_cases),
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
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    submission_id = f"sub_{uuid.uuid4()}"
    now = _now_ts()

    if challenge_type == "aptitude":
        selected = (payload.get("selected_answer") or "").strip()
        correct = (item.get("correct_answer") or "").strip()
        is_correct = selected == correct
        score = item.get("points", 0) if is_correct else 0

        submission_item = {
            "PK": f"CHALLENGE#{challenge_id}",
            "SK": f"SUBMISSION#{now}#{user_id}",
            "submission_id": submission_id,
            "challenge_id": challenge_id,
            "challenge_type": challenge_type,
            "user_id": user_id,
            "selected_answer": selected,
            "is_correct": is_correct,
            "score": int(score),
            "created_at": now,
        }

        table2.put_item(Item=submission_item)

        user_item = {
            "PK": f"USER#{user_id}",
            "SK": f"SUBMISSION#{now}#{challenge_id}",
            "submission_id": submission_id,
            "challenge_id": challenge_id,
            "challenge_title": item.get("title"),
            "challenge_type": challenge_type,
            "score": int(score),
            "selected_answer": selected,
            "is_correct": is_correct,
            "created_at": now,
        }
        table2.put_item(Item=user_item)

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

        if is_passed:
            passed_count += 1

        result_item = {
            "index": index,
            "status": status_desc,
            "passed": is_passed,
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
    points = int(item.get("points", 0))
    score = int(points * (passed_count / total_count)) if total_count else 0

    submission_item = {
        "PK": f"CHALLENGE#{challenge_id}",
        "SK": f"SUBMISSION#{now}#{user_id}",
        "submission_id": submission_id,
        "challenge_id": challenge_id,
        "challenge_type": challenge_type,
        "user_id": user_id,
        "score": score,
        "passed_count": passed_count,
        "total_count": total_count,
        "language_id": int(language_id),
        "source_code": source_code,
        "results": results,
        "created_at": now,
    }

    table2.put_item(Item=submission_item)

    user_item = {
        "PK": f"USER#{user_id}",
        "SK": f"SUBMISSION#{now}#{challenge_id}",
        "submission_id": submission_id,
        "challenge_id": challenge_id,
        "challenge_title": item.get("title"),
        "challenge_type": challenge_type,
        "score": score,
        "passed_count": passed_count,
        "total_count": total_count,
        "language_id": int(language_id),
        "created_at": now,
    }
    table2.put_item(Item=user_item)

    return {
        "submission_id": submission_id,
        "challenge_id": challenge_id,
        "status": "COMPLETED",
        "score": score,
        "passed_count": passed_count,
        "total_count": total_count,
        "results": results,
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
                "created_at": int(item.get("created_at", 0)),
            }
            for item in items
        ],
        "next_key": _encode_key(last_key),
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
