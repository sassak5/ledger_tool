"""エントリーポイント — GUI起動"""

import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main() -> None:
    # `python src/main.py` や VS Code の「Python ファイルを実行」でも
    # `import src...` が解決できるようにプロジェクトルートを sys.path に追加する。
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    try:
        from src.gui.app import App
        app = App()
        app.mainloop()
    except Exception as e:
        logging.error(f"起動失敗: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
