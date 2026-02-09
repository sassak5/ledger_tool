"""GUI本体 — CustomTkinter ベースのMVP画面"""

from __future__ import annotations

import tkinter as tk
import tkinter.ttk as ttk
from tkinter import filedialog, messagebox
from pathlib import Path
from typing import Any

import customtkinter as ctk

from src.core.pipeline import run as pipeline_run
from src.core.models import PipelineResult, ProcessingSummary, LedgerDraft, ValidationError


class App(ctk.CTk):
    """帳簿自動作成ツール メインウィンドウ"""

    def __init__(self) -> None:
        super().__init__()

        self.title("帳簿自動作成ツール")
        self.geometry("1200x800")
        ctk.set_appearance_mode("light")

        self._selected_files: list[str] = []
        self._summary: ProcessingSummary | None = None
        self._drafts: list[LedgerDraft] = []
        self._errors: list[ValidationError] = []
        self._output_dir: str = ""

        self._build_ui()

    def _build_ui(self) -> None:
        # --- 上部: ボタンバー ---
        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(fill="x", padx=10, pady=5)

        self._btn_select = ctk.CTkButton(
            btn_frame, text="ファイルを選択", command=self._on_select_files,
        )
        self._btn_select.pack(side="left", padx=5)

        self._lbl_files = ctk.CTkLabel(btn_frame, text="ファイル未選択")
        self._lbl_files.pack(side="left", padx=10)

        self._btn_convert = ctk.CTkButton(
            btn_frame, text="変換（帳簿作成）", command=self._on_convert,
            state="disabled",
        )
        self._btn_convert.pack(side="left", padx=5)

        self._btn_export = ctk.CTkButton(
            btn_frame, text="出力フォルダを開く", command=self._on_open_output,
            state="disabled",
        )
        self._btn_export.pack(side="left", padx=5)

        # --- タブ ---
        self._tabview = ctk.CTkTabview(self)
        self._tabview.pack(fill="both", expand=True, padx=10, pady=5)

        self._tab_log = self._tabview.add("実行ログ")
        self._tab_summary = self._tabview.add("サマリ")
        self._tab_errors = self._tabview.add("エラー/警告")
        self._tab_ledger = self._tabview.add("仕訳確認")

        # 実行ログ
        self._txt_log = ctk.CTkTextbox(self._tab_log)
        self._txt_log.pack(fill="both", expand=True)

        # サマリ
        self._txt_summary = ctk.CTkTextbox(self._tab_summary)
        self._txt_summary.pack(fill="both", expand=True)

        # エラー/警告 (Treeview)
        self._error_tree_frame = ctk.CTkFrame(self._tab_errors)
        self._error_tree_frame.pack(fill="both", expand=True)
        self._error_tree = self._create_treeview(
            self._error_tree_frame,
            columns=("row_id", "level", "field", "message", "raw_value"),
            headings=("行ID", "レベル", "フィールド", "メッセージ", "元値"),
        )

        # 仕訳確認 (Treeview)
        self._ledger_tree_frame = ctk.CTkFrame(self._tab_ledger)
        self._ledger_tree_frame.pack(fill="both", expand=True)
        self._ledger_tree = self._create_treeview(
            self._ledger_tree_frame,
            columns=("date", "debit_account", "debit_amount",
                     "credit_account", "credit_amount", "description", "partner"),
            headings=("日付", "借方科目", "借方金額", "貸方科目", "貸方金額", "摘要", "取引先"),
        )

    def _create_treeview(
        self,
        parent: ctk.CTkFrame,
        columns: tuple[str, ...],
        headings: tuple[str, ...],
    ) -> ttk.Treeview:
        """Treeview (テーブル) を作成"""
        tree_frame = tk.Frame(parent)
        tree_frame.pack(fill="both", expand=True)

        scrollbar_y = ttk.Scrollbar(tree_frame, orient="vertical")
        scrollbar_x = ttk.Scrollbar(tree_frame, orient="horizontal")

        tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            yscrollcommand=scrollbar_y.set,
            xscrollcommand=scrollbar_x.set,
        )
        scrollbar_y.config(command=tree.yview)
        scrollbar_x.config(command=tree.xview)

        for col, heading in zip(columns, headings):
            tree.heading(col, text=heading)
            tree.column(col, width=120, minwidth=60)

        scrollbar_y.pack(side="right", fill="y")
        scrollbar_x.pack(side="bottom", fill="x")
        tree.pack(fill="both", expand=True)

        return tree

    def _log(self, msg: str) -> None:
        self._txt_log.insert("end", msg + "\n")
        self._txt_log.see("end")

    def _on_select_files(self) -> None:
        files = filedialog.askopenfilenames(
            title="明細ファイルを選択",
            filetypes=[
                ("CSV/TSV ファイル", "*.csv *.tsv *.txt"),
                ("全てのファイル", "*.*"),
            ],
        )
        if files:
            self._selected_files = list(files)
            self._lbl_files.configure(text=f"{len(files)} ファイル選択済み")
            self._btn_convert.configure(state="normal")
            self._log(f"選択: {len(files)} ファイル")
            for f in files:
                self._log(f"  - {f}")

    def _on_convert(self) -> None:
        if not self._selected_files:
            messagebox.showwarning("警告", "ファイルが選択されていません")
            return

        self._log("\n--- 変換開始 ---")
        self._btn_convert.configure(state="disabled")

        rules_dir = str(Path(__file__).parent.parent / "rules")
        output_dir = str(Path(__file__).parent.parent / "outputs")

        try:
            result = pipeline_run(
                file_paths=self._selected_files,
                rules_dir=rules_dir,
                output_base_dir=output_dir,
            )
            self._summary = result.summary
            self._drafts = result.drafts
            self._errors = result.errors
            self._display_summary(result.summary)
            self._display_errors(result.errors)
            self._display_ledger(result.drafts)
            self._btn_export.configure(state="normal")
            self._log("--- 変換完了 ---")

        except Exception as e:
            self._log(f"エラー: {e}")
            messagebox.showerror("エラー", f"変換中にエラーが発生しました:\n{e}")

        finally:
            self._btn_convert.configure(state="normal")

    def _display_summary(self, summary: ProcessingSummary) -> None:
        # サマリタブ
        self._txt_summary.delete("1.0", "end")
        lines = [
            f"実行日時: {summary.run_at}",
            f"対象期間: {summary.period_start} 〜 {summary.period_end}",
            f"取込総件数: {summary.total_count}",
            f"入金合計: ¥{summary.total_in:,}",
            f"出金合計: ¥{summary.total_out:,}",
            f"仕訳候補件数: {summary.ledger_count}",
            f"エラー件数: {summary.error_count}",
            f"警告件数: {summary.warn_count}",
            "",
            "--- ファイル別 ---",
        ]
        for sf in summary.source_files:
            lines.append(f"  {sf.path}")
            lines.append(f"    フォーマット: {sf.format_id} ({sf.source_kind})")
            lines.append(f"    取込行数: {sf.row_count}")
            lines.append(f"    エラー: {sf.error_count} / 警告: {sf.warn_count}")

        self._txt_summary.insert("1.0", "\n".join(lines))

        # ログにもサマリ
        self._log(f"取込: {summary.total_count}件, 仕訳: {summary.ledger_count}件, "
                   f"エラー: {summary.error_count}, 警告: {summary.warn_count}")

    def _display_errors(self, errors: list[ValidationError]) -> None:
        """エラー/警告テーブルにデータを表示"""
        for item in self._error_tree.get_children():
            self._error_tree.delete(item)
        for e in errors:
            self._error_tree.insert("", "end", values=(
                e.row_id, e.level, e.field, e.message, e.raw_value,
            ))

    def _display_ledger(self, drafts: list[LedgerDraft]) -> None:
        """仕訳確認テーブルにデータを表示"""
        for item in self._ledger_tree.get_children():
            self._ledger_tree.delete(item)
        for d in drafts:
            self._ledger_tree.insert("", "end", values=(
                d.date, d.debit_account, f"¥{d.debit_amount:,}",
                d.credit_account, f"¥{d.credit_amount:,}",
                d.description, d.partner,
            ))

    def _on_open_output(self) -> None:
        """出力フォルダをOSのファイルマネージャで開く"""
        import subprocess, sys
        output_dir = str(Path(__file__).parent.parent / "outputs")
        if sys.platform == "win32":
            subprocess.Popen(["explorer", output_dir])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", output_dir])
        else:
            subprocess.Popen(["xdg-open", output_dir])
