"""
字段提取器 —— 从 OCR 原始文本中提取结构化字段。

支持中英文发票（中文优先，英文兜底）。
支持布局标注文本（[HEADER]/[BODY]/[FOOTER]/[LOW-CONF]）。

设计要点:
  - 每行可能是独立 OCR 检测框 → key 和 value 可能在不同行
  - OCR 会有字符识别错误（如 人→入，¥→半）→ 模式需容错
  - 金额优先匹配"合计/总计/Total"，避免选中子项金额
  - 布局标注行 [HEADER] 等不会被当作商户名或其他字段值
"""

import re
from typing import Optional


# ══════════════════════════════════════════════════════════
#  布局标签处理
# ══════════════════════════════════════════════════════════

_LAYOUT_TAG = re.compile(r"^\[(?:HEADER|BODY|FOOTER|LOW-CONF[^\]]*)\]$")
_LOW_CONF_PREFIX = re.compile(r"\[LOW-CONF:[^\]]+\]\s*")


def _clean_line(line: str) -> str:
    """去掉行首的 [LOW-CONF:XX%] 前缀，返回清理后的文本。"""
    return _LOW_CONF_PREFIX.sub("", line).strip()


def _is_layout_tag(line: str) -> bool:
    """判断该行是否仅为布局标签（[HEADER] 等）。"""
    return bool(_LAYOUT_TAG.match(line.strip()))


def _non_tag_lines(text: str) -> list[str]:
    """返回去掉布局标签行后的所有有效行。"""
    return [
        _clean_line(l) for l in text.split("\n")
        if not _is_layout_tag(l) and _clean_line(l)
    ]


def _clean_text(text: str) -> str:
    """清理 OCR 文本：去除布局标注行和 [LOW-CONF] 前缀。"""
    return "\n".join(_non_tag_lines(text))


# ── 清理后的文本缓存（避免重复清理） ──
_clean_cache: dict[str, str] = {}


def _get_clean(text: str) -> str:
    """获取清理后的文本（带缓存）。"""
    if text not in _clean_cache:
        _clean_cache[text] = _clean_text(text)
    return _clean_cache[text]


# ══════════════════════════════════════════════════════════
#  金额提取
# ══════════════════════════════════════════════════════════

# 优先：合计/总计/应付/实收/Total/Grand Total 标签后的金额
_AMOUNT_PATTERNS_PRIORITY = [
    # 中文标签
    re.compile(r"(?:金额合计|合计金额|总计|合计|总金额|应付|实收|消费金额)\s*[：:]\s*[半¥￥$€£]?\s*(\d[\d,]*\.?\d{0,2})"),
    re.compile(r"(?:金额合计|合计金额|总计|合计|总金额|应付|实收|消费金额)\s*\n\s*[半¥￥$€£]?\s*(\d[\d,]*\.?\d{0,2})"),
    # 英文标签
    re.compile(r"(?:Grand\s*Total|Total\s+Amount|Amount\s+Due|Net\s+Amount|Balance\s+Due|Total\s+Due|Invoice\s+Total)\s*[：:]\s*[$€£¥]?\s*(\d[\d,]*\.?\d{0,2})", re.IGNORECASE),
    re.compile(r"(?:Grand\s*Total|Total\s+Amount|Amount\s+Due|Net\s+Amount|Balance\s+Due|Total\s+Due|Invoice\s+Total)\s*\n\s*[$€£¥]?\s*(\d[\d,]*\.?\d{0,2})", re.IGNORECASE),
    # 简写 Total / AMOUNT: / Total $xx.xx（无冒号）
    re.compile(r"(?:^|\n)\s*(?:TOTAL|AMOUNT)\s*[：:]\s*[$€£¥]?\s*(\d[\d,]*\.?\d{0,2})", re.IGNORECASE | re.MULTILINE),
    re.compile(r"\bTotal\s+[$€£¥]?\s*(\d[\d,]*\.\d{2})", re.IGNORECASE),  # "Total $8.80"
    # £/€/¥/$ 结尾的行（仅中文符号以避免英文子项金额干扰）
    re.compile(r"[半¥￥]\s*(\d[\d\s,]*\.?\d{0,2})\s*$", re.MULTILINE),
    # OCR 容错：合计→合针/合it/合汁，总计→总针，应付→应村
    re.compile(r"(?:合[针汁计it]{1,3}|总[针计it]{1,3}|应[付村时]{1,2})\s*[：:]\s*[半¥￥$€£]?\s*(\d[\d\s,]*\.?\d{0,2})"),
]

# 兜底：任意货币符号金额（取最大的一个，避免子项金额）
_FALLBACK_AMOUNT = re.compile(r"[半¥￥$€£]\s*(\d[\d,]*\.?\d{0,2})")


def extract_amount(text: str) -> Optional[float]:
    """从文本中提取金额，优先匹配合计/总计/Total。"""
    # 先尝试优先级模式
    for pat in _AMOUNT_PATTERNS_PRIORITY:
        m = pat.search(text)
        if m:
            try:
                # 修正 OCR 常见错误：空格替代小数点 "200 00" → 200.00
                val = m.group(1).replace(",", "").replace(" ", ".")
                return float(val)
            except ValueError:
                continue

    # 兜底：取所有货币金额中最大的（通常是总额而非子项）
    amounts = []
    for m in _FALLBACK_AMOUNT.finditer(text):
        try:
            val = m.group(1).replace(",", "").replace(" ", ".")
            amounts.append(float(val))
        except ValueError:
            pass
    if amounts:
        return max(amounts)

    return None


# ══════════════════════════════════════════════════════════
#  报销人 / 员工提取（含 OCR 容错）
# ══════════════════════════════════════════════════════════

_APPLICANT_PATTERNS = [
    # ── 中文 ──
    re.compile(r"报销人\s*[：:]\s*(\S+)"),
    re.compile(r"申请人\s*[：:]\s*(\S+)"),
    re.compile(r"报销[入人]\s*[：:]\s*(\S+)"),          # OCR 容错
    re.compile(r"报[销消][入人]\s*[：:]\s*(\S+)"),      # OCR 容错
    re.compile(r"报销[入人]?\s*[：:]?\s*\n\s*(\S{2,4})"),  # 跨行
    re.compile(r"姓名\s*[：:]\s*(\S+)"),
    re.compile(r"员工\s*[：:]\s*(\S+)"),
    # ── 英文 ──
    re.compile(r"(?:Employee|Cardholder|Customer|Name)\s*[：:]\s*(\S[^\n]{1,30})", re.IGNORECASE),
    re.compile(r"(?:Employee|Cardholder|Customer)\s*\n\s*(\S[^\n]{1,30})", re.IGNORECASE),
]


def extract_applicant(text: str) -> Optional[str]:
    """从文本中提取报销人姓名。"""
    for pat in _APPLICANT_PATTERNS:
        m = pat.search(text)
        if m:
            val = m.group(1).strip()
            # 修复 OCR 伪影：去除常见错误字符
            val = re.sub(r"[=\-_|/\\]", "", val)
            val = val.strip()
            # 过滤明显误识别（纯数字、货币符号开头）
            if 2 <= len(val) <= 30 and not re.match(r"^[\d\s.,:：$€£¥半]+$", val):
                return val
    return None


# ══════════════════════════════════════════════════════════
#  商户提取
# ══════════════════════════════════════════════════════════

_MERCHANT_SINGLE_PATTERNS = [
    # ── 中文 ──
    re.compile(r"商户(?:名称)?\s*[：:]\s*(.+)"),
    re.compile(r"收款单位\s*[：:]\s*(.+)"),
    re.compile(r"店名\s*[：:]\s*(.+)"),
    re.compile(r"公司名称\s*[：:]\s*(.+)"),
    re.compile(r"销售方(?:名称)?\s*[：:]\s*(.+)"),
    # ── 英文 ──
    re.compile(r"(?:Merchant|Vendor|Store|From|Sold\s+[Bb]y|Pay\s+[Tt]o)\s*[：:]\s*(.+)", re.IGNORECASE),
]

_MERCHANT_KEY_PATTERNS = [
    # ── 中文 ──
    re.compile(r"商户(?:名称)?\s*[：:]?\s*$"),
    re.compile(r"收款单位\s*[：:]?\s*$"),
    re.compile(r"店名\s*[：:]?\s*$"),
    re.compile(r"销售方(?:名称)?\s*[：:]?\s*$"),
    # ── 英文 ──
    re.compile(r"(?:Merchant|Vendor)\s*[：:]?\s*$", re.IGNORECASE),
]


def extract_merchant(text: str) -> Optional[str]:
    """从文本中提取商户名称（支持跨行匹配）。"""
    lines = text.split("\n")

    # 方式1：同行匹配
    for pat in _MERCHANT_SINGLE_PATTERNS:
        for line in lines:
            m = pat.search(line)
            if m:
                val = m.group(1).strip()
                if len(val) >= 2 and not re.match(r"^[\d\s.,:：$€£半¥￥]+$", val):
                    return val

    # 方式2：跨行匹配（标签在上行，值在下行）
    for i, line in enumerate(lines):
        for key_pat in _MERCHANT_KEY_PATTERNS:
            if key_pat.search(line) and i + 1 < len(lines):
                val = lines[i + 1].strip()
                if len(val) >= 2 and not re.match(r"^[\d\s.,:：半¥￥$€£]+$", val):
                    return val

    # 方式3：首行启发式（英文发票商户名通常在首行）
    for line in lines:
        candidate = line.strip()
        if (
            len(candidate) >= 3
            and not re.match(r"^[\d\s.,:：半¥￥$€£\-]+$", candidate)
            and not re.search(r"(?:合计|总计|Total|Amount|Date|日期|Tax|税|Receipt|Invoice|Order)",
                              candidate, re.IGNORECASE)
        ):
            return candidate

    return None


# ══════════════════════════════════════════════════════════
#  报销类型提取（中英文分类）
# ══════════════════════════════════════════════════════════

_TYPE_PATTERNS = [
    # ── 交通 / Transport ──
    (re.compile(r"交通|出租车|打车|过路费|加油|停车|通行费|机票|Taxi|Uber|Lyft|Gas|Fuel|Toll|Parking|Ride|Transport|Bus|Metro|Subway",
                re.IGNORECASE), "交通"),
    # ── 餐饮 / Meals ──
    (re.compile(r"餐饮|餐费|食品|外卖|火锅|餐厅|饭店|食堂|Restaurant|Cafe|Coffee|Dining|Meal|Bar|Grill|Bistro|Pizza|Sushi|Buffet|Bakery|Breakfast|Lunch|Dinner",
                re.IGNORECASE), "餐饮"),
    # ── 住宿 / Lodging ──
    (re.compile(r"住宿|酒店|宾馆|旅店|民宿|房费|Hotel|Motel|Inn|Lodge|Hostel|Resort|Suite|Room",
                re.IGNORECASE), "住宿"),
    # ── 办公用品 / Office Supplies ──
    (re.compile(r"办公|文具|打印|复印|耗材|电脑|用品|Office|Stationery|Print|Paper|Ink|Toner|Pen|Notebook|Supply",
                re.IGNORECASE), "办公用品"),
]

_TYPE_LABEL_PATTERNS = [
    re.compile(r"报销[类类型]\s*[：:]\s*(\S+)"),
    re.compile(r"(?:Category|Type|Expense\s+Type)\s*[：:]\s*(\S+)", re.IGNORECASE),
]


def extract_expense_type(text: str) -> Optional[str]:
    """从文本中提取报销类型。"""
    # 优先：匹配 "报销类型" 标签后的值
    for label_pat in _TYPE_LABEL_PATTERNS:
        m = label_pat.search(text)
        if m:
            val = m.group(1)
            for pat, etype in _TYPE_PATTERNS:
                if pat.search(val):
                    return etype

    # 关键字匹配
    for pat, etype in _TYPE_PATTERNS:
        if pat.search(text):
            return etype

    return None


# ══════════════════════════════════════════════════════════
#  人数提取（中英文）
# ══════════════════════════════════════════════════════════

_HEAD_COUNT_PATTERNS = [
    # ── 中文 ──
    re.compile(r"人数\s*[：:]\s*(\d+)"),
    re.compile(r"共\s*(\d+)\s*人"),
    re.compile(r"用餐人数\s*[：:]?\s*(\d+)"),
    re.compile(r"(\d+)\s*人\s*用餐"),
    re.compile(r"(\d+)\s*人[次均]?"),
    # ── 英文 ──
    re.compile(r"(?:Guests|People|Diners|Party|Covers|Pax|Persons?)\s*[：:]\s*(\d+)", re.IGNORECASE),
    re.compile(r"(\d+)\s*(?:Guests|People|Diners|Pax)", re.IGNORECASE),
]


def extract_head_count(text: str) -> int:
    """从文本中提取参与人数，默认返回 1。"""
    for pat in _HEAD_COUNT_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                n = int(m.group(1))
                if 1 <= n <= 100:
                    return n
            except ValueError:
                continue
    return 1


# ══════════════════════════════════════════════════════════
#  日期提取（中英文）
# ══════════════════════════════════════════════════════════

_DATE_PATTERNS = [
    # ── 中文 ──
    re.compile(r"[日开票]期\s*[：:]\s*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})"),
    re.compile(r"(\d{4}年\d{1,2}月\d{1,2}[日号])"),
    # ── 英文 ──
    re.compile(r"(?:Date|Invoice\s*Date|Trans(?:action)?\s*Date|Purchase\s*Date)\s*[：:]\s*(\d{1,4}[-/]\d{1,2}[-/]\d{1,4})", re.IGNORECASE),
    re.compile(r"(?:Date|Invoice\s*Date)\s*\n\s*(\d{1,4}[-/]\d{1,2}[-/]\d{1,4})", re.IGNORECASE),
    # ── 通用 ──
    re.compile(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})"),
    re.compile(r"(\d{1,2}[-/]\d{1,2}[-/]\d{4})"),  # MM/DD/YYYY or DD/MM/YYYY
]


def extract_date(text: str) -> Optional[str]:
    """从文本中提取日期。"""
    for pat in _DATE_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1).strip()
    return None


# ══════════════════════════════════════════════════════════
#  货币检测
# ══════════════════════════════════════════════════════════

_CURRENCY_MAP = {
    "¥": "CNY", "￥": "CNY", "¥": "CNY", "CNY": "CNY", "RMB": "CNY",
    "$": "USD", "USD": "USD",
    "€": "EUR", "EUR": "EUR",
    "£": "GBP", "GBP": "GBP",
    "₩": "KRW", "KRW": "KRW",
    "¥": "JPY", "JPY": "JPY",
}


def extract_currency(text: str) -> Optional[str]:
    """检测文本中的货币类型。"""
    for symbol, code in _CURRENCY_MAP.items():
        if symbol in text:
            return code
    # 从金额模式推断
    if re.search(r"[半¥￥]", text) or re.search(r"元|块", text):
        return "CNY"
    if re.search(r"\$\s*\d", text):
        return "USD"
    if re.search(r"€\s*\d", text):
        return "EUR"
    if re.search(r"£\s*\d", text):
        return "GBP"
    return None


# ══════════════════════════════════════════════════════════
#  税额提取
# ══════════════════════════════════════════════════════════

_TAX_PATTERNS = [
    re.compile(r"(?:税[额金]|Tax(?:\s+Amount)?|VAT|GST|HST)\s*[：:]\s*[$€£¥]?\s*(\d[\d,]*\.?\d{0,2})", re.IGNORECASE),
    re.compile(r"(?:Tax|VAT|GST)\s*\n\s*[$€£¥]?\s*(\d[\d,]*\.?\d{0,2})", re.IGNORECASE),
    re.compile(r"\b(?:Tax|VAT|GST)\s+[$€£¥]?\s*(\d[\d,]*\.\d{0,2})", re.IGNORECASE),  # "Tax $0.80"
]


def extract_tax(text: str) -> Optional[float]:
    """提取税额。"""
    for pat in _TAX_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                continue
    return None


# ══════════════════════════════════════════════════════════
#  批量提取
# ══════════════════════════════════════════════════════════

def extract_all(text: str) -> dict:
    """一次性提取所有字段，返回 dict。自动去除布局标签。"""
    clean = _get_clean(text)
    return {
        "applicant": extract_applicant(clean),
        "expense_type": extract_expense_type(clean),
        "merchant": extract_merchant(clean),
        "total_amount": extract_amount(clean),
        "head_count": extract_head_count(clean),
        "invoice_date": extract_date(clean),
        "currency": extract_currency(text),   # currency 用原始文本检测符号
        "tax_amount": extract_tax(clean),
    }
