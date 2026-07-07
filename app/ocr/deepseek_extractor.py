"""
DeepSeek 智能字段提取器 —— 两轮提取 + 布局感知 + OCR 噪声容忍。

流程：
  1. 第 1 轮：从 OCR 文本提取所有字段
  2. 第 2 轮：校验 — 金额是否合理？商户与分类是否匹配？纠正 OCR 错误
  3. 如果两轮结果不一致 → 信任第 2 轮（带校验的结果）

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
#  Prompt 定义
# ══════════════════════════════════════════════════════════

SYSTEM_PROMPT = """你是一个精确的财务票据信息提取助手。你的任务是从 OCR 识别出的文本中提取结构化报销信息。

重要规则：
- 只返回纯 JSON，不要 markdown 代码块
- 仔细分析文本的布局标注 [HEADER]/[BODY]/[FOOTER]
- [LOW-CONF] 标记的文本可能有 OCR 错误，需根据上下文推断
- 如果文本包含中文和英文混合，优先使用中文标签名
- 商户名通常在 [HEADER] 区域，合计金额通常在 [FOOTER] 区域"""

EXTRACTION_PROMPT = """从以下 OCR 文本中提取票据报销信息。

## 文本布局说明

- `[HEADER]` — 页面上部：商户名、地址、日期
- `[BODY]` — 页面中部：商品/服务明细
- `[FOOTER]` — 页面下部：合计金额、税额、付款方式
- `[LOW-CONF:XX%]` — 该行 OCR 置信度低，可能有识别错误，请根据上下文修正

## 字段定义

| 字段 | 说明 | 中英文示例 |
|------|------|-----------|
| applicant | 报销人/员工 | 报销人: 张三 / Employee: John |
| expense_type | 费用分类（见下方规则） | 交通/餐饮/住宿/办公用品 |
| merchant | 商户名称（通常在 HEADER） | 海底捞火锅 / STARBUCKS |
| total_amount | 合计金额（通常在 FOOTER，取最终总额不要取子项） | 200.00 |
| head_count | 用餐人数（默认 1） | 4 |
| invoice_date | 发票日期，YYYY-MM-DD | 2025-03-15 |
| currency | 货币：CNY/USD/EUR/GBP | CNY |
| tax_amount | 税额（没有则为 null） | 0.80 |
| line_items | 商品明细 [{name, quantity, unit_price}] | 见示例 |
| reasoning | 简短说明提取和分类的理由 | |

## 费用分类规则

根据商户名 + 商品名推断消费场景：
- **交通**: 出租车/Taxi/加油/Gas/停车/Parking/过路费/Toll/机票/Flight/巴士/Bus
- **餐饮**: 餐费/火锅/外卖/咖啡/Restaurant/Cafe/Coffee/Food/Meal/Bar/Grill
- **住宿**: 酒店/Hotel/宾馆/Motel/Inn/民宿/Lodge/房费
- **办公用品**: 文具/打印/电脑/Office/Stationery/Print/Paper/耗材

## OCR 噪声容忍

- 中文字符可能被 OCR 误识别（如"人"→"入"，"报销"→"报消"），请根据语义纠正
- 货币符号可能被误识别（如"¥"→"半"，"$"→"S"），请结合上下文判断
- 数字可能被拆分（如"200 00"→200.00），请尝试组合

## Few-shot 示例

### 示例 1：中文餐饮
OCR 文本：
---
[HEADER]
海底捞火锅望京店
[LOW-CONF:35%] 报消人：张=三
[BODY]
肥牛 1 88.00
虾滑 1 48.00
啤酒 4 64.00
[FOOTER]
[LOW-CONF:45%] 合针：200 00
日期：2025-03-15
---
输出：
{"applicant":"张三","expense_type":"餐饮","merchant":"海底捞火锅望京店","total_amount":200.0,"head_count":1,"invoice_date":"2025-03-15","currency":"CNY","tax_amount":null,"line_items":[{"name":"肥牛","quantity":1,"unit_price":88.0},{"name":"虾滑","quantity":1,"unit_price":48.0},{"name":"啤酒","quantity":4,"unit_price":16.0}],"reasoning":"商户名含'火锅'，商品为肥牛虾滑啤酒等餐饮品；OCR将'张三'误识为'张=三'、'合计'误识为'合针'、'200.00'误识为'200 00'，根据上下文纠正"}

### 示例 2：英文咖啡
OCR 文本：
---
[HEADER]
STARBUCKS COFFEE #12345
Date: 02/20/2025
[BODY]
Latte 1 $4.50
Croissant 1 $3.50
[FOOTER]
Subtotal $8.00
Tax $0.80
Total $8.80
---
输出：
{"applicant":null,"expense_type":"餐饮","merchant":"STARBUCKS COFFEE","total_amount":8.80,"head_count":1,"invoice_date":"2025-02-20","currency":"USD","tax_amount":0.80,"line_items":[{"name":"Latte","quantity":1,"unit_price":4.50},{"name":"Croissant","quantity":1,"unit_price":3.50}],"reasoning":"商户为星巴克咖啡店，商品为拿铁和可颂，典型咖啡简餐消费，推断为餐饮类"}

### 示例 3：中文出租车
OCR 文本：
---
[HEADER]
北京市出租汽车发票
日期：2025/01/10
[BODY]
[FOOTER]
金额：56.00元
---
输出：
{"applicant":null,"expense_type":"交通","merchant":"北京市出租车","total_amount":56.0,"head_count":1,"invoice_date":"2025-01-10","currency":"CNY","tax_amount":null,"line_items":[],"reasoning":"出租车发票'交通'类，车牌号忽略"}

## 当前 OCR 文本
---
{ocr_text}
---

请直接返回 JSON（不要 markdown 代码块）："""

VALIDATION_PROMPT = """你是财务票据审核员。请校验以下从 OCR 文本中提取的报销信息是否合理。

## 校验规则
1. total_amount 是否在合理范围（>0，<100000）？
2. merchant 与 expense_type 是否匹配？（如"海底捞"→餐饮 ✓，"海底捞"→交通 ✗）
3. 如果有 line_items，其单价之和的合理范围是否接近 total_amount？
4. 如果有 [LOW-CONF] 标记的行，OCR 文本可能被误读，请尝试根据上下文修正
5. 货币符号与金额是否一致？

## 原始 OCR 文本
---
{ocr_text}
---

## 提取结果
```json
{extracted_json}
```

## 修正说明
如果提取结果正确，返回 `{"valid": true}`。
如果发现错误，返回修正后的完整 JSON（格式与提取结果相同）。

请直接返回 JSON："""


def _parse_deepseek_response(content: str) -> dict:
    """解析 DeepSeek 返回的内容，提取 JSON。"""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    m = re.search(r"\{.*\}", content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    logger.warning("无法解析 DeepSeek 返回的 JSON: %s", content[:200])
    return {}


def _call_deepseek(system: str, user: str, max_tokens: int = 1000) -> Optional[str]:
    """调用 DeepSeek API，返回响应文本或 None。"""
    if not settings.DEEPSEEK_API_KEY:
        return None

    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )
        response = client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()
    except ImportError:
        logger.warning("openai 库未安装，pip install openai")
        return None
    except Exception as exc:
        logger.warning("DeepSeek API 调用失败: %s", exc)
        return None


def extract_with_deepseek(ocr_text: str) -> Optional[dict]:
    """
    两轮提取：第 1 轮提取 → 第 2 轮校验。

    Args:
        ocr_text: OCR 识别出的原始文本（可包含布局标注）

    Returns:
        dict 或 None
    """
    if not ocr_text.strip():
        return None

    # ── 第 1 轮：提取 ──
    prompt = EXTRACTION_PROMPT.replace("{ocr_text}", ocr_text)
    content = _call_deepseek(SYSTEM_PROMPT, prompt, max_tokens=1000)

    if not content:
        return None

    result = _parse_deepseek_response(content)
    if not result:
        logger.warning("第 1 轮提取 JSON 解析失败")
        return None

    logger.info(
        "第 1 轮提取: applicant=%s, type=%s, merchant=%s, amount=%s",
        result.get("applicant"), result.get("expense_type"),
        result.get("merchant"), result.get("total_amount"),
    )

    # ── 第 2 轮：校验 ──
    try:
        extracted_json = json.dumps(result, ensure_ascii=False, indent=2)
    except Exception:
        extracted_json = str(result)

    validation_user = VALIDATION_PROMPT.replace("{ocr_text}", ocr_text)
    validation_user = validation_user.replace("{extracted_json}", extracted_json)

    validated_content = _call_deepseek(
        "你是一个精确的财务审核员。只返回 JSON。",
        validation_user,
        max_tokens=1000,
    )

    if validated_content:
        validated = _parse_deepseek_response(validated_content)
        if validated:
            if validated.get("valid") is True:
                logger.info("第 2 轮校验通过，结果无需修正")
            else:
                # 移除 valid 标记，保留修正后的字段
                validated.pop("valid", None)
                result = validated
                logger.info(
                    "第 2 轮校验修正: applicant=%s, type=%s, merchant=%s, amount=%s",
                    result.get("applicant"), result.get("expense_type"),
                    result.get("merchant"), result.get("total_amount"),
                )

    logger.info(
        "最终结果: applicant=%s, type=%s, merchant=%s, amount=%s, date=%s, items=%d",
        result.get("applicant"), result.get("expense_type"),
        result.get("merchant"), result.get("total_amount"),
        result.get("invoice_date"),
        len(result.get("line_items") or []),
    )
    return result


def extract_hybrid(ocr_text: str) -> dict:
    """
    混合提取策略：两轮 DeepSeek → 正则降级。

    合并策略：
      - DeepSeek 成功提取到 total_amount → 以 AI 结果为主
      - DeepSeek 部分字段为 null → 用正则结果补充
      - DeepSeek 完全失败 → 只用正则结果
    """
    deepseek_result = extract_with_deepseek(ocr_text)

    if deepseek_result and deepseek_result.get("total_amount") is not None:
        regex_result = regex_extract_all(ocr_text)
        return _merge_results(deepseek_result, regex_result, prefer="deepseek")

    regex_result = regex_extract_all(ocr_text)

    if deepseek_result:
        return _merge_results(deepseek_result, regex_result, prefer="regex")

    return regex_result


def _merge_results(ai: dict, regex: dict, prefer: str = "deepseek") -> dict:
    """合并 AI 和正则提取结果。"""
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
