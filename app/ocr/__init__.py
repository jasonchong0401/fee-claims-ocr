"""
OCR 服务包 —— 统一的 OCR 接口。

支持引擎:
  - easyocr  : EasyOCR (PyTorch, 推荐，无 MKL 依赖)
  - paddle   : PaddleOCR PP-Structure (需 PaddlePaddle 环境)
  - mock     : Mock 随机数据 (开发调试用)
  - auto     : 自动选择 (EasyOCR > PaddleOCR > Mock)

使用方式:
    from app.ocr import get_ocr_service, OCRResult

    service = get_ocr_service("auto")    # 自动选择最佳引擎
    result = service.recognize("/path/to/receipt.jpg")
"""

from app.ocr.base import BaseOCRService, OCRResult
from app.ocr.mock import MockOCRService


def get_ocr_service(engine: str = "auto") -> BaseOCRService:
    """
    OCR 服务工厂。

    Args:
        engine: "easyocr" | "paddle" | "mock" | "auto"

    Returns:
        BaseOCRService 实例
    """
    if engine == "mock":
        return MockOCRService()

    if engine == "easyocr":
        from app.ocr.easy_ocr import EasyOCRService
        svc = EasyOCRService()
        if svc.available:
            return svc
        return MockOCRService()

    if engine == "paddle":
        from app.ocr.paddle_ocr import PaddleOCRService
        svc = PaddleOCRService()
        if svc.available:
            return svc
        return MockOCRService()

    # "auto": EasyOCR → PaddleOCR → Mock
    if engine == "auto":
        from app.ocr.easy_ocr import EasyOCRService
        svc = EasyOCRService()
        if svc.available:
            return svc

        from app.ocr.paddle_ocr import PaddleOCRService
        svc = PaddleOCRService()
        if svc.available:
            return svc

        return MockOCRService()

    raise ValueError(f"未知 OCR 引擎: {engine}，可选: easyocr | paddle | mock | auto")
