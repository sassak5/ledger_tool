"""エントリーポイント — GUI起動

起動時に以下を行う:
1. プロジェクトルートを sys.path に追加
2. データディレクトリ (src/data/) を初期化
3. App を起動
"""

import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


def _ensure_data_dir() -> None:
    """データディレクトリ (src/data/) を作成する。

    資金管理モジュールの SQLite DB ファイル (cash.db) がここに格納される。
    """
    data_dir = Path(__file__).parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    logger.info("データディレクトリ確認: %s", data_dir)


def main() -> None:
    # `python src/main.py` や VS Code の「Python ファイルを実行」でも
    # `import src...` が解決できるようにプロジェクトルートを sys.path に追加する。
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    _ensure_data_dir()

    try:
        from src.gui.app import App
        app = App()
        app.mainloop()
    except Exception as e:
        logging.error(f"起動失敗: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
