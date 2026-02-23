# # app/services/profile_client.py

# import httpx
# import base64
# import os

# PROFILE_SERVICE_URL = os.getenv("PROFILE_SERVICE_URL", "http://profile-service:8080")


# def fetch_profile_image(user_id: str) -> bytes | None:
#     """
#     Calls profile microservice and returns image bytes.
#     """

#     try:
#         url = f"{PROFILE_SERVICE_URL}/api/profile/{user_id}/image"

#         response = httpx.get(url, timeout=5.0)

#         if response.status_code != 200:
#             return None

#         # Assume profile service returns base64 string
#         data = response.json()

#         image_base64 = data.get("image")

#         if not image_base64:
#             return None

#         return base64.b64decode(image_base64)

#     except Exception as e:
#         print("Profile image fetch failed:", str(e))
#         return None
