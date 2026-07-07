"""
工具函数 —— 文件校验、保存上传文件。
"""

import os
import uuid
import logging
from datetime import datetime
from pathlib import Path

from fastapi import UploadFile

from config import settings
from app.schemas import FileValidationError

logger = logging.getLogger("fee_claims")


def validate_upload_file(file: UploadFile) -> None:
    """校验上传文件的扩展名、大小、非空。"""
    if not file.filename:
        raise FileValidationError("文件名为空")
    ext = Path(file.filename).suffix.lstrip(".").lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise FileValidationError(
            f"不支持的文件类型 .{ext}，仅允许: {', '.join(sorted(settings.ALLOWED_EXTENSIONS))}"
        )
    file.file.seek(0, os.SEEK_END)
    size = file.file.tell()
    file.file.seek(0)
    if size > settings.MAX_FILE_SIZE_BYTES:
        max_mb = settings.MAX_FILE_SIZE_BYTES // (1024 * 1024)
        raise FileValidationError(f"文件大小超过 {max_mb}MB 限制")
    if size == 0:
        raise FileValidationError("文件为空")


async def save_upload_file(file: UploadFile, employee_id: str, receipt_uuid: str) -> str:
    """
    保存上传文件至分层目录:
      uploads/receipts/{employee_id}/{YYYY-MM-DD}/{uuid}.{ext}

    返回相对于项目根目录的路径。
    """
    ext = Path(file.filename).suffix
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    sub_dir = Path(settings.UPLOAD_DIR) / employee_id / date_str
    sub_dir.mkdir(parents=True, exist_ok=True)

    new_filename = f"{receipt_uuid}{ext}"
    dest = sub_dir / new_filename

    content = await file.read()
    dest.write_bytes(content)
    relative_path = str(dest)
    logger.info(f"图片已保存: {relative_path} ({len(content)} bytes)")
    return relative_path
