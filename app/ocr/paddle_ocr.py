"""
PaddleOCR PP-Structure 实现。

使用 PaddleOCR v3 的 PP-Structure 能力：
  1. 版面分析 (layout detection) —— 识别文本区域、表格区域
  2. 文本识别 (OCR) —— 逐区域提取文字
  3. 字段提取 (extractors) —— 正则从全文提取结构化字段

若 PaddleOCR 库不可用，自动降级为 MockOCRService。
"""

import logging
from typing import Optional

from app.ocr.base import BaseOCRService, OCRResult
from app.ocr.extractors import extract_all

logger = logging.getLogger("fee_claims.ocr")


class PaddleOCRService(BaseOCRService):
    """
    基于 PaddleOCR PP-Structure 的票据识别服务。

    工作流：
      1. 调用 PaddleOCR.predict(img, task="ocr") 获取全文
      2. 拼接所有检测到的文本行 → raw_text
      3. 使用 extractors 从 raw_text 提取结构化字段

    Usage:
        service = PaddleOCRService(use_doc_orientation=True)
        result = service.recognize("/path/to/receipt.jpg")
    """

    def __init__(
        self,
        lang: str = "ch",
        use_doc_orientation_classify: bool = True,
        use_textline_orientation: bool = True,
    ):
        """
        Args:
            lang: OCR 语言，默认 "ch" (中英文混合)
            use_doc_orientation_classify: 是否启用文档方向分类
            use_textline_orientation: 是否启用文本行方向检测
        """
        self._lang = lang
        self._use_doc_orientation_classify = use_doc_orientation_classify
        self._use_textline_orientation = use_textline_orientation
        self._model = None
        self._init_error: Optional[str] = None
        self._try_init()

    def _try_init(self):
        """尝试加载 PaddleOCR 模型，失败则记录错误。"""
        try:
            from paddleocr import PaddleOCR
            self._model = PaddleOCR(
                lang=self._lang,
                use_doc_orientation_classify=self._use_doc_orientation_classify,
                use_textline_orientation=self._use_textline_orientation,
            )
            logger.info("PaddleOCR 模型加载成功 (lang=%s)", self._lang)
        except Exception as exc:
            self._init_error = str(exc)
            logger.warning("PaddleOCR 初始化失败: %s，将使用 Mock 降级", exc)

    @property
    def available(self) -> bool:
        """OCR 模型是否可用。"""
        return self._model is not None

    def recognize(self, image_path: str) -> OCRResult:
        """
        对图片执行 PP-Structure OCR 并提取字段。

        Args:
            image_path: 图片文件路径

        Returns:
            OCRResult 对象
        """
        if not self.available:
            # 降级到 Mock
            from app.ocr.mock import MockOCRService
            logger.warning("PaddleOCR 不可用，降级到 Mock (%s)", self._init_error)
            return MockOCRService().recognize(image_path)

        # ── 1. 执行 OCR ──
        try:
            raw_text = self._run_ocr(image_path)
        except Exception as exc:
            logger.exception("PaddleOCR 识别异常")
            return OCRResult(
                raw_text=f"[PaddleOCR Error] {exc}",
            )

        if not raw_text.strip():
            return OCRResult(raw_text="[PaddleOCR] 未能从图像中识别出文字")

        # ── 2. 提取结构化字段 ──
        fields = extract_all(raw_text)
        logger.info(
            "PaddleOCR 提取结果: applicant=%s, type=%s, merchant=%s, amount=%s, head=%s",
            fields["applicant"], fields["expense_type"],
            fields["merchant"], fields["total_amount"], fields["head_count"],
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
        调用 PaddleOCR 执行全文识别，返回拼接后的文本。

        PaddleOCR.predict() 返回一个列表，每个元素是一个 dict:
          {
            "rec_texts": [...],       # 识别出的文字
            "rec_scores": [...],      # 置信度
            "dt_polys": [...],        # 检测框坐标
          }
        或直接返回 list[list[dict]] 格式。
        """
        result = self._model.predict(input=image_path)

        lines: list[str] = []

        # PaddleOCR v3 返回格式: list[list[dict]]
        # 每个元素是一页的结果
        if isinstance(result, list):
            for page in result:
                if isinstance(page, dict):
                    # 单页 dict 格式
                    texts = page.get("rec_texts", [])
                    lines.extend(texts)
                elif isinstance(page, list):
                    # 嵌套 list 格式
                    for item in page:
                        if isinstance(item, dict):
                            text = item.get("rec_text", "") or item.get("text", "")
                            if text:
                                lines.append(str(text))
                        elif isinstance(item, (list, tuple)):
                            # (bbox, text, score) 元组格式
                            if len(item) >= 2:
                                lines.append(str(item[1]))

        raw_text = "\n".join(lines)
        logger.info("PaddleOCR 识别到 %d 行文本 (共 %d 字符)", len(lines), len(raw_text))
        return raw_text
