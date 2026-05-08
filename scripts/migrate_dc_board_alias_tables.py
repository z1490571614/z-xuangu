"""创建东财动态板块别名相关表。"""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.database import Base, engine
from backend.models.board import DcBoardAlias, DcBoardAliasObservation, DcBoardAliasSyncState


def main():
    Base.metadata.create_all(
        bind=engine,
        tables=[
            DcBoardAlias.__table__,
            DcBoardAliasObservation.__table__,
            DcBoardAliasSyncState.__table__,
        ],
    )
    print("东财动态板块别名表创建完成")


if __name__ == "__main__":
    main()
