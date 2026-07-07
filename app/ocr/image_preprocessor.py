"""
图片预处理 —— 提升 OCR 识别率。

在送入 OCR 之前对票据图片进行增强处理：
  1. 灰度化 — 减少颜色干扰
  2. 自适应对比度增强 — 让文字更清晰
  3. 锐化 — 增强边缘
  4. 自适应二值化 — 分离文字和背景
  5. 去噪 — 去除噪点

使用 PIL/Pillow + OpenCV，均为已安装依赖。
"""

import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

logger = logging.getLogger("fee_claims.ocr.preprocess")


def preprocess(image_path: str, output_dir: Optional[str] = None) -> str:
    """
    对图片进行完整预处理管线，返回预处理后的图片路径。

    Args:
        image_path: 原始图片路径
        output_dir: 输出目录，默认与原始图片同目录

    Returns:
        预处理后的图片路径（PNG 格式）
    """
    src = Path(image_path)
    out_dir = Path(output_dir) if output_dir else src.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{src.stem}_preprocessed.png"

    img = cv2.imread(str(src))
    if img is None:
        logger.warning("OpenCV 无法读取 %s，回退到 PIL", image_path)
        return _preprocess_pil(image_path, str(out_path))

    h, w = img.shape[:2]
    logger.info("预处理图片: %s (%dx%d)", src.name, w, h)

    # 1. 转灰度
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 2. CLAHE 自适应直方图均衡化 — 增强局部对比度
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # 3. 去噪（保留边缘）
    denoised = cv2.fastNlMeansDenoising(enhanced, h=10, templateWindowSize=7, searchWindowSize=21)

    # 4. 锐化
    kernel = np.array([[-0.5, -1, -0.5], [-1, 7, -1], [-0.5, -1, -0.5]])
    sharp = cv2.filter2D(denoised, -1, kernel)

    # 5. 自适应阈值二值化（仅在文字不清晰时有帮助）
    # 不做强制二值化，而是做一个增强版本供 OCR 使用
    # 保留灰度图但提高对比度
    result = cv2.normalize(sharp, None, 0, 255, cv2.NORM_MINMAX)

    cv2.imwrite(str(out_path), result)
    logger.info("预处理完成: %s", out_path)
    return str(out_path)


def _preprocess_pil(image_path: str, out_path: str) -> str:
    """PIL 预处理（OpenCV 不可用时的降级方案）。"""
    img = Image.open(image_path).convert("L")  # 灰度

    # 对比度增强
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0)

    # 锐化
    enhancer = ImageEnhance.Sharpness(img)
    img = enhancer.enhance(2.0)

    # 亮度
    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(1.05)

    img.save(out_path, "PNG")
    return out_path


def preprocess_if_needed(image_path: str, min_size_kb: int = 50) -> str:
    """
    判断是否需要预处理，仅对小图/模糊图进行处理。

    Args:
        image_path: 原始图片路径
        min_size_kb: 小于此大小的图片将被预处理

    Returns:
        处理后（或原始）图片路径
    """
    path = Path(image_path)
    size_kb = path.stat().st_size / 1024

    # 大文件通常是高质量照片，无需预处理
    if size_kb > 500:
        logger.info("图片较大 (%d KB)，跳过预处理", int(size_kb))
        return image_path

    if size_kb < min_size_kb:
        logger.info("图片过小 (%d KB)，可能是缩略图，进行增强", int(size_kb))

    return preprocess(image_path)
