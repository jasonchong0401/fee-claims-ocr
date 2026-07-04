"""
EasyOCR 实现 —— 基于 PyTorch，无需 PaddlePaddle/MKL。

EasyOCR 支持 80+ 语言，中英文混合识别效果好，
是 PaddleOCR 不可用时的首选替代方案。
"""

import logging
from typing import Optional

from app.ocr.base import BaseOCRService, OCRResult
from app.ocr.extractors import extract_all

logger = logging.getLogger("fee_claims.ocr")


class EasyOCRService(BaseOCRService):
    """
    基于 EasyOCR 的票据识别服务。

    工作流：
      1. EasyOCR 读取图片 → 逐行文字 + 置信度
      2. 拼接所有文本行 → raw_text
      3. 使用 extractors 提取结构化字段

    Usage:
        service = EasyOCRService(lang_list=["ch_sim", "en"])
        result = service.recognize("/path/to/receipt.jpg")
    """

    def __init__(
        self,
        lang_list: Optional[list[str]] = None,
        gpu: bool = False,
    ):
        """
        Args:
            lang_list: 语言列表，默认 ["ch_sim", "en"] (简体中文 + 英文)
            gpu: 是否使用 GPU，默认 False (CPU)
        """
        self._lang_list = lang_list or ["ch_sim", "en"]
        self._gpu = gpu
        self._reader = None
        self._init_error: Optional[str] = None
        self._try_init()

    def _try_init(self):
        """尝试加载 EasyOCR 模型。"""
        try:
            import easyocr
            self._reader = easyocr.Reader(
                self._lang_list,
                gpu=self._gpu,
                verbose=False,
            )
            logger.info(
                "EasyOCR 模型加载成功 (langs=%s, gpu=%s)",
                self._lang_list, self._gpu,
            )
        except Exception as exc:
            self._init_error = str(exc)
            logger.warning("EasyOCR 初始化失败: %s，将使用 Mock 降级", exc)

    @property
    def available(self) -> bool:
        return self._reader is not None

    def recognize(self, image_path: str) -> OCRResult:
        if not self.available:
            from app.ocr.mock import MockOCRService
            logger.warning("EasyOCR 不可用，降级到 Mock (%s)", self._init_error)
            return MockOCRService().recognize(image_path)

        # ── 1. 执行 OCR ──
        try:
            raw_text = self._run_ocr(image_path)
        except Exception as exc:
            logger.exception("EasyOCR 识别异常")
            return OCRResult(raw_text=f"[EasyOCR Error] {exc}")

        if not raw_text.strip():
            return OCRResult(raw_text="[EasyOCR] 未能从图像中识别出文字")

        # ── 2. 提取结构化字段 ──
        fields = extract_all(raw_text)
        logger.info(
            "EasyOCR 提取: applicant=%s, type=%s, merchant=%s, amount=%s",
            fields["applicant"], fields["expense_type"],
            fields["merchant"], fields["total_amount"],
        )

        return OCRResult(
            applicant=fields["applicant"],
            expense_type=fields["expense_type"],
            merchant=fields["merchant"],
            total_amount=fields["total_amount"],
            head_count=fields["head_count"],
            raw_text=raw_text,
        )

    def _run_ocr(self, image_path: str) -> str:
        """
        调用 EasyOCR 识别图片，返回拼接后的文本。

        EasyOCR.readtext() 返回 list of (bbox, text, confidence):
          [
            ([[x1,y1],[x2,y2],[x3,y3],[x4,y4]], "识别文字", 0.98),
            ...
          ]
        """
        results = self._reader.readtext(image_path)

        lines: list[str] = []
        for item in results:
            # 格式: (bbox, text, confidence)
            text = str(item[1]).strip()
            confidence = float(item[2])
            if text:
                lines.append(text)
                logger.debug("  [%.2f] %s", confidence, text[:60])

        raw_text = "\n".join(lines)
        logger.info("EasyOCR 识别到 %d 行文本 (共 %d 字符)", len(lines), len(raw_text))
        return raw_text
