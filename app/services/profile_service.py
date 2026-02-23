import httpx
import base64
import os
from typing import Optional


async def fetch_profile_photo_async(
    user_id: str,
    tenant_id: Optional[str] = None,
    role: Optional[str] = None,
    email_or_phone: Optional[str] = None,
    auth_token: Optional[str] = None,
) -> Optional[str]:
    """Fetch profile photo from profile API and convert to base64 data URL.

    Accepts optional tenant/role/email query params and an Authorization token
    which will be forwarded to the profile API.
    """
    try:
        profile_api_url = os.getenv("PROFILE_API_URL", "http://localhost:8081/api/v1")
        photo_url = f"{profile_api_url}/profile/basic/photo"

        params = {}
        if user_id:
            params["userId"] = user_id
        if tenant_id:
            params["tenantId"] = tenant_id
        if role:
            params["role"] = role
        if email_or_phone:
            params["emailOrPhone"] = email_or_phone

        headers = {}
        # Forward Authorization header exactly as received (e.g. "Bearer ...")
        if auth_token:
            headers["Authorization"] = auth_token

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(photo_url, params=params, headers=headers)

            if response.status_code != 200:
                return None

            content_type = response.headers.get("content-type", "")

            # If API returned JSON with a base64 field, use it
            if content_type.startswith("application/json"):
                try:
                    data = response.json()
                    # common field name observed: profilePhotoBase64
                    for key in ("profilePhotoBase64", "profilePhoto", "photoBase64"):
                        if key in data and data[key]:
                            return data[key]
                except Exception:
                    pass

            # Otherwise treat response as binary image
            image_data = response.content
            if not image_data:
                return None
            base64_str = base64.b64encode(image_data).decode("utf-8")
            # fallback mime type
            mime = content_type.split(";")[0] if content_type else "image/jpeg"
            return f"data:{mime};base64,{base64_str}"
    except Exception as e:
        print(f"Error fetching profile photo: {str(e)}")
        return None


def fetch_profile_photo(
    user_id: str,
    tenant_id: Optional[str] = None,
    role: Optional[str] = None,
    email_or_phone: Optional[str] = None,
    auth_token: Optional[str] = None,
) -> Optional[str]:
    """Sync wrapper for fetching profile photo with optional query params and auth."""
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            fetch_profile_photo_async(user_id, tenant_id, role, email_or_phone, auth_token)
        )
    finally:
        loop.close()
