"""
DeepSeek 智能字段提取器 —— 将 OCR 原始文本 + Prompt 发送到 DeepSeek，
由大模型理解票据内容并返回结构化 JSON。

DeepSeek API 兼容 OpenAI SDK，使用 openai 库调用。
"""

import json
import logging
import re
from typing import Optional

from config import settings
from app.ocr.extractors import extract_all as regex_extract_all

logger = logging.getLogger("fee_claims.ocr.deepseek")

# ── 提取 Prompt ─────────────────────────────────────────

EXTRACTION_PROMPT = """你是一个财务票据信息提取助手。请从以下 OCR 识别出的文本中提取报销相关信息。

要求：
1. 仔细阅读 OCR 文本，理解票据内容
2. 提取以下字段，返回纯 JSON（不要 markdown 代码块，不要额外解释）
3. 如果某个字段无法从文本中确定，值设为 null
4. total_amount 必须是数字（浮点数），去除货币符号如 ¥ 或 ￥
5. head_count 默认为 1

返回 JSON 格式：
{{
  "applicant": "报销人姓名",
  "expense_type": "交通|餐饮|住宿|办公用品",
  "merchant": "商户名称",
  "total_amount": 数字,
  "head_count": 数字
}}

OCR 识别文本：
---
{ocr_text}
---

请直接返回 JSON："""


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
        {"applicant": ..., ...} 或 None（API 不可用时）
    """
    if not settings.DEEPSEEK_API_KEY:
        logger.warning("DEEPSEEK_API_KEY 未配置，跳过 DeepSeek 提取")
        return None

    if not ocr_text.strip():
        return None

    prompt = EXTRACTION_PROMPT.format(ocr_text=ocr_text)

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )

        response = client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": "你是一个精确的财务数据提取助手。只返回 JSON，不返回其他内容。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,  # 确定性输出
            max_tokens=500,
        )

        content = response.choices[0].message.content.strip()
        logger.info("DeepSeek 返回: %s", content[:200])

        result = _parse_deepseek_response(content)
        if result:
            logger.info(
                "DeepSeek 提取成功: applicant=%s, type=%s, merchant=%s, amount=%s",
                result.get("applicant"), result.get("expense_type"),
                result.get("merchant"), result.get("total_amount"),
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

    这是推荐的生产环境使用方法。
    """
    # 尝试 DeepSeek
    deepseek_result = extract_with_deepseek(ocr_text)

    if deepseek_result and deepseek_result.get("total_amount") is not None:
        # DeepSeek 成功提取到了金额 → 信任 AI 结果
        return {
            "applicant": deepseek_result.get("applicant"),
            "expense_type": deepseek_result.get("expense_type"),
            "merchant": deepseek_result.get("merchant"),
            "total_amount": deepseek_result.get("total_amount"),
            "head_count": deepseek_result.get("head_count", 1),
        }

    # 降级：不规则提取
    regex_result = regex_extract_all(ocr_text)

    # 如果有 DeepSeek 的部分结果，合并（DeepSeek 优先）
    if deepseek_result:
        return {
            "applicant": deepseek_result.get("applicant") or regex_result["applicant"],
            "expense_type": deepseek_result.get("expense_type") or regex_result["expense_type"],
            "merchant": deepseek_result.get("merchant") or regex_result["merchant"],
            "total_amount": deepseek_result.get("total_amount") or regex_result["total_amount"],
            "head_count": deepseek_result.get("head_count") or regex_result["head_count"],
        }

    return regex_result
