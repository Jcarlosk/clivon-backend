import os
import uuid
from fastapi import UploadFile, HTTPException

UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def validate_image(file: UploadFile) -> None:
    ext = os.path.splitext(file.filename or "")[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{ext}'. Allowed: {ALLOWED_EXTENSIONS}",
        )


async def save_upload(file: UploadFile) -> str:
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    ext = os.path.splitext(file.filename or ".jpg")[-1].lower()
    filename = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(UPLOADS_DIR, filename)

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 10 MB).")

    with open(path, "wb") as f:
        f.write(content)

    return path
