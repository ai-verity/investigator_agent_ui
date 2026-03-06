"""
backend/routers/upload.py
Handles photo and blueprint uploads, stored under:
  uploads/{app_id}/photos/
  uploads/{app_id}/blueprint/
"""

import os
import shutil
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse

UPLOAD_ROOT = "uploads"   # set via env var in production

router = APIRouter(prefix="/upload", tags=["upload"])


def _ensure_dirs(app_id: str):
    for sub in ("photos", "blueprint"):
        os.makedirs(os.path.join(UPLOAD_ROOT, app_id, sub), exist_ok=True)


@router.post("/{app_id}/photos")
async def upload_photos(app_id: str, files: list[UploadFile] = File(...)):
    _ensure_dirs(app_id)
    saved = []
    for file in files:
        dest = os.path.join(UPLOAD_ROOT, app_id, "photos", file.filename)
        with open(dest, "wb") as f:
            shutil.copyfileobj(file.file, f)
        saved.append(dest)
    return JSONResponse({"uploaded": saved})


@router.post("/{app_id}/blueprint")
async def upload_blueprint(app_id: str, file: UploadFile = File(...)):
    _ensure_dirs(app_id)
    dest = os.path.join(UPLOAD_ROOT, app_id, "blueprint", file.filename)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return JSONResponse({"uploaded": dest})