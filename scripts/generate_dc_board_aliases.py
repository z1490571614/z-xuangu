"""生成同花顺涨停标签到东财板块的别名候选。

默认抓取近 30 个交易日的 limit_list_ths 涨停池，和 dc_index 板块词典做模糊匹配，
输出高置信自动别名与待人工复核候选。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.services.dc_board_service import DC_BOARD_TYPES
from backend.utils.tushare_client import get_tushare_pro


AUTO_SCORE_THRESHOLD = 95
REVIEW_SCORE_THRESHOLD = 58
MAX_REVIEW_PER_TAG = 3

IGNORE_TAG_KEYWORDS = (
    "亏损", "扭亏", "减亏", "业绩", "净利润", "同比", "增长", "下降", "预增", "预亏",
    "中报", "年报", "一季报", "三季报", "摘帽", "复牌", "停牌", "公告", "回购",
)

BOARD_SUFFIX_PATTERN = re.compile(
    r"(概念|板块|行业|产业|服务|业务|应用|技术|设备|工程|经济|指数|主题|方向)$"
)

EXPLICIT_BOARD_BRIDGES = {
    "算力概念": {"算力", "算力租赁", "智算", "智算中心", "智算租赁", "智算租赁服务", "AI算力"},
}


def clean_text(text: str) -> str:
    return re.sub(r"[\s,，/、;；|｜（）()【】\[\]：:._-]+", "", str(text or "")).upper()


def strip_board_suffix(text: str) -> str:
    clean = clean_text(text)
    previous = None
    while clean and clean != previous:
        previous = clean
        clean = BOARD_SUFFIX_PATTERN.sub("", clean)
    return clean


def split_lu_desc_tags(lu_desc: str) -> List[str]:
    tags: List[str] = []
    seen = set()
    for raw in re.split(r"[+＋,，/、;；|｜\s]+", str(lu_desc or "")):
        tag = raw.strip()
        clean = clean_text(tag)
        if len(clean) < 2:
            continue
        if any(keyword in tag for keyword in IGNORE_TAG_KEYWORDS):
            continue
        if clean in seen:
            continue
        seen.add(clean)
        tags.append(tag)
    return tags


def _is_ascii_short(text: str) -> bool:
    return len(text) <= 2 and all(ord(ch) < 128 for ch in text)


def _is_ascii_token(text: str) -> bool:
    return bool(text) and all(ord(ch) < 128 for ch in text)


def _contains_ascii_token(haystack: str, needle: str) -> bool:
    start = haystack.find(needle)
    while start >= 0:
        before = haystack[start - 1] if start > 0 else ""
        after_index = start + len(needle)
        after = haystack[after_index] if after_index < len(haystack) else ""
        before_ok = not before or not before.isascii() or not before.isalnum()
        after_ok = not after or not after.isascii() or not after.isalnum()
        if before_ok and after_ok:
            return True
        start = haystack.find(needle, start + 1)
    return False


def _explicit_bridge_score(tag_core: str, board_name: str) -> int:
    for board_alias, aliases in EXPLICIT_BOARD_BRIDGES.items():
        board_terms = {clean_text(board_alias), strip_board_suffix(board_alias)}
        if clean_text(board_name) not in board_terms and strip_board_suffix(board_name) not in board_terms:
            continue
        terms = {clean_text(item) for item in aliases}
        if any(term and term in tag_core for term in terms):
            return 118
    return 0


def score_tag_board_match(tag: str, board: Dict[str, Any]) -> Tuple[int, str]:
    board_name = str(board.get("name", "") or "")
    tag_clean = clean_text(tag)
    board_clean = clean_text(board_name)
    tag_core = strip_board_suffix(tag)
    board_core = strip_board_suffix(board_name)
    if not tag_clean or not board_clean:
        return 0, ""

    if tag_clean == board_clean or tag_core == board_core:
        return 140, "精确命中"

    bridge_score = _explicit_bridge_score(tag_core, board_name)
    if bridge_score:
        return bridge_score, "主题族命中"

    if len(board_core) >= 3 and (
        (_is_ascii_token(board_core) and _contains_ascii_token(tag_clean, board_core))
        or (not _is_ascii_token(board_core) and board_core in tag_clean)
    ):
        return 112, "标签包含板块核心词"
    if len(tag_core) >= 3 and (
        (_is_ascii_token(tag_core) and _contains_ascii_token(board_clean, tag_core))
        or (not _is_ascii_token(tag_core) and tag_core in board_clean)
    ):
        return 104, "板块包含标签核心词"

    prefix_len = 0
    for left, right in zip(tag_core, board_core):
        if left != right:
            break
        prefix_len += 1
    if prefix_len >= 2 and not _is_ascii_short(tag_core[:prefix_len]):
        return min(92, 68 + prefix_len * 8), "核心词前缀相同"

    if len(tag_core) >= 4 and len(board_core) >= 4:
        ratio = SequenceMatcher(None, tag_core, board_core).ratio()
        if ratio >= 0.62:
            return int(85 * ratio), "字符相似"

    return 0, ""


def build_alias_candidates(
    tag_stats: Dict[str, Dict[str, Any]],
    boards: List[Dict[str, Any]],
    auto_threshold: int = AUTO_SCORE_THRESHOLD,
) -> Dict[str, Any]:
    auto_aliases: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    review_candidates: List[Dict[str, Any]] = []

    for tag, stats in sorted(tag_stats.items(), key=lambda item: item[1]["count"], reverse=True):
        matches = []
        for board in boards:
            score, reason = score_tag_board_match(tag, board)
            if score < REVIEW_SCORE_THRESHOLD:
                continue
            matches.append({
                "alias": tag,
                "board_name": board.get("name", ""),
                "board_code": board.get("ts_code", ""),
                "board_type": board.get("type", ""),
                "score": score,
                "reason": reason,
                "count": stats["count"],
                "stock_count": len(stats.get("stocks", [])),
                "date_count": len(stats.get("dates", [])),
                "sample_stocks": sorted(stats.get("stocks", []))[:8],
            })

        matches.sort(key=lambda item: (item["score"], item["count"], item["stock_count"]), reverse=True)
        if not matches:
            continue

        best = matches[0]
        if best["score"] >= auto_threshold and not _is_ascii_short(clean_text(tag)):
            auto_aliases[best["board_name"]].append(best)
            review_candidates.extend(matches[1:MAX_REVIEW_PER_TAG])
        else:
            review_candidates.extend(matches[:MAX_REVIEW_PER_TAG])

    for aliases in auto_aliases.values():
        aliases.sort(key=lambda item: (item["score"], item["count"]), reverse=True)
    review_candidates.sort(key=lambda item: (item["score"], item["count"]), reverse=True)

    return {
        "auto_aliases": dict(auto_aliases),
        "review_candidates": review_candidates,
    }


def fetch_recent_trading_dates(pro: Any, end_date: str, days: int) -> List[str]:
    start = (datetime.strptime(end_date, "%Y%m%d") - timedelta(days=days * 3)).strftime("%Y%m%d")
    df = pro.trade_cal(exchange="SSE", start_date=start, end_date=end_date, is_open="1")
    if df is None or df.empty:
        return []
    dates = sorted(str(item) for item in df["cal_date"].dropna().tolist())
    return dates[-days:]


def fetch_dc_boards(pro: Any, trade_date: str) -> List[Dict[str, Any]]:
    boards: List[Dict[str, Any]] = []
    seen = set()
    for board_type in DC_BOARD_TYPES:
        df = pro.dc_index(trade_date=trade_date, idx_type=board_type)
        if df is None or df.empty:
            continue
        for _, row in df.iterrows():
            code = str(row.get("ts_code", "") or "")
            name = str(row.get("name", "") or "")
            if not code or not name or code in seen:
                continue
            seen.add(code)
            boards.append({"ts_code": code, "name": name, "type": str(row.get("idx_type", board_type) or board_type)})
    return boards


def collect_limit_tag_stats(pro: Any, trade_dates: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    tag_stats: Dict[str, Dict[str, Any]] = {}
    for trade_date in trade_dates:
        df = pro.limit_list_ths(trade_date=trade_date, limit_type="涨停池")
        if df is None or df.empty or "lu_desc" not in df.columns:
            continue
        for _, row in df.iterrows():
            ts_code = str(row.get("ts_code", "") or "")
            for tag in split_lu_desc_tags(str(row.get("lu_desc", "") or "")):
                stats = tag_stats.setdefault(tag, {"count": 0, "stocks": set(), "dates": set()})
                stats["count"] += 1
                if ts_code:
                    stats["stocks"].add(ts_code)
                stats["dates"].add(trade_date)
    return tag_stats


def _json_ready(value: Any) -> Any:
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def write_reports(result: Dict[str, Any], output_json: Path, output_md: Path) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(_json_ready(result), ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 东财板块别名候选报告",
        "",
        f"- 交易日数量: {len(result['trade_dates'])}",
        f"- 涨停标签数量: {result['tag_count']}",
        f"- 东财板块数量: {result['board_count']}",
        f"- 高置信板块数: {len(result['auto_aliases'])}",
        f"- 待复核候选数: {len(result['review_candidates'])}",
        "",
        "## 高置信别名",
        "",
    ]
    for board_name, aliases in result["auto_aliases"].items():
        alias_text = "、".join(f"{item['alias']}({item['score']}/{item['count']}次)" for item in aliases)
        lines.append(f"- {board_name}: {alias_text}")
    lines.extend(["", "## 待复核 Top 80", ""])
    for item in result["review_candidates"][:80]:
        lines.append(
            f"- {item['alias']} -> {item['board_name']} "
            f"({item['score']}分, {item['reason']}, {item['count']}次)"
        )
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_python_aliases(result: Dict[str, Any], output_py: Path, min_count: int = 2) -> None:
    aliases_by_board: Dict[str, List[str]] = {}
    for board_name, aliases in result["auto_aliases"].items():
        values = []
        seen = set()
        for item in aliases:
            alias = str(item.get("alias", "") or "").strip()
            if not alias or item.get("count", 0) < min_count:
                continue
            if clean_text(alias) == clean_text(board_name):
                continue
            if alias in seen:
                continue
            seen.add(alias)
            values.append(alias)
        if values:
            aliases_by_board[board_name] = values

    output_py.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        '"""自动生成的东财板块别名映射。',
        "",
        "来源: scripts/generate_dc_board_aliases.py",
        "说明: 仅包含近 30 个交易日中出现次数达到阈值的高置信候选。",
        '"""',
        "",
        "GENERATED_BOARD_ALIASES = {",
    ]
    for board_name in sorted(aliases_by_board):
        aliases = ", ".join(json.dumps(alias, ensure_ascii=False) for alias in aliases_by_board[board_name])
        lines.append(f"    {json.dumps(board_name, ensure_ascii=False)}: [{aliases}],")
    lines.append("}")
    output_py.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--end-date", default=datetime.now().strftime("%Y%m%d"))
    parser.add_argument("--output-json", default="data/dc_board_alias_candidates.json")
    parser.add_argument("--output-md", default="data/dc_board_alias_candidates.md")
    parser.add_argument("--output-py", default="")
    parser.add_argument("--py-min-count", type=int, default=2)
    args = parser.parse_args()

    pro = get_tushare_pro()
    trade_dates = fetch_recent_trading_dates(pro, args.end_date, args.days)
    if not trade_dates:
        raise RuntimeError("未获取到交易日")

    boards = fetch_dc_boards(pro, trade_dates[-1])
    tag_stats = collect_limit_tag_stats(pro, trade_dates)
    candidates = build_alias_candidates(tag_stats, boards)
    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "trade_dates": trade_dates,
        "tag_count": len(tag_stats),
        "board_count": len(boards),
        "auto_aliases": candidates["auto_aliases"],
        "review_candidates": candidates["review_candidates"],
    }
    write_reports(result, Path(args.output_json), Path(args.output_md))
    if args.output_py:
        write_python_aliases(result, Path(args.output_py), min_count=args.py_min_count)
    print(json.dumps({
        "trade_dates": len(trade_dates),
        "tag_count": len(tag_stats),
        "board_count": len(boards),
        "auto_board_count": len(candidates["auto_aliases"]),
        "review_count": len(candidates["review_candidates"]),
        "output_json": args.output_json,
        "output_md": args.output_md,
        "output_py": args.output_py,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
