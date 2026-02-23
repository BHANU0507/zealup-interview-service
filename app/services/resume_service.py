import uuid
import time
from app.dynamo import table1
from boto3.dynamodb.conditions import Key
from fastapi import HTTPException


def create_resume_draft(user_id: str, resume_name: str, tenant_id: str, role: str = None,
    email_or_phone: str = None):

    if not resume_name.strip():
        raise ValueError("Resume name cannot be empty")

    resume_id = f"res_{uuid.uuid4()}"
    now = int(time.time())

    item = {
        "PK": f"USER#{user_id}",
        "SK": f"RESUME#{resume_id}",

        "resume_id": resume_id,
        "resume_name": resume_name,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "emailOrPhone": email_or_phone,

        "status": "DRAFT",
        "stage": "INITIALIZED",

        "ats_score": None,
        "job_description": None,

        "created_at": now,
        "updated_at": now
    }

    table1.put_item(Item=item)

    return {
        "resume_id": resume_id,
        "resume_name": resume_name,
        "status": "DRAFT",
        "created_at": now
    }



def get_user_resumes(user_id: str):

    response = table1.query(
        KeyConditionExpression=Key("PK").eq(f"USER#{user_id}")
    )

    items = response.get("Items", [])

    resumes = [
        {
            "resume_id": item.get("resume_id"),
            "resume_name": item.get("resume_name"),
            "status": item.get("status"),
            "created_at": item.get("created_at")
        }
        for item in items
        if item.get("SK", "").startswith("RESUME#")
    ]

    resumes = sorted(resumes, key=lambda x: x["created_at"], reverse=True)

    return {
        "user_id": user_id,
        "resumes": resumes
    }




def save_resume_data(user_id: str, resume_id: str, resume_payload: dict):

    now = int(time.time())

    table1.update_item(
        Key={
            "PK": f"USER#{user_id}",
            "SK": f"RESUME#{resume_id}"
        },
        UpdateExpression="""
            SET resume_data = :data,
                #st = :status,
                updated_at = :updated
        """,
        ExpressionAttributeNames={
            "#st": "status"
        },
        ExpressionAttributeValues={
            ":data": resume_payload,
            ":status": "COMPLETED",
            ":updated": now
        }
    )

    return {
        "resume_id": resume_id,
        "status": "COMPLETED",
        "updated_at": now
    }



def fetch_resume(user_id: str, resume_id: str):

    response = table1.get_item(
        Key={
            "PK": f"USER#{user_id}",
            "SK": f"RESUME#{resume_id}"
        }
    )

    item = response.get("Item")

    if not item:
        raise HTTPException(status_code=404, detail="Resume not found")

    return {
        "resume_id": resume_id,
        "status": item.get("status"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "resume_data": item.get("resume_data")
    }
