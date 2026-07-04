"""
OCR 识别服务 —— 兼容旧导入路径的包装。

推荐用法:
    from app.ocr import get_ocr_service, OCRResult
    service = get_ocr_service("auto")
"""

from app.ocr import get_ocr_service, OCRResult
from app.ocr.base import BaseOCRService as OCRServiceBase

# ── 默认服务实例（兼容旧代码） ──────────────────────────

_default_service = get_ocr_service("auto")


class OCRService:
    """
    默认 OCR 服务包装（兼容旧接口）。

    >>> from app.ocr_service import OCRService
    >>> service = OCRService()
    >>> result = service.recognize("/path/to/img.jpg")
    """

    def recognize(self, image_path: str) -> OCRResult:
        return _default_service.recognize(image_path)

    def recognize_from_bytes(self, image_bytes: bytes, filename: str = "") -> OCRResult:
        """从内存字节识别（Mock 兼容）。"""
        return _default_service.recognize(image_path=filename or "memory_upload")
