"""
College Leaderboard Service

Flow:
1. Query MySQL zealup_db.users → fetch all COLLEGE_STUDENT rows for the given college_id
   (id, name, student_id, branch, year_of_study, email)
2. For each user, query DynamoDB TABLE8 (cusub#{user_id} / CASSIGNMENT#...)
   to get all their college assignment submissions and compute avg score %.
3. Rank students by avg score % descending.
4. Return ranked list with: rank, name, student_id, branch, score_percentage.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dynamo import college_assignments_table, table as interviews_table, table1 as resumes_table
from boto3.dynamodb.conditions import Key


# ---------------------------------------------------------------------------
# Helpers
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


def _get_user_avg_score_pct(user_id: str) -> float:
    """
    Query DynamoDB for all finalised college assignment submissions by this user
    and return their average score percentage (0-100). Returns 0 if none submitted.
    """
    if college_assignments_table is None:
        return 0.0
    try:
        resp = college_assignments_table.query(
            KeyConditionExpression=(
                Key("PK").eq(f"cusub#{user_id}")
                & Key("SK").begins_with("CASSIGNMENT#")
            ),
            ProjectionExpression="score, total_points, #st",
            ExpressionAttributeNames={"#st": "status"},
        )
        items = resp.get("Items", [])
    except Exception:
        return 0.0

    percentages: List[float] = []
    for item in items:
        if str(item.get("status", "")).lower() != "submitted":
            continue
        score = _to_float(item.get("score", 0))
        total = _to_float(item.get("total_points", 0))
        if total > 0:
            percentages.append(round(score / total * 100, 2))

    return round(sum(percentages) / len(percentages), 2) if percentages else 0.0


def _get_user_submission_stats(user_id: str) -> Dict[str, Any]:
    """
    Single DynamoDB query that returns both avg score % and submitted count
    for a user's college assignments.
    """
    if college_assignments_table is None:
        return {"avg_score_pct": 0.0, "submitted_count": 0}
    try:
        resp = college_assignments_table.query(
            KeyConditionExpression=(
                Key("PK").eq(f"cusub#{user_id}")
                & Key("SK").begins_with("CASSIGNMENT#")
            ),
            ProjectionExpression="score, total_points, #st",
            ExpressionAttributeNames={"#st": "status"},
        )
        items = resp.get("Items", [])
    except Exception:
        return {"avg_score_pct": 0.0, "submitted_count": 0}

    percentages: List[float] = []
    submitted_count = 0
    for item in items:
        if str(item.get("status", "")).lower() != "submitted":
            continue
        submitted_count += 1
        score = _to_float(item.get("score", 0))
        total = _to_float(item.get("total_points", 0))
        if total > 0:
            percentages.append(round(score / total * 100, 2))

    avg_score_pct = (
        round(sum(percentages) / len(percentages), 2) if percentages else 0.0
    )
    return {"avg_score_pct": avg_score_pct, "submitted_count": submitted_count}


def _get_total_college_assignments(college_id: str) -> int:
    """Count total assignments published for the college (published = present in list index)."""
    if college_assignments_table is None:
        return 0
    try:
        resp = college_assignments_table.query(
            KeyConditionExpression=(
                Key("PK").eq(f"COLLEGE_ASSIGN_LIST#{college_id}")
                & Key("SK").begins_with("CASSIGNMENT#")
            ),
            Select="COUNT",
        )
        return int(resp.get("Count", 0))
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_college_leaderboard(college_id: str, db: Session, branch_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Return ranked list of college students ordered by their avg assignment
    score percentage (DynamoDB) descending.

    Student profile data (name, student_id, branch, …) comes from MySQL.
    """
    # 1. Fetch all college students from MySQL
    branch_clause = "AND branch_id = :branch_id" if branch_id else ""
    params: Dict[str, Any] = {"college_id": college_id}
    if branch_id:
        params["branch_id"] = branch_id
    try:
        rows = db.execute(
            text(
                f"""
                SELECT id, name, student_id, branch, year_of_study, email
                FROM   users
                WHERE  college_id  = :college_id
                  AND  user_type   = 'COLLEGE_STUDENT'
                  AND  account_status = 'ACTIVE'
                  {branch_clause}
                ORDER BY name
                """
            ),
            params,
        ).fetchall()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch students from database: {exc}",
        )

    if not rows:
        return {
            "college_id": college_id,
            "branch_filter": branch_id,
            "total_students": 0,
            "leaderboard": [],
        }

    # 2. Compute DynamoDB score for each student
    students: List[Dict[str, Any]] = []
    for row in rows:
        user_id    = str(row.id)
        avg_pct    = _get_user_avg_score_pct(user_id)
        students.append(
            {
                "user_id":       user_id,
                "name":          str(row.name or ""),
                "student_id":    str(row.student_id or ""),
                "branch":        str(row.branch or ""),
                "year_of_study": int(row.year_of_study) if row.year_of_study else None,
                "email":         str(row.email or ""),
                "score_pct":     avg_pct,
            }
        )

    # 3. Sort by score descending, then name ascending for ties
    students.sort(key=lambda x: (-x["score_pct"], x["name"].lower()))

    # 4. Assign ranks (shared rank on equal score)
    leaderboard: List[Dict[str, Any]] = []
    rank = 1
    for i, s in enumerate(students):
        if i > 0 and s["score_pct"] < students[i - 1]["score_pct"]:
            rank = i + 1
        leaderboard.append(
            {
                "rank":          rank,
                "name":          s["name"],
                "student_id":    s["student_id"],
                "branch":        s["branch"],
                "year_of_study": s["year_of_study"],
                "email":         s["email"],
                "score_pct":     s["score_pct"],
                "score_display": f"{s['score_pct']}%",
            }
        )

    return {
        "college_id":     college_id,
        "branch_filter":  branch_id,
        "total_students": len(leaderboard),
        "leaderboard":    leaderboard,
    }


def get_college_department_stats(college_id: str, db: Session, branch_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Return department-wise analytics for a college:
    - student_count    : number of active students in that branch
    - avg_score_pct    : average assignment score % across students in the branch
    - avg_attendance_pct: avg of per-student attendance %
                          (attendance % = assignments_submitted / total_assignments * 100)
    """
    # 1. MySQL: fetch all active COLLEGE_STUDENT rows for this college
    branch_clause = "AND branch_id = :branch_id" if branch_id else ""
    params: Dict[str, Any] = {"college_id": college_id}
    if branch_id:
        params["branch_id"] = branch_id
    try:
        rows = db.execute(
            text(
                f"""
                SELECT id, branch
                FROM   users
                WHERE  college_id    = :college_id
                  AND  user_type     = 'COLLEGE_STUDENT'
                  AND  account_status = 'ACTIVE'
                  {branch_clause}
                """
            ),
            params,
        ).fetchall()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch students from database: {exc}",
        )

    if not rows:
        return {
            "college_id":    college_id,
            "branch_filter": branch_id,
            "departments":   [],
        }

    # 2. DynamoDB: total assignments published for this college
    total_assignments = _get_total_college_assignments(college_id)

    # 3. Per-student stats + group by branch
    branch_buckets: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        user_id = str(row.id)
        branch  = str(row.branch or "Unknown").strip() or "Unknown"

        stats = _get_user_submission_stats(user_id)
        avg_score_pct = stats["avg_score_pct"]
        submitted_count = stats["submitted_count"]

        # Attendance for this student
        if total_assignments > 0:
            attendance_pct = round(submitted_count / total_assignments * 100, 2)
        else:
            attendance_pct = 0.0

        if branch not in branch_buckets:
            branch_buckets[branch] = {
                "student_count": 0,
                "_score_sum":    0.0,
                "_attend_sum":   0.0,
            }
        bucket = branch_buckets[branch]
        bucket["student_count"] += 1
        bucket["_score_sum"]    += avg_score_pct
        bucket["_attend_sum"]   += attendance_pct

    # 4. Aggregate per branch
    departments = []
    for branch, bucket in sorted(branch_buckets.items()):
        count = bucket["student_count"]
        departments.append(
            {
                "branch":             branch,
                "student_count":      count,
                "avg_score_pct":      round(bucket["_score_sum"] / count, 2),
                "avg_attendance_pct": round(bucket["_attend_sum"] / count, 2),
            }
        )

    return {
        "college_id":        college_id,
        "branch_filter":     branch_id,
        "total_assignments": total_assignments,
        "departments":       departments,
    }


def get_college_activity_stats(college_id: str, db: Session, branch_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Return aggregate interview and resume counts for all active COLLEGE_STUDENT
    users belonging to the given college.

    - total_interviews : sum of interview sessions taken by all college students
    - total_resumes    : sum of resumes created by all college students
    """
    # 1. Fetch all active college student IDs from MySQL
    branch_clause = "AND branch_id = :branch_id" if branch_id else ""
    params: Dict[str, Any] = {"college_id": college_id}
    if branch_id:
        params["branch_id"] = branch_id
    try:
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
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch students from database: {exc}",
        )

    user_ids = [str(row.id) for row in rows]

    if not user_ids:
        return {
            "college_id":       college_id,
            "branch_filter":    branch_id,
            "total_students":   0,
            "total_interviews": 0,
            "total_resumes":    0,
        }

    total_interviews = 0
    total_resumes = 0

    for user_id in user_ids:
        # -- Interviews: query GSI user-session-index, count METADATA items --
        try:
            if interviews_table is not None:
                last_key = None
                while True:
                    q: Dict[str, Any] = {
                        "IndexName": "user-session-index",
                        "KeyConditionExpression": Key("user_id").eq(user_id),
                        "FilterExpression": "SK = :sk",
                        "ExpressionAttributeValues": {":sk": "METADATA"},
                        "Select": "COUNT",
                    }
                    if last_key:
                        q["ExclusiveStartKey"] = last_key
                    resp = interviews_table.query(**q)
                    total_interviews += int(resp.get("Count", 0))
                    last_key = resp.get("LastEvaluatedKey")
                    if not last_key:
                        break
        except Exception:
            pass

        # -- Resumes: query PK=USER#{user_id}, SK begins_with RESUME# --
        try:
            if resumes_table is not None:
                last_key = None
                while True:
                    q = {
                        "KeyConditionExpression": (
                            Key("PK").eq(f"USER#{user_id}")
                            & Key("SK").begins_with("RESUME#")
                        ),
                        "Select": "COUNT",
                    }
                    if last_key:
                        q["ExclusiveStartKey"] = last_key
                    resp = resumes_table.query(**q)
                    total_resumes += int(resp.get("Count", 0))
                    last_key = resp.get("LastEvaluatedKey")
                    if not last_key:
                        break
        except Exception:
            pass

    return {
        "college_id":       college_id,
        "branch_filter":    branch_id,
        "total_students":   len(user_ids),
        "total_interviews": total_interviews,
        "total_resumes":    total_resumes,
    }


def get_college_overview(college_id: str, db: Session, branch_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Single-call college overview returning:
      - total_students       : active COLLEGE_STUDENT count
      - active_departments   : number of distinct branches with ≥ 1 student
      - overall_avg_score_pct: college-wide average assignment score %
      - overall_attendance_pct: college-wide average attendance %
                                (per-student: submitted / total_assignments * 100)
    """
    # 1. MySQL: fetch all active students with their branch
    branch_clause = "AND branch_id = :branch_id" if branch_id else ""
    params: Dict[str, Any] = {"college_id": college_id}
    if branch_id:
        params["branch_id"] = branch_id
    try:
        rows = db.execute(
            text(
                f"""
                SELECT id, branch
                FROM   users
                WHERE  college_id    = :college_id
                  AND  user_type     = 'COLLEGE_STUDENT'
                  AND  account_status = 'ACTIVE'
                  {branch_clause}
                """
            ),
            params,
        ).fetchall()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch students from database: {exc}",
        )

    total_students = len(rows)
    if total_students == 0:
        return {
            "college_id":             college_id,
            "branch_filter":          branch_id,
            "total_students":         0,
            "active_departments":     0,
            "overall_avg_score_pct":  0.0,
            "overall_attendance_pct": 0.0,
        }

    # 2. Total assignments for this college (DynamoDB)
    total_assignments = _get_total_college_assignments(college_id)

    # 3. Per-student stats in one pass
    branches: set = set()
    score_sum    = 0.0
    attend_sum   = 0.0

    for row in rows:
        user_id = str(row.id)
        branch  = str(row.branch or "Unknown").strip() or "Unknown"
        branches.add(branch)

        stats           = _get_user_submission_stats(user_id)
        score_sum      += stats["avg_score_pct"]
        submitted_count = stats["submitted_count"]
        attendance_pct  = (
            round(submitted_count / total_assignments * 100, 2)
            if total_assignments > 0 else 0.0
        )
        attend_sum += attendance_pct

    return {
        "college_id":             college_id,
        "branch_filter":          branch_id,
        "total_students":         total_students,
        "active_departments":     len(branches),
        "overall_avg_score_pct":  round(score_sum / total_students, 2),
        "overall_attendance_pct": round(attend_sum / total_students, 2),
    }


# ---------------------------------------------------------------------------
# Shared helper — fetch all students with stats (used by insight APIs)
# ---------------------------------------------------------------------------

def _fetch_college_students_with_stats(
    college_id: str,
    branch_id: Optional[str],
    db: Session,
) -> tuple:
    """
    Returns (students_list, total_assignments) where each student dict has:
      user_id, name, student_id, branch, avg_score_pct,
      submitted_count, absent_count, attendance_pct
    Optionally filtered to a single branch.
    """
    branch_clause = "AND branch_id = :branch_id" if branch_id else ""
    params: Dict[str, Any] = {"college_id": college_id}
    if branch_id:
        params["branch_id"] = branch_id
    try:
        rows = db.execute(
            text(
                f"""
                SELECT id, name, student_id, branch
                FROM   users
                WHERE  college_id    = :college_id
                  AND  user_type     = 'COLLEGE_STUDENT'
                  AND  account_status = 'ACTIVE'
                  {branch_clause}
                ORDER BY name
                """
            ),
            params,
        ).fetchall()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch students from database: {exc}",
        )

    total_assignments = _get_total_college_assignments(college_id)

    students = []
    for row in rows:
        user_id = str(row.id)
        stats   = _get_user_submission_stats(user_id)
        submitted_count = stats["submitted_count"]
        absent_count    = max(0, total_assignments - submitted_count)
        attendance_pct  = (
            round(submitted_count / total_assignments * 100, 2)
            if total_assignments > 0 else 0.0
        )
        students.append(
            {
                "user_id":        user_id,
                "name":           str(row.name or ""),
                "student_id":     str(row.student_id or ""),
                "branch":         str(row.branch or ""),
                "avg_score_pct":  stats["avg_score_pct"],
                "submitted_count": submitted_count,
                "absent_count":   absent_count,
                "attendance_pct": attendance_pct,
            }
        )
    return students, total_assignments


# ---------------------------------------------------------------------------
# Insight API 1  —  Low Engagement / Absentees
# ---------------------------------------------------------------------------

def get_low_engagement_students(
    college_id: str,
    branch_id: Optional[str],
    attendance_threshold: float,
    db: Session,
) -> Dict[str, Any]:
    """
    Students whose attendance % is below `attendance_threshold`.
    Sorted by attendance_pct ascending (worst first).
    """
    students, total_assignments = _fetch_college_students_with_stats(
        college_id, branch_id, db
    )

    low = [s for s in students if s["attendance_pct"] < attendance_threshold]
    low.sort(key=lambda x: x["attendance_pct"])

    result = []
    for s in low:
        result.append(
            {
                "user_id":           s["user_id"],
                "name":              s["name"],
                "student_id":        s["student_id"],
                "branch":            s["branch"],
                "attendance_pct":    s["attendance_pct"],
                "absent_count":      s["absent_count"],
                "submitted_count":   s["submitted_count"],
                "attendance_metric": (
                    f"{s['absent_count']} assignment(s) absent (approx)"
                    if total_assignments > 0
                    else "No assignments yet"
                ),
            }
        )

    return {
        "college_id":           college_id,
        "branch_filter":        branch_id,
        "attendance_threshold": attendance_threshold,
        "total_assignments":    total_assignments,
        "count":                len(result),
        "students":             result,
    }


# ---------------------------------------------------------------------------
# Insight API 2  —  Academic Support Needed
# ---------------------------------------------------------------------------

def get_academic_support_students(
    college_id: str,
    branch_id: Optional[str],
    score_threshold: float,
    db: Session,
) -> Dict[str, Any]:
    """
    Students whose avg assignment score % is below `score_threshold`.
    Sorted by avg_score_pct ascending (worst first).
    """
    students, total_assignments = _fetch_college_students_with_stats(
        college_id, branch_id, db
    )

    struggling = [
        s for s in students
        if s["avg_score_pct"] < score_threshold
    ]
    struggling.sort(key=lambda x: x["avg_score_pct"])

    result = []
    for s in struggling:
        result.append(
            {
                "user_id":            s["user_id"],
                "name":               s["name"],
                "student_id":         s["student_id"],
                "branch":             s["branch"],
                "avg_score_pct":      s["avg_score_pct"],
                "performance_metric": f"Avg. Score: {s['avg_score_pct']}%",
            }
        )

    return {
        "college_id":      college_id,
        "branch_filter":   branch_id,
        "score_threshold": score_threshold,
        "count":           len(result),
        "students":        result,
    }


# ---------------------------------------------------------------------------
# Insight API 3  —  Top Performers
# ---------------------------------------------------------------------------

def get_top_performers(
    college_id: str,
    branch_id: Optional[str],
    score_threshold: float,
    db: Session,
) -> Dict[str, Any]:
    """
    Students whose avg assignment score % is >= `score_threshold`.
    Sorted by avg_score_pct descending (best first).
    """
    students, _ = _fetch_college_students_with_stats(college_id, branch_id, db)

    top = [s for s in students if s["avg_score_pct"] >= score_threshold]
    top.sort(key=lambda x: -x["avg_score_pct"])

    result = []
    for s in top:
        result.append(
            {
                "user_id":            s["user_id"],
                "name":               s["name"],
                "student_id":         s["student_id"],
                "branch":             s["branch"],
                "avg_score_pct":      s["avg_score_pct"],
                "performance_metric": f"Avg. Score: {s['avg_score_pct']}%",
            }
        )

    return {
        "college_id":      college_id,
        "branch_filter":   branch_id,
        "score_threshold": score_threshold,
        "count":           len(result),
        "students":        result,
    }


# ---------------------------------------------------------------------------
# Student search (by name or student_id, partial match)
# ---------------------------------------------------------------------------

def search_college_students(
    college_id: str,
    query: str,
    branch_id: Optional[str],
    db: Session,
) -> Dict[str, Any]:
    """
    Partial-match search across name and student_id for a college.
    Optionally filtered to a single branch.

    Returns: user_id, name, student_id, email, branch, year_of_study
    """
    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")

    like_term = f"%{query.strip()}%"
    params: Dict[str, Any] = {
        "college_id": college_id,
        "q":          like_term,
    }

    branch_clause = ""
    if branch_id:
        branch_clause = "AND branch_id = :branch_id"
        params["branch_id"] = branch_id

    try:
        rows = db.execute(
            text(
                f"""
                SELECT id, name, student_id, email, branch, year_of_study
                FROM   users
                WHERE  college_id     = :college_id
                  AND  user_type      = 'COLLEGE_STUDENT'
                  AND  account_status = 'ACTIVE'
                  AND  (name LIKE :q OR student_id LIKE :q)
                  {branch_clause}
                ORDER BY name
                LIMIT  50
                """
            ),
            params,
        ).fetchall()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Search query failed: {exc}",
        )

    results = [
        {
            "user_id":       str(row.id),
            "name":          str(row.name or ""),
            "student_id":    str(row.student_id or ""),
            "email":         str(row.email or ""),
            "branch":        str(row.branch or ""),
            "year_of_study": int(row.year_of_study) if row.year_of_study else None,
        }
        for row in rows
    ]

    return {
        "college_id":    college_id,
        "branch_filter": branch_id,
        "query":         query.strip(),
        "count":         len(results),
        "students":      results,
    }
