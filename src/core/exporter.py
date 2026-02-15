"""
ドキュメント最終更新: 2026-02-15

帳簿自動作成ツールのエクスポーター

GUIで帳票作成を押した時のフォーマット検出 → パース → 正規化 → バリデーション → 仕訳生成 → 出力 
の中の最終フロー

出力ファイル一覧（outputs/<timestamp>/ 配下）:
- normalized_transactions.csv: 正規化済み取引データ（全フィールド一覧）
- ledger_draft.csv: 仕訳候補（借方/貸方/金額/摘要など）
- error_report.csv: エラー/警告レポート（row_id / level / field / message / raw_value）
- smart_import.csv: 会計ソフト取込用CSV（やよい形式）
- run_log.txt: 実行ログ（サマリ・ファイル別集計・エラー件数など）
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from src.core.models import (
    ExportError,
    LedgerDraft,
    NormalizedTransaction,
    ProcessingSummary,
    ValidationError,
)


def _ensure_dir(dir_path: Path) -> None:
    """出力ディレクトリを作成（存在してもOK）"""
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise ExportError(f"出力ディレクトリ作成失敗: {dir_path} ({e})")


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    """CSVファイルを書き出す。エラーがあれば ExportError を投げる。"""
    try:
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
    except OSError as e:
        raise ExportError(f"CSV書き込み失敗: {path} ({e})")


def export_normalized(
    path: Path,
    transactions: list[NormalizedTransaction],
) -> None:
    """NormalizedTransaction(正規化済み取引データ)をnormalized_transactions.csv に出力"""
    fieldnames = [
        "source_type", "source_name", "row_id", "date",
        "summary", "details", "amount_out", "amount_in",
        "balance", "memo",
    ]
    rows = []
    for txn in transactions:
        row = {k: getattr(txn, k) for k in fieldnames}
        row["balance"] = "" if txn.balance is None else txn.balance
        rows.append(row)
    _write_csv(path, rows, fieldnames)


def export_ledger_draft(path: Path, drafts: list[LedgerDraft]) -> None:
    """LedgerDraft(仕訳候補)をledger_draft.csv に出力"""
    fieldnames = [
        "date", "debit_account", "debit_amount",
        "credit_account", "credit_amount",
        "description", "partner", "source_row_id", "tags",
    ]
    rows = []
    for d in drafts:
        row = {k: getattr(d, k) for k in fieldnames}
        row["tags"] = ",".join(d.tags)
        rows.append(row)
    _write_csv(path, rows, fieldnames)


def export_error_report(path: Path, errors: list[ValidationError]) -> None:
    """ValidationError(エラー/警告)をerror_report.csv に出力 (0件でもヘッダ付き)"""
    fieldnames = ["row_id", "level", "field", "message", "raw_value"]
    rows = [{k: getattr(e, k) for k in fieldnames} for e in errors]
    _write_csv(path, rows, fieldnames)


def export_smart_import(path: Path, drafts: list[LedgerDraft]) -> None:
    """LedgerDraft(仕訳候補)をスマート取引取込CSV(smart_import.csv / やよい用)に出力"""
    fieldnames = [
        "取引日", "借方勘定科目", "借方金額",
        "貸方勘定科目", "貸方金額",
        "摘要", "取引先", "備考",
    ]
    rows = []
    for d in drafts:
        rows.append({
            "取引日": d.date.replace("-", "/"),  # YYYY/MM/DD
            "借方勘定科目": d.debit_account,
            "借方金額": d.debit_amount,
            "貸方勘定科目": d.credit_account,
            "貸方金額": d.credit_amount,
            "摘要": d.description,
            "取引先": d.partner,
            "備考": "",
        })
    _write_csv(path, rows, fieldnames)


def export_run_log(path: Path, summary: ProcessingSummary) -> None:
    """ProcessingSummary(実行サマリ)をrun_log.txt に出力"""
    lines = [
        "=== 帳簿自動作成ツール 実行ログ ===",
        f"実行日時: {summary.run_at}",
        "",
        "--- 入力ファイル ---",
    ]
    for i, sf in enumerate(summary.source_files, 1):
        lines.append(f"[{i}] {sf.path}")
        lines.append(f"    フォーマット: {sf.format_id} ({sf.source_kind})")
        lines.append(f"    取込行数: {sf.row_count}")
        lines.append(f"    エラー: {sf.error_count}件 / 警告: {sf.warn_count}件")

    lines.extend([
        "",
        "--- サマリ ---",
        f"対象期間: {summary.period_start} 〜 {summary.period_end}",
        f"取込総件数: {summary.total_count}",
        f"入金合計: ¥{summary.total_in:,}",
        f"出金合計: ¥{summary.total_out:,}",
        f"仕訳候補件数: {summary.ledger_count}",
        f"エラー件数: {summary.error_count}",
        f"警告件数: {summary.warn_count}",
    ])

    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError as e:
        raise ExportError(f"ログ書き込み失敗: {path} ({e})")


def export_all(
    base_dir: str | Path,
    transactions: list[NormalizedTransaction],
    drafts: list[LedgerDraft],
    errors: list[ValidationError],
    summary: ProcessingSummary,
) -> str:
    """全出力ファイルを一括生成する。

    Returns:
        出力ディレクトリのパス
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(base_dir) / timestamp
    _ensure_dir(out_dir)

    export_normalized(out_dir / "normalized_transactions.csv", transactions)
    export_ledger_draft(out_dir / "ledger_draft.csv", drafts)
    export_error_report(out_dir / "error_report.csv", errors)
    export_smart_import(out_dir / "smart_import.csv", drafts)
    export_run_log(out_dir / "run_log.txt", summary)

    return str(out_dir)
