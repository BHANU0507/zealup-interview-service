# from fastapi import APIRouter, UploadFile, File,Form
# import boto3
# import os
# import uuid
# import json
# import tempfile

# router = APIRouter()

# s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION"))
# sqs = boto3.client("sqs", region_name=os.getenv("AWS_REGION"))

# VIDEO_BUCKET = os.getenv("VIDEO_BUCKET")
# QUEUE_URL = os.getenv("VIDEO_QUEUE_URL")



# # @router.post("/{session_id}/upload-video")
# # async def upload_video(session_id: str, file: UploadFile = File(...)):

# #     # Add uploads/ prefix
# #     file_key = f"uploads/{session_id}-{uuid.uuid4()}.mp4"

# #     # Upload to S3
# #     s3.upload_fileobj(file.file, VIDEO_BUCKET, file_key)

# #     # Send SQS message
# #     sqs.send_message(
# #         QueueUrl=QUEUE_URL,
# #         MessageBody=json.dumps({
# #             "session_id": session_id,
# #             "video_key": file_key
# #         })
# #     )

# #     return {
# #         "status": "Video uploaded to uploads/ folder. Processing started."
# #     }

# # @router.post("/{session_id}/upload-video")
# # async def upload_video(
# #     session_id: str,
# #     video: UploadFile = File(...),
# #     question_timestamps: str = Form(...)
# # ):
# #     """
# #     question_timestamps JSON format:

# #     [
# #       {
# #         "question_id": "uuid",
# #         "start": 0,
# #         "end": 45
# #       },
# #       {
# #         "question_id": "uuid",
# #         "start": 45,
# #         "end": 90
# #       }
# #     ]
# #     """

# #     try:
# #         timestamps = json.loads(question_timestamps)
# #     except:
# #         raise HTTPException(status_code=400, detail="Invalid timestamps JSON")

# #     video_key = f"uploads/{session_id}.mp4"

# #     # Save locally temporarily
# #     temp_path = f"/tmp/{session_id}.mp4"

# #     with open(temp_path, "wb") as f:
# #         f.write(await video.read())

# #     # Upload to S3
# #     s3.upload_file(temp_path, VIDEO_BUCKET, video_key)

# #     # Send SQS message
# #     sqs.send_message(
# #         QueueUrl=VIDEO_QUEUE_URL,
# #         MessageBody=json.dumps({
# #             "session_id": session_id,
# #             "video_key": video_key,
# #             "question_timestamps": timestamps
# #         })
# #     )

# #     return {
# #         "status": "UPLOADED",
# #         "session_id": session_id
# #     }

# @router.post("/{session_id}/upload-video")
# async def upload_video(
#     session_id: str,
#     video: UploadFile = File(...),
#     question_timestamps: str = Form(...)
# ):

#     try:
#         timestamps = json.loads(question_timestamps)
#     except Exception:
#         raise HTTPException(status_code=400, detail="Invalid question_timestamps JSON")

#     # Save temp video safely (cross-platform)
#     temp_dir = tempfile.gettempdir()
#     temp_path = os.path.join(temp_dir, f"{session_id}.webm")

#     with open(temp_path, "wb") as f:
#         f.write(await video.read())

#     s3_key = f"uploads/{session_id}.webm"

#     # Upload to S3
#     s3.upload_file(temp_path, VIDEO_BUCKET, s3_key)

#     # Send SQS message
#     sqs.send_message(
#         QueueUrl=QUEUE_URL,
#         MessageBody=json.dumps({
#             "session_id": session_id,
#             "video_key": s3_key,
#             "question_timestamps": timestamps
#         })
#     )

#     os.remove(temp_path)

#     return {
#         "status": "Video uploaded. Processing started."
#     }