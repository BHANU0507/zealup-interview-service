import time
import uuid
import os
import mimetypes
from decimal import Decimal
from typing import Any, Dict, List

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError
from fastapi import HTTPException

from app.dynamo import course_enrollments_table, courses_table


def _courses_table_or_error():
    if courses_table is None:
        raise HTTPException(
            status_code=500,
            detail="Courses table is not configured. Set DYNAMODB_COURSES_TABLE or DYNAMODB_TABLE5.",
        )
    return courses_table


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


def _to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_decimal_number(value: Any, default: str = "0") -> Decimal:
    if value is None:
        return Decimal(default)
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (TypeError, ValueError):
        return Decimal(default)


def _to_str_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(v) for v in value]


def _normalize_percentage(value: Any) -> int:
    return max(0, min(100, _to_int(value, default=0)))


def _now() -> int:
    return int(time.time())


def _course_list_key(course_id: str) -> Dict[str, str]:
    return {"PK": "COURSE_LIST", "SK": f"COURSE#{course_id}"}


def _course_meta_key(course_id: str) -> Dict[str, str]:
    return {"PK": f"COURSE#{course_id}", "SK": "METADATA"}


def _module_key(course_id: str, module_id: str) -> Dict[str, str]:
    return {"PK": f"COURSE#{course_id}", "SK": f"MODULE#{module_id}"}


def _topic_key(course_id: str, module_id: str, topic_id: str) -> Dict[str, str]:
    return {"PK": f"COURSE#{course_id}", "SK": f"MODULE#{module_id}#TOPIC#{topic_id}"}


def _topic_discussion_pk(course_id: str, module_id: str, topic_id: str) -> str:
    return f"COURSE#{course_id}#MODULE#{module_id}#TOPIC#{topic_id}"


def _discussion_sk(discussion_id: str) -> str:
    return f"DISCUSSION#{discussion_id}"


def _topic_user_notes_pk(user_id: str, course_id: str, module_id: str, topic_id: str) -> str:
    return f"USER#{user_id}#COURSE#{course_id}#MODULE#{module_id}#TOPIC#{topic_id}"


def _note_sk(note_id: str) -> str:
    return f"NOTE#{note_id}"


def _material_key(course_id: str, module_id: str, topic_id: str, material_id: str) -> Dict[str, str]:
    return {
        "PK": f"COURSE#{course_id}",
        "SK": f"MODULE#{module_id}#TOPIC#{topic_id}#MATERIAL#{material_id}",
    }


def _topic_video_bucket_or_error() -> str:
    bucket = (
        os.getenv("COURSE_TOPIC_VIDEO_BUCKET")
        or os.getenv("AWS_S3_BUCKET")
        or os.getenv("S3_BUCKET")
    )
    if not bucket:
        raise HTTPException(
            status_code=500,
            detail="S3 bucket is not configured. Set COURSE_TOPIC_VIDEO_BUCKET (or AWS_S3_BUCKET).",
        )
    return bucket


def _materials_bucket_or_error() -> str:
    bucket = (
        os.getenv("COURSE_TOPIC_MATERIALS_BUCKET")
        or os.getenv("COURSE_TOPIC_VIDEO_BUCKET")
        or os.getenv("AWS_S3_BUCKET")
        or os.getenv("S3_BUCKET")
    )
    if not bucket:
        raise HTTPException(
            status_code=500,
            detail=(
                "S3 bucket is not configured. Set COURSE_TOPIC_MATERIALS_BUCKET "
                "(or COURSE_TOPIC_VIDEO_BUCKET / AWS_S3_BUCKET)."
            ),
        )
    return bucket


def _topic_video_cdn_base_url() -> str | None:
    raw_base = (
        os.getenv("COURSE_TOPIC_VIDEO_CDN_URL")
        or os.getenv("CLOUDFRONT_DOMAIN_URL")
        or os.getenv("CLOUDFRONT_URL")
        or os.getenv("CLOUDFRONT_DOMAIN")
    )
    if not raw_base:
        return None

    base = str(raw_base).strip().rstrip("/")
    if not base:
        return None
    if not base.startswith("http://") and not base.startswith("https://"):
        base = f"https://{base}"
    return base


def _materials_cdn_base_url() -> str | None:
    raw_base = (
        os.getenv("COURSE_TOPIC_MATERIALS_CDN_URL")
        or os.getenv("COURSE_TOPIC_VIDEO_CDN_URL")
        or os.getenv("CLOUDFRONT_DOMAIN_URL")
        or os.getenv("CLOUDFRONT_URL")
        or os.getenv("CLOUDFRONT_DOMAIN")
    )
    if not raw_base:
        return None

    base = str(raw_base).strip().rstrip("/")
    if not base:
        return None
    if not base.startswith("http://") and not base.startswith("https://"):
        base = f"https://{base}"
    return base


def _s3_public_url(bucket: str, key: str) -> str:
    region = os.getenv("AWS_REGION") or "us-east-1"
    if region == "us-east-1":
        return f"https://{bucket}.s3.amazonaws.com/{key}"
    return f"https://{bucket}.s3.{region}.amazonaws.com/{key}"


def _topic_video_url_from_key(video_key: str) -> str:
    normalized_key = str(video_key or "").strip().lstrip("/")
    if not normalized_key:
        return ""

    cdn_base = _topic_video_cdn_base_url()
    if cdn_base:
        return f"{cdn_base}/{normalized_key}"

    bucket = _topic_video_bucket_or_error()
    return _s3_public_url(bucket, normalized_key)


def _resolve_topic_video_fields(item: Dict[str, Any]) -> tuple[str, str]:
    stored_key = str(item.get("video_key") or "").strip()
    legacy_value = str(item.get("video_url") or "").strip()

    if stored_key:
        return stored_key, _topic_video_url_from_key(stored_key)

    if legacy_value and "://" not in legacy_value:
        return legacy_value, _topic_video_url_from_key(legacy_value)

    return "", legacy_value


def _topic_video_signed_url(video_key: str, expires_in_seconds: int = 900) -> str:
    key = str(video_key or "").strip().lstrip("/")
    if not key:
        return ""

    bucket = _topic_video_bucket_or_error()
    ttl = max(60, min(3600, _to_int(expires_in_seconds, default=900)))
    s3_client = boto3.client("s3")
    return s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=ttl,
    )


def _is_missing_s3_error(exc: ClientError) -> bool:
    error_code = str(exc.response.get("Error", {}).get("Code") or "")
    return error_code in {"NoSuchKey", "404", "NotFound"}


def _topic_video_delete_object(video_key: str, allow_missing: bool = False) -> None:
    key = str(video_key or "").strip().lstrip("/")
    if not key:
        return

    bucket = _topic_video_bucket_or_error()
    s3_client = boto3.client("s3")
    try:
        s3_client.delete_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if allow_missing and _is_missing_s3_error(exc):
            return
        raise HTTPException(status_code=500, detail="Failed to delete topic video from S3") from exc


def _material_url_from_key(s3_key: str) -> str:
    key = str(s3_key or "").strip().lstrip("/")
    if not key:
        return ""

    cdn_base = _materials_cdn_base_url()
    if cdn_base:
        return f"{cdn_base}/{key}"

    bucket = _materials_bucket_or_error()
    return _s3_public_url(bucket, key)


def _material_signed_url(s3_key: str, expires_in_seconds: int = 900) -> str:
    key = str(s3_key or "").strip().lstrip("/")
    if not key:
        return ""

    ttl = max(60, min(3600, _to_int(expires_in_seconds, default=900)))
    bucket = _materials_bucket_or_error()
    s3_client = boto3.client("s3")
    return s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=ttl,
    )


def _resolve_material_fields(item: Dict[str, Any]) -> tuple[str, str, str]:
    s3_key = str(item.get("s3_key") or "").strip()
    file_url = str(item.get("file_url") or "").strip()
    file_type = str(item.get("file_type") or "").strip()

    if not s3_key and file_url and "://" not in file_url:
        s3_key = file_url
    if s3_key and not file_type:
        ext = os.path.splitext(s3_key)[1].replace(".", "").lower()
        file_type = ext

    resolved_url = _material_url_from_key(s3_key) if s3_key else file_url
    return s3_key, resolved_url, file_type


def _material_move_object(old_s3_key: str, new_s3_key: str) -> None:
    old_key = str(old_s3_key or "").strip().lstrip("/")
    new_key = str(new_s3_key or "").strip().lstrip("/")
    if not old_key or not new_key or old_key == new_key:
        return

    bucket = _materials_bucket_or_error()
    s3_client = boto3.client("s3")
    try:
        s3_client.copy_object(
            Bucket=bucket,
            CopySource={"Bucket": bucket, "Key": old_key},
            Key=new_key,
        )
        s3_client.delete_object(Bucket=bucket, Key=old_key)
    except ClientError as exc:
        raise HTTPException(status_code=500, detail="Failed to update material object in S3") from exc


def _material_delete_object(s3_key: str, allow_missing: bool = False) -> None:
    key = str(s3_key or "").strip().lstrip("/")
    if not key:
        return

    bucket = _materials_bucket_or_error()
    s3_client = boto3.client("s3")
    try:
        s3_client.delete_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if allow_missing and _is_missing_s3_error(exc):
            return
        raise HTTPException(status_code=500, detail="Failed to delete material object from S3") from exc


def _list_topic_materials(course_id: str, module_id: str, topic_id: str) -> List[Dict[str, Any]]:
    table = _courses_table_or_error()
    response = table.query(
        KeyConditionExpression=(
            Key("PK").eq(f"COURSE#{course_id}")
            & Key("SK").begins_with(f"MODULE#{module_id}#TOPIC#{topic_id}#MATERIAL#")
        ),
        ScanIndexForward=True,
    )
    return response.get("Items", [])


def _user_pk(user_id: str) -> str:
    return f"USER#{user_id}"


def _user_course_pk(user_id: str, course_id: str) -> str:
    return f"USER#{user_id}#COURSE#{course_id}"


def _enrollment_sk(course_id: str) -> str:
    return f"ENROLLMENT#COURSE#{course_id}"


def _ensure_course_exists(course_id: str) -> Dict[str, Any]:
    table = _courses_table_or_error()
    response = table.get_item(Key=_course_meta_key(course_id))
    item = response.get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Course not found")
    return item


def _get_enrollment_item(user_id: str, course_id: str) -> Dict[str, Any] | None:
    table = _enrollments_table_or_error()
    response = table.get_item(Key={"PK": _user_pk(user_id), "SK": _enrollment_sk(course_id)})
    return response.get("Item")


def _list_user_enrollments(user_id: str) -> List[Dict[str, Any]]:
    table = _enrollments_table_or_error()
    response = table.query(
        KeyConditionExpression=Key("PK").eq(_user_pk(user_id)) & Key("SK").begins_with("ENROLLMENT#COURSE#"),
        ScanIndexForward=False,
    )
    return response.get("Items", [])


def _assert_user_can_open_course(user_id: str, course_id: str) -> None:
    enrollment = _get_enrollment_item(user_id, course_id)
    if enrollment:
        return

    raise HTTPException(status_code=403, detail="User is not enrolled in this course. Please enroll first.")


def _topic_status_for_user(default_status: str, progress_status: str | None) -> str:
    status = (progress_status or default_status or "NOT_STARTED").strip().upper()
    if status in {"COMPLETED", "ENDED"}:
        return "ENDED"
    if status in {"IN_PROGRESS", "STARTED"}:
        return "IN_PROGRESS"
    return "STARTED" if status == "START" else "NOT_STARTED"


def get_user_enrollments(user_id: str) -> Dict[str, Any]:
    enrollments = _list_user_enrollments(user_id)
    
    table = _courses_table_or_error()
    enrolled_courses: List[Dict[str, Any]] = []
    
    for enrollment in enrollments:
        course_id = str(enrollment.get("course_id") or "")
        if not course_id:
            continue
        
        course_item = table.get_item(Key=_course_list_key(course_id)).get("Item")
        if course_item:
            progress_percentage = _normalize_percentage(enrollment.get("progress_percentage", 0))
            
            # Determine course status based on progress
            if progress_percentage == 0:
                course_status = "JUST_ENROLLED"
            elif progress_percentage == 100:
                course_status = "COMPLETED"
            else:
                course_status = "IN_PROGRESS"
            
            enrolled_courses.append(
                {
                    "course_id": course_id,
                    "title": str(course_item.get("title") or ""),
                    "progress_percentage": progress_percentage,
                    "status": course_status,
                }
            )
    
    return {
        "user_id": user_id,
        "enrolled_count": len(enrolled_courses),
        "enrolled_courses": enrolled_courses,
    }


def get_user_enrollments_count(user_id: str) -> Dict[str, Any]:
    """Returns only enrolled course count and course IDs."""
    enrollments = _list_user_enrollments(user_id)
    
    course_ids: List[str] = []
    for enrollment in enrollments:
        course_id = str(enrollment.get("course_id") or "")
        if course_id:
            course_ids.append(course_id)
    
    return {
        "user_id": user_id,
        "enrolled_count": len(course_ids),
        "course_ids": course_ids,
    }


def get_user_enrollments_detail(user_id: str) -> Dict[str, Any]:
    """Returns detailed enrollment info including course description, level, duration, technologies."""
    enrollments = _list_user_enrollments(user_id)
    
    table = _courses_table_or_error()
    enrolled_courses: List[Dict[str, Any]] = []
    
    for enrollment in enrollments:
        course_id = str(enrollment.get("course_id") or "")
        if not course_id:
            continue
        
        # Get course list item
        course_list_item = table.get_item(Key=_course_list_key(course_id)).get("Item")
        
        # Get course metadata
        course_meta = table.get_item(Key=_course_meta_key(course_id)).get("Item")
        
        if course_list_item and course_meta:
            progress_percentage = _normalize_percentage(enrollment.get("progress_percentage", 0))
            
            # Determine course status based on progress
            if progress_percentage == 0:
                course_status = "JUST_ENROLLED"
            elif progress_percentage == 100:
                course_status = "COMPLETED"
            else:
                course_status = "IN_PROGRESS"
            
            enrolled_courses.append(
                {
                    "course_id": course_id,
                    "title": str(course_list_item.get("title") or ""),
                    "instructor_name": str(course_list_item.get("instructor_name") or ""),
                    "description": str(course_meta.get("description") or ""),
                    "level": str(course_meta.get("level") or ""),
                    "duration_hours": _to_float(course_meta.get("duration_hours", 0)),
                    "progress_percentage": progress_percentage,
                    "key_technologies": _to_str_list(course_meta.get("key_technologies", [])),
                    "status": course_status,
                }
            )
    
    return {
        "user_id": user_id,
        "enrolled_count": len(enrolled_courses),
        "enrolled_courses": enrolled_courses,
    }


def get_user_enrolled_courses_simple(user_id: str) -> Dict[str, Any]:
    """Return only course_id and course_name for every course the user is enrolled in."""
    enrollments = _list_user_enrollments(user_id)
    table = _courses_table_or_error()
    courses: List[Dict[str, Any]] = []
    for enrollment in enrollments:
        course_id = str(enrollment.get("course_id") or "")
        if not course_id:
            continue
        course_list_item = table.get_item(Key=_course_list_key(course_id)).get("Item")
        courses.append({
            "course_id": course_id,
            "course_name": str(course_list_item.get("title") or "") if course_list_item else "",
        })
    return {
        "user_id": user_id,
        "total_count": len(courses),
        "courses": courses,
    }


# ---------------------------------------------------------------------------
# Admin enrollment management
# ---------------------------------------------------------------------------

def admin_get_course_enrollments(course_id: str) -> Dict[str, Any]:
    """Return all users enrolled in the given course (admin only)."""
    _ensure_course_exists(course_id)
    table = _enrollments_table_or_error()
    sk_value = _enrollment_sk(course_id)

    response = table.scan(FilterExpression=Attr("SK").eq(sk_value))
    items: List[Dict[str, Any]] = list(response.get("Items", []))
    while "LastEvaluatedKey" in response:
        response = table.scan(
            FilterExpression=Attr("SK").eq(sk_value),
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        items.extend(response.get("Items", []))

    enrollments: List[Dict[str, Any]] = []
    for item in items:
        uid = str(item.get("user_id") or "")
        if not uid:
            continue
        enrollments.append({
            "user_id": uid,
            "enrolled_at": _to_int(item.get("enrolled_at"), default=0),
            "status": str(item.get("status") or "IN_PROGRESS"),
            "progress_percentage": _normalize_percentage(item.get("progress_percentage", 0)),
        })

    return {
        "course_id": course_id,
        "total_count": len(enrollments),
        "enrollments": enrollments,
    }


def admin_enroll_user(course_id: str, user_id: str) -> Dict[str, Any]:
    """Admin-force enroll a user into a course without subscription checks."""
    user_id = str(user_id or "").strip()
    course_id = str(course_id or "").strip()
    if not user_id or not course_id:
        raise HTTPException(status_code=400, detail="user_id and course_id are required")

    _ensure_course_exists(course_id)

    if _get_enrollment_item(user_id, course_id):
        raise HTTPException(status_code=409, detail="User is already enrolled in this course")

    now = _now()
    table = _enrollments_table_or_error()
    table.put_item(
        Item={
            "PK": _user_pk(user_id),
            "SK": _enrollment_sk(course_id),
            "user_id": user_id,
            "course_id": course_id,
            "status": "IN_PROGRESS",
            "progress_percentage": 0,
            "enrolled_at": now,
            "updated_at": now,
        }
    )
    return {"status": "ENROLLED", "message": f"User {user_id} enrolled in course {course_id} successfully"}


def admin_unenroll_user(course_id: str, user_id: str) -> Dict[str, Any]:
    """Admin-remove a user from a course."""
    user_id = str(user_id or "").strip()
    course_id = str(course_id or "").strip()
    if not user_id or not course_id:
        raise HTTPException(status_code=400, detail="user_id and course_id are required")

    _ensure_course_exists(course_id)

    if not _get_enrollment_item(user_id, course_id):
        raise HTTPException(status_code=404, detail="User is not enrolled in this course")

    table = _enrollments_table_or_error()
    table.delete_item(Key={"PK": _user_pk(user_id), "SK": _enrollment_sk(course_id)})
    return {"status": "REMOVED", "message": f"User {user_id} removed from course {course_id} successfully"}


def list_courses(limit: int = 20, user_id: str | None = None) -> Dict[str, Any]:
    table = _courses_table_or_error()
    response = table.query(
        KeyConditionExpression=Key("PK").eq("COURSE_LIST"),
        Limit=limit,
        ScanIndexForward=False,
    )
    items = response.get("Items", [])

    enrollment_map: Dict[str, Dict[str, Any]] = {}
    if user_id:
        enrollments = _list_user_enrollments(user_id)
        enrollment_map = {
            str(item.get("course_id") or item.get("SK", "").replace("ENROLLMENT#COURSE#", "")): item
            for item in enrollments
        }

    courses: List[Dict[str, Any]] = []
    for item in items:
        course_id = str(item.get("course_id") or item.get("id") or "")
        if not course_id:
            continue

        enrolled_item = enrollment_map.get(course_id)
        progress = _normalize_percentage(enrolled_item.get("progress_percentage", 0) if enrolled_item else 0)
        status = str(enrolled_item.get("status") or "") if enrolled_item else ""

        if enrolled_item and (status.upper() == "COMPLETED" or progress >= 100):
            action = "PREVIEW"
        elif enrolled_item:
            action = "CONTINUE_LEARNING"
        else:
            action = "ENROLL"

        courses.append(
            {
                "course_id": course_id,
                "title": str(item.get("title") or ""),
                "instructor_name": str(item.get("instructor_name") or ""),
                "progress_percentage": progress,
                "level": str(item.get("level") or ""),
                "duration_hours": max(0.0, _to_float(item.get("duration_hours"), default=0.0)),
                "key_technologies": _to_str_list(item.get("key_technologies")),
                "action": action,
            }
        )

    if not user_id:
        return {
            "user_id": None,
            "plan_name": None,
            "course_limit": None,
            "enrolled_count": None,
            "courses": courses,
        }

    return {
        "user_id": user_id,
        "plan_name": None,
        "course_limit": None,
        "enrolled_count": len(enrollment_map),
        "courses": courses,
    }


def list_all_courses_admin(limit: int = 200) -> Dict[str, Any]:
    table = _courses_table_or_error()

    # Count total courses available in COURSE_LIST partition.
    total_courses = 0
    count_kwargs: Dict[str, Any] = {
        "KeyConditionExpression": Key("PK").eq("COURSE_LIST"),
        "Select": "COUNT",
    }
    while True:
        count_response = table.query(**count_kwargs)
        total_courses += _to_int(count_response.get("Count"), 0)
        lek = count_response.get("LastEvaluatedKey")
        if not lek:
            break
        count_kwargs["ExclusiveStartKey"] = lek

    response = table.query(
        KeyConditionExpression=Key("PK").eq("COURSE_LIST"),
        Limit=limit,
        ScanIndexForward=False,
    )
    items = response.get("Items", [])

    courses: List[Dict[str, Any]] = []
    for item in items:
        course_id = str(item.get("course_id") or item.get("id") or "")
        if not course_id:
            continue

        meta = table.get_item(Key=_course_meta_key(course_id)).get("Item") or {}
        courses.append(
            {
                "course_id": course_id,
                "title": str(item.get("title") or ""),
                "instructor_name": str(item.get("instructor_name") or ""),
                "course_overview": str(meta.get("course_overview") or ""),
                "description": str(meta.get("description") or ""),
                "level": str(item.get("level") or meta.get("level") or ""),
                "duration_hours": max(0.0, _to_float(item.get("duration_hours", meta.get("duration_hours", 0)))),
                "key_technologies": _to_str_list(item.get("key_technologies", meta.get("key_technologies", []))),
                "created_at": _to_int(item.get("created_at"), 0),
                "updated_at": _to_int(item.get("updated_at"), 0),
            }
        )

    return {
        "total_courses": total_courses,
        "limit": limit,
        "courses": courses,
    }


def enroll_course(payload: Dict[str, Any]) -> Dict[str, Any]:
    user_id = str(payload.get("user_id") or "").strip()
    course_id = str(payload.get("course_id") or "").strip()
    if not user_id or not course_id:
        raise HTTPException(status_code=400, detail="user_id and course_id are required")

    plan_type = str(payload.get("planType") or payload.get("plan_type") or "UNKNOWN").strip() or "UNKNOWN"
    subscription_status = str(payload.get("status") or "ACTIVE").strip().upper()
    if subscription_status not in {"ACTIVE", "TRIAL"}:
        raise HTTPException(
            status_code=403,
            detail=f"Subscription is not active (status={subscription_status}).",
        )

    courses_limit = _to_int(
        payload.get("coursesLimit", payload.get("courses_limit", payload.get("course_limit"))),
        default=-1,
    )
    if courses_limit < 0:
        raise HTTPException(status_code=400, detail="coursesLimit is required and must be >= 0")

    _ensure_course_exists(course_id)

    existing = _get_enrollment_item(user_id, course_id)
    if existing:
        raise HTTPException(
            status_code=409,
            detail="User is already enrolled in this course",
        )

    enrolled_count = len(_list_user_enrollments(user_id))
    if enrolled_count >= courses_limit:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Enrollment limit is over for {plan_type}. Upgrade your subscription plan."
            ),
        )

    now = _now()
    table = _enrollments_table_or_error()
    table.put_item(
        Item={
            "PK": _user_pk(user_id),
            "SK": _enrollment_sk(course_id),
            "user_id": user_id,
            "course_id": course_id,
            "status": "IN_PROGRESS",
            "progress_percentage": 0,
            "enrolled_at": now,
            "updated_at": now,
        }
    )

    return {
        "status": "ENROLLED",
        "message": "Course enrollment successful",
    }


def get_course_detail(course_id: str, user_id: str) -> Dict[str, Any]:
    _assert_user_can_open_course(user_id, course_id)

    item = _ensure_course_exists(course_id)
    list_item = _courses_table_or_error().get_item(Key=_course_list_key(course_id)).get("Item") or {}
    return {
        "course_id": course_id,
        "title": str(item.get("title") or ""),
        "instructor_name": str(list_item.get("instructor_name") or ""),
        "course_overview": str(item.get("course_overview") or ""),
        "description": str(item.get("description") or ""),
        "level": str(item.get("level") or ""),
        "duration_hours": max(0.0, _to_float(item.get("duration_hours"), default=0.0)),
        "prerequisites": _to_str_list(item.get("prerequisites")),
        "key_topics": _to_str_list(item.get("key_topics")),
        "key_technologies": _to_str_list(item.get("key_technologies")),
    }


def get_course_detail_admin(course_id: str) -> Dict[str, Any]:
    item = _ensure_course_exists(course_id)
    list_item = _courses_table_or_error().get_item(Key=_course_list_key(course_id)).get("Item") or {}
    return {
        "course_id": course_id,
        "title": str(item.get("title") or ""),
        "instructor_name": str(list_item.get("instructor_name") or ""),
        "course_overview": str(item.get("course_overview") or ""),
        "description": str(item.get("description") or ""),
        "level": str(item.get("level") or ""),
        "duration_hours": max(0.0, _to_float(item.get("duration_hours"), default=0.0)),
        "prerequisites": _to_str_list(item.get("prerequisites")),
        "key_topics": _to_str_list(item.get("key_topics")),
        "key_technologies": _to_str_list(item.get("key_technologies")),
    }


def _list_modules(course_id: str) -> List[Dict[str, Any]]:
    table = _courses_table_or_error()
    response = table.query(
        KeyConditionExpression=Key("PK").eq(f"COURSE#{course_id}") & Key("SK").begins_with("MODULE#"),
        ScanIndexForward=True,
    )
    module_items = []
    for item in response.get("Items", []):
        sk = str(item.get("SK") or "")
        if "#TOPIC#" in sk:
            continue
        module_items.append(item)
    return module_items


def _is_topic_record(item: Dict[str, Any], module_id: str | None = None, topic_id: str | None = None) -> bool:
    sk = str(item.get("SK") or "")
    if not sk or "#TOPIC#" not in sk or "#MATERIAL#" in sk:
        return False

    if module_id and not sk.startswith(f"MODULE#{module_id}#TOPIC#"):
        return False

    if topic_id and module_id and sk != f"MODULE#{module_id}#TOPIC#{topic_id}":
        return False

    if topic_id and not module_id and not sk.endswith(f"#TOPIC#{topic_id}"):
        return False

    return True


def _list_module_topics(course_id: str, module_id: str) -> List[Dict[str, Any]]:
    table = _courses_table_or_error()
    response = table.query(
        KeyConditionExpression=Key("PK").eq(f"COURSE#{course_id}") & Key("SK").begins_with(f"MODULE#{module_id}#TOPIC#"),
        ScanIndexForward=True,
    )
    return [item for item in response.get("Items", []) if _is_topic_record(item, module_id=module_id)]


def _list_user_topic_progress(user_id: str, course_id: str, module_id: str) -> Dict[str, str]:
    table = _enrollments_table_or_error()
    response = table.query(
        KeyConditionExpression=(
            Key("PK").eq(_user_course_pk(user_id, course_id))
            & Key("SK").begins_with(f"TOPIC_PROGRESS#MODULE#{module_id}#TOPIC#")
        ),
        ScanIndexForward=True,
    )

    progress_map: Dict[str, str] = {}
    for item in response.get("Items", []):
        sk = str(item.get("SK") or "")
        topic_id = sk.split("#TOPIC#")[-1] if "#TOPIC#" in sk else ""
        if topic_id:
            progress_map[topic_id] = str(item.get("status") or "NOT_STARTED")
    return progress_map


def list_course_modules(course_id: str, user_id: str) -> Dict[str, Any]:
    _assert_user_can_open_course(user_id, course_id)

    modules = _list_modules(course_id)
    mapped_modules: List[Dict[str, Any]] = []
    for module in modules:
        module_id = str(module.get("module_id") or str(module.get("SK", "")).replace("MODULE#", ""))
        topics = _list_module_topics(course_id, module_id)
        total_topics = len(topics)

        progress_map = _list_user_topic_progress(user_id, course_id, module_id)
        completed_topics = 0
        for topic in topics:
            topic_id = str(topic.get("topic_id") or str(topic.get("SK", "")).split("#TOPIC#")[-1])
            p_status = progress_map.get(topic_id, "")
            if p_status.upper() in {"COMPLETED", "ENDED"}:
                completed_topics += 1

        completion_percentage = int((completed_topics / total_topics) * 100) if total_topics > 0 else 0

        mapped_modules.append(
            {
                "module_id": module_id,
                "title": str(module.get("title") or ""),
                "total_topics": total_topics,
                "completed_topics": completed_topics,
                "completion_percentage": completion_percentage,
            }
        )

    return {
        "course_id": course_id,
        "user_id": user_id,
        "modules": mapped_modules,
    }


def list_course_modules_admin(course_id: str) -> Dict[str, Any]:
    _ensure_course_exists(course_id)

    modules = _list_modules(course_id)
    mapped_modules: List[Dict[str, Any]] = []
    for module in modules:
        module_id = str(module.get("module_id") or str(module.get("SK", "")).replace("MODULE#", ""))
        topics = _list_module_topics(course_id, module_id)
        total_topics = len(topics)

        mapped_modules.append(
            {
                "module_id": module_id,
                "title": str(module.get("title") or ""),
                "total_topics": total_topics,
                "completed_topics": 0,
                "completion_percentage": 0,
            }
        )

    return {
        "course_id": course_id,
        "modules": mapped_modules,
    }


def list_module_topics(course_id: str, module_id: str, user_id: str) -> Dict[str, Any]:
    _assert_user_can_open_course(user_id, course_id)

    topics = _list_module_topics(course_id, module_id)
    progress_map = _list_user_topic_progress(user_id, course_id, module_id)

    mapped_topics: List[Dict[str, Any]] = []
    for item in topics:
        topic_id = str(item.get("topic_id") or str(item.get("SK", "")).split("#TOPIC#")[-1])
        video_key, video_url = _resolve_topic_video_fields(item)
        mapped_topics.append(
            {
                "topic_id": topic_id,
                "title": str(item.get("title") or ""),
                "description": str(item.get("description") or ""),
                "duration_minutes": max(0, _to_int(item.get("duration_minutes"), default=0)),
                "locked": bool(item.get("locked", False)),
                "video_key": video_key,
                "video_url": video_url,
                "status": _topic_status_for_user(
                    str(item.get("status") or "NOT_STARTED"),
                    progress_map.get(topic_id),
                ),
            }
        )

    return {
        "course_id": course_id,
        "module_id": module_id,
        "user_id": user_id,
        "topics": mapped_topics,
    }


def list_module_topics_admin(course_id: str, module_id: str) -> Dict[str, Any]:
    _ensure_course_exists(course_id)

    module = _courses_table_or_error().get_item(Key=_module_key(course_id, module_id)).get("Item")
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")

    topics = _list_module_topics(course_id, module_id)

    mapped_topics: List[Dict[str, Any]] = []
    for item in topics:
        topic_id = str(item.get("topic_id") or str(item.get("SK", "")).split("#TOPIC#")[-1])
        video_key, video_url = _resolve_topic_video_fields(item)
        mapped_topics.append(
            {
                "topic_id": topic_id,
                "title": str(item.get("title") or ""),
                "description": str(item.get("description") or ""),
                "duration_minutes": max(0, _to_int(item.get("duration_minutes"), default=0)),
                "locked": bool(item.get("locked", False)),
                "video_key": video_key,
                "video_url": video_url,
                "status": str(item.get("status") or "NOT_STARTED"),
            }
        )

    return {
        "course_id": course_id,
        "module_id": module_id,
        "topics": mapped_topics,
    }


def get_topic_detail_admin(topic_id: str) -> Dict[str, Any]:
    topic_id = str(topic_id or "").strip()
    if not topic_id:
        raise HTTPException(status_code=400, detail="topic_id is required")

    table = _courses_table_or_error()
    response = table.scan(
        FilterExpression=Attr("topic_id").eq(topic_id) & Attr("SK").contains("#TOPIC#")
    )
    items = [item for item in response.get("Items", []) if _is_topic_record(item, topic_id=topic_id)]

    if not items:
        raise HTTPException(status_code=404, detail="Topic not found")

    item = items[0]
    course_id = str(item.get("course_id") or "")
    module_id = str(item.get("module_id") or "")
    video_key, video_url = _resolve_topic_video_fields(item)

    return {
        "course_id": course_id,
        "module_id": module_id,
        "topic_id": topic_id,
        "title": str(item.get("title") or ""),
        "description": str(item.get("description") or ""),
        "duration_minutes": max(0, _to_int(item.get("duration_minutes"), default=0)),
        "locked": bool(item.get("locked", False)),
        "video_key": video_key,
        "video_url": video_url,
        "status": str(item.get("status") or "NOT_STARTED"),
    }


def update_topic_progress(course_id: str, module_id: str, topic_id: str, user_id: str, status: str) -> Dict[str, Any]:
    _assert_user_can_open_course(user_id, course_id)

    topic = _courses_table_or_error().get_item(Key=_topic_key(course_id, module_id, topic_id)).get("Item")
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    normalized = _topic_status_for_user("NOT_STARTED", status)
    now = _now()

    table = _enrollments_table_or_error()
    table.put_item(
        Item={
            "PK": _user_course_pk(user_id, course_id),
            "SK": f"TOPIC_PROGRESS#MODULE#{module_id}#TOPIC#{topic_id}",
            "user_id": user_id,
            "course_id": course_id,
            "module_id": module_id,
            "topic_id": topic_id,
            "status": normalized,
            "updated_at": now,
        }
    )

    enrollment = _get_enrollment_item(user_id, course_id)
    if enrollment:
        modules = _list_modules(course_id)
        total_topics = 0
        completed_topics = 0
        for module in modules:
            m_id = str(module.get("module_id") or str(module.get("SK", "")).replace("MODULE#", ""))
            module_topics = _list_module_topics(course_id, m_id)
            total_topics += len(module_topics)

            mod_progress = _list_user_topic_progress(user_id, course_id, m_id)
            for topic_item in module_topics:
                t_id = str(topic_item.get("topic_id") or str(topic_item.get("SK", "")).split("#TOPIC#")[-1])
                if mod_progress.get(t_id, "").upper() in {"COMPLETED", "ENDED"}:
                    completed_topics += 1

        progress_percentage = int((completed_topics / total_topics) * 100) if total_topics > 0 else 0
        table.put_item(
            Item={
                **enrollment,
                "status": "COMPLETED" if progress_percentage == 100 else "IN_PROGRESS",
                "progress_percentage": progress_percentage,
                "updated_at": now,
            }
        )

    return {
        "status": "UPDATED",
        "message": "Topic progress updated",
    }


def mark_topic_completed(course_id: str, module_id: str, topic_id: str, user_id: str) -> Dict[str, Any]:
    return update_topic_progress(
        course_id=course_id,
        module_id=module_id,
        topic_id=topic_id,
        user_id=user_id,
        status="ENDED",
    )


def create_course(payload: Dict[str, Any]) -> Dict[str, Any]:
    title = str(payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")

    course_id = str(payload.get("course_id") or f"course_{uuid.uuid4().hex[:10]}")
    now = _now()

    list_item = {
        "PK": "COURSE_LIST",
        "SK": f"COURSE#{course_id}",
        "course_id": course_id,
        "title": title,
        "instructor_name": str(payload.get("instructor_name") or ""),
        "level": str(payload.get("level") or ""),
        "duration_hours": max(Decimal("0"), _to_decimal_number(payload.get("duration_hours"), default="0")),
        "key_technologies": _to_str_list(payload.get("key_technologies")),
        "created_at": now,
        "updated_at": now,
    }

    meta_item = {
        "PK": f"COURSE#{course_id}",
        "SK": "METADATA",
        "course_id": course_id,
        "title": title,
        "course_overview": str(payload.get("course_overview") or ""),
        "description": str(payload.get("description") or ""),
        "level": str(payload.get("level") or ""),
        "duration_hours": max(Decimal("0"), _to_decimal_number(payload.get("duration_hours"), default="0")),
        "prerequisites": _to_str_list(payload.get("prerequisites")),
        "key_topics": _to_str_list(payload.get("key_topics")),
        "key_technologies": _to_str_list(payload.get("key_technologies")),
        "created_at": now,
        "updated_at": now,
    }

    table = _courses_table_or_error()
    table.put_item(Item=list_item)
    table.put_item(Item=meta_item)

    return {
        "status": "CREATED",
        "message": f"Course {course_id} created",
    }


def update_course(course_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    table = _courses_table_or_error()
    meta = _ensure_course_exists(course_id)
    list_item = table.get_item(Key=_course_list_key(course_id)).get("Item") or {}

    now = _now()
    updated_title = str(payload.get("title", meta.get("title", ""))).strip()

    table.put_item(
        Item={
            **meta,
            "title": updated_title,
            "course_overview": str(payload.get("course_overview", meta.get("course_overview", ""))),
            "description": str(payload.get("description", meta.get("description", ""))),
            "level": str(payload.get("level", meta.get("level", ""))),
            "duration_hours": max(
                Decimal("0"),
                _to_decimal_number(payload.get("duration_hours", meta.get("duration_hours", 0)), default="0"),
            ),
            "prerequisites": _to_str_list(payload.get("prerequisites", meta.get("prerequisites", []))),
            "key_topics": _to_str_list(payload.get("key_topics", meta.get("key_topics", []))),
            "key_technologies": _to_str_list(payload.get("key_technologies", meta.get("key_technologies", []))),
            "updated_at": now,
        }
    )

    table.put_item(
        Item={
            **list_item,
            "PK": "COURSE_LIST",
            "SK": f"COURSE#{course_id}",
            "course_id": course_id,
            "title": updated_title,
            "instructor_name": str(payload.get("instructor_name", list_item.get("instructor_name", ""))),
            "level": str(payload.get("level", list_item.get("level", meta.get("level", ""))),),
            "duration_hours": max(
                Decimal("0"),
                _to_decimal_number(payload.get("duration_hours", list_item.get("duration_hours", 0)), default="0"),
            ),
            "key_technologies": _to_str_list(payload.get("key_technologies", list_item.get("key_technologies", []))),
            "updated_at": now,
        }
    )

    return {
        "status": "UPDATED",
        "message": f"Course {course_id} updated",
    }


def delete_course(course_id: str) -> Dict[str, Any]:
    _ensure_course_exists(course_id)

    courses = _courses_table_or_error()
    enrollments = _enrollments_table_or_error()

    deleted_count = 0

    courses.delete_item(Key=_course_list_key(course_id))
    deleted_count += 1

    response = courses.query(KeyConditionExpression=Key("PK").eq(f"COURSE#{course_id}"))
    for item in response.get("Items", []):
        courses.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
        deleted_count += 1

    scan = enrollments.scan(FilterExpression=Attr("SK").eq(_enrollment_sk(course_id)))
    for item in scan.get("Items", []):
        enrollments.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
        deleted_count += 1

    return {
        "status": "DELETED",
        "message": f"Course {course_id} deleted with {deleted_count} related records",
    }


def create_module(course_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_course_exists(course_id)

    module_id = str(payload.get("module_id") or f"m_{uuid.uuid4().hex[:8]}")
    title = str(payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")

    now = _now()
    _courses_table_or_error().put_item(
        Item={
            "PK": f"COURSE#{course_id}",
            "SK": f"MODULE#{module_id}",
            "module_id": module_id,
            "title": title,
            "description": str(payload.get("description") or ""),
            "created_at": now,
            "updated_at": now,
        }
    )

    return {
        "status": "CREATED",
        "message": f"Module {module_id} created",
    }


def update_module(course_id: str, module_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_course_exists(course_id)

    table = _courses_table_or_error()
    current = table.get_item(Key=_module_key(course_id, module_id)).get("Item")
    if not current:
        raise HTTPException(status_code=404, detail="Module not found")

    table.put_item(
        Item={
            **current,
            "title": str(payload.get("title", current.get("title", ""))).strip(),
            "description": str(payload.get("description", current.get("description", ""))),
            "updated_at": _now(),
        }
    )

    return {
        "status": "UPDATED",
        "message": f"Module {module_id} updated",
    }


def delete_module(course_id: str, module_id: str) -> Dict[str, Any]:
    _ensure_course_exists(course_id)

    table = _courses_table_or_error()
    module = table.get_item(Key=_module_key(course_id, module_id)).get("Item")
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")

    deleted = 0
    table.delete_item(Key=_module_key(course_id, module_id))
    deleted += 1

    topics = _list_module_topics(course_id, module_id)
    for item in topics:
        table.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
        deleted += 1

    return {
        "status": "DELETED",
        "message": f"Module {module_id} deleted with {deleted} records",
    }


def create_topic(course_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_course_exists(course_id)

    module_id = str(payload.get("module_id") or "").strip()
    if not module_id:
        raise HTTPException(status_code=400, detail="module_id is required")

    module = _courses_table_or_error().get_item(Key=_module_key(course_id, module_id)).get("Item")
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")

    topic_id = str(payload.get("topic_id") or f"t_{uuid.uuid4().hex[:8]}")
    title = str(payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")

    now = _now()
    _courses_table_or_error().put_item(
        Item={
            "PK": f"COURSE#{course_id}",
            "SK": f"MODULE#{module_id}#TOPIC#{topic_id}",
            "course_id": course_id,
            "module_id": module_id,
            "topic_id": topic_id,
            "title": title,
            "description": str(payload.get("description") or ""),
            "duration_minutes": max(0, _to_int(payload.get("duration_minutes"), default=0)),
            "locked": bool(payload.get("locked", False)),
            "video_url": str(payload.get("video_url") or ""),
            "status": str(payload.get("status") or "NOT_STARTED"),
            "created_at": now,
            "updated_at": now,
        }
    )

    return {
        "status": "CREATED",
        "message": f"Topic {topic_id} created",
    }


def update_topic(course_id: str, module_id: str, topic_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_course_exists(course_id)

    table = _courses_table_or_error()
    current = table.get_item(Key=_topic_key(course_id, module_id, topic_id)).get("Item")
    if not current:
        raise HTTPException(status_code=404, detail="Topic not found")

    table.put_item(
        Item={
            **current,
            "title": str(payload.get("title", current.get("title", ""))).strip(),
            "description": str(payload.get("description", current.get("description", ""))),
            "duration_minutes": max(
                0,
                _to_int(payload.get("duration_minutes", current.get("duration_minutes", 0)), default=0),
            ),
            "locked": bool(payload.get("locked", current.get("locked", False))),
            "video_url": str(payload.get("video_url", current.get("video_url", ""))),
            "status": str(payload.get("status", current.get("status", "NOT_STARTED"))),
            "updated_at": _now(),
        }
    )

    return {
        "status": "UPDATED",
        "message": f"Topic {topic_id} updated",
    }


def delete_topic(course_id: str, module_id: str, topic_id: str) -> Dict[str, Any]:
    _ensure_course_exists(course_id)

    table = _courses_table_or_error()
    current = table.get_item(Key=_topic_key(course_id, module_id, topic_id)).get("Item")
    if not current:
        raise HTTPException(status_code=404, detail="Topic not found")

    video_key, _ = _resolve_topic_video_fields(current)
    if video_key:
        _topic_video_delete_object(video_key, allow_missing=True)

    materials = _list_topic_materials(course_id, module_id, topic_id)
    for material in materials:
        material_s3_key, _, _ = _resolve_material_fields(material)
        _material_delete_object(material_s3_key, allow_missing=True)
        table.delete_item(Key={"PK": material["PK"], "SK": material["SK"]})

    table.delete_item(Key=_topic_key(course_id, module_id, topic_id))

    return {
        "status": "DELETED",
        "message": f"Topic {topic_id} deleted",
    }


def get_topic_video_url(
    course_id: str,
    module_id: str,
    topic_id: str,
    user_id: str,
    expires_in_seconds: int = 900,
) -> Dict[str, Any]:
    _assert_user_can_open_course(user_id, course_id)

    topic = _courses_table_or_error().get_item(Key=_topic_key(course_id, module_id, topic_id)).get("Item")
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    video_key, video_url = _resolve_topic_video_fields(topic)
    if not video_key:
        raise HTTPException(status_code=404, detail="Topic video is not configured")

    ttl = max(60, min(3600, _to_int(expires_in_seconds, default=900)))
    signed_url = _topic_video_signed_url(video_key, expires_in_seconds=ttl)

    return {
        "course_id": course_id,
        "module_id": module_id,
        "topic_id": topic_id,
        "video_key": video_key,
        "video_url": signed_url or video_url,
        "expires_in_seconds": ttl,
    }


def get_topic_video_url_admin(
    course_id: str,
    module_id: str,
    topic_id: str,
    expires_in_seconds: int = 900,
) -> Dict[str, Any]:
    _ensure_course_exists(course_id)

    topic = _courses_table_or_error().get_item(Key=_topic_key(course_id, module_id, topic_id)).get("Item")
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    video_key, fallback_url = _resolve_topic_video_fields(topic)
    if not video_key:
        raise HTTPException(status_code=404, detail="Topic video is not configured")

    ttl = max(60, min(3600, _to_int(expires_in_seconds, default=900)))
    signed_url = _topic_video_signed_url(video_key, expires_in_seconds=ttl)

    return {
        "course_id": course_id,
        "module_id": module_id,
        "topic_id": topic_id,
        "video_key": video_key,
        "video_url": signed_url or fallback_url,
        "expires_in_seconds": ttl,
    }


def update_topic_video_url(course_id: str, module_id: str, topic_id: str, video_url: str) -> Dict[str, Any]:
    table = _courses_table_or_error()
    current = table.get_item(Key=_topic_key(course_id, module_id, topic_id)).get("Item")
    if not current:
        raise HTTPException(status_code=404, detail="Topic not found")

    raw_value = str(video_url or "").strip()
    updated_item = dict(current)
    updated_item.pop("video_url", None)

    if raw_value and "://" not in raw_value:
        updated_item["video_key"] = raw_value.lstrip("/")
    else:
        updated_item["video_key"] = ""
        updated_item["video_url"] = raw_value

    table.put_item(
        Item={**updated_item, "updated_at": _now()}
    )

    return {
        "status": "UPDATED",
        "message": "Topic video URL updated",
    }


def upload_topic_video_file(
    course_id: str,
    module_id: str,
    topic_id: str,
    file_bytes: bytes,
    filename: str,
    content_type: str,
    locked: bool,
    duration_minutes: int,
) -> Dict[str, Any]:
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Video file is required")

    table = _courses_table_or_error()
    current = table.get_item(Key=_topic_key(course_id, module_id, topic_id)).get("Item")
    if not current:
        raise HTTPException(status_code=404, detail="Topic not found")

    duration_minutes = max(0, _to_int(duration_minutes, default=0))

    bucket = _topic_video_bucket_or_error()
    safe_name = os.path.basename(filename or "video.mp4")
    key = (
        f"courses/{course_id}/modules/{module_id}/topics/{topic_id}/"
        f"video/{uuid.uuid4().hex}_{safe_name}"
    )

    s3_client = boto3.client("s3")
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=file_bytes,
        ContentType=content_type or "video/mp4",
    )
    video_url = _topic_video_url_from_key(key)

    updated_item = dict(current)
    updated_item.pop("video_url", None)

    table.put_item(
        Item={
            **updated_item,
            "video_key": key,
            "duration_minutes": duration_minutes,
            "locked": bool(locked),
            "updated_at": _now(),
        }
    )

    return {
        "course_id": course_id,
        "module_id": module_id,
        "topic_id": topic_id,
        "video_key": key,
        "video_url": video_url,
        "duration_minutes": duration_minutes,
        "locked": bool(locked),
    }


def list_topic_discussions(course_id: str, module_id: str, topic_id: str, user_id: str) -> Dict[str, Any]:
    _assert_user_can_open_course(user_id, course_id)

    table = _enrollments_table_or_error()
    response = table.query(
        KeyConditionExpression=(
            Key("PK").eq(_topic_discussion_pk(course_id, module_id, topic_id))
            & Key("SK").begins_with("DISCUSSION#")
        ),
        ScanIndexForward=True,
    )

    items = sorted(response.get("Items", []), key=lambda x: _to_int(x.get("created_at"), 0))
    discussions: List[Dict[str, Any]] = []
    for item in items:
        discussions.append(
            {
                "discussion_id": str(item.get("discussion_id") or ""),
                "user_id": str(item.get("user_id") or ""),
                "user_name": str(item.get("user_name") or ""),
                "author_role": str(item.get("author_role") or "USER"),
                "content": str(item.get("content") or ""),
                "created_at": _to_int(item.get("created_at"), 0),
                "updated_at": _to_int(item.get("updated_at"), 0),
            }
        )

    return {
        "course_id": course_id,
        "module_id": module_id,
        "topic_id": topic_id,
        "user_id": user_id,
        "discussions": discussions,
    }


def list_topic_discussions_public(course_id: str, module_id: str, topic_id: str) -> Dict[str, Any]:
    topic = _courses_table_or_error().get_item(Key=_topic_key(course_id, module_id, topic_id)).get("Item")
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    table = _enrollments_table_or_error()
    response = table.query(
        KeyConditionExpression=(
            Key("PK").eq(_topic_discussion_pk(course_id, module_id, topic_id))
            & Key("SK").begins_with("DISCUSSION#")
        ),
        ScanIndexForward=True,
    )

    items = sorted(response.get("Items", []), key=lambda x: _to_int(x.get("created_at"), 0))
    discussions: List[Dict[str, Any]] = []
    for item in items:
        discussions.append(
            {
                "discussion_id": str(item.get("discussion_id") or ""),
                "user_id": str(item.get("user_id") or ""),
                "user_name": str(item.get("user_name") or ""),
                "author_role": str(item.get("author_role") or "USER"),
                "content": str(item.get("content") or ""),
                "created_at": _to_int(item.get("created_at"), 0),
                "updated_at": _to_int(item.get("updated_at"), 0),
            }
        )

    return {
        "course_id": course_id,
        "module_id": module_id,
        "topic_id": topic_id,
        "discussions": discussions,
    }


def create_topic_discussion(course_id: str, module_id: str, topic_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    user_id = str(payload.get("user_id") or "").strip()
    content = str(payload.get("content") or "").strip()
    author_role = str(payload.get("author_role") or "USER").strip().upper()
    user_name = str(payload.get("user_name") or "")
    is_admin = bool(payload.get("is_admin", False))

    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    if not content:
        raise HTTPException(status_code=400, detail="content is required")
    if author_role not in {"USER", "INSTRUCTOR"}:
        raise HTTPException(status_code=400, detail="author_role must be USER or INSTRUCTOR")

    if author_role == "USER" and not is_admin:
        _assert_user_can_open_course(user_id, course_id)

    topic = _courses_table_or_error().get_item(Key=_topic_key(course_id, module_id, topic_id)).get("Item")
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    now = _now()
    discussion_id = f"d_{uuid.uuid4().hex[:10]}"
    _enrollments_table_or_error().put_item(
        Item={
            "PK": _topic_discussion_pk(course_id, module_id, topic_id),
            "SK": _discussion_sk(discussion_id),
            "course_id": course_id,
            "module_id": module_id,
            "topic_id": topic_id,
            "discussion_id": discussion_id,
            "user_id": user_id,
            "user_name": user_name,
            "author_role": author_role,
            "content": content,
            "created_at": now,
            "updated_at": now,
        }
    )

    return {
        "status": "CREATED",
        "message": f"Discussion {discussion_id} created",
    }


def update_topic_discussion(
    course_id: str,
    module_id: str,
    topic_id: str,
    discussion_id: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    user_id = str(payload.get("user_id") or "").strip()
    content = str(payload.get("content") or "").strip()
    is_admin = bool(payload.get("is_admin", False))
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    if not content:
        raise HTTPException(status_code=400, detail="content is required")

    table = _enrollments_table_or_error()
    key = {
        "PK": _topic_discussion_pk(course_id, module_id, topic_id),
        "SK": _discussion_sk(discussion_id),
    }
    current = table.get_item(Key=key).get("Item")
    if not current:
        raise HTTPException(status_code=404, detail="Discussion not found")

    author_role = str(current.get("author_role") or "USER").upper()
    discussion_owner_id = str(current.get("user_id") or "")

    if author_role != "USER":
        raise HTTPException(status_code=403, detail="Only USER discussions can be edited")
    if not is_admin and discussion_owner_id != user_id:
        raise HTTPException(status_code=403, detail="You can edit only your own discussion")

    table.put_item(
        Item={
            **current,
            "content": content,
            "updated_at": _now(),
        }
    )

    return {
        "status": "UPDATED",
        "message": f"Discussion {discussion_id} updated",
    }


def delete_topic_discussion(
    course_id: str,
    module_id: str,
    topic_id: str,
    discussion_id: str,
    user_id: str,
    is_admin: bool = False,
) -> Dict[str, Any]:
    user_id = str(user_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    table = _enrollments_table_or_error()
    key = {
        "PK": _topic_discussion_pk(course_id, module_id, topic_id),
        "SK": _discussion_sk(discussion_id),
    }
    current = table.get_item(Key=key).get("Item")
    if not current:
        raise HTTPException(status_code=404, detail="Discussion not found")

    author_role = str(current.get("author_role") or "USER").upper()
    discussion_owner_id = str(current.get("user_id") or "")

    if author_role != "USER":
        raise HTTPException(status_code=403, detail="Only USER discussions can be deleted")
    if not is_admin and discussion_owner_id != user_id:
        raise HTTPException(status_code=403, detail="You can delete only your own discussion")

    table.delete_item(Key=key)
    return {
        "status": "DELETED",
        "message": f"Discussion {discussion_id} deleted",
    }


def list_topic_notes(course_id: str, module_id: str, topic_id: str, user_id: str) -> Dict[str, Any]:
    _assert_user_can_open_course(user_id, course_id)

    table = _enrollments_table_or_error()
    response = table.query(
        KeyConditionExpression=(
            Key("PK").eq(_topic_user_notes_pk(user_id, course_id, module_id, topic_id))
            & Key("SK").begins_with("NOTE#")
        ),
        ScanIndexForward=True,
    )

    items = sorted(response.get("Items", []), key=lambda x: _to_int(x.get("created_at"), 0))
    notes: List[Dict[str, Any]] = []
    for item in items:
        notes.append(
            {
                "note_id": str(item.get("note_id") or ""),
                "user_id": str(item.get("user_id") or ""),
                "title": str(item.get("title") or ""),
                "content": str(item.get("content") or ""),
                "created_at": _to_int(item.get("created_at"), 0),
                "updated_at": _to_int(item.get("updated_at"), 0),
            }
        )

    return {
        "course_id": course_id,
        "module_id": module_id,
        "topic_id": topic_id,
        "user_id": user_id,
        "notes": notes,
    }


def create_topic_note(course_id: str, module_id: str, topic_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    user_id = str(payload.get("user_id") or "").strip()
    content = str(payload.get("content") or "").strip()
    title = str(payload.get("title") or "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    if not content:
        raise HTTPException(status_code=400, detail="content is required")

    _assert_user_can_open_course(user_id, course_id)
    topic = _courses_table_or_error().get_item(Key=_topic_key(course_id, module_id, topic_id)).get("Item")
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    now = _now()
    note_id = f"n_{uuid.uuid4().hex[:10]}"
    _enrollments_table_or_error().put_item(
        Item={
            "PK": _topic_user_notes_pk(user_id, course_id, module_id, topic_id),
            "SK": _note_sk(note_id),
            "course_id": course_id,
            "module_id": module_id,
            "topic_id": topic_id,
            "user_id": user_id,
            "note_id": note_id,
            "title": title,
            "content": content,
            "created_at": now,
            "updated_at": now,
        }
    )

    return {
        "status": "CREATED",
        "message": f"Note {note_id} created",
    }


def update_topic_note(
    course_id: str,
    module_id: str,
    topic_id: str,
    note_id: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    user_id = str(payload.get("user_id") or "").strip()
    content = str(payload.get("content") or "").strip()
    title = str(payload.get("title") or "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    if not content:
        raise HTTPException(status_code=400, detail="content is required")

    _assert_user_can_open_course(user_id, course_id)

    table = _enrollments_table_or_error()
    key = {
        "PK": _topic_user_notes_pk(user_id, course_id, module_id, topic_id),
        "SK": _note_sk(note_id),
    }
    current = table.get_item(Key=key).get("Item")
    if not current:
        raise HTTPException(status_code=404, detail="Note not found")

    table.put_item(
        Item={
            **current,
            "title": title,
            "content": content,
            "updated_at": _now(),
        }
    )

    return {
        "status": "UPDATED",
        "message": f"Note {note_id} updated",
    }


def delete_topic_note(course_id: str, module_id: str, topic_id: str, note_id: str, user_id: str) -> Dict[str, Any]:
    user_id = str(user_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    _assert_user_can_open_course(user_id, course_id)

    table = _enrollments_table_or_error()
    key = {
        "PK": _topic_user_notes_pk(user_id, course_id, module_id, topic_id),
        "SK": _note_sk(note_id),
    }
    current = table.get_item(Key=key).get("Item")
    if not current:
        raise HTTPException(status_code=404, detail="Note not found")

    table.delete_item(Key=key)
    return {
        "status": "DELETED",
        "message": f"Note {note_id} deleted",
    }


def list_topic_materials(course_id: str, module_id: str, topic_id: str, user_id: str) -> Dict[str, Any]:
    _assert_user_can_open_course(user_id, course_id)

    topic = _courses_table_or_error().get_item(Key=_topic_key(course_id, module_id, topic_id)).get("Item")
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    items = _list_topic_materials(course_id, module_id, topic_id)
    materials: List[Dict[str, Any]] = []
    for item in items:
        s3_key, resolved_url, file_type = _resolve_material_fields(item)
        materials.append(
            {
                "material_id": str(item.get("material_id") or ""),
                "file_name": str(item.get("file_name") or ""),
                "file_type": file_type,
                "s3_key": s3_key,
                "file_url": resolved_url,
                "uploaded_by": str(item.get("uploaded_by") or ""),
                "created_at": _to_int(item.get("created_at"), 0),
                "updated_at": _to_int(item.get("updated_at"), 0),
            }
        )

    return {
        "course_id": course_id,
        "module_id": module_id,
        "topic_id": topic_id,
        "user_id": user_id,
        "materials": materials,
    }


def list_topic_materials_admin(course_id: str, module_id: str, topic_id: str) -> Dict[str, Any]:
    _ensure_course_exists(course_id)

    topic = _courses_table_or_error().get_item(Key=_topic_key(course_id, module_id, topic_id)).get("Item")
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    items = _list_topic_materials(course_id, module_id, topic_id)
    materials: List[Dict[str, Any]] = []
    for item in items:
        s3_key, resolved_url, file_type = _resolve_material_fields(item)
        materials.append(
            {
                "material_id": str(item.get("material_id") or ""),
                "file_name": str(item.get("file_name") or ""),
                "file_type": file_type,
                "s3_key": s3_key,
                "file_url": resolved_url,
                "uploaded_by": str(item.get("uploaded_by") or ""),
                "created_at": _to_int(item.get("created_at"), 0),
                "updated_at": _to_int(item.get("updated_at"), 0),
            }
        )

    return {
        "course_id": course_id,
        "module_id": module_id,
        "topic_id": topic_id,
        "materials": materials,
    }


def create_topic_material(course_id: str, module_id: str, topic_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    file_name = str(payload.get("file_name") or "").strip()
    s3_key = str(payload.get("s3_key") or payload.get("file_url") or "").strip()
    uploaded_by = str(payload.get("uploaded_by") or "")
    file_type = str(payload.get("file_type") or "").strip()
    if not file_name or not s3_key:
        raise HTTPException(status_code=400, detail="file_name and s3_key are required")

    if not file_type:
        file_type = os.path.splitext(file_name)[1].replace(".", "").lower()

    topic = _courses_table_or_error().get_item(Key=_topic_key(course_id, module_id, topic_id)).get("Item")
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    material_id = f"mat_{uuid.uuid4().hex[:10]}"
    now = _now()
    _courses_table_or_error().put_item(
        Item={
            **_material_key(course_id, module_id, topic_id, material_id),
            "course_id": course_id,
            "module_id": module_id,
            "topic_id": topic_id,
            "material_id": material_id,
            "file_name": file_name,
            "file_type": file_type,
            "s3_key": s3_key,
            "file_url": _material_url_from_key(s3_key),
            "uploaded_by": uploaded_by,
            "created_at": now,
            "updated_at": now,
        }
    )

    return {
        "status": "CREATED",
        "message": f"Material {material_id} created",
    }


def update_topic_material(
    course_id: str,
    module_id: str,
    topic_id: str,
    material_id: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    table = _courses_table_or_error()
    key = _material_key(course_id, module_id, topic_id, material_id)
    current = table.get_item(Key=key).get("Item")
    if not current:
        raise HTTPException(status_code=404, detail="Material not found")

    current_s3_key, _, _ = _resolve_material_fields(current)
    file_name = str(payload.get("file_name", current.get("file_name", ""))).strip()
    s3_key = str(payload.get("s3_key", payload.get("file_url", current_s3_key))).strip()
    file_type = str(payload.get("file_type", current.get("file_type", ""))).strip()
    if not file_name or not s3_key:
        raise HTTPException(status_code=400, detail="file_name and s3_key are required")

    if not file_type:
        file_type = os.path.splitext(file_name)[1].replace(".", "").lower()

    _material_move_object(current_s3_key, s3_key)

    table.put_item(
        Item={
            **current,
            "file_name": file_name,
            "file_type": file_type,
            "s3_key": s3_key,
            "file_url": _material_url_from_key(s3_key),
            "uploaded_by": str(payload.get("uploaded_by", current.get("uploaded_by", ""))),
            "updated_at": _now(),
        }
    )

    return {
        "status": "UPDATED",
        "message": f"Material {material_id} updated",
    }


def delete_topic_material(course_id: str, module_id: str, topic_id: str, material_id: str) -> Dict[str, Any]:
    table = _courses_table_or_error()
    key = _material_key(course_id, module_id, topic_id, material_id)
    current = table.get_item(Key=key).get("Item")
    if not current:
        raise HTTPException(status_code=404, detail="Material not found")

    current_s3_key, _, _ = _resolve_material_fields(current)
    _material_delete_object(current_s3_key)
    table.delete_item(Key=key)
    return {
        "status": "DELETED",
        "message": f"Material {material_id} deleted",
    }


def upload_topic_material_file(
    course_id: str,
    module_id: str,
    topic_id: str,
    file_bytes: bytes,
    filename: str,
    content_type: str,
    material_id: str | None,
    uploaded_by: str,
) -> Dict[str, Any]:
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Material file is required")

    topic = _courses_table_or_error().get_item(Key=_topic_key(course_id, module_id, topic_id)).get("Item")
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    safe_name = os.path.basename(filename or "material.bin")
    resolved_material_id = str(material_id or f"mat_{uuid.uuid4().hex[:10]}").strip()
    if not resolved_material_id:
        raise HTTPException(status_code=400, detail="material_id is invalid")

    s3_key = (
        f"courses/{course_id}/modules/{module_id}/topics/{topic_id}/"
        f"materials/{uuid.uuid4().hex}_{safe_name}"
    )
    bucket = _materials_bucket_or_error()

    s3_client = boto3.client("s3")
    s3_client.put_object(
        Bucket=bucket,
        Key=s3_key,
        Body=file_bytes,
        ContentType=content_type or "application/octet-stream",
    )

    file_type = os.path.splitext(safe_name)[1].replace(".", "").lower()
    now = _now()
    _courses_table_or_error().put_item(
        Item={
            **_material_key(course_id, module_id, topic_id, resolved_material_id),
            "course_id": course_id,
            "module_id": module_id,
            "topic_id": topic_id,
            "material_id": resolved_material_id,
            "file_name": safe_name,
            "file_type": file_type,
            "s3_key": s3_key,
            "file_url": _material_url_from_key(s3_key),
            "uploaded_by": str(uploaded_by or ""),
            "created_at": now,
            "updated_at": now,
        }
    )

    return {
        "course_id": course_id,
        "module_id": module_id,
        "topic_id": topic_id,
        "material_id": resolved_material_id,
        "file_name": safe_name,
        "file_type": file_type,
        "s3_key": s3_key,
        "file_url": _material_url_from_key(s3_key),
        "uploaded_by": str(uploaded_by or ""),
    }


def get_topic_material_download_url(
    course_id: str,
    module_id: str,
    topic_id: str,
    material_id: str,
    user_id: str,
    expires_in_seconds: int = 900,
) -> Dict[str, Any]:
    _assert_user_can_open_course(user_id, course_id)

    item = _courses_table_or_error().get_item(Key=_material_key(course_id, module_id, topic_id, material_id)).get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Material not found")

    s3_key, _, file_type = _resolve_material_fields(item)
    if not s3_key:
        raise HTTPException(status_code=404, detail="Material S3 key is not configured")

    ttl = max(60, min(3600, _to_int(expires_in_seconds, default=900)))
    return {
        "course_id": course_id,
        "module_id": module_id,
        "topic_id": topic_id,
        "material_id": material_id,
        "file_name": str(item.get("file_name") or ""),
        "file_type": file_type,
        "s3_key": s3_key,
        "file_url": _material_signed_url(s3_key, expires_in_seconds=ttl),
        "expires_in_seconds": ttl,
    }


def get_topic_material_download_url_admin(
    course_id: str,
    module_id: str,
    topic_id: str,
    material_id: str,
    expires_in_seconds: int = 900,
) -> Dict[str, Any]:
    _ensure_course_exists(course_id)

    item = _courses_table_or_error().get_item(Key=_material_key(course_id, module_id, topic_id, material_id)).get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Material not found")

    s3_key, _, file_type = _resolve_material_fields(item)
    if not s3_key:
        raise HTTPException(status_code=404, detail="Material S3 key is not configured")

    ttl = max(60, min(3600, _to_int(expires_in_seconds, default=900)))
    return {
        "course_id": course_id,
        "module_id": module_id,
        "topic_id": topic_id,
        "material_id": material_id,
        "file_name": str(item.get("file_name") or ""),
        "file_type": file_type,
        "s3_key": s3_key,
        "file_url": _material_signed_url(s3_key, expires_in_seconds=ttl),
        "expires_in_seconds": ttl,
    }


def get_topic_material_download_stream(
    course_id: str,
    module_id: str,
    topic_id: str,
    material_id: str,
    user_id: str,
) -> Dict[str, Any]:
    _assert_user_can_open_course(user_id, course_id)

    item = _courses_table_or_error().get_item(Key=_material_key(course_id, module_id, topic_id, material_id)).get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Material not found")

    s3_key, _, _ = _resolve_material_fields(item)
    if not s3_key:
        raise HTTPException(status_code=404, detail="Material S3 key is not configured")

    file_name = str(item.get("file_name") or os.path.basename(s3_key) or f"{material_id}.bin")
    item_file_type = str(item.get("file_type") or "").strip().lower()
    bucket = _materials_bucket_or_error()
    s3_client = boto3.client("s3")
    try:
        response = s3_client.get_object(Bucket=bucket, Key=s3_key)
    except ClientError as exc:
        if _is_missing_s3_error(exc):
            raise HTTPException(status_code=404, detail="Material file not found in S3") from exc
        raise HTTPException(status_code=500, detail="Failed to download material from S3") from exc

    raw_content_type = str(response.get("ContentType") or "").strip().lower()
    guessed_content_type, _ = mimetypes.guess_type(file_name)
    content_type = raw_content_type or "application/octet-stream"
    if content_type == "application/octet-stream":
        if guessed_content_type:
            content_type = guessed_content_type
        elif item_file_type == "pdf":
            content_type = "application/pdf"

    return {
        "file_name": file_name,
        "content_type": content_type,
        "body": response["Body"],
    }


def get_topic_material_download_stream_admin(
    course_id: str,
    module_id: str,
    topic_id: str,
    material_id: str,
) -> Dict[str, Any]:
    _ensure_course_exists(course_id)

    item = _courses_table_or_error().get_item(Key=_material_key(course_id, module_id, topic_id, material_id)).get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Material not found")

    s3_key, _, _ = _resolve_material_fields(item)
    if not s3_key:
        raise HTTPException(status_code=404, detail="Material S3 key is not configured")

    file_name = str(item.get("file_name") or os.path.basename(s3_key) or f"{material_id}.bin")
    item_file_type = str(item.get("file_type") or "").strip().lower()
    bucket = _materials_bucket_or_error()
    s3_client = boto3.client("s3")
    try:
        response = s3_client.get_object(Bucket=bucket, Key=s3_key)
    except ClientError as exc:
        if _is_missing_s3_error(exc):
            raise HTTPException(status_code=404, detail="Material file not found in S3") from exc
        raise HTTPException(status_code=500, detail="Failed to download material from S3") from exc

    raw_content_type = str(response.get("ContentType") or "").strip().lower()
    guessed_content_type, _ = mimetypes.guess_type(file_name)
    content_type = raw_content_type or "application/octet-stream"
    if content_type == "application/octet-stream":
        if guessed_content_type:
            content_type = guessed_content_type
        elif item_file_type == "pdf":
            content_type = "application/pdf"

    return {
        "file_name": file_name,
        "content_type": content_type,
        "body": response["Body"],
    }
