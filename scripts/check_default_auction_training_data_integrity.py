"""
检查 default_auction_relay_v2 训练数据完整性。

示例:
  python scripts/check_default_auction_training_data_integrity.py
  python scripts/check_default_auction_training_data_integrity.py --json
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import SessionLocal  # noqa: E402
from backend.services.model_engine.default_auction_training_data_audit import (  # noqa: E402
    TrainingDataAuditConfig,
    audit_default_auction_training_data,
)


def _parse_args():
    parser = argparse.ArgumentParser(description="检查默认竞价接力 V2 训练数据完整性")
    parser.add_argument("--json", action="store_true", help="输出完整 JSON")
    parser.add_argument("--strict", action="store_true", help="warning 也返回非 0 退出码")
    parser.add_argument("--skip-replay-validation", action="store_true", help="跳过真实选股回放误差验证")
    parser.add_argument("--recent-real-days", type=int, default=5, help="用于回放误差验证的最近真实选股日数量")
    parser.add_argument("--min-replay-days", type=int, default=60, help="回放样本最少交易日数量")
    parser.add_argument("--min-replay-samples", type=int, default=300, help="回放样本最少数量")
    parser.add_argument("--max-replay-avg-per-day", type=float, default=15.0, help="回放样本日均数量上限")
    parser.add_argument("--max-replay-daily-count", type=int, default=40, help="单日回放样本数量上限")
    return parser.parse_args()


def _print_text(result):
    status = "PASS" if result["ok"] else "FAIL"
    print(f"[{status}] default_auction_relay_v2 训练数据完整性")
    print(f"  errors: {result['errors'] or []}")
    print(f"  warnings: {result['warnings'] or []}")

    summary = result["sample_summary"]
    print(f"  total_samples: {summary['total_count']}")
    for source, item in sorted(summary["by_source"].items()):
        print(
            "  source:"
            f" {source} count={item['count']}"
            f" days={item['distinct_trade_dates']}"
            f" range={item['min_trade_date']}~{item['max_trade_date']}"
        )

    replay_stats = result["replay_daily_stats"]
    print(
        "  replay_daily:"
        f" days={replay_stats['trade_date_count']}"
        f" avg={replay_stats['avg_count']}"
        f" max={replay_stats['max_count']}"
        f" min={replay_stats['min_count']}"
    )
    print(f"  feature_missing: {result['feature_missing_counts']}")
    print(f"  non_a_share_count: {result['code_quality']['non_a_share_count']}")

    replay_validation = result["replay_validation"]
    if replay_validation.get("checked"):
        print(
            "  replay_validation:"
            f" accepted={replay_validation.get('accepted')}"
            f" avg_recall={replay_validation.get('avg_recall')}"
            f" avg_jaccard={replay_validation.get('avg_jaccard')}"
            f" max_count_error={replay_validation.get('max_count_error')}"
            f" reject_reasons={replay_validation.get('reject_reasons') or []}"
        )
    else:
        print(f"  replay_validation: skipped ({replay_validation.get('reason')})")

    job = result["latest_training_job"]
    print(
        "  latest_job:"
        f" exists={job.get('exists')}"
        f" id={job.get('id')}"
        f" status={job.get('status')}"
        f" error={job.get('error_message')}"
    )


def main() -> int:
    args = _parse_args()
    config = TrainingDataAuditConfig(
        recent_real_days=args.recent_real_days,
        min_replay_days=args.min_replay_days,
        min_replay_samples=args.min_replay_samples,
        max_replay_avg_per_day=args.max_replay_avg_per_day,
        max_replay_daily_count=args.max_replay_daily_count,
        require_replay_validation=not args.skip_replay_validation,
    )
    db = SessionLocal()
    try:
        result = audit_default_auction_training_data(db, config)
    finally:
        db.close()

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        _print_text(result)

    if result["errors"]:
        return 1
    if args.strict and result["warnings"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
