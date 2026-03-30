import os
from typing import Any, Dict, List

import httpx
from boto3.dynamodb.conditions import Key
from fastapi import HTTPException

from app.dynamo import course_enrollments_table, table

USER_SERVICE_BASE_URL = os.getenv("USER_SERVICE_BASE_URL", "http://localhost:8080")


def _enrollments_table_or_error():
    if course_enrollments_table is None:
        raise HTTPException(
            status_code=500,
            detail=(
                "Course enrollments table is not configured. "
                "Set DYNAMODB_COURSE_ENROLLMENTS_TABLE or DYNAMODB_TABLE6."
            ),
        )
    return course_enrollments_table


async def fetch_college_user_ids(college_id: str, auth_token: str) -> List[str]:
    """Call the user-service to get all student user IDs for a college."""
    url = f"{USER_SERVICE_BASE_URL}/api/v1/colleges/{college_id}/students/user-ids"
    headers = {"Authorization": auth_token, "accept": "application/json"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)

    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"User service returned error: {response.text}",
        )

    data = response.json()
    return data.get("userIds", [])


def _delete_user_interview_data(user_id: str) -> Dict[str, int]:
    """
    Delete all interview session items and quota records for a user.
    Sessions are discovered via the 'user-session-index' GSI.
    Quota records live at PK=USER#{user_id}, SK begins_with INTERVIEW_QUOTA#.
    """
    # --- Sessions ---
    gsi_response = table.query(
        IndexName="user-session-index",
        KeyConditionExpression=Key("user_id").eq(user_id),
    )
    session_metadata_items = [
        item for item in gsi_response.get("Items", []) if item.get("SK") == "METADATA"
    ]

    sessions_deleted = 0
    for meta_item in session_metadata_items:
        session_id = meta_item.get("session_id")
        if not session_id:
            continue

        # Fetch and delete every item in the session partition
        session_items = table.query(
            KeyConditionExpression=Key("PK").eq(f"SESSION#{session_id}")
        ).get("Items", [])

        with table.batch_writer() as batch:
            for si in session_items:
                batch.delete_item(Key={"PK": si["PK"], "SK": si["SK"]})

        sessions_deleted += 1

    # --- Quota records ---
    quota_items = table.query(
        KeyConditionExpression=(
            Key("PK").eq(f"USER#{user_id}") & Key("SK").begins_with("INTERVIEW_QUOTA#")
        )
    ).get("Items", [])

    if quota_items:
        with table.batch_writer() as batch:
            for qi in quota_items:
                batch.delete_item(Key={"PK": qi["PK"], "SK": qi["SK"]})

    return {
        "sessions_deleted": sessions_deleted,
        "quota_records_deleted": len(quota_items),
    }


def _delete_user_course_enrollments(user_id: str) -> int:
    """Delete all course enrollment records for a user from the enrollments table."""
    enroll_table = _enrollments_table_or_error()

    response = enroll_table.query(
        KeyConditionExpression=(
            Key("PK").eq(f"USER#{user_id}") & Key("SK").begins_with("ENROLLMENT#COURSE#")
        )
    )
    items = response.get("Items", [])

    if items:
        with enroll_table.batch_writer() as batch:
            for item in items:
                batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})

    return len(items)


async def purge_college_users(
    college_id: str, college_name: str, reason: str, auth_token: str
) -> Dict[str, Any]:
    """
    1. Fetch all student user IDs for the college from the user-service.
    2. For each user, remove:
       - All course enrollments (enrollments table)
       - All interview sessions + quota records (interview table)
    3. Return a summary of what was deleted.
    """
    user_ids = await fetch_college_user_ids(college_id, auth_token)

    user_results: List[Dict[str, Any]] = []
    for user_id in user_ids:
        interview_result = _delete_user_interview_data(user_id)
        enrollments_deleted = _delete_user_course_enrollments(user_id)
        user_results.append(
            {
                "user_id": user_id,
                "enrollments_deleted": enrollments_deleted,
                "sessions_deleted": interview_result["sessions_deleted"],
                "quota_records_deleted": interview_result["quota_records_deleted"],
            }
        )

    return {
        "status": "SUCCESS",
        "college_id": college_id,
        "college_name": college_name,
        "reason": reason,
        "total_users_processed": len(user_ids),
        "user_results": user_results,
    }
