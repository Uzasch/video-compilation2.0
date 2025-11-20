from fastapi import APIRouter, UploadFile, File, HTTPException
from pathlib import Path
import uuid
import shutil
from typing import Optional

router = APIRouter(prefix="/uploads", tags=["uploads"])

UPLOAD_DIR = Path("uploads/images")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

@router.post("/image")
async def upload_image(file: UploadFile = File(...)):
    """
    Upload an image file for use in compilation.
    Images can be inserted as static slides with custom duration.

    Returns:
        dict: Contains filename, path, and file size
    """
    # Validate file extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Generate unique filename
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = UPLOAD_DIR / unique_filename

    # Save file
    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Validate file size
        file_size = file_path.stat().st_size
        if file_size > MAX_FILE_SIZE:
            file_path.unlink()
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size: {MAX_FILE_SIZE / 1024 / 1024}MB"
            )

    except Exception as e:
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    return {
        "filename": unique_filename,
        "path": str(file_path),
        "size": file_size
    }

@router.delete("/image/{filename}")
async def delete_image(filename: str):
    """Delete an uploaded image"""
    # Validate filename (prevent path traversal)
    if '/' in filename or '\\' in filename or '..' in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = UPLOAD_DIR / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        file_path.unlink()
        return {"message": "File deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")

@router.get("/image/{filename}")
async def get_image(filename: str):
    """Get info about an uploaded image"""
    # Validate filename
    if '/' in filename or '\\' in filename or '..' in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = UPLOAD_DIR / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return {
        "filename": filename,
        "path": str(file_path),
        "size": file_path.stat().st_size
    }
