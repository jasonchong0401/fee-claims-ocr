#!/usr/bin/env python
"""
PaddleOCR PP-Structure 效果测试脚本。

用法:
    python test_ocr.py                          # 使用生成的测试图片
    python test_ocr.py /path/to/receipt.jpg     # 使用真实票据图片
"""

import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

from app.ocr import get_ocr_service, OCRResult


def generate_test_image() -> str:
    """生成一张包含中文票据信息的测试图片。"""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (800, 500), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # 尝试加载中文字体
    font_paths = [
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        "/usr/share/fonts/truetype/arphic/uming.ttc",
    ]
    font = None
    for fp in font_paths:
        if Path(fp).exists():
            font = ImageFont.truetype(fp, 24)
            break
    if font is None:
        font = ImageFont.load_default()

    # 绘制票据内容
    lines = [
        ("增值税电子普通发票", 30, (0, 0, 0)),
        ("", 0, (0, 0, 0)),
        ("商户名称：北京华联超市（望京店）", 20, (80, 80, 80)),
        ("开票日期：2026年07月01日", 20, (80, 80, 80)),
        ("", 0, (0, 0, 0)),
        ("商品明细：", 20, (80, 80, 80)),
        ("  1. 办公用纸 A4         2包    ¥45.00", 20, (60, 60, 60)),
        ("  2. 签字笔 黑色         5支    ¥25.00", 20, (60, 60, 60)),
        ("  3. 文件夹 A4           3个    ¥19.90", 20, (60, 60, 60)),
        ("", 0, (0, 0, 0)),
        ("金额合计：¥89.90", 22, (0, 0, 0)),
        ("", 0, (0, 0, 0)),
        ("报销人：张三", 20, (80, 80, 80)),
        ("报销类型：办公用品", 20, (80, 80, 80)),
        ("人数：1人", 20, (80, 80, 80)),
    ]

    y = 40
    for text, size, color in lines:
        if text:
            draw.text((50, y), text, fill=color, font=font)
        y += 30

    path = "/tmp/test_receipt_ocr.png"
    img.save(path)
    print(f"测试图片已生成: {path}")
    return path


def print_result(result: OCRResult):
    """格式化打印 OCR 结果。"""
    print("\n" + "=" * 50)
    print("  OCR 识别结果")
    print("=" * 50)
    print(f"  报销人   : {result.applicant or '(未识别)'}")
    print(f"  报销类型 : {result.expense_type or '(未识别)'}")
    print(f"  商户名称 : {result.merchant or '(未识别)'}")
    print(f"  费用总额 : {result.total_amount if result.total_amount else '(未识别)'}")
    print(f"  参与人数 : {result.head_count}")
    print("-" * 50)
    print(f"  OCR 原始文本:")
    for line in result.raw_text.split("\n"):
        print(f"    | {line}")
    print("=" * 50)


def main():
    # 确定图片路径
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
    else:
        image_path = generate_test_image()

    if not Path(image_path).exists():
        print(f"错误: 图片不存在: {image_path}")
        sys.exit(1)

    print(f"\n测试图片: {image_path}")

    # ── 测试 OCR ──
    print("\n▶ 测试 OCR 引擎 (auto) ...")
    service = get_ocr_service("auto")

    # 判断当前引擎类型
    cls_name = type(service).__name__
    engine_map = {
        "EasyOCRService": "EasyOCR (PyTorch)",
        "PaddleOCRService": "PaddleOCR PP-Structure",
        "MockOCRService": "Mock (降级)",
    }
    engine = engine_map.get(cls_name, cls_name)
    print(f"  当前引擎: {engine}")

    result = service.recognize(image_path)
    print_result(result)

    # ── 评估 ──
    print("\n▶ 提取率评估:")
    fields = ["applicant", "expense_type", "merchant", "total_amount"]
    hit = sum(1 for f in fields if getattr(result, f) is not None)
    print(f"  字段命中: {hit}/{len(fields)} ({hit*100//len(fields)}%)")


if __name__ == "__main__":
    main()
