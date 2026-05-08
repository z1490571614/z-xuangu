import re

CARRIER_WORDS = [
    "公告", "公告称", "发布公告", "披露", "信息披露",
    "发布", "刊发", "刊登", "表示", "称", "显示",
]


def normalize_text(title: str, content: str = "") -> str:
    text = f"{title or ''}。{content or ''}"
    text = text.replace(" ", "")
    text = text.replace("\n", "")
    text = text.replace("\t", "")
    text = text.replace("％", "%")
    text = text.replace("，", ",")
    text = text.replace("。", ".")
    return text


def extract_percentage(text: str) -> list:
    """抽取百分比数值"""
    return [float(x) for x in re.findall(r"(\d+\.?\d*)%", text)]


def extract_amount(text: str) -> list:
    """抽取金额数值（万元/亿元）并转为元"""
    amounts = []
    for m in re.finditer(r"(\d+\.?\d*)\s*万亿", text):
        amounts.append(float(m.group(1)) * 1e12)
    for m in re.finditer(r"(\d+\.?\d*)\s*亿", text):
        amounts.append(float(m.group(1)) * 1e8)
    for m in re.finditer(r"(\d+\.?\d*)\s*万", text):
        amounts.append(float(m.group(1)) * 1e4)
    for m in re.finditer(r"(\d+\.?\d*)\s*元", text):
        amounts.append(float(m.group(1)))
    return amounts


def extract_stock_count(text: str) -> list:
    """抽取股票数量（万股/亿股）并转为股"""
    counts = []
    for m in re.finditer(r"(\d+\.?\d*)\s*万亿股", text):
        counts.append(float(m.group(1)) * 1e12)
    for m in re.finditer(r"(\d+\.?\d*)\s*亿股", text):
        counts.append(float(m.group(1)) * 1e8)
    for m in re.finditer(r"(\d+\.?\d*)\s*万股", text):
        counts.append(float(m.group(1)) * 1e4)
    return counts
