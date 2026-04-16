import os
import base64
import httpx
from fastapi import APIRouter, HTTPException, Response

router = APIRouter()

PROFILE_API_URL = os.getenv("PROFILE_API_URL", "http://localhost:8081/api/v1")


@router.get("/admin-profile-image/{admin_id}")
async def get_admin_profile_image(admin_id: str):
    """
    Proxy endpoint that fetches the admin profile image and returns raw binary image bytes.
    Use as <img src="/api/proxy/admin-profile-image/{admin_id}"> directly.
    """
    url = f"{PROFILE_API_URL}/admin/profile-image/{admin_id}"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream request failed: {exc}")

    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail="Failed to fetch profile image")

    content_type = resp.headers.get("content-type", "")

    # If the upstream returned raw image bytes, stream them directly
    if content_type.startswith("image/"):
        return Response(content=resp.content, media_type=content_type)

    # If the upstream returned JSON with a base64 imageData field, decode it
    try:
        body = resp.json()
        data = body.get("data") or body
        image_data_str: str = data.get("imageData", "")
        mime = data.get("contentType", "image/jpeg")

        if not image_data_str:
            raise HTTPException(status_code=404, detail="No image data in response")

        # Strip the data URL prefix: "data:image/jpeg;base64,..."
        if ";" in image_data_str and "base64," in image_data_str:
            header, b64 = image_data_str.split("base64,", 1)
            # extract mime from "data:image/jpeg;"
            mime = header.replace("data:", "").rstrip(";")
        else:
            b64 = image_data_str

        image_bytes = base64.b64decode(b64)
        return Response(content=image_bytes, media_type=mime)

    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=502, detail=f"Unexpected upstream response format: {exc}")
