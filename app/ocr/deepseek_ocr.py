"""
DeepSeek 增强 OCR 服务 —— EasyOCR 识别文字 + DeepSeek 智能提取字段。

流程：
  图片 → EasyOCR → 原始文本 → DeepSeek (Prompt + OCR Text) → 结构化 JSON
                                                    ↓ (失败时降级)
                                               正则提取器
"""

import logging

from app.ocr.base import BaseOCRService, OCRResult
from app.ocr.easy_ocr import EasyOCRService
from app.ocr.deepseek_extractor import extract_hybrid

logger = logging.getLogger("fee_claims.ocr")


class DeepSeekOCRService(BaseOCRService):
    """
    EasyOCR + DeepSeek 组合服务。

    EasyOCR 负责文字识别，DeepSeek 负责理解票据内容并提取字段。
    当 DeepSeek 不可用时，自动降级到正则提取器。
    """

    def __init__(self):
        self._easyocr = EasyOCRService()
        self._deepseek_available = None  # 延迟检测

    @property
    def available(self) -> bool:
        return self._easyocr.available

    def recognize(self, image_path: str) -> OCRResult:
        # ── 步骤 1: EasyOCR 提取原始文本 ──
        if not self._easyocr.available:
            from app.ocr.mock import MockOCRService
            return MockOCRService().recognize(image_path)

        ocr_result = self._easyocr.recognize(image_path)
        raw_text = ocr_result.raw_text

        if not raw_text.strip():
            return OCRResult(raw_text="[OCR] 未能识别出文字")

        # ── 步骤 2: DeepSeek 智能提取（带降级） ──
        fields = extract_hybrid(raw_text)

        logger.info(
            "DeepSeekOCR 最终结果: applicant=%s, type=%s, merchant=%s, amount=%s",
            fields["applicant"], fields["expense_type"],
            fields["merchant"], fields["total_amount"],
        )

        return OCRResult(
            applicant=fields["applicant"],
            expense_type=fields["expense_type"],
            merchant=fields["merchant"],
            total_amount=fields["total_amount"],
            head_count=fields.get("head_count", 1),
            raw_text=raw_text,
        )
