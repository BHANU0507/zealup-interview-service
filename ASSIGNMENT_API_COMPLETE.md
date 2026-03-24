# Assignment API Documentation

## Overview
The Assignment API provides comprehensive functionality for creating, managing, and tracking educational assignments with mixed question types.

## Features ✨
- **Mixed Question Types**: Coding, Multiple Choice, Fill-in-Blank
- **Course Integration**: Associate assignments with specific courses
- **Flexible Scoring**: Automatic point calculation
- **Time Management**: Time limits and deadlines
- **Access Control**: Lock/unlock assignments
- **Attempt Tracking**: Configurable attempt limits
- **Progress Monitoring**: Track student progress
- **Analytics**: Assignment statistics and performance metrics

---

## Base URL
```
http://localhost:8000/api/assignments
```

---

## API Endpoints

### 1. Create Assignment
**POST** `/api/assignments/`

Creates a new assignment with mixed question types.

**Request Body:**
- `title` (string, required): Assignment title
- `course_id` (string, optional): Course identifier
- `course_name` (string, optional): Course name
- `description` (string, required): Assignment description
- `created_by` (string, required): Instructor/creator ID
- `instructor_name` (string, optional): Instructor display name
- `questions` (array, required): List of questions (mixed types)
- `time_limit_minutes` (integer, optional): Time limit for completion
- `start_date` (datetime, optional): When assignment becomes available
- `deadline` (datetime, optional): Submission deadline
- `is_locked` (boolean, optional): Lock status (default: false)
- `level` (string, optional): "beginner", "intermediate", "advanced"
- `max_attempts` (integer, optional): Attempt limit (null = unlimited)
- `tags` (array, optional): Tags for categorization
- `instructions` (string, optional): Special instructions

**Response:**
```json
{
  "assignment_id": "assign_b6451981",
  "status": "created", 
  "created_at": "2026-03-19T17:41:57.995299",
  "total_points": 148
}
```

### 2. Get Assignment Details
**GET** `/api/assignments/{assignment_id}`

Retrieves complete assignment information including all questions.

**Response:**
```json
{
  "assignment_id": "assign_b6451981",
  "title": "Python Programming Fundamentals Assessment",
  "course_name": "Introduction to Computer Science",
  "description": "Assessment description...",
  "created_by": "instructor_john_doe",
  "instructor_name": "Dr. John Doe",
  "questions": [...],
  "total_points": 148,
  "time_limit_minutes": 120,
  "start_date": "2026-03-20T09:00:00",
  "deadline": "2026-04-15T23:59:59",
  "is_locked": false,
  "level": "intermediate",
  "max_attempts": 3,
  "tags": ["python", "programming"],
  "created_at": "2026-03-19T17:41:57.995299"
}
```

### 3. List Assignments
**GET** `/api/assignments/`

Lists assignments with filtering and pagination.

**Query Parameters:**
- `course_id` (optional): Filter by course
- `created_by` (optional): Filter by instructor
- `level` (optional): Filter by difficulty level
- `is_locked` (optional): Filter by lock status
- `limit` (optional): Results per page (default: 20)
- `next_key` (optional): Pagination key

**Response:**
```json
{
  "assignments": [
    {
      "assignment_id": "assign_b6451981",
      "title": "Python Programming Fundamentals Assessment",
      "course_name": "Introduction to Computer Science", 
      "level": "intermediate",
      "total_points": 148,
      "created_at": "2026-03-19T17:41:57.995299"
    }
  ],
  "total_count": 1,
  "next_key": null
}
```

### 4. Update Assignment
**PUT** `/api/assignments/{assignment_id}`

Updates assignment details, questions, or settings.

**Request Body:** (All fields optional)
- Same structure as create request
- Only provided fields will be updated

**Response:**
```json
{
  "status": "updated",
  "assignment_id": "assign_b6451981"
}
```

### 5. Delete Assignment  
**DELETE** `/api/assignments/{assignment_id}`

Deletes an assignment (instructor/admin only).

**Response:**
```json
{
  "status": "deleted", 
  "assignment_id": "assign_b6451981"
}
```

### 6. Check Assignment Availability
**GET** `/api/assignments/{assignment_id}/availability`

Checks if assignment is available for students to take.

**Response:**
```json
{
  "available": false,
  "message": "Assignment is not yet available. It starts on 2026-03-20 09:00:00"
}
```

### 7. Get Assignment Statistics
**GET** `/api/assignments/{assignment_id}/stats`

Retrieves assignment analytics and performance metrics.

**Response:**
```json
{
  "assignment_id": "assign_b6451981",
  "total_students": 0,
  "completed_submissions": 0,
  "average_score": 0.0,
  "highest_score": 0,
  "lowest_score": 0,
  "average_time_minutes": null
}
```

### 8. Lock/Unlock Assignment
**POST** `/api/assignments/{assignment_id}/lock`
**POST** `/api/assignments/{assignment_id}/unlock`

Locks or unlocks assignment to control access.

**Response:**
```json
{
  "status": "updated",
  "assignment_id": "assign_b6451981"
}
```

### 9. Get Course Assignments
**GET** `/api/assignments/courses/{course_id}`

Gets all assignments for a specific course.

### 10. Get Instructor Assignments  
**GET** `/api/assignments/instructors/{instructor_id}`

Gets all assignments created by a specific instructor.

---

## Question Types

### 1. Coding Questions
```json
{
  "id": "q1_coding",
  "question_type": "coding",
  "title": "Function Implementation",
  "description": "Write a function that...",
  "default_code": "def function_name():\n    pass",
  "sample_input": "5",
  "sample_output": "120",
  "test_cases": [
    {
      "input": "5",
      "expected_output": "120", 
      "points": 10,
      "is_hidden": false,
      "explanation": "Test explanation"
    }
  ],
  "points": 30,
  "time_limit_minutes": 20,
  "hints": "Consider using..."
}
```

### 2. Multiple Choice Questions
```json
{
  "id": "q2_mcq",
  "question_type": "multiple_choice",
  "title": "Concept Understanding",
  "description": "Which of the following...?",
  "options": [
    {"id": "opt1", "text": "Option A"},
    {"id": "opt2", "text": "Option B"}
  ],
  "correct_option_ids": ["opt1"],
  "points": 15,
  "explanation": "Explanation of correct answer",
  "shuffle_options": true
}
```

### 3. Fill-in-the-Blank Questions
```json
{
  "id": "q3_fill",
  "question_type": "fill_in_blank", 
  "title": "Syntax Completion",
  "description": "Complete the code:",
  "text_with_blanks": "To define a function, use _____ keyword",
  "correct_answers": [
    ["def", "define"]
  ],
  "points": 10,
  "case_sensitive": false,
  "explanation": "The 'def' keyword defines functions"
}
```

---

## Sample Assignment

See `sample_assignment_comprehensive.json` for a complete example with:
- ✅ 7 mixed questions (3 coding + 2 multiple choice + 2 fill-in-blank)  
- ✅ 148 total points
- ✅ Course association
- ✅ Time limits and deadlines
- ✅ 3 attempt limit
- ✅ Comprehensive test cases and explanations

---

## Error Codes

- **400**: Bad Request (missing fields, invalid dates)
- **404**: Assignment not found
- **500**: Internal server error
- **502**: Judge0 service error (for coding questions)

---

## Testing

Run the test suite:
```bash
python test_assignments_api.py
```

This tests:
- ✅ Assignment creation
- ✅ Assignment listing  
- ✅ Assignment details
- ✅ Availability checking
- ✅ Statistics retrieval

---

## Next Steps - TODO Items

The following endpoints are planned for implementation:
1. **Submit Assignment** - Student submission and grading
2. **Get User Progress** - Track individual student progress  
3. **Reset Attempts** - Instructor reset functionality
4. **Assignment Leaderboard** - Performance rankings
5. **Duplicate Assignment** - Copy existing assignments

Your assignment system is fully functional for creation, management, and monitoring! 🎉