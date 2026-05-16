"""
完整 LightGBM 龙头 T+0 训练管线（6步）。
用法: python scripts/train_leader_main_t0_pipeline.py [--start 20240101] [--end 20260510]
"""
import os, sys, argparse, logging, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

from backend.services.auction_data_service import AuctionDataService
from backend.services.tdx_local_daily_sync_service import TdxLocalDailySyncService
from backend.services.backtest.leader_main_t0_feature_builder import LeaderMainT0FeatureBuilder
from backend.services.backtest.leader_main_t0_label_builder import LeaderMainT0LabelBuilder
from backend.services.model_engine.lightgbm_service import train_leader_main_t0_lgbm


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="20240101")
    parser.add_argument("--end", default="20260510")
    args = parser.parse_args()

    total_start = time.time()

    # ====== Step 1: 同步集合竞价数据 ======
    logger.info(f"[Step 1/6] 同步集合竞价数据 ({args.start} ~ {args.end})")
    step_start = time.time()
    try:
        result = AuctionDataService().sync_auction_open_date_range(args.start, args.end)
        trade_dates = result.get("trade_dates", [])
        logger.info(f"  完成: synced={result.get('synced_count')}, dates={len(trade_dates)}, {time.time()-step_start:.0f}s")
    except Exception as e:
        logger.error(f"  同步竞价数据失败: {e}")
        return

    if not trade_dates:
        logger.error("  无交易日数据，退出")
        return

    # ====== Step 2: 同步本地日线数据 ======
    logger.info(f"[Step 2/6] 同步本地日线数据 ({args.start} ~ {args.end})")
    step_start = time.time()
    try:
        tdx_path = os.getenv("TDX_VIPDOC_PATH", "G:/new_tdx/vipdoc")
        sync_result = TdxLocalDailySyncService(tdx_vipdoc_path=tdx_path).sync_range(args.start, args.end)
        logger.info(f"  完成: synced={sync_result.get('rows_synced')}, {time.time()-step_start:.0f}s")
    except Exception as e:
        logger.error(f"  同步日线失败: {e}")
        return

    # ====== Step 3: 重算竞昨比 ======
    logger.info(f"[Step 3/6] 重算竞昨比 ({args.start} ~ {args.end})")
    step_start = time.time()
    try:
        recalc_result = AuctionDataService().recalculate_auction_ratios_from_daily_cache(args.start, args.end)
        logger.info(f"  完成: updated={recalc_result.get('updated_count')}, missing={recalc_result.get('missing_count')}, {time.time()-step_start:.0f}s")
    except Exception as e:
        logger.error(f"  重算竞昨比失败: {e}")
        return

    # ====== Step 4: 构建候选股特征 ======
    logger.info(f"[Step 4/6] 构建候选股特征 ({len(trade_dates)} dates)")
    step_start = time.time()
    try:
        saved = LeaderMainT0FeatureBuilder().build_leader_main_t0_range(trade_dates)
        logger.info(f"  完成: saved={saved}, {time.time()-step_start:.0f}s")
    except Exception as e:
        logger.error(f"  构建特征失败: {e}")
        return

    # ====== Step 5: 生成T+0标签 ======
    logger.info(f"[Step 5/6] 生成T+0标签 ({args.start} ~ {args.end})")
    step_start = time.time()
    try:
        updated = LeaderMainT0LabelBuilder().build_leader_main_t0_labels(args.start, args.end)
        logger.info(f"  完成: updated={updated}, {time.time()-step_start:.0f}s")
    except Exception as e:
        logger.error(f"  生成标签失败: {e}")
        return

    # ====== Step 6: 训练模型 ======
    logger.info(f"[Step 6/6] 训练 9 维 LightGBM 模型 ({args.start} ~ {args.end})")
    step_start = time.time()
    try:
        model_path = train_leader_main_t0_lgbm(args.start, args.end)
        if model_path:
            logger.info(f"  完成: {model_path}, {time.time()-step_start:.0f}s")
        else:
            logger.error("  训练失败：样本不足或其他错误")
            return
    except Exception as e:
        logger.error(f"  训练失败: {e}")
        return

    logger.info(f"全部完成! 总耗时 {time.time()-total_start:.0f}s")


if __name__ == "__main__":
    main()
