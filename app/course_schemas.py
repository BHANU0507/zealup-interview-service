from typing import List, Optional

from pydantic import BaseModel, Field


class CourseCardItem(BaseModel):
    course_id: str
    title: str
    instructor_name: str
    progress_percentage: int = Field(0, ge=0, le=100)
    level: str
    duration_hours: float = Field(0, ge=0)
    key_technologies: List[str] = []
    action: str


class CourseListResponse(BaseModel):
    user_id: Optional[str] = None
    plan_name: Optional[str] = None
    course_limit: Optional[int] = Field(None, ge=0)
    enrolled_count: Optional[int] = Field(None, ge=0)
    courses: List[CourseCardItem]


class AdminCourseItem(BaseModel):
    course_id: str
    title: str
    instructor_name: str = ""
    course_overview: str = ""
    description: str = ""
    level: str = ""
    duration_hours: float = Field(0, ge=0)
    key_technologies: List[str] = []
    created_at: int = Field(0, ge=0)
    updated_at: int = Field(0, ge=0)


class AdminCourseListResponse(BaseModel):
    total_courses: int = Field(0, ge=0)
    limit: int = Field(0, ge=1)
    courses: List[AdminCourseItem]


class CourseDetailResponse(BaseModel):
    course_id: str
    title: str
    instructor_name: str = ""
    course_overview: str = ""
    description: str
    level: str
    duration_hours: float = Field(0, ge=0)
    prerequisites: List[str] = []
    key_topics: List[str] = []
    key_technologies: List[str] = []


class ModuleSummaryItem(BaseModel):
    module_id: str
    title: str
    total_topics: int = Field(0, ge=0)
    completed_topics: int = Field(0, ge=0)
    completion_percentage: int = Field(0, ge=0, le=100)


class CourseModulesResponse(BaseModel):
    course_id: str
    user_id: str
    modules: List[ModuleSummaryItem]


class AdminCourseModulesResponse(BaseModel):
    course_id: str
    modules: List[ModuleSummaryItem]


class ModuleTopicItem(BaseModel):
    topic_id: str
    title: str
    description: str
    duration_minutes: int = Field(0, ge=0)
    locked: bool = False
    video_key: str = ""
    video_url: str = ""
    status: str


class ModuleTopicsResponse(BaseModel):
    course_id: str
    module_id: str
    user_id: str
    topics: List[ModuleTopicItem]


class AdminModuleTopicsResponse(BaseModel):
    course_id: str
    module_id: str
    topics: List[ModuleTopicItem]


class AdminTopicDetailResponse(BaseModel):
    course_id: str
    module_id: str
    topic_id: str
    title: str
    description: str = ""
    duration_minutes: int = Field(0, ge=0)
    locked: bool = False
    video_key: str = ""
    video_url: str = ""
    status: str = "NOT_STARTED"


class EnrollmentRequest(BaseModel):
    user_id: str
    course_id: str
    planType: Optional[str] = None
    status: Optional[str] = None
    coursesLimit: int = Field(..., ge=0)


class CourseUpsertRequest(BaseModel):
    course_id: Optional[str] = None
    title: str
    instructor_name: str = ""
    course_overview: str = ""
    description: str = ""
    level: str = ""
    duration_hours: float = Field(0, ge=0)
    prerequisites: List[str] = []
    key_topics: List[str] = []
    key_technologies: List[str] = []


class ModuleUpsertRequest(BaseModel):
    module_id: Optional[str] = None
    title: str
    description: str = ""


class TopicUpsertRequest(BaseModel):
    topic_id: Optional[str] = None
    title: str
    description: str = ""


class TopicProgressRequest(BaseModel):
    user_id: str
    status: str


class ApiStatusResponse(BaseModel):
    status: str
    message: Optional[str] = None


class EnrolledCourseItem(BaseModel):
    course_id: str
    title: str
    progress_percentage: int = Field(0, ge=0, le=100)
    status: str = "IN_PROGRESS"


class UserEnrollmentsResponse(BaseModel):
    user_id: str
    enrolled_count: int = Field(0, ge=0)
    enrolled_courses: List[EnrolledCourseItem]


class UserEnrollmentsCountResponse(BaseModel):
    user_id: str
    enrolled_count: int = Field(0, ge=0)
    course_ids: List[str]


class EnrolledCourseDetailItem(BaseModel):
    course_id: str
    title: str
    instructor_name: str = ""
    description: str = ""
    level: str = ""
    duration_hours: float = Field(0, ge=0)
    progress_percentage: int = Field(0, ge=0, le=100)
    key_technologies: List[str] = []
    status: str = "IN_PROGRESS"


class UserEnrollmentsDetailResponse(BaseModel):
    user_id: str
    enrolled_count: int = Field(0, ge=0)
    enrolled_courses: List[EnrolledCourseDetailItem]


class SimpleEnrolledCourseItem(BaseModel):
    course_id: str
    course_name: str


class SimpleEnrolledCoursesResponse(BaseModel):
    user_id: str
    total_count: int = Field(0, ge=0)
    courses: List[SimpleEnrolledCourseItem]


class TopicVideoRequest(BaseModel):
    video_url: str


class TopicVideoResponse(BaseModel):
    course_id: str
    module_id: str
    topic_id: str
    video_key: str = ""
    video_url: str
    expires_in_seconds: int = Field(0, ge=0)


class TopicVideoUploadResponse(BaseModel):
    course_id: str
    module_id: str
    topic_id: str
    video_key: str = ""
    video_url: str
    duration_minutes: int = Field(0, ge=0)
    locked: bool = False


class DiscussionCreateRequest(BaseModel):
    user_id: str
    content: str
    user_name: Optional[str] = None
    author_role: str = "USER"


class DiscussionUpdateRequest(BaseModel):
    user_id: str
    content: str
    is_admin: bool = False


class DiscussionItem(BaseModel):
    discussion_id: str
    user_id: str
    user_name: str = ""
    author_role: str = "USER"
    content: str
    created_at: int
    updated_at: int


class DiscussionListResponse(BaseModel):
    course_id: str
    module_id: str
    topic_id: str
    user_id: str
    discussions: List[DiscussionItem]


class PublicDiscussionListResponse(BaseModel):
    course_id: str
    module_id: str
    topic_id: str
    discussions: List[DiscussionItem]


class NoteCreateRequest(BaseModel):
    user_id: str
    title: str = ""
    content: str


class NoteUpdateRequest(BaseModel):
    user_id: str
    title: str = ""
    content: str


class NoteItem(BaseModel):
    note_id: str
    user_id: str
    title: str = ""
    content: str
    created_at: int
    updated_at: int


class NoteListResponse(BaseModel):
    course_id: str
    module_id: str
    topic_id: str
    user_id: str
    notes: List[NoteItem]


class MaterialUpsertRequest(BaseModel):
    material_id: Optional[str] = None
    file_name: str
    file_type: str = ""
    s3_key: str = ""
    file_url: str = ""
    uploaded_by: str = ""


class MaterialItem(BaseModel):
    material_id: str
    file_name: str
    file_type: str = ""
    s3_key: str = ""
    file_url: str
    uploaded_by: str = ""
    created_at: int
    updated_at: int


class MaterialListResponse(BaseModel):
    course_id: str
    module_id: str
    topic_id: str
    user_id: str
    materials: List[MaterialItem]


class AdminMaterialListResponse(BaseModel):
    course_id: str
    module_id: str
    topic_id: str
    materials: List[MaterialItem]


class MaterialUploadResponse(BaseModel):
    course_id: str
    module_id: str
    topic_id: str
    material_id: str
    file_name: str
    file_type: str = ""
    s3_key: str
    file_url: str
    uploaded_by: str = ""


class MaterialDownloadUrlResponse(BaseModel):
    course_id: str
    module_id: str
    topic_id: str
    material_id: str
    file_name: str
    file_type: str = ""
    s3_key: str
    file_url: str
    expires_in_seconds: int = Field(0, ge=0)


# ---------------------------------------------------------------------------
# Admin enrollment management
# ---------------------------------------------------------------------------

class AdminEnrolledUserItem(BaseModel):
    user_id: str
    enrolled_at: int
    status: str = "IN_PROGRESS"
    progress_percentage: int = Field(0, ge=0, le=100)


class AdminCourseEnrollmentsResponse(BaseModel):
    course_id: str
    total_count: int = Field(0, ge=0)
    enrollments: List[AdminEnrolledUserItem]


class AdminEnrollUserRequest(BaseModel):
    user_id: str
