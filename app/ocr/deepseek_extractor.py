"""
DeepSeek 智能字段提取器 —— 将 OCR 原始文本 + Prompt 发送到 DeepSeek，
由大模型理解票据内容并返回结构化 JSON。

支持中英文发票，包含 few-shot 示例和商品明细提取。

DeepSeek API 兼容 OpenAI SDK，使用 openai 库调用。
"""

import json
import logging
import re
from typing import Optional

from config import settings
from app.ocr.extractors import extract_all as regex_extract_all

logger = logging.getLogger("fee_claims.ocr.deepseek")

# ══════════════════════════════════════════════════════════
#  提取 Prompt（双语 · few-shot · 商品明细）
# ══════════════════════════════════════════════════════════

SYSTEM_PROMPT = """你是一个精确的财务票据信息提取助手。你的任务是从 OCR 识别出的票据文本中提取结构化信息。

你的回复必须是纯 JSON，不包含任何 markdown 代码块或额外解释。"""

EXTRACTION_PROMPT = """从以下 OCR 文本中提取报销票据的信息。文本可能来自中文或英文发票，包含 OCR 识别错误。

## 字段说明

| 字段 | 中英文示例 |
|------|-----------|
| applicant | 报销人/Employee/Name/Cardholder |
| expense_type | 交通/餐饮/住宿/办公用品（根据商品名推断） |
| merchant | 商户名称/Merchant/Vendor |
| total_amount | 合计金额/Total（只取最终总额，不要取子项金额） |
| head_count | 用餐人数/Guests（默认 1） |
| invoice_date | 日期/Date/Invoice Date（YYYY-MM-DD 格式） |
| currency | CNY/USD/EUR/GBP/JPY/KRW |
| tax_amount | 税额/Tax/VAT（无则为 null） |
| line_items | 商品明细 [{name, quantity, unit_price}]（可为空数组） |
| reasoning | 简短说明提取和分类的理由（中文） |

## 费用类型分类规则

根据商户名称、商品名称推断消费场景：
- **交通**: 出租车/加油/停车/过路费/机票/巴士/Taxi/Uber/Gas/Fuel/Toll/Parking
- **餐饮**: 餐费/火锅/外卖/咖啡/食品/Restaurant/Cafe/Coffee/Food/Meal
- **住宿**: 酒店/宾馆/民宿/Hotel/Motel/Inn/Lodge
- **办公用品**: 文具/打印/电脑/耗材/Office/Stationery/Print/Paper

**重要**: 商品明细（如 "拿铁 Latte x2"、"肥牛 1份"）是推断 expense_type 的重要线索。

## Few-shot 示例

### 示例 1：中文餐饮发票
OCR 文本：
---
海底捞火锅望京店
用餐人数：4人
肥牛 1 88.00
虾滑 1 48.00
啤酒 4 64.00
合计：200.00
日期：2025-03-15
---
输出：
{"applicant":null,"expense_type":"餐饮","merchant":"海底捞火锅望京店","total_amount":200.0,"head_count":4,"invoice_date":"2025-03-15","currency":"CNY","tax_amount":null,"line_items":[{"name":"肥牛","quantity":1,"unit_price":88.0},{"name":"虾滑","quantity":1,"unit_price":48.0},{"name":"啤酒","quantity":4,"unit_price":16.0}],"reasoning":"商户名含'火锅'，商品为肥牛虾滑啤酒等餐饮项目，4人用餐，推断为餐饮类"}

### 示例 2：英文咖啡店发票
OCR 文本：
---
STARBUCKS COFFEE #12345
123 Main Street
Date: 02/20/2025
Latte 1 $4.50
Croissant 1 $3.50
Subtotal $8.00
Tax $0.80
Total $8.80
---
输出：
{"applicant":null,"expense_type":"餐饮","merchant":"STARBUCKS COFFEE","total_amount":8.80,"head_count":1,"invoice_date":"2025-02-20","currency":"USD","tax_amount":0.80,"line_items":[{"name":"Latte","quantity":1,"unit_price":4.50},{"name":"Croissant","quantity":1,"unit_price":3.50}],"reasoning":"商户为星巴克咖啡店，商品为拿铁和可颂，典型的咖啡简餐消费，推断为餐饮类"}

### 示例 3：中文出租车发票
OCR 文本：
---
北京市出租汽车发票
车号：京B12345
日期：2025/01/10
金额：56.00元
---
输出：
{"applicant":null,"expense_type":"交通","merchant":"北京市出租车","total_amount":56.0,"head_count":1,"invoice_date":"2025-01-10","currency":"CNY","tax_amount":null,"line_items":[],"reasoning":"出租车发票，商户为出租车公司，金额为车费，推断为交通类"}

## 当前 OCR 文本
---
{ocr_text}
---

请直接返回 JSON（不要 markdown 代码块）："""


def _parse_deepseek_response(content: str) -> dict:
    """解析 DeepSeek 返回的内容，提取 JSON。"""
    # 尝试直接解析
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # 尝试从 markdown 代码块中提取
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试找到第一个 { 到最后一个 }
    m = re.search(r"\{.*\}", content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    logger.warning("无法解析 DeepSeek 返回的 JSON: %s", content[:200])
    return {}


def extract_with_deepseek(ocr_text: str) -> Optional[dict]:
    """
    将 OCR 文本发送到 DeepSeek 进行智能提取。

    Args:
        ocr_text: OCR 识别出的原始文本

    Returns:
        {"applicant": ..., "expense_type": ..., ...} 或 None（API 不可用时）
    """
    if not settings.DEEPSEEK_API_KEY:
        logger.warning("DEEPSEEK_API_KEY 未配置，跳过 DeepSeek 提取")
        return None

    if not ocr_text.strip():
        return None

    prompt = EXTRACTION_PROMPT.replace("{ocr_text}", ocr_text)

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )

        response = client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=1000,  # 增加 token 预算以容纳 line_items
        )

        content = response.choices[0].message.content.strip()
        logger.info("DeepSeek 返回 (%d chars): %s", len(content), content[:300])

        result = _parse_deepseek_response(content)
        if result:
            logger.info(
                "DeepSeek 提取成功: applicant=%s, type=%s, merchant=%s, amount=%s, date=%s, items=%d",
                result.get("applicant"), result.get("expense_type"),
                result.get("merchant"), result.get("total_amount"),
                result.get("invoice_date"),
                len(result.get("line_items") or []),
            )
            return result
        else:
            logger.warning("DeepSeek 返回解析失败，降级到正则提取")
            return None

    except ImportError:
        logger.warning("openai 库未安装，无法使用 DeepSeek。pip install openai")
        return None
    except Exception as exc:
        logger.warning("DeepSeek API 调用失败: %s，降级到正则提取", exc)
        return None


def extract_hybrid(ocr_text: str) -> dict:
    """
    混合提取策略：优先 DeepSeek，失败时降级到正则提取。

    合并策略：
      - DeepSeek 成功提取到 total_amount → 以 AI 结果为主
      - DeepSeek 部分字段为 null → 用正则结果补充
      - DeepSeek 完全失败 → 只用正则结果

    返回统一 dict，包含所有字段。
    """
    # ── 尝试 DeepSeek ──
    deepseek_result = extract_with_deepseek(ocr_text)

    if deepseek_result and deepseek_result.get("total_amount") is not None:
        # ── DeepSeek 成功 — 以 AI 为主，缺失字段用正则补 ──
        regex_result = regex_extract_all(ocr_text)
        return _merge_results(deepseek_result, regex_result, prefer="deepseek")

    # ── DeepSeek 失败 — 降级到正则 ──
    regex_result = regex_extract_all(ocr_text)

    # 如果有 DeepSeek 的部分结果（有值但没 total_amount），合并
    if deepseek_result:
        return _merge_results(deepseek_result, regex_result, prefer="regex")

    return regex_result


def _merge_results(ai: dict, regex: dict, prefer: str = "deepseek") -> dict:
    """
    合并 AI 和正则的提取结果。

    Args:
        ai: DeepSeek 返回的字段
        regex: 正则提取的字段
        prefer: "deepseek" = AI 优先；"regex" = 正则优先
    """
    if prefer == "deepseek":
        primary, fallback = ai, regex
    else:
        primary, fallback = regex, ai

    return {
        "applicant": primary.get("applicant") or fallback.get("applicant"),
        "expense_type": primary.get("expense_type") or fallback.get("expense_type"),
        "merchant": primary.get("merchant") or fallback.get("merchant"),
        "total_amount": primary.get("total_amount") or fallback.get("total_amount"),
        "head_count": primary.get("head_count") or fallback.get("head_count", 1),
        "invoice_date": primary.get("invoice_date") or fallback.get("invoice_date"),
        "currency": primary.get("currency") or fallback.get("currency"),
        "tax_amount": primary.get("tax_amount") or fallback.get("tax_amount"),
        "line_items": primary.get("line_items") or [],
        "reasoning": primary.get("reasoning"),
    }
