"""
诊断 default_auction_t1_premium_lgbm 溢价模型。

示例:
  python scripts/diagnose_default_auction_t1_premium.py
  python scripts/diagnose_default_auction_t1_premium.py --json
  python scripts/diagnose_default_auction_t1_premium.py --output output/t1_premium_diagnostic.json
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import SessionLocal  # noqa: E402
from backend.services.model_engine.default_auction_t1_diagnostic import (  # noqa: E402
    diagnose_t1_premium_model,
)


def _parse_args():
    parser = argparse.ArgumentParser(description="诊断默认竞价接力 T1 溢价模型")
    parser.add_argument("--json", action="store_true", help="只输出完整 JSON")
    parser.add_argument("--output", help="保存完整 JSON 报告到指定路径")
    return parser.parse_args()


def _print_text(result):
    active = result["active_model"]
    samples = result["current_samples"]
    labels = result["label_distribution"]
    prediction = result.get("prediction_diagnostics") or {}
    distribution = prediction.get("distribution") or {}
    bucket_summary = prediction.get("bucket_summary") or {}

    print("[T1溢价模型诊断] default_auction_t1_premium_lgbm")
    print(f"  标签口径: {result['label_rule']}")
    print(
        "  活跃模型:"
        f" version={active.get('version')}"
        f" file_exists={active.get('model_file_exists')}"
        f" trained_samples={(active.get('metrics') or {}).get('sample_count')}"
        f" auc={(active.get('metrics') or {}).get('auc')}"
    )
    print(
        "  当前样本:"
        f" raw={samples['raw_count']}"
        f" dedup={samples['dedup_count']}"
        f" range={samples['date_range'][0]}~{samples['date_range'][1]}"
    )
    print(
        "  标签分布:"
        f" total={labels['total']}"
        f" positive={labels['positive']}"
        f" negative={labels['negative']}"
        f" positive_rate={labels['positive_rate']}"
    )
    print(
        "  预测分布:"
        f" min={distribution.get('min')}"
        f" p50={distribution.get('p50')}"
        f" max={distribution.get('max')}"
        f" spread={bucket_summary.get('probability_spread')}"
    )
    print("  分层命中:")
    for bucket in bucket_summary.get("buckets") or []:
        print(
            "   -"
            f" {bucket['bucket']}:"
            f" count={bucket['count']}"
            f" prob={bucket['prob_min']}~{bucket['prob_max']}"
            f" hit_rate={bucket['hit_rate']}"
            f" lift={bucket['lift']}"
        )
    print(f"  发现: {result['findings']}")
    print(f"  建议: {result['recommendations']}")


def main() -> int:
    args = _parse_args()
    db = SessionLocal()
    try:
        result = diagnose_t1_premium_model(db)
    finally:
        db.close()

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        _print_text(result)
        if args.output:
            print(f"  JSON报告: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
