from app.services.course_service import (
    create_course,
    create_module,
    create_topic,
    enroll_course,
    create_topic_discussion,
    create_topic_note,
    create_topic_material,
    update_topic_video_url,
)


def run_seed() -> None:
    course_id = "course_python_backend"
    module_id_1 = "mod_fastapi_basics"
    module_id_2 = "mod_dynamo_patterns"
    topic_id_1 = "topic_routing"
    topic_id_2 = "topic_dependency_injection"
    topic_id_3 = "topic_partition_keys"

    # 1) Course
    print(create_course({
        "course_id": course_id,
        "title": "Python Backend Mastery",
        "instructor_name": "Anita Verma",
        "description": "Build production-ready APIs with FastAPI and DynamoDB.",
        "level": "Intermediate",
        "duration_hours": 18,
        "prerequisites": ["Python basics", "REST fundamentals"],
        "key_topics": ["FastAPI", "DynamoDB", "API design"],
        "key_technologies": ["Python", "FastAPI", "DynamoDB", "Pydantic"],
    }))

    # 2) Modules
    print(create_module(course_id, {
        "module_id": module_id_1,
        "title": "FastAPI Core",
        "description": "Routing, validation, and request lifecycle",
    }))

    print(create_module(course_id, {
        "module_id": module_id_2,
        "title": "DynamoDB Data Modeling",
        "description": "Keys, access patterns, and scalable queries",
    }))

    # 3) Topics with video URLs
    print(create_topic(course_id, {
        "module_id": module_id_1,
        "topic_id": topic_id_1,
        "title": "Routing and Response Models",
        "description": "Create robust route handlers and response contracts",
        "duration_minutes": 35,
        "locked": False,
        "video_url": "https://cdn.example.com/videos/routing-response-models.mp4",
        "status": "NOT_STARTED",
    }))

    print(create_topic(course_id, {
        "module_id": module_id_1,
        "topic_id": topic_id_2,
        "title": "Dependency Injection",
        "description": "Reusable dependencies, auth, and service wiring",
        "duration_minutes": 30,
        "locked": False,
        "video_url": "https://cdn.example.com/videos/dependency-injection.mp4",
        "status": "NOT_STARTED",
    }))

    print(create_topic(course_id, {
        "module_id": module_id_2,
        "topic_id": topic_id_3,
        "title": "Partition Key Strategies",
        "description": "Design PK/SK for single-table patterns",
        "duration_minutes": 40,
        "locked": False,
        "video_url": "https://cdn.example.com/videos/partition-key-strategies.mp4",
        "status": "NOT_STARTED",
    }))

    # 4) Enroll users (required for user discussion/note APIs)
    for user_id in ["user123", "user456"]:
        print(enroll_course({
            "user_id": user_id,
            "course_id": course_id,
            "planType": "SILVER",
            "status": "ACTIVE",
            "coursesLimit": 10,
        }))

    # 5) Discussions (user posts + instructor read-only post)
    print(create_topic_discussion(course_id, module_id_1, topic_id_1, {
        "user_id": "user123",
        "user_name": "Rahul",
        "author_role": "USER",
        "content": "Can someone explain when to use response_model_exclude_none?",
    }))

    print(create_topic_discussion(course_id, module_id_1, topic_id_1, {
        "user_id": "user456",
        "user_name": "Meera",
        "author_role": "USER",
        "content": "I used it to keep response payload clean for optional fields.",
    }))

    print(create_topic_discussion(course_id, module_id_1, topic_id_1, {
        "user_id": "instr_001",
        "user_name": "Anita Verma",
        "author_role": "INSTRUCTOR",
        "content": "Great question. Use it when null keys should not appear in API responses.",
    }))

    # 6) Notes (per user/topic)
    print(create_topic_note(course_id, module_id_1, topic_id_1, {
        "user_id": "user123",
        "title": "Routing quick notes",
        "content": "Use typed response models to keep contracts stable.",
    }))

    print(create_topic_note(course_id, module_id_1, topic_id_1, {
        "user_id": "user456",
        "title": "Validation reminder",
        "content": "Prefer Pydantic Field constraints over manual validation where possible.",
    }))

    # 7) Materials for download
    print(create_topic_material(course_id, module_id_1, topic_id_1, {
        "file_name": "fastapi-routing-cheatsheet.pdf",
        "file_url": "https://cdn.example.com/materials/fastapi-routing-cheatsheet.pdf",
        "uploaded_by": "Anita Verma",
    }))

    print(create_topic_material(course_id, module_id_2, topic_id_3, {
        "file_name": "dynamodb-single-table-guide.pdf",
        "file_url": "https://cdn.example.com/materials/dynamodb-single-table-guide.pdf",
        "uploaded_by": "Anita Verma",
    }))

    # 8) Explicit video URL update API usage demo
    print(update_topic_video_url(
        course_id,
        module_id_1,
        topic_id_2,
        "https://cdn.example.com/videos/dependency-injection-v2.mp4",
    ))

    print("Dummy course data seeded successfully.")


if __name__ == "__main__":
    run_seed()
