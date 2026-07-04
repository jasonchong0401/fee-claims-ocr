"""
OCR 识别服务。

当前为 Mock 实现（返回预设 JSON 用于测试）。
接入真实 API 时，只需替换 OCRService.recognize() 的内部实现，
接口签名保持不变即可。
"""

import random
import re
from datetime import datetime
from typing import Optional


# ── Mock 数据池 ─────────────────────────────────────────
_MOCK_RECEIPTS = [
    {
        "applicant": "张三",
        "expense_type": "餐饮",
        "merchant": "海底捞火锅（朝阳大悦城店）",
        "total_amount": 458.00,
        "head_count": 5,
        "date": "2026-06-15",
    },
    {
        "applicant": "李四",
        "expense_type": "交通",
        "merchant": "中国石化加油站（望京站）",
        "total_amount": 350.50,
        "head_count": 1,
        "date": "2026-06-20",
    },
    {
        "applicant": "王五",
        "expense_type": "住宿",
        "merchant": "汉庭酒店（北京西站店）",
        "total_amount": 1280.00,
        "head_count": 1,
        "date": "2026-06-18",
    },
    {
        "applicant": "赵六",
        "expense_type": "办公用品",
        "merchant": "得力文具（中关村店）",
        "total_amount": 89.90,
        "head_count": 1,
        "date": "2026-06-22",
    },
    {
        "applicant": "孙七",
        "expense_type": "餐饮",
        "merchant": "西贝莜面村（望京华彩店）",
        "total_amount": 632.00,
        "head_count": 8,
        "date": "2026-07-01",
    },
]


# ── 简单正则提取（真实场景下替换为 PaddleOCR / 百度OCR 调用）──
_AMOUNT_PATTERN = re.compile(r"[\d,]+\.?\d*")
_APPLICANT_PATTERNS = [
    re.compile(r"报销人[：:]\s*(\S+)"),
    re.compile(r"姓名[：:]\s*(\S+)"),
]
_MERCHANT_PATTERNS = [
    re.compile(r"商户[：:]\s*(.+)"),
    re.compile(r"收款单位[：:]\s*(.+)"),
]
_TYPE_PATTERNS = [
    re.compile(r"(交通|餐饮|住宿|办公用品)"),
]
_HEAD_COUNT_PATTERNS = [
    re.compile(r"人数[：:]\s*(\d+)"),
    re.compile(r"共\s*(\d+)\s*人"),
]


class OCRResult:
    """OCR 识别结果"""

    def __init__(
        self,
        applicant: Optional[str] = None,
        expense_type: Optional[str] = None,
        merchant: Optional[str] = None,
        total_amount: Optional[float] = None,
        head_count: int = 1,
        raw_text: str = "",
    ):
        self.applicant = applicant
        self.expense_type = expense_type
        self.merchant = merchant
        self.total_amount = total_amount
        self.head_count = head_count
        self.raw_text = raw_text

    def to_dict(self) -> dict:
        return {
            "applicant": self.applicant,
            "expense_type": self.expense_type,
            "merchant": self.merchant,
            "total_amount": self.total_amount,
            "head_count": self.head_count,
            "raw_text": self.raw_text,
        }


class OCRService:
    """
    OCR 识别服务。

    使用方式:
        service = OCRService()
        result = service.recognize(image_path="/path/to/receipt.jpg")
        # result 是 OCRResult 对象
    """

    # 模拟 OCR 调用延迟（秒）
    MOCK_DELAY_SECONDS = 0.3

    def recognize(self, image_path: str) -> OCRResult:
        """
        对图片执行 OCR 识别，返回结构化结果。

        当前是 Mock 实现：随机返回一笔预设数据 + 图片路径。
        接入真实 OCR API 时替换此方法体即可。

        Args:
            image_path: 图片文件路径

        Returns:
            OCRResult 对象
        """
        # 随机选择一条 Mock 数据
        mock = random.choice(_MOCK_RECEIPTS)

        # 构造一段模拟的 OCR 原始文本
        raw = (
            f"Mock OCR Result for: {image_path}\n"
            f"商户：{mock['merchant']}\n"
            f"日期：{mock['date']}\n"
            f"报销人：{mock['applicant']}\n"
            f"类型：{mock['expense_type']}\n"
            f"金额：¥{mock['total_amount']:.2f}\n"
            f"人数：{mock['head_count']}人\n"
        )

        return OCRResult(
            applicant=mock["applicant"],
            expense_type=mock["expense_type"],
            merchant=mock["merchant"],
            total_amount=mock["total_amount"],
            head_count=mock["head_count"],
            raw_text=raw,
        )

    def recognize_from_bytes(self, image_bytes: bytes, filename: str = "") -> OCRResult:
        """
        从内存中的图片字节数据直接识别（与 recognize() 等效的 Mock 实现）。
        """
        return self.recognize(image_path=filename or "memory_upload")


# ── 正则提取工具函数（对外暴露，未来可被真实 OCR 调用）─────

def extract_amount(text: str) -> Optional[float]:
    """从文本中提取金额（去除 ¥、$ 等货币符号后转 float）。"""
    # 先尝试匹配货币格式
    cleaned = re.sub(r"[¥￥$€£元]", "", text).strip()
    m = _AMOUNT_PATTERN.search(cleaned)
    if m:
        try:
            return float(m.group().replace(",", ""))
        except ValueError:
            pass
    return None


def extract_applicant(text: str) -> Optional[str]:
    """从文本中提取报销人姓名。"""
    for pat in _APPLICANT_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1).strip()
    return None


def extract_merchant(text: str) -> Optional[str]:
    """从文本中提取商户名称。"""
    for pat in _MERCHANT_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1).strip()
    return None


def extract_expense_type(text: str) -> Optional[str]:
    """从文本中提取报销类型（交通/餐饮/住宿/办公用品）。"""
    for pat in _TYPE_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1).strip()
    return None


def extract_head_count(text: str) -> int:
    """从文本中提取参与人数，默认返回 1。"""
    for pat in _HEAD_COUNT_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass
    return 1
