from fastapi import APIRouter, Query, UploadFile, File, Form
from fastapi.responses import StreamingResponse
import mimetypes
import os
from urllib.parse import quote

from app.course_schemas import (
    ApiStatusResponse,
    AdminCourseListResponse,
    AdminCourseModulesResponse,
    AdminCourseEnrollmentsResponse,
    AdminEnrollUserRequest,
    AdminTopicDetailResponse,
    AdminModuleTopicsResponse,
    CourseDetailResponse,
    CourseListResponse,
    CourseModulesResponse,
    CourseUpsertRequest,
    EnrolledCourseItem,
    EnrollmentRequest,
    ModuleTopicsResponse,
    ModuleUpsertRequest,
    TopicProgressRequest,
    TopicVideoRequest,
    TopicVideoResponse,
    TopicVideoUploadResponse,
    TopicUpsertRequest,
    DiscussionCreateRequest,
    DiscussionListResponse,
    PublicDiscussionListResponse,
    DiscussionUpdateRequest,
    NoteCreateRequest,
    NoteListResponse,
    NoteUpdateRequest,
    MaterialListResponse,
    AdminMaterialListResponse,
    MaterialUploadResponse,
    MaterialDownloadUrlResponse,
    MaterialUpsertRequest,
    UserEnrollmentsResponse,
    UserEnrollmentsCountResponse,
    UserEnrollmentsDetailResponse,
    SimpleEnrolledCoursesResponse,
)
from app.services.course_service import (
    admin_enroll_user,
    admin_get_course_enrollments,
    admin_unenroll_user,
    create_course,
    create_module,
    create_topic,
    delete_course,
    delete_module,
    delete_topic,
    enroll_course,
    get_topic_video_url,
    get_topic_video_url_admin,
    get_course_detail_admin,
    get_course_detail,
    get_user_enrollments,
    get_user_enrollments_count,
    get_user_enrollments_detail,
    get_user_enrolled_courses_simple,
    get_topic_detail_admin,
    list_course_modules_admin,
    list_course_modules,
    list_all_courses_admin,
    list_courses,
    list_topic_discussions,
    list_topic_discussions_public,
    list_topic_materials,
    list_topic_materials_admin,
    list_topic_notes,
    list_module_topics_admin,
    list_module_topics,
    create_topic_discussion,
    create_topic_note,
    create_topic_material,
    upload_topic_material_file,
    upload_topic_video_file,
    update_topic_video_url,
    update_topic_discussion,
    update_topic_note,
    update_topic_material,
    delete_topic_discussion,
    delete_topic_note,
    delete_topic_material,
    get_topic_material_download_url,
    get_topic_material_download_url_admin,
    get_topic_material_download_stream,
    get_topic_material_download_stream_admin,
    update_course,
    mark_topic_completed,
    update_module,
    update_topic,
    update_topic_progress,
)


router = APIRouter()


# @router.get("/", response_model=CourseListResponse)
# def list_courses_endpoint(
#     user_id: str | None = Query(None),
#     limit: int = Query(20, ge=1, le=100),
# ):
#     return list_courses(limit=limit, user_id=user_id)


@router.get("/catalog", response_model=CourseListResponse)
def get_course_catalog_endpoint(limit: int = Query(100, ge=1, le=500)):
    return list_courses(limit=limit, user_id=None)


@router.get("/admin/all", response_model=AdminCourseListResponse)
def get_all_courses_admin_endpoint(limit: int = Query(200, ge=1, le=1000)):
    return list_all_courses_admin(limit=limit)


@router.get("/admin/{course_id}", response_model=CourseDetailResponse)
def get_course_detail_admin_endpoint(course_id: str):
    return get_course_detail_admin(course_id)


@router.get("/admin/{course_id}/modules", response_model=AdminCourseModulesResponse)
def list_course_modules_admin_endpoint(course_id: str):
    return list_course_modules_admin(course_id)


@router.get("/admin/{course_id}/modules/{module_id}/topics", response_model=AdminModuleTopicsResponse)
def list_module_topics_admin_endpoint(course_id: str, module_id: str):
    return list_module_topics_admin(course_id, module_id)


@router.get(
    "/admin/{course_id}/modules/{module_id}/topics/{topic_id}/video",
    response_model=TopicVideoResponse,
)
def get_topic_video_admin_endpoint(
    course_id: str,
    module_id: str,
    topic_id: str,
    expires_in: int = Query(900, ge=60, le=3600),
):
    return get_topic_video_url_admin(
        course_id=course_id,
        module_id=module_id,
        topic_id=topic_id,
        expires_in_seconds=expires_in,
    )


@router.get("/admin/topics/{topic_id}", response_model=AdminTopicDetailResponse)
def get_topic_detail_admin_endpoint(topic_id: str):
    return get_topic_detail_admin(topic_id)


@router.get("/admin/{course_id}/enrollments", response_model=AdminCourseEnrollmentsResponse)
def admin_get_course_enrollments_endpoint(course_id: str):
    """Admin: list all users enrolled in a course."""
    return admin_get_course_enrollments(course_id)


@router.post("/admin/{course_id}/enrollments", response_model=ApiStatusResponse)
def admin_enroll_user_endpoint(course_id: str, payload: AdminEnrollUserRequest):
    """Admin: enroll a user into a course (no subscription check)."""
    return admin_enroll_user(course_id, payload.user_id)


@router.delete("/admin/{course_id}/enrollments/{user_id}", response_model=ApiStatusResponse)
def admin_unenroll_user_endpoint(course_id: str, user_id: str):
    """Admin: remove a user from a course."""
    return admin_unenroll_user(course_id, user_id)


@router.get("/user-enrollments/{user_id}", response_model=UserEnrollmentsResponse)
def get_user_enrollments_endpoint(user_id: str):
    return get_user_enrollments(user_id)


@router.get("/user-enrollments/{user_id}/count", response_model=UserEnrollmentsCountResponse)
def get_user_enrollments_count_endpoint(user_id: str):
    return get_user_enrollments_count(user_id)


@router.get("/user-enrollments/{user_id}/details", response_model=UserEnrollmentsDetailResponse)
def get_user_enrollments_detail_endpoint(user_id: str):
    return get_user_enrollments_detail(user_id)


@router.get("/user-enrollments/{user_id}/simple", response_model=SimpleEnrolledCoursesResponse)
def get_user_enrolled_courses_simple_endpoint(user_id: str):
    """Return just course_id and course_name for every course the user is enrolled in."""
    return get_user_enrolled_courses_simple(user_id)


@router.post("/enroll", response_model=ApiStatusResponse)
def enroll_course_endpoint(payload: EnrollmentRequest):
    return enroll_course(payload.model_dump())


@router.get("/{course_id}", response_model=CourseDetailResponse)
def get_course_detail_endpoint(course_id: str, user_id: str = Query(...)):
    return get_course_detail(course_id, user_id)


@router.get("/{course_id}/modules", response_model=CourseModulesResponse)
def list_course_modules_endpoint(course_id: str, user_id: str = Query(...)):
    return list_course_modules(course_id, user_id)


@router.get("/{course_id}/modules/{module_id}/topics", response_model=ModuleTopicsResponse)
def list_module_topics_endpoint(course_id: str, module_id: str, user_id: str = Query(...)):
    return list_module_topics(course_id, module_id, user_id)


@router.put("/{course_id}/modules/{module_id}/topics/{topic_id}/progress", response_model=ApiStatusResponse)
def update_topic_progress_endpoint(
    course_id: str,
    module_id: str,
    topic_id: str,
    payload: TopicProgressRequest,
):
    return update_topic_progress(
        course_id=course_id,
        module_id=module_id,
        topic_id=topic_id,
        user_id=payload.user_id,
        status=payload.status,
    )


@router.put("/{course_id}/modules/{module_id}/topics/{topic_id}/complete", response_model=ApiStatusResponse)
def mark_topic_completed_endpoint(
    course_id: str,
    module_id: str,
    topic_id: str,
    user_id: str = Query(...),
):
    return mark_topic_completed(course_id, module_id, topic_id, user_id)


@router.get(
    "/{course_id}/modules/{module_id}/topics/{topic_id}/video",
    response_model=TopicVideoResponse,
)
def get_topic_video_endpoint(
    course_id: str,
    module_id: str,
    topic_id: str,
    user_id: str = Query(...),
    expires_in: int = Query(900, ge=60, le=3600),
):
    return get_topic_video_url(course_id, module_id, topic_id, user_id, expires_in_seconds=expires_in)


@router.put(
    "/{course_id}/modules/{module_id}/topics/{topic_id}/video",
    response_model=ApiStatusResponse,
)
def update_topic_video_endpoint(
    course_id: str,
    module_id: str,
    topic_id: str,
    payload: TopicVideoRequest,
):
    return update_topic_video_url(course_id, module_id, topic_id, payload.video_url)


@router.post(
    "/{course_id}/modules/{module_id}/topics/{topic_id}/video-upload",
    response_model=TopicVideoUploadResponse,
)
async def upload_topic_video_endpoint(
    course_id: str,
    module_id: str,
    topic_id: str,
    video: UploadFile = File(...),
    locked: bool = Form(False),
    duration_minutes: int = Form(0),
):
    file_bytes = await video.read()
    return upload_topic_video_file(
        course_id=course_id,
        module_id=module_id,
        topic_id=topic_id,
        file_bytes=file_bytes,
        filename=video.filename or "video.mp4",
        content_type=video.content_type or "video/mp4",
        locked=locked,
        duration_minutes=duration_minutes,
    )


@router.get(
    "/{course_id}/modules/{module_id}/topics/{topic_id}/discussions",
    response_model=DiscussionListResponse,
)
def list_topic_discussions_endpoint(course_id: str, module_id: str, topic_id: str, user_id: str = Query(...)):
    return list_topic_discussions(course_id, module_id, topic_id, user_id)


@router.get(
    "/{course_id}/modules/{module_id}/topics/{topic_id}/discussions/public",
    response_model=PublicDiscussionListResponse,
)
def list_topic_discussions_public_endpoint(course_id: str, module_id: str, topic_id: str):
    return list_topic_discussions_public(course_id, module_id, topic_id)


@router.post(
    "/{course_id}/modules/{module_id}/topics/{topic_id}/discussions",
    response_model=ApiStatusResponse,
)
def create_topic_discussion_endpoint(
    course_id: str,
    module_id: str,
    topic_id: str,
    payload: DiscussionCreateRequest,
):
    return create_topic_discussion(course_id, module_id, topic_id, payload.model_dump())


@router.post(
    "/admin/{course_id}/modules/{module_id}/topics/{topic_id}/discussions",
    response_model=ApiStatusResponse,
)
def create_topic_discussion_admin_endpoint(
    course_id: str,
    module_id: str,
    topic_id: str,
    payload: DiscussionCreateRequest,
):
    admin_payload = payload.model_dump()
    admin_payload["is_admin"] = True
    return create_topic_discussion(course_id, module_id, topic_id, admin_payload)


@router.put(
    "/{course_id}/modules/{module_id}/topics/{topic_id}/discussions/{discussion_id}",
    response_model=ApiStatusResponse,
)
def update_topic_discussion_endpoint(
    course_id: str,
    module_id: str,
    topic_id: str,
    discussion_id: str,
    payload: DiscussionUpdateRequest,
):
    return update_topic_discussion(
        course_id,
        module_id,
        topic_id,
        discussion_id,
        payload.model_dump(),
    )


@router.delete(
    "/{course_id}/modules/{module_id}/topics/{topic_id}/discussions/{discussion_id}",
    response_model=ApiStatusResponse,
)
def delete_topic_discussion_endpoint(
    course_id: str,
    module_id: str,
    topic_id: str,
    discussion_id: str,
    user_id: str = Query(...),
    is_admin: bool = Query(False),
):
    return delete_topic_discussion(course_id, module_id, topic_id, discussion_id, user_id, is_admin=is_admin)


@router.put(
    "/admin/{course_id}/modules/{module_id}/topics/{topic_id}/discussions/{discussion_id}",
    response_model=ApiStatusResponse,
)
def update_topic_discussion_admin_endpoint(
    course_id: str,
    module_id: str,
    topic_id: str,
    discussion_id: str,
    payload: DiscussionUpdateRequest,
):
    admin_payload = payload.model_dump()
    admin_payload["is_admin"] = True
    return update_topic_discussion(
        course_id,
        module_id,
        topic_id,
        discussion_id,
        admin_payload,
    )


@router.delete(
    "/admin/{course_id}/modules/{module_id}/topics/{topic_id}/discussions/{discussion_id}",
    response_model=ApiStatusResponse,
)
def delete_topic_discussion_admin_endpoint(
    course_id: str,
    module_id: str,
    topic_id: str,
    discussion_id: str,
    user_id: str = Query(...),
):
    return delete_topic_discussion(course_id, module_id, topic_id, discussion_id, user_id, is_admin=True)


@router.get(
    "/{course_id}/modules/{module_id}/topics/{topic_id}/notes",
    response_model=NoteListResponse,
)
def list_topic_notes_endpoint(course_id: str, module_id: str, topic_id: str, user_id: str = Query(...)):
    return list_topic_notes(course_id, module_id, topic_id, user_id)


@router.post(
    "/{course_id}/modules/{module_id}/topics/{topic_id}/notes",
    response_model=ApiStatusResponse,
)
def create_topic_note_endpoint(
    course_id: str,
    module_id: str,
    topic_id: str,
    payload: NoteCreateRequest,
):
    return create_topic_note(course_id, module_id, topic_id, payload.model_dump())


@router.put(
    "/{course_id}/modules/{module_id}/topics/{topic_id}/notes/{note_id}",
    response_model=ApiStatusResponse,
)
def update_topic_note_endpoint(
    course_id: str,
    module_id: str,
    topic_id: str,
    note_id: str,
    payload: NoteUpdateRequest,
):
    return update_topic_note(
        course_id,
        module_id,
        topic_id,
        note_id,
        payload.model_dump(),
    )


@router.delete(
    "/{course_id}/modules/{module_id}/topics/{topic_id}/notes/{note_id}",
    response_model=ApiStatusResponse,
)
def delete_topic_note_endpoint(
    course_id: str,
    module_id: str,
    topic_id: str,
    note_id: str,
    user_id: str = Query(...),
):
    return delete_topic_note(course_id, module_id, topic_id, note_id, user_id)


@router.get(
    "/{course_id}/modules/{module_id}/topics/{topic_id}/materials",
    response_model=MaterialListResponse,
)
def list_topic_materials_endpoint(course_id: str, module_id: str, topic_id: str, user_id: str = Query(...)):
    return list_topic_materials(course_id, module_id, topic_id, user_id)


@router.get(
    "/admin/{course_id}/modules/{module_id}/topics/{topic_id}/materials",
    response_model=AdminMaterialListResponse,
)
def list_topic_materials_admin_endpoint(course_id: str, module_id: str, topic_id: str):
    return list_topic_materials_admin(course_id, module_id, topic_id)


@router.post(
    "/admin/{course_id}/modules/{module_id}/topics/{topic_id}/materials/upload",
    response_model=MaterialUploadResponse,
)
async def upload_topic_material_admin_endpoint(
    course_id: str,
    module_id: str,
    topic_id: str,
    file: UploadFile = File(...),
    material_id: str | None = Form(None),
    uploaded_by: str = Form(""),
):
    file_bytes = await file.read()
    return upload_topic_material_file(
        course_id=course_id,
        module_id=module_id,
        topic_id=topic_id,
        file_bytes=file_bytes,
        filename=file.filename or "material.bin",
        content_type=file.content_type or "application/octet-stream",
        material_id=material_id,
        uploaded_by=uploaded_by,
    )


@router.post(
    "/{course_id}/modules/{module_id}/topics/{topic_id}/materials",
    response_model=ApiStatusResponse,
)
def create_topic_material_endpoint(
    course_id: str,
    module_id: str,
    topic_id: str,
    payload: MaterialUpsertRequest,
):
    return create_topic_material(course_id, module_id, topic_id, payload.model_dump())


@router.put(
    "/{course_id}/modules/{module_id}/topics/{topic_id}/materials/{material_id}",
    response_model=ApiStatusResponse,
)
def update_topic_material_endpoint(
    course_id: str,
    module_id: str,
    topic_id: str,
    material_id: str,
    payload: MaterialUpsertRequest,
):
    return update_topic_material(
        course_id,
        module_id,
        topic_id,
        material_id,
        payload.model_dump(),
    )


@router.delete(
    "/{course_id}/modules/{module_id}/topics/{topic_id}/materials/{material_id}",
    response_model=ApiStatusResponse,
)
def delete_topic_material_endpoint(course_id: str, module_id: str, topic_id: str, material_id: str):
    return delete_topic_material(course_id, module_id, topic_id, material_id)


@router.get(
    "/{course_id}/modules/{module_id}/topics/{topic_id}/materials/{material_id}/download",
    response_model=MaterialDownloadUrlResponse,
)
def get_topic_material_download_url_endpoint(
    course_id: str,
    module_id: str,
    topic_id: str,
    material_id: str,
    user_id: str = Query(...),
    expires_in: int = Query(900, ge=60, le=3600),
):
    return get_topic_material_download_url(
        course_id=course_id,
        module_id=module_id,
        topic_id=topic_id,
        material_id=material_id,
        user_id=user_id,
        expires_in_seconds=expires_in,
    )


@router.get("/{course_id}/modules/{module_id}/topics/{topic_id}/materials/{material_id}/download-direct")
def download_topic_material_direct_endpoint(
    course_id: str,
    module_id: str,
    topic_id: str,
    material_id: str,
    user_id: str = Query(...),
):
    stream_data = get_topic_material_download_stream(
        course_id=course_id,
        module_id=module_id,
        topic_id=topic_id,
        material_id=material_id,
        user_id=user_id,
    )
    file_name = str(stream_data["file_name"] or "download")
    content_type = str(stream_data["content_type"] or "application/octet-stream")
    guessed_ext = os.path.splitext(file_name)[1]
    if not guessed_ext:
        derived_ext = mimetypes.guess_extension(content_type) or ""
        if content_type == "application/pdf":
            derived_ext = ".pdf"
        if derived_ext:
            file_name = f"{file_name}{derived_ext}"
    encoded_name = quote(file_name)
    return StreamingResponse(
        stream_data["body"].iter_chunks(chunk_size=1024 * 1024),
        media_type=content_type,
        headers={
            "Content-Disposition": f"attachment; filename=\"{file_name}\"; filename*=UTF-8''{encoded_name}",
        },
    )


@router.get(
    "/admin/{course_id}/modules/{module_id}/topics/{topic_id}/materials/{material_id}/download",
    response_model=MaterialDownloadUrlResponse,
)
def get_topic_material_download_url_admin_endpoint(
    course_id: str,
    module_id: str,
    topic_id: str,
    material_id: str,
    expires_in: int = Query(900, ge=60, le=3600),
):
    return get_topic_material_download_url_admin(
        course_id=course_id,
        module_id=module_id,
        topic_id=topic_id,
        material_id=material_id,
        expires_in_seconds=expires_in,
    )


@router.get("/admin/{course_id}/modules/{module_id}/topics/{topic_id}/materials/{material_id}/download-direct")
def download_topic_material_direct_admin_endpoint(
    course_id: str,
    module_id: str,
    topic_id: str,
    material_id: str,
):
    stream_data = get_topic_material_download_stream_admin(
        course_id=course_id,
        module_id=module_id,
        topic_id=topic_id,
        material_id=material_id,
    )
    file_name = str(stream_data["file_name"] or "download")
    content_type = str(stream_data["content_type"] or "application/octet-stream")
    guessed_ext = os.path.splitext(file_name)[1]
    if not guessed_ext:
        derived_ext = mimetypes.guess_extension(content_type) or ""
        if content_type == "application/pdf":
            derived_ext = ".pdf"
        if derived_ext:
            file_name = f"{file_name}{derived_ext}"
    encoded_name = quote(file_name)
    return StreamingResponse(
        stream_data["body"].iter_chunks(chunk_size=1024 * 1024),
        media_type=content_type,
        headers={
            "Content-Disposition": f"attachment; filename=\"{file_name}\"; filename*=UTF-8''{encoded_name}",
        },
    )


@router.post("/", response_model=ApiStatusResponse)
def create_course_endpoint(payload: CourseUpsertRequest):
    return create_course(payload.model_dump())


@router.put("/{course_id}", response_model=ApiStatusResponse)
def update_course_endpoint(course_id: str, payload: CourseUpsertRequest):
    return update_course(course_id, payload.model_dump(exclude_none=True))


@router.delete("/{course_id}", response_model=ApiStatusResponse)
def delete_course_endpoint(course_id: str):
    return delete_course(course_id)


@router.post("/{course_id}/modules", response_model=ApiStatusResponse)
def create_module_endpoint(course_id: str, payload: ModuleUpsertRequest):
    return create_module(course_id, payload.model_dump(exclude_none=True))


@router.put("/{course_id}/modules/{module_id}", response_model=ApiStatusResponse)
def update_module_endpoint(course_id: str, module_id: str, payload: ModuleUpsertRequest):
    return update_module(course_id, module_id, payload.model_dump(exclude_none=True))


@router.delete("/{course_id}/modules/{module_id}", response_model=ApiStatusResponse)
def delete_module_endpoint(course_id: str, module_id: str):
    return delete_module(course_id, module_id)


@router.post("/{course_id}/modules/{module_id}/topics", response_model=ApiStatusResponse)
def create_topic_endpoint(course_id: str, module_id: str, payload: TopicUpsertRequest):
    topic_payload = payload.model_dump(exclude_none=True)
    topic_payload["module_id"] = module_id
    return create_topic(course_id, topic_payload)


@router.put("/{course_id}/modules/{module_id}/topics/{topic_id}", response_model=ApiStatusResponse)
def update_topic_endpoint(course_id: str, module_id: str, topic_id: str, payload: TopicUpsertRequest):
    topic_payload = payload.model_dump(exclude_none=True)
    topic_payload["module_id"] = module_id
    return update_topic(course_id, module_id, topic_id, topic_payload)


@router.delete("/{course_id}/modules/{module_id}/topics/{topic_id}", response_model=ApiStatusResponse)
def delete_topic_endpoint(course_id: str, module_id: str, topic_id: str):
    return delete_topic(course_id, module_id, topic_id)
