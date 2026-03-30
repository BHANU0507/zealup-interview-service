from fastapi import APIRouter, Header
from pydantic import BaseModel

from app.services.college_cleanup_service import purge_college_users

router = APIRouter()


class CollegeCleanupRequest(BaseModel):
    collegeId: str
    collegeName: str
    reason: str


@router.post("/purge-users", summary="Purge all users of a college from courses and interviews")
async def purge_college_users_endpoint(
    request: CollegeCleanupRequest,
    authorization: str = Header(..., description="Bearer token, e.g. 'Bearer eyJ...'"),
):
    """
    Remove all students of the given college from:
    - Every course they are enrolled in
    - All their interview session data and quota records

    Steps:
    1. Calls the user-service `GET /api/v1/colleges/{collegeId}/students/user-ids`
       using the supplied Authorization header to fetch the list of user IDs.
    2. Deletes every course enrollment for each user.
    3. Deletes every interview session and quota record for each user.
    """
    return await purge_college_users(
        college_id=request.collegeId,
        college_name=request.collegeName,
        reason=request.reason,
        auth_token=authorization,
    )
