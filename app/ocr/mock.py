"""
Mock OCR 实现 —— 用于开发调试，随机返回预设数据。
"""

import random

from app.ocr.base import BaseOCRService, OCRResult

_MOCK_RECEIPTS = [
    {"applicant": "张三", "expense_type": "餐饮", "merchant": "海底捞火锅（朝阳大悦城店）", "total_amount": 458.00, "head_count": 5, "date": "2026-06-15"},
    {"applicant": "李四", "expense_type": "交通", "merchant": "中国石化加油站（望京站）",     "total_amount": 350.50, "head_count": 1, "date": "2026-06-20"},
    {"applicant": "王五", "expense_type": "住宿", "merchant": "汉庭酒店（北京西站店）",       "total_amount": 1280.00, "head_count": 1, "date": "2026-06-18"},
    {"applicant": "赵六", "expense_type": "办公用品", "merchant": "得力文具（中关村店）",     "total_amount": 89.90,  "head_count": 1, "date": "2026-06-22"},
    {"applicant": "孙七", "expense_type": "餐饮", "merchant": "西贝莜面村（望京华彩店）",     "total_amount": 632.00, "head_count": 8, "date": "2026-07-01"},
]


class MockOCRService(BaseOCRService):
    """Mock OCR：随机返回预设数据，用于开发调试。"""

    def recognize(self, image_path: str) -> OCRResult:
        mock = random.choice(_MOCK_RECEIPTS)
        raw = (
            f"[Mock OCR]\n"
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
