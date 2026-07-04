"""
OCR 服务抽象基类。

所有 OCR 实现（Mock / PaddleOCR / 百度OCR 等）需继承此类，
实现 recognize() 方法，返回统一的 OCRResult。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class OCRResult:
    """OCR 识别结果 —— 统一数据结构"""
    applicant: Optional[str] = None
    expense_type: Optional[str] = None
    merchant: Optional[str] = None
    total_amount: Optional[float] = None
    head_count: int = 1
    raw_text: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class BaseOCRService(ABC):
    """OCR 服务抽象基类"""

    @abstractmethod
    def recognize(self, image_path: str) -> OCRResult:
        """对图片执行 OCR，返回结构化结果"""
        ...
