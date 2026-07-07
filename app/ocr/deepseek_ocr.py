"""
DeepSeek 增强 OCR 服务 —— 图片预处理 + EasyOCR + DeepSeek 两轮提取。

流程：
  图片 → 预处理（增强对比度/去噪/锐化）
       → EasyOCR 布局感知识别（HEADER/BODY/FOOTER + 置信度标注）
       → DeepSeek 第 1 轮：智能提取字段
       → DeepSeek 第 2 轮：校验修正
       → 结构化 OCRResult
       失败时降级 → 正则提取器（中英文）
"""

import logging

from app.ocr.base import BaseOCRService, OCRResult
from app.ocr.easy_ocr import EasyOCRService
from app.ocr.deepseek_extractor import extract_hybrid
from app.ocr.image_preprocessor import preprocess_if_needed

logger = logging.getLogger("fee_claims.ocr")


class DeepSeekOCRService(BaseOCRService):
    """
    图片预处理 + EasyOCR + DeepSeek 两轮提取的组合服务。

    EasyOCR 负责文字识别（带布局标注），DeepSeek 负责理解票据内容
    并提取字段（两轮：提取 + 校验）。DeepSeek 不可用时降级到正则。
    """

    def __init__(self):
        self._easyocr = EasyOCRService()

    @property
    def available(self) -> bool:
        return self._easyocr.available

    def recognize(self, image_path: str) -> OCRResult:
        # ── 步骤 0: 图片预处理 ──
        try:
            processed_path = preprocess_if_needed(image_path)
        except Exception as exc:
            logger.warning("图片预处理失败，使用原始图片: %s", exc)
            processed_path = image_path

        # ── 步骤 1: EasyOCR 布局感知识别 ──
        if not self._easyocr.available:
            from app.ocr.mock import MockOCRService
            return MockOCRService().recognize(image_path)

        ocr_result = self._easyocr.recognize(processed_path)
        raw_text = ocr_result.raw_text

        if not raw_text.strip():
            return OCRResult(raw_text="[OCR] 未能识别出文字")

        # ── 步骤 2-3: DeepSeek 两轮提取（带降级） ──
        fields = extract_hybrid(raw_text)

        logger.info(
            "DeepSeekOCR 最终: applicant=%s, type=%s, merchant=%s, amount=%s, date=%s, items=%d",
            fields["applicant"], fields["expense_type"],
            fields["merchant"], fields["total_amount"],
            fields.get("invoice_date"),
            len(fields.get("line_items") or []),
        )

        return OCRResult(
            applicant=fields["applicant"],
            expense_type=fields["expense_type"],
            merchant=fields["merchant"],
            total_amount=fields["total_amount"],
            head_count=fields.get("head_count", 1),
            raw_text=raw_text,
            invoice_date=fields.get("invoice_date"),
            currency=fields.get("currency"),
            tax_amount=fields.get("tax_amount"),
            line_items=fields.get("line_items"),
            reasoning=fields.get("reasoning"),
        )
