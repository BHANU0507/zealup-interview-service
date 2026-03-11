from fastapi import APIRouter, File, Query, UploadFile

from app.challenge_schemas import (
    CreateChallengeRequest,
    CreateChallengeResponse,
    UpdateChallengeRequest,
    UpdateChallengeResponse,
    BulkDeleteRequest,
    BulkDeleteResponse,
    ChallengeDetailResponse,
    ChallengeListResponse,
    ChallengeSubmitRequest,
    ChallengeSubmitResponse,
    SubmissionDetailResponse,
    RunTestsRequest,
    RunTestsResponse,
    ScoreboardResponse,
    UserSubmissionListResponse,
)
from app.services.challenge_service import (
    bulk_create_challenges_from_csv,
    bulk_delete_challenges,
    create_challenge,
    delete_challenge,
    get_challenge,
    get_languages,
    get_scoreboard,
    get_submission_detail,
    list_challenges,
    list_user_submissions,
    run_visible_tests,
    submit_challenge,
    update_challenge,
)


router = APIRouter()


@router.post("/", response_model=CreateChallengeResponse)
def create_challenge_endpoint(request: CreateChallengeRequest):
    return create_challenge(request.dict())


@router.get("/", response_model=ChallengeListResponse)
def list_challenges_endpoint(
    challenge_type: str | None = None,
    difficulty: str | None = None,
    tag: str | None = None,
    keyword: str | None = None,
    created_by: str | None = None,
    user_id: str | None = Query(None, alias="userId"),
    page_size: int = Query(10, ge=1, le=100),
    start_key: str | None = None,
):
    return list_challenges(
        challenge_type=challenge_type,
        difficulty=difficulty,
        tag=tag,
        keyword=keyword,
        created_by=created_by,
        user_id=user_id,
        page_size=page_size,
        start_key=start_key,
    )


@router.get("/languages")
def list_languages_endpoint():
    return get_languages()


@router.get("/{challenge_id}", response_model=ChallengeDetailResponse)
def get_challenge_endpoint(challenge_id: str, user_id: str | None = Query(None, alias="userId")):
    return get_challenge(challenge_id, user_id=user_id)


@router.put("/{challenge_id}", response_model=UpdateChallengeResponse)
def update_challenge_endpoint(challenge_id: str, request: UpdateChallengeRequest):
    return update_challenge(challenge_id, request.dict(exclude_unset=True))


@router.delete("/{challenge_id}")
def delete_challenge_endpoint(challenge_id: str):
    return delete_challenge(challenge_id)


@router.post("/bulk-delete", response_model=BulkDeleteResponse)
def bulk_delete_challenges_endpoint(request: BulkDeleteRequest):
    return bulk_delete_challenges(request.challenge_ids)


@router.post("/{challenge_id}/submit", response_model=ChallengeSubmitResponse)
def submit_challenge_endpoint(challenge_id: str, request: ChallengeSubmitRequest):
    return submit_challenge(challenge_id, request.dict())


@router.post("/{challenge_id}/run", response_model=RunTestsResponse)
def run_code_endpoint(challenge_id: str, request: RunTestsRequest):
    return run_visible_tests(challenge_id, request.language_id, request.source_code)


@router.post("/{challenge_id}/run-tests", response_model=RunTestsResponse)
def run_tests_endpoint(challenge_id: str, request: RunTestsRequest):
    return run_visible_tests(challenge_id, request.language_id, request.source_code)


@router.get("/{challenge_id}/scoreboard", response_model=ScoreboardResponse)
def scoreboard_endpoint(challenge_id: str):
    return get_scoreboard(challenge_id)


@router.get("/users/{user_id}/submissions", response_model=UserSubmissionListResponse)
def user_submissions_endpoint(
    user_id: str,
    challenge_id: str | None = None,
    page_size: int = Query(10, ge=1, le=100),
    start_key: str | None = None,
):
    return list_user_submissions(
        user_id=user_id,
        challenge_id=challenge_id,
        page_size=page_size,
        start_key=start_key,
    )


@router.get("/submissions/{submission_id}", response_model=SubmissionDetailResponse)
def get_submission_endpoint(submission_id: str):
    return get_submission_detail(submission_id)


@router.post("/upload")
async def upload_challenges(file: UploadFile = File(...)):
    content = (await file.read()).decode("utf-8-sig")
    return bulk_create_challenges_from_csv(content)
