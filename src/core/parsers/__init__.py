"""パーサパッケージ — パーサ登録

このパッケージは、利用可能なパーサを `ParserRegistry` に登録するための窓口を提供する。

以前は import の副作用で登録していたが、依存が見えにくくなるため、
`register_parsers()` を明示的に呼び出す方式にしている。
"""

from __future__ import annotations


def register_parsers() -> None:
	"""
	ドキュメント最終更新: 2026-02-15
	
	パイプラインが source_kind に応じてパーサを動的選択できるようにする。
	
	使用目的:
	    - 入力ファイルの種別（銀行CSV / Amazon TSV など）に応じて、
	      適切なパーサを実行時に選べるようにする（pipeline が if 分岐を書かずに済む）。
	    - 新しいパーサ追加時の変更箇所をここだけに局所化する。
	
	呼び出し側: pipeline.run() の冒頭で1度だけ呼ばれる。
	"""
	# ここで import することで、登録時にだけパーサ実装を読み込む。
	from src.core.parsers.bank import BankParser
	from src.core.parsers.amazon import AmazonParser
	from src.core.registry import registry

	registry.register("bank_statement", BankParser)
	registry.register("amazon_settlement_report", AmazonParser)
