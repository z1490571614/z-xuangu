import importlib.util
import runpy
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "generate_dc_board_aliases.py"
spec = importlib.util.spec_from_file_location("generate_dc_board_aliases", SCRIPT_PATH)
alias_gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(alias_gen)


def test_split_lu_desc_tags_removes_non_theme_fragments():
    tags = alias_gen.split_lu_desc_tags("算力租赁+通信运维+5G消息+亏损收窄")

    assert tags == ["算力租赁", "通信运维", "5G消息"]


def test_build_alias_candidates_promotes_computing_rental_to_computing_concept():
    boards = [
        {"ts_code": "BK1134.DC", "name": "算力概念", "type": "概念板块"},
        {"ts_code": "BK0736.DC", "name": "通信服务", "type": "行业板块"},
    ]
    tag_stats = {
        "算力租赁": {"count": 12, "stocks": {"000889.SZ", "002217.SZ"}, "dates": {"20260508"}},
        "通信运维": {"count": 4, "stocks": {"000889.SZ"}, "dates": {"20260508"}},
    }

    result = alias_gen.build_alias_candidates(tag_stats, boards)

    assert result["auto_aliases"]["算力概念"][0]["alias"] == "算力租赁"
    assert result["auto_aliases"]["算力概念"][0]["score"] >= alias_gen.AUTO_SCORE_THRESHOLD
    assert any(item["alias"] == "通信运维" for item in result["review_candidates"])


def test_build_alias_candidates_does_not_auto_promote_short_ambiguous_tags():
    boards = [
        {"ts_code": "BK0714.DC", "name": "5G概念", "type": "概念板块"},
        {"ts_code": "BK1650.DC", "name": "通信技术", "type": "概念板块"},
    ]
    tag_stats = {
        "5G": {"count": 8, "stocks": {"000001.SZ"}, "dates": {"20260508"}},
    }

    result = alias_gen.build_alias_candidates(tag_stats, boards)

    assert "5G概念" not in result["auto_aliases"]
    assert result["review_candidates"][0]["alias"] == "5G"


def test_ascii_board_token_does_not_match_inside_english_word():
    score, reason = alias_gen.score_tag_board_match("Micro", {"name": "CRO"})

    assert score == 0
    assert reason == ""


def test_write_python_aliases_exports_repeatable_high_confidence_aliases(tmp_path):
    result = {
        "auto_aliases": {
            "算力概念": [
                {"alias": "算力租赁", "count": 12},
                {"alias": "算力概念", "count": 12},
                {"alias": "绿色算力", "count": 1},
            ],
            "机器人概念": [
                {"alias": "机器人", "count": 8},
            ],
        },
        "review_candidates": [],
    }
    output_py = tmp_path / "aliases.py"

    alias_gen.write_python_aliases(result, output_py, min_count=2)
    generated = runpy.run_path(str(output_py))["GENERATED_BOARD_ALIASES"]

    assert generated["算力概念"] == ["算力租赁"]
    assert generated["机器人概念"] == ["机器人"]
    assert "绿色算力" not in generated["算力概念"]
