"""
字段提取器 —— 从 OCR 原始文本中提取结构化字段。

设计要点:
  - 每行可能是独立 OCR 检测框 → key 和 value 可能在不同行
  - OCR 会有字符识别错误（如 人→入，¥→半）→ 模式需容错
  - 金额优先匹配"合计/总计"，避免选中子项金额
"""

import re
from typing import Optional


# ══════════════════════════════════════════════════════════
#  金额提取
# ══════════════════════════════════════════════════════════

# 优先：合计/总计/应付/实收 标签后的金额
_AMOUNT_PATTERNS_PRIORITY = [
    re.compile(r"(?:金额合计|合计金额|总计|合计|总金额|应付|实收|消费金额)\s*[：:]\s*[半¥￥$]?\s*(\d[\d,]*\.?\d{0,2})"),
    re.compile(r"(?:金额合计|合计金额|总计|合计|总金额|应付|实收|消费金额)\s*\n\s*[半¥￥$]?\s*(\d[\d,]*\.?\d{0,2})"),
    re.compile(r"[半¥￥$]\s*(\d[\d,]*\.\d{2})\s*$", re.MULTILINE),
]

# 兜底：任意 ¥/￥ 金额（取最大的一个，避免子项金额）
_FALLBACK_AMOUNT = re.compile(r"[半¥￥$]\s*(\d[\d,]*\.?\d{0,2})")


def extract_amount(text: str) -> Optional[float]:
    """从文本中提取金额，优先匹配合计/总计。"""
    # 先尝试优先级模式
    for pat in _AMOUNT_PATTERNS_PRIORITY:
        m = pat.search(text)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                continue

    # 兜底：取所有 ¥ 金额中最大的（通常是总额而非子项）
    amounts = []
    for m in _FALLBACK_AMOUNT.finditer(text):
        try:
            amounts.append(float(m.group(1).replace(",", "")))
        except ValueError:
            pass
    if amounts:
        return max(amounts)  # 最大金额通常是总额

    return None


# ══════════════════════════════════════════════════════════
#  报销人提取（含 OCR 容错）
# ══════════════════════════════════════════════════════════

_APPLICANT_PATTERNS = [
    # 标准
    re.compile(r"报销人\s*[：:]\s*(\S+)"),
    re.compile(r"申请人\s*[：:]\s*(\S+)"),
    # OCR 容错 (人→入, 报→报)
    re.compile(r"报销[入人]\s*[：:]\s*(\S+)"),
    re.compile(r"报[销消][入人]\s*[：:]\s*(\S+)"),
    # 跨行：标签在上行，值在下行
    re.compile(r"报销[入人]?\s*[：:]?\s*\n\s*(\S{2,4})"),
    # 姓名
    re.compile(r"姓名\s*[：:]\s*(\S+)"),
    # 员工
    re.compile(r"员工\s*[：:]\s*(\S+)"),
]


def extract_applicant(text: str) -> Optional[str]:
    """从文本中提取报销人姓名。"""
    for pat in _APPLICANT_PATTERNS:
        m = pat.search(text)
        if m:
            val = m.group(1).strip()
            # 过滤明显误识别
            if len(val) >= 2 and len(val) <= 6 and not val.startswith(("¥", "￥", "半")):
                return val
    return None


# ══════════════════════════════════════════════════════════
#  商户提取
# ══════════════════════════════════════════════════════════

_MERCHANT_KEY_PATTERNS = [
    re.compile(r"商户(?:名称)?\s*[：:]?\s*$"),
    re.compile(r"收款单位\s*[：:]?\s*$"),
    re.compile(r"店名\s*[：:]?\s*$"),
    re.compile(r"销售方(?:名称)?\s*[：:]?\s*$"),
]


def extract_merchant(text: str) -> Optional[str]:
    """从文本中提取商户名称（支持跨行匹配）。"""
    lines = text.split("\n")

    # 方式1：同行匹配 "商户名称：XXX"
    single_pats = [
        re.compile(r"商户(?:名称)?\s*[：:]\s*(.+)"),
        re.compile(r"收款单位\s*[：:]\s*(.+)"),
        re.compile(r"店名\s*[：:]\s*(.+)"),
        re.compile(r"公司名称\s*[：:]\s*(.+)"),
        re.compile(r"销售方(?:名称)?\s*[：:]\s*(.+)"),
    ]
    for pat in single_pats:
        for line in lines:
            m = pat.search(line)
            if m:
                val = m.group(1).strip()
                if len(val) >= 2 and not re.match(r"^[\d\s.,:：]+$", val):
                    return val

    # 方式2：跨行匹配 "商户名称" → 下一行是商户名
    for i, line in enumerate(lines):
        for key_pat in _MERCHANT_KEY_PATTERNS:
            if key_pat.search(line) and i + 1 < len(lines):
                val = lines[i + 1].strip()
                if len(val) >= 2 and not re.match(r"^[\d\s.,:：半¥￥]+$", val):
                    return val

    return None


# ══════════════════════════════════════════════════════════
#  报销类型提取
# ══════════════════════════════════════════════════════════

_TYPE_PATTERNS = [
    (re.compile(r"交通|出租车|打车|过路费|加油|停车|通行费|机票"), "交通"),
    (re.compile(r"餐饮|餐费|食品|外卖|火锅|餐厅|饭店|食堂"), "餐饮"),
    (re.compile(r"住宿|酒店|宾馆|旅店|民宿|房费"), "住宿"),
    (re.compile(r"办公|文具|打印|复印|耗材|电脑|用品"), "办公用品"),
]


def extract_expense_type(text: str) -> Optional[str]:
    """从文本中提取报销类型。"""
    # 优先匹配 "报销类型" 标签后的值
    type_label = re.search(r"报销[类类型]\s*[：:]\s*(\S+)", text)
    if type_label:
        val = type_label.group(1)
        for pat, etype in _TYPE_PATTERNS:
            if pat.search(val):
                return etype

    # 关键字匹配
    for pat, etype in _TYPE_PATTERNS:
        if pat.search(text):
            return etype
    return None


# ══════════════════════════════════════════════════════════
#  人数提取
# ══════════════════════════════════════════════════════════

_HEAD_COUNT_PATTERNS = [
    re.compile(r"人数\s*[：:]\s*(\d+)"),
    re.compile(r"共\s*(\d+)\s*人"),
    re.compile(r"用餐人数\s*[：:]?\s*(\d+)"),
    re.compile(r"(\d+)\s*人\s*用餐"),
    re.compile(r"(\d+)\s*人[次均]?"),
]


def extract_head_count(text: str) -> int:
    """从文本中提取参与人数，默认返回 1。"""
    for pat in _HEAD_COUNT_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                n = int(m.group(1))
                if 1 <= n <= 100:  # 合理范围
                    return n
            except ValueError:
                continue
    return 1


# ══════════════════════════════════════════════════════════
#  日期提取
# ══════════════════════════════════════════════════════════

_DATE_PATTERNS = [
    re.compile(r"[日开票]期\s*[：:]\s*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})"),
    re.compile(r"(\d{4}年\d{1,2}月\d{1,2}[日号])"),
    re.compile(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})"),
]


def extract_date(text: str) -> Optional[str]:
    """从文本中提取日期。"""
    for pat in _DATE_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1).strip()
    return None


# ══════════════════════════════════════════════════════════
#  批量提取
# ══════════════════════════════════════════════════════════

def extract_all(text: str) -> dict:
    """一次性提取所有字段，返回 dict。"""
    return {
        "applicant": extract_applicant(text),
        "expense_type": extract_expense_type(text),
        "merchant": extract_merchant(text),
        "total_amount": extract_amount(text),
        "head_count": extract_head_count(text),
    }
