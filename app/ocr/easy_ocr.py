"""
EasyOCR 实现 —— 基于 PyTorch，无需 PaddlePaddle/MKL。

EasyOCR 支持 80+ 语言，中英文混合识别效果好，
是 PaddleOCR 不可用时的首选替代方案。

语言检测：识别后自动检测文本语言（中文/英文/混合），
便于后续 Prompt 和正则选择合适的策略。
"""

import logging
import re
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
        lang = _detect_language(raw_text)
        logger.info(
            "EasyOCR 提取 (lang=%s): applicant=%s, type=%s, merchant=%s, amount=%s, date=%s",
            lang, fields["applicant"], fields["expense_type"],
            fields["merchant"], fields["total_amount"], fields.get("invoice_date"),
        )

        return OCRResult(
            applicant=fields["applicant"],
            expense_type=fields["expense_type"],
            merchant=fields["merchant"],
            total_amount=fields["total_amount"],
            head_count=fields["head_count"],
            raw_text=raw_text,
            invoice_date=fields.get("invoice_date"),
            currency=fields.get("currency"),
            tax_amount=fields.get("tax_amount"),
        )

    def _run_ocr(self, image_path: str) -> str:
        """
        调用 EasyOCR 识别图片，返回布局感知的文本。

        利用 bbox 坐标标注文本位置：
          [HEADER]  — 页面上部 30%（商户名、日期通常在顶部）
          [BODY]    — 页面中部（商品明细）
          [FOOTER]  — 页面下部 30%（合计金额、税额）

        置信度标注：
          [LOW-CONF] — 置信度 < 0.5 的行，提醒 LLM 该行可能有 OCR 错误

        EasyOCR.readtext() 返回 list of (bbox, text, confidence):
          [
            ([[x1,y1],[x2,y2],[x3,y3],[x4,y4]], "识别文字", 0.98),
            ...
          ]
        """
        results = self._reader.readtext(
            image_path,
            text_threshold=0.4,    # 降低阈值以捕获更多文字（默认 0.7）
            low_text=0.3,          # 低置信度文字也保留
        )

        if not results:
            logger.warning("EasyOCR 未识别到任何文字")
            return ""

        # ── 获取图片高度用于布局判断 ──
        try:
            from PIL import Image
            with Image.open(image_path) as im:
                img_h = im.height
        except Exception:
            img_h = None

        # ── 收集带 bbox 的行 ──
        rows: list[dict] = []
        for item in results:
            bbox = item[0]  # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
            text = str(item[1]).strip()
            confidence = float(item[2])
            if not text:
                continue
            # 计算 y 中心
            y_center = sum(pt[1] for pt in bbox) / 4
            rows.append({"text": text, "conf": confidence, "y": y_center})

        if not rows:
            return ""

        # ── 按 y 坐标排序（从上到下）──
        rows.sort(key=lambda r: r["y"])

        # ── 构建布局感知文本 ──
        lines: list[str] = []
        prev_section = None

        for r in rows:
            text = r["text"]
            conf = r["conf"]

            # 布局标签
            if img_h and img_h > 0:
                rel_y = r["y"] / img_h
                if rel_y < 0.30:
                    section = "HEADER"
                elif rel_y > 0.70:
                    section = "FOOTER"
                else:
                    section = "BODY"
            else:
                section = "BODY"

            # 在区域切换时插入标签
            if section != prev_section:
                lines.append(f"[{section}]")
                prev_section = section

            # 低置信度标注
            if conf < 0.5:
                lines.append(f"[LOW-CONF:{conf:.0%}] {text}")
                logger.debug("  [%.2f LOW] %s", conf, text[:60])
            else:
                lines.append(text)
                logger.debug("  [%.2f] %s @ y=%.0f (%.0f%%)", conf, text[:60], r["y"],
                             (r["y"] / img_h * 100) if img_h else 0)

        raw_text = "\n".join(lines)
        avg_conf = sum(r["conf"] for r in rows) / len(rows)
        logger.info(
            "EasyOCR: %d 行, 平均置信度=%.0f%%, 布局=%s",
            len(rows), avg_conf * 100,
            "HEADER/BODY/FOOTER" if img_h else "flat",
        )
        return raw_text


def _detect_language(text: str) -> str:
    """
    检测 OCR 文本的主导语言。

    Returns:
        "zh"  — 中文为主 (>30% CJK 字符)
        "en"  — 英文为主 (<10% CJK 字符)
        "mix" — 中英混合
    """
    if not text.strip():
        return "en"

    cjk = len(re.findall(r"[一-鿿㐀-䶿]", text))
    latin = len(re.findall(r"[a-zA-Z]", text))
    total = cjk + latin

    if total == 0:
        return "en"

    cjk_ratio = cjk / total if total > 0 else 0

    if cjk_ratio > 0.3:
        return "zh"
    elif cjk_ratio > 0.1:
        return "mix"
    else:
        return "en"
