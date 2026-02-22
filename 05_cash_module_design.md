# 資金管理モジュール 設計書
更新日: 2026-02-21

---

## 0. 設計方針サマリ

| 方針 | 内容 |
|------|------|
| **既存パイプライン非侵襲** | `core/` は一切変更しない。資金管理モジュール (`cash/`) は既存の仕訳CSV出力を**読み取り専用**で参照するのみ |
| **一方向依存** | 既存パイプラインは `cash/` の存在を知らない。`cash/` → `core/outputs/` の参照のみ |
| **データソース抽象化** | 手入力・SP-API・CSV取込・仕訳CSV参照を共通インターフェース (`EntrySource`) で統一 |
| **設定駆動** | プルダウン項目・SP-API設定・CSV取込定義はすべて YAML |
| **拡張可能** | 新しい販路・仕入先は YAML 追加のみ。新しい取込形式は `EntrySource` 実装の追加のみ |
| **ストレージ独立** | MVP は SQLite。将来的な DB 移行に備え、リポジトリパターンで抽象化 |

---

## 1. アーキテクチャ概要

### 1.1 依存関係図

```
┌─────────────────────────────────────────────┐
│  既存パイプライン (src/core/)                 │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │ detector │→ │ parsers  │→ │ normalizer│  │
│  └──────────┘  └──────────┘  └─────┬─────┘  │
│                                    ↓        │
│  ┌───────────┐  ┌──────────────────────┐    │
│  │ validator │→ │ ledger_generator     │    │
│  └───────────┘  └──────────┬───────────┘    │
│                            ↓                │
│                    ┌──────────────┐         │
│                    │   exporter   │         │
│                    └──────┬───────┘         │
│                           ↓                 │
│                  outputs/YYYYMMDD_HHMMSS/   │
│                  ├── ledger_draft.csv       │
│                  ├── normalized_transactions│
│                  └── ...                    │
└─────────────────────┬───────────────────────┘
                      │ 読み取り専用（一方向）
                      ▼
┌─────────────────────────────────────────────┐
│  資金管理モジュール (src/cash/)               │
│                                             │
│  ┌── sources/ ──────────────────────────┐   │
│  │ manual.py   ← GUI手入力              │    │
│  │ spapi.py    ← Amazon SP-API 自動取得  │   │
│  │ csv_import.py ← 汎用CSV取込（将来）   │    │
│  │ ledger_ref.py ← 仕訳CSV参照          │    │
│  └──────────────────┬───────────────────┘   │
│                      ↓                      │
│              ┌──────────────┐               │
│              │   storage    │  SQLite       │
│              └──────┬───────┘               │
│                     ↓                       │
│  ┌──────────────────────────────────────┐   │
│  │  engine.py   残高計算・日別集計        │   │
│  │  reconciler.py 仕訳CSV突合・警告      │   │
│  └──────────────────┬───────────────────┘   │
│                      ↓                      │
│              GUI (cash_tab.py)              │
│              ├── 残高一覧                    │
│              ├── 入力フォーム                │
│              └── 将来: グラフ表示            │
└─────────────────────────────────────────────┘
```

### 1.2 データフロー

```
[売上入力]
  手入力（GUI）────────┐
  SP-API（自動取得）───┤
  売上CSV（将来）──────┤
                      ├→ CashEntry 生成 → storage 保存
[仕入入力]             │
  手入力（GUI）────────┤
  クレカCSV（将来）────┘

[参照]
  既存仕訳CSV ──→ ledger_ref.py ──→ ReconciliationResult（警告のみ）

[出力]
  storage ──→ engine.py ──→ AccountBalance（残高一覧）
                          ──→ DailySummary（日別集計、将来グラフ用）
```

---

## 2. ディレクトリ構成

```
src/
├── main.py                              # エントリーポイント（変更なし）
├── core/                                # 既存パイプライン（変更なし）
│   ├── models.py
│   ├── pipeline.py
│   ├── detector.py
│   ├── base_parser.py
│   ├── parsers/
│   │   ├── bank.py
│   │   └── amazon.py
│   ├── normalizer.py
│   ├── validator.py
│   ├── ledger_generator.py
│   ├── exporter.py
│   ├── registry.py
│   └── ruleset/
│       └── loader.py
│
├── cash/                                # ★ 新規: 資金管理モジュール# TODO: 全部未確認
│   ├── __init__.py
│   ├── models.py                        # CashEntry, AccountBalance, DailySummary 等
│   ├── engine.py                        # 残高計算・日別集計ロジック
│   ├── reconciler.py                    # 既存仕訳CSVとの突合
│   ├── storage.py                       # SQLiteリポジトリ（CRUD + クエリ）
│   ├── config_loader.py                 # cash_config.yml / spapi_config.yml 読み込み
│   ├── exceptions.py                    # 資金管理モジュール固有の例外
│   └── sources/                         # データソース実装
│       ├── __init__.py
│       ├── base.py                      # EntrySource Protocol 定義
│       ├── manual.py                    # 手入力ソース
│       ├── spapi.py                     # Amazon SP-API 連携
│       ├── csv_import.py                # 汎用CSV取込（将来）
│       └── ledger_ref.py               # 既存仕訳CSV読み込み（参照専用）
│
├── gui/
│   ├── app.py                           # 既存GUI（タブ追加のみ）
│   └── cash_tab.py                      # ★ 新規: 資金管理タブ
│
├── rules/                               # 既存 + 新規
│   ├── bank_format_mufj.yml             # 既存
│   ├── bank_format_aichibank.yml        # 既存
│   ├── amazon_summary_map.yml           # 既存
│   ├── ledger_mapping.yml               # 既存
│   ├── cash_config.yml                  # ★ 新規: プルダウン定義・勘定科目
│   └── spapi_config.yml                 # ★ 新規: SP-API接続設定
│
├── data/                                # ★ 新規: 永続化ストレージ
│   └── cash.db                          # SQLiteデータベース
│
└── outputs/                             # 既存（変更なし）
    └── YYYYMMDD_HHMMSS/

tests/
├── unit/
│   ├── test_detector.py                 # 既存
│   ├── ...                              # 既存
│   ├── test_cash_models.py              # ★ 新規
│   ├── test_cash_engine.py              # ★ 新規
│   ├── test_cash_storage.py             # ★ 新規
│   ├── test_cash_reconciler.py          # ★ 新規
│   ├── test_source_manual.py            # ★ 新規
│   └── test_source_spapi.py             # ★ 新規
├── integration/
│   ├── test_pipeline_integration.py     # 既存
│   └── test_cash_integration.py         # ★ 新規
└── e2e/
    ├── test_gui_e2e.py                  # 既存
    └── test_cash_gui_e2e.py             # ★ 新規
```

---

## 3. データモデル一覧

### 3.1 CashEntry — 資金エントリ（中心モデル）

全てのデータソース（手入力・SP-API・CSV取込）から生成される資金移動の1レコード。

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `id` | `str` | UUID v4。全ソース共通のユニーク識別子。重複排除・更新時のキー |
| `date` | `str` | 取引日。`YYYY-MM-DD` 形式 |
| `entry_type` | `str` | エントリ種別。`"sales"` / `"purchase"` / `"deposit"` / `"payment"` |
| `channel` | `str` | 販路名または仕入先名。YAML `cash_config.yml` のプルダウン定義値。例: `"Amazon"`, `"楽天"`, `"仕入先A"` |
| `amount` | `int` | 金額（円）。常に正値 |
| `payment_method` | `str` | 決済手段。`"amazon_pending"` / `"credit_card"` / `"bank_transfer"` / `"cash"` 等 |
| `memo` | `str` | 自由メモ。空文字許容 |
| `settlement_date` | `str \| None` | 入金予定日 / 引落予定日。`YYYY-MM-DD` 形式。未定の場合は `None`（将来カレンダー機能で使用） |
| `source` | `str` | データソース識別子。`"manual"` / `"sp_api"` / `"csv_import"` / `"ledger_ref"` |
| `external_ref` | `str \| None` | 外部参照ID。SP-APIの注文番号、CSVの行ID等。**同一取引の二重登録防止キー** |
| `reconciled` | `bool` | 既存仕訳CSVと突合済みか。デフォルト `False` |
| `created_at` | `str` | レコード作成日時。`YYYY-MM-DD HH:MM:SS` 形式。自動付与 |
| `updated_at` | `str` | レコード更新日時。`YYYY-MM-DD HH:MM:SS` 形式。自動付与 |

**entry_type の詳細:**

| entry_type | 意味 | 例 |
|-----------|------|-----|
| `sales` | 売上発生 | Amazon商品売上、楽天売上 |
| `purchase` | 仕入・経費発生 | 商品仕入、FBA納品送料 |
| `deposit` | 入金（口座着金） | Amazon売上入金、楽天入金 |
| `payment` | 出金（口座引落） | クレカ引落、振込支払 |

**payment_method の詳細:**

| payment_method | 意味 | 残高影響 |
|---------------|------|---------|
| `amazon_pending` | Amazon保留（未入金） | 売掛金 +、普通預金 変動なし |
| `credit_card` | クレカ支払（未引落） | 未払金 +、普通預金 変動なし |
| `bank_transfer` | 銀行振込（即時） | 普通預金 直接増減 |
| `cash` | 現金支払 | 現金 直接増減 |

---

### 3.2 AccountBalance — 勘定科目残高

勘定科目ごとの残高スナップショット。`engine.py` が `CashEntry` リストから算出する。

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `account_name` | `str` | 勘定科目名。例: `"普通預金"`, `"売掛金_Amazon"`, `"未払金_クレカ"` |
| `balance` | `int` | 現在残高（円）。負値は負債方向 |
| `as_of` | `str` | 残高基準日。`YYYY-MM-DD` 形式 |

**追跡対象の勘定科目（MVP）:**

| 勘定科目 | 増加条件 | 減少条件 |
|---------|---------|---------|
| `普通預金` | deposit (入金) | payment (出金), purchase (bank_transfer) |
| `売掛金_Amazon` | sales (amazon_pending) | deposit (channel=Amazon) |
| `売掛金_その他` | sales (他販路, amazon_pending以外の pending系) | deposit (該当channel) |
| `未払金_クレカ` | purchase (credit_card) | payment (credit_card) |
| `在庫` | purchase (仕入系) | sales に連動（将来: 原価計算時） |

---

### 3.3 DailySummary — 日別集計

日別の入出金集計。将来のグラフ描画の基礎データ。

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `date` | `str` | 対象日。`YYYY-MM-DD` 形式 |
| `total_sales` | `int` | 当日売上合計（円） |
| `total_purchases` | `int` | 当日仕入合計（円） |
| `total_deposits` | `int` | 当日入金合計（円） |
| `total_payments` | `int` | 当日出金合計（円） |
| `bank_balance` | `int` | 当日末時点の普通預金残高（累積） |
| `net_cash` | `int` | 実質キャッシュ（普通預金 + 売掛金 − 未払金） |
| `breakdown` | `dict[str, int]` | チャネル別内訳。例: `{"Amazon": 15000, "楽天": 8000}` |

---

### 3.4 ReconciliationResult — 突合結果

既存仕訳CSVとの突合結果。`reconciler.py` が生成する。

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `period` | `str` | 突合対象期間。`"YYYY-MM"` 形式 |
| `channel` | `str` | 突合対象チャネル。`"Amazon"`, `"bank"` 等 |
| `cash_total` | `int` | 資金管理側の合計（円） |
| `ledger_total` | `int` | 仕訳CSV側の合計（円） |
| `difference` | `int` | 差額（円）。`cash_total - ledger_total` |
| `status` | `str` | `"matched"` (差額0) / `"minor_diff"` (差額 < 閾値) / `"mismatch"` (差額 ≥ 閾値) |
| `details` | `str` | 差異の説明メッセージ |

---

### 3.5 SPAPIOrder — SP-API注文データ（中間モデル）

SP-APIから取得した注文データ。`CashEntry` に変換される前の一時的な中間表現。

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `order_id` | `str` | Amazon注文番号。例: `"250-1234567-8901234"` |
| `purchase_date` | `str` | 注文日。`YYYY-MM-DD` 形式（SP-API の `PurchaseDate` から変換） |
| `order_total` | `int` | 注文合計金額（円）。`OrderTotal.Amount` から変換 |
| `order_status` | `str` | 注文ステータス。`"Shipped"` / `"Delivered"` 等 |
| `marketplace` | `str` | マーケットプレイスID。例: `"A1VC38T7YXB528"` (JP) |
| `raw_response` | `dict` | SP-APIの生レスポンス（デバッグ用） |

---

### 3.6 CashValidationError — 資金管理バリデーションエラー

資金管理モジュール固有のエラー/警告。既存の `ValidationError` と同構造だが、`cash/` モジュール内で独立管理する。

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `entry_id` | `str` | 問題の `CashEntry.id`。エントリ特定用 |
| `level` | `str` | `"error"` / `"warn"` |
| `field` | `str` | 問題のフィールド名 |
| `message` | `str` | 人間向けエラーメッセージ |
| `raw_value` | `str` | 問題となった元の値 |

---

## 4. モジュール一覧

### 4.1 cash/sources/base.py — データソース共通インターフェース

| 項目 | 内容 |
|------|------|
| **責務** | 全データソースが実装する `EntrySource` Protocol を定義 |
| **定義** | `source_kind: str` プロパティ、`fetch(date_from, date_to) -> list[CashEntry]` メソッド |
| **使用するデータモデル** | `CashEntry` （戻り値型） |

```python
from typing import Protocol

class EntrySource(Protocol):
    """全てのデータソースが実装するインターフェース"""

    @property
    def source_kind(self) -> str:
        """ソース識別子。"manual" / "sp_api" / "csv_import" / "ledger_ref" """
        ...

    def fetch(self, date_from: str, date_to: str) -> list[CashEntry]:
        """指定期間のエントリを取得する"""
        ...

    def validate_entry(self, entry: CashEntry) -> list[CashValidationError]:
        """エントリのバリデーション。空リスト = OK"""
        ...
```

---

### 4.2 cash/sources/manual.py — 手入力ソース

| 項目 | 内容 |
|------|------|
| **責務** | GUI手入力フォームからの `CashEntry` 生成・バリデーション |
| **使用するデータモデル** | `CashEntry` （出力）, `CashValidationError` |
| **参照するSpec/YAML** | `cash_config.yml` — プルダウン選択肢の取得 |
| **source_kind** | `"manual"` |
| **処理内容** | |
| | GUIフォームの入力値から `CashEntry` を生成 |
| | `id`: UUID v4 を自動付与 |
| | `created_at` / `updated_at`: 現在日時を自動付与 |
| | `external_ref`: `None`（手入力には外部参照なし） |
| **バリデーション** | |
| | 日付が空 or 不正形式 → `error` |
| | 金額が 0 以下 → `error` |
| | channel がプルダウン定義にない → `warn` |
| | entry_type と payment_method の組み合わせ不整合 → `warn` |
| **主要エラー** | 上記バリデーションで検出された問題を `CashValidationError` として返却 |

---

### 4.3 cash/sources/spapi.py — Amazon SP-API連携

| 項目 | 内容 |
|------|------|
| **責務** | Amazon SP-API (Orders API) から注文データを取得し `CashEntry` に変換 |
| **使用するデータモデル** | `SPAPIOrder` （中間）, `CashEntry` （出力）, `CashValidationError` |
| **参照するSpec/YAML** | `spapi_config.yml` — 認証情報・API設定・フィールドマッピング |
| **source_kind** | `"sp_api"` |
| **依存ライブラリ** | `python-amazon-sp-api` (PyPI) または直接 `requests` + OAuth2 |
| **処理内容** | |
| | **認証**: `spapi_config.yml` から credentials を読み込み、アクセストークンを取得 |
| | **注文取得**: `getOrders` API で指定期間の出荷済み注文を取得 |
| | **ページネーション**: `NextToken` による自動ページ送り |
| | **変換**: `SPAPIOrder` → `CashEntry` (entry_type=`"sales"`, channel=`"Amazon"`, payment_method=`"amazon_pending"`) |
| | **重複排除**: `external_ref` (= `order_id`) で storage 内の既存エントリと突合。既存があればスキップ |
| **バリデーション** | |
| | API応答のパース失敗 → `error` (該当注文スキップ、他は継続) |
| | 金額が 0 の注文 → `warn` |
| | 注文ステータスが想定外 → `warn` |
| **主要エラー** | |
| | `SPAPIAuthError` — 認証失敗（トークン期限切れ等） |
| | `SPAPIFetchError` — API呼び出し失敗（ネットワーク・レート制限等） |
| | `SPAPIParseError` — レスポンスのパース失敗 |
| **例外処理** | 認証失敗は即座にGUIへ通知。API呼び出し失敗はリトライ（最大3回、指数バックオフ）。個別注文のパース失敗は `CashValidationError` に記録し残りは処理継続 |
| **レート制限対策** | SP-API のスロットリングに従い、1リクエスト/秒を基本とする。`429 Too Many Requests` 受信時は `Retry-After` ヘッダに従う |

---

### 4.4 cash/sources/csv_import.py — 汎用CSV取込 [将来]

| 項目 | 内容 |
|------|------|
| **責務** | 楽天・Yahoo等の売上CSV、およびクレカ明細CSVを取り込み `CashEntry` に変換 |
| **使用するデータモデル** | `CashEntry` （出力）, `CashValidationError` |
| **参照するSpec/YAML** | `cash_config.yml` 内の `csv_formats` セクション（将来定義） |
| **source_kind** | `"csv_import"` |
| **未確定** | CSVフォーマット定義の構造（既存 `bank_format_*.yml` と同等の `header_aliases` 方式を想定） |
| **拡張方針** | 既存パイプラインの detector + parser パターンを参考に、YAML定義 + 汎用パーサで対応 |

---

### 4.5 cash/sources/ledger_ref.py — 仕訳CSV参照（読み取り専用）

| 項目 | 内容 |
|------|------|
| **責務** | 既存パイプラインの出力 (`ledger_draft.csv`, `normalized_transactions.csv`) を読み取り、突合用のデータを提供 |
| **使用するデータモデル** | `ReconciliationResult` （出力） |
| **参照先** | `outputs/YYYYMMDD_HHMMSS/ledger_draft.csv` — 仕訳候補 |
| **source_kind** | `"ledger_ref"` |
| **処理内容** | |
| | 指定された出力ディレクトリから `ledger_draft.csv` を読み込み |
| | チャネル別・月別に仕訳金額を集計 |
| | `reconciler.py` に集計結果を渡す |
| **注意** | **書き込みは一切行わない**。既存出力ファイルの内容を変更しない |
| **主要エラー** | |
| | 出力ディレクトリが存在しない → `warn`（突合スキップ） |
| | CSV読み込み失敗 → `warn`（突合スキップ） |

---

### 4.6 cash/engine.py — 残高計算・集計エンジン

| 項目 | 内容 |
|------|------|
| **責務** | `CashEntry` のリストから勘定科目残高 (`AccountBalance`) と日別集計 (`DailySummary`) を算出 |
| **使用するデータモデル** | `CashEntry` （入力）, `AccountBalance` / `DailySummary` （出力） |
| **参照するSpec/YAML** | `cash_config.yml` — 勘定科目定義、残高計算ルール |

**残高計算ルール:**

```
entry_type=sales, payment_method=amazon_pending:
    売掛金_Amazon += amount

entry_type=sales, payment_method=他のpending系:
    売掛金_その他 += amount

entry_type=purchase, payment_method=credit_card:
    未払金_クレカ += amount

entry_type=purchase, payment_method=bank_transfer:
    普通預金 -= amount

entry_type=purchase, payment_method=cash:
    現金 -= amount

entry_type=deposit:
    普通預金 += amount
    売掛金_{channel} -= amount  # 入金により売掛解消

entry_type=payment, payment_method=credit_card:
    未払金_クレカ -= amount
    普通預金 -= amount          # 引落による現金減少
```

| **主要メソッド** | |
| | `calculate_balances(entries, as_of) -> list[AccountBalance]` — 指定日時点の全勘定残高 |
| | `calculate_net_cash(entries, as_of) -> int` — 実質キャッシュ（預金 + 売掛 − 未払） |
| | `daily_summary(entries, date_from, date_to) -> list[DailySummary]` — 日別集計 |
| | `channel_breakdown(entries, date_from, date_to) -> dict[str, int]` — チャネル別合計 |
| **主要エラー** | 計算自体は例外を出さない設計。不正データは事前にバリデーション済みの前提 |

---

### 4.7 cash/reconciler.py — 突合エンジン

| 項目 | 内容 |
|------|------|
| **責務** | 資金管理モジュールのデータと既存仕訳CSVを突合し、差異を報告する |
| **使用するデータモデル** | `CashEntry` （入力）, `ReconciliationResult` （出力） |
| **参照先** | `ledger_ref.py` 経由で既存仕訳CSVを取得 |
| **処理内容** | |
| | 月別・チャネル別に資金管理側の合計と仕訳CSV側の合計を比較 |
| | 差額と差異ステータスを `ReconciliationResult` として返却 |
| **突合ロジック** | |
| | `差額 = 0` → `status: "matched"` |
| | `0 < |差額| < 閾値（デフォルト: ¥1,000）` → `status: "minor_diff"` |
| | `|差額| ≥ 閾値` → `status: "mismatch"` |
| **注意** | あくまで**参照・警告のみ**。仕訳CSVの書き換えや既存パイプラインへのフィードバックは行わない |

---

### 4.8 cash/storage.py — データ永続化

| 項目 | 内容 |
|------|------|
| **責務** | `CashEntry` の CRUD 操作、クエリ、重複チェック |
| **ストレージ** | SQLite (`data/cash.db`) |
| **パターン** | リポジトリパターン（将来の DB 移行に備え、インターフェースを分離） |

**テーブル定義:**

```sql
CREATE TABLE IF NOT EXISTS cash_entries (
    id              TEXT PRIMARY KEY,
    date            TEXT NOT NULL,          -- YYYY-MM-DD
    entry_type      TEXT NOT NULL,          -- sales/purchase/deposit/payment
    channel         TEXT NOT NULL,          -- 販路/仕入先
    amount          INTEGER NOT NULL,       -- 金額（円）
    payment_method  TEXT NOT NULL,          -- 決済手段
    memo            TEXT DEFAULT '',
    settlement_date TEXT,                   -- 入金/引落予定日（NULL許容）
    source          TEXT NOT NULL,          -- manual/sp_api/csv_import/ledger_ref
    external_ref    TEXT,                   -- 外部参照ID（NULL許容）
    reconciled      INTEGER DEFAULT 0,      -- 0=未突合, 1=突合済
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- 重複チェック用インデックス
CREATE UNIQUE INDEX IF NOT EXISTS idx_external_ref
    ON cash_entries(source, external_ref)
    WHERE external_ref IS NOT NULL;

-- 日付範囲クエリ用インデックス
CREATE INDEX IF NOT EXISTS idx_date ON cash_entries(date);

-- チャネル別集計用インデックス
CREATE INDEX IF NOT EXISTS idx_channel ON cash_entries(channel, date);
```

| **主要メソッド** | |
|----------------|------|
| `insert(entry: CashEntry) -> None` | エントリ登録。`external_ref` 重複時は `DuplicateEntryError` |
| `update(entry: CashEntry) -> None` | エントリ更新。`id` で特定 |
| `delete(entry_id: str) -> None` | エントリ削除 |
| `find_by_date_range(date_from, date_to) -> list[CashEntry]` | 日付範囲検索 |
| `find_by_channel(channel, date_from, date_to) -> list[CashEntry]` | チャネル別検索 |
| `find_by_external_ref(source, ref) -> CashEntry \| None` | 外部参照で検索（重複チェック用） |
| `find_all() -> list[CashEntry]` | 全件取得 |

| **主要エラー** | |
| | `DuplicateEntryError` — `external_ref` の重複（SP-APIの同一注文を2度取り込み等） |
| | `EntryNotFoundError` — 更新/削除時に `id` が見つからない |
| | `StorageIOError` — SQLiteファイルへのアクセス失敗 |

---

### 4.9 cash/config_loader.py — 設定ファイル読み込み

| 項目 | 内容 |
|------|------|
| **責務** | `cash_config.yml` と `spapi_config.yml` を読み込み、バリデーション済みの設定オブジェクトを返す |
| **使用するデータモデル** | `CashConfig` / `SPAPIConfig` （内部設定クラス） |
| **処理内容** | |
| | YAML読み込み（`ruamel.yaml` or `PyYAML`） |
| | 必須キーの存在チェック |
| | 環境変数の展開（`${ENV_VAR}` 形式） |
| **主要エラー** | |
| | YAML構文エラー → `CashConfigError` |
| | 必須キー欠損 → `CashConfigError` |
| | 環境変数未設定（SP-API credentials） → `CashConfigError`（メッセージに変数名を含める） |

---

### 4.10 cash/exceptions.py — 例外クラス階層

```
CashModuleError (基底)
├── CashConfigError              # YAML設定読み込み・バリデーション失敗
├── StorageError
│   ├── DuplicateEntryError      # external_ref 重複
│   ├── EntryNotFoundError       # 更新/削除対象なし
│   └── StorageIOError           # SQLiteアクセス失敗
├── SPAPIError
│   ├── SPAPIAuthError           # 認証失敗（トークン期限切れ等）
│   ├── SPAPIFetchError          # API呼び出し失敗
│   └── SPAPIParseError          # レスポンスパース失敗
├── ReconciliationError          # 突合処理のエラー
└── CSVImportError               # [将来] CSV取込エラー
```

> `CashModuleError` は既存の `TaxToolError` とは**独立した階層**。既存パイプラインの例外体系に影響しない。

---

## 5. YAML設定ファイル

### 5.1 cash_config.yml — プルダウン定義・勘定科目

```yaml
version: 1
kind: cash_config

# ── プルダウン選択肢 ──────────────────────────
channels:
  sales:                         # 売上チャネル（販路）
    - id: "amazon"
      label: "Amazon"
      default_payment_method: "amazon_pending"
    - id: "rakuten"
      label: "楽天"
      default_payment_method: "rakuten_pending"
    - id: "yahoo"
      label: "Yahoo!ショッピング"
      default_payment_method: "yahoo_pending"
    - id: "own_ec"
      label: "自社EC"
      default_payment_method: "bank_transfer"
    - id: "other_sales"
      label: "その他"
      default_payment_method: "bank_transfer"

  purchase:                      # 仕入先
    - id: "supplier_a"
      label: "仕入先A"
      default_payment_method: "credit_card"
    - id: "supplier_b"
      label: "仕入先B"
      default_payment_method: "credit_card"
    - id: "amazon_purchase"
      label: "Amazon仕入"
      default_payment_method: "credit_card"
    - id: "other_purchase"
      label: "その他"
      default_payment_method: "credit_card"

# ── 決済手段 ─────────────────────────────────
payment_methods:
  - id: "amazon_pending"
    label: "Amazon保留（入金待ち）"
    affects_account: "売掛金_Amazon"
  - id: "rakuten_pending"
    label: "楽天保留（入金待ち）"
    affects_account: "売掛金_その他"
  - id: "yahoo_pending"
    label: "Yahoo保留（入金待ち）"
    affects_account: "売掛金_その他"
  - id: "credit_card"
    label: "クレジットカード"
    affects_account: "未払金_クレカ"
  - id: "bank_transfer"
    label: "銀行振込"
    affects_account: "普通預金"
  - id: "cash"
    label: "現金"
    affects_account: "現金"

# ── 勘定科目 ─────────────────────────────────
accounts:
  - name: "普通預金"
    type: "asset"           # asset（資産）/ liability（負債）
    initial_balance: 0      # 初期残高（セットアップ時にユーザーが入力）
  - name: "売掛金_Amazon"
    type: "asset"
    initial_balance: 0
  - name: "売掛金_その他"
    type: "asset"
    initial_balance: 0
  - name: "未払金_クレカ"
    type: "liability"
    initial_balance: 0
  - name: "在庫"
    type: "asset"
    initial_balance: 0
  - name: "現金"
    type: "asset"
    initial_balance: 0

# ── 突合設定 ─────────────────────────────────
reconciliation:
  threshold: 1000           # 差額警告閾値（円）
  auto_match_channel_map:   # 資金管理チャネル → 仕訳CSVの対応タグ
    Amazon: ["amazon"]
    楽天: ["rakuten"]
```

---

### 5.2 spapi_config.yml — SP-API接続設定

```yaml
version: 1
kind: spapi_config

# ── 認証情報（環境変数参照）──────────────────
credentials:
  refresh_token: "${SPAPI_REFRESH_TOKEN}"
  client_id: "${SPAPI_CLIENT_ID}"
  client_secret: "${SPAPI_CLIENT_SECRET}"
  aws_access_key: "${SPAPI_AWS_ACCESS_KEY}"      # [任意] STS不要の場合
  aws_secret_key: "${SPAPI_AWS_SECRET_KEY}"       # [任意]
  role_arn: "${SPAPI_ROLE_ARN}"                   # [任意]

# ── マーケットプレイス ────────────────────────
marketplace:
  id: "A1VC38T7YXB528"          # 日本
  region: "us-west-2"           # FE (Far East) リージョン
  endpoint: "https://sellingpartnerapi-fe.amazon.com"

# ── 取得設定 ──────────────────────────────────
fetch:
  orders:
    api: "Orders"
    operation: "getOrders"
    status_filter:               # 取得対象の注文ステータス
      - "Shipped"
    default_lookback_days: 14    # デフォルト取得期間（直近N日）
    max_results_per_page: 100
    fields_map:                  # SP-APIフィールド → CashEntryフィールド
      date: "PurchaseDate"
      amount: "OrderTotal.Amount"
      currency: "OrderTotal.CurrencyCode"
      order_id: "AmazonOrderId"
      status: "OrderStatus"

  # ── 将来拡張 ─────────────────────────────
  # finances:
  #   api: "Finances"
  #   operation: "listFinancialEvents"
  #   ...

# ── リトライ設定 ──────────────────────────────
retry:
  max_attempts: 3
  base_delay_seconds: 1          # 指数バックオフの基底遅延
  max_delay_seconds: 30

# ── スケジュール（将来: 自動定期取得）─────────
# schedule:
#   interval_minutes: 60
#   enabled: false
```

---

## 6. エラー/ログ体系

### 6.1 エラーレベル定義

| レベル | 意味 | エントリの扱い | 例 |
|--------|------|-------------|-----|
| `error` | 致命的。そのエントリは保存しない | 登録拒否 | 日付不正、金額0以下、SP-API認証失敗 |
| `warn` | 注意。処理は継続するが確認が必要 | 登録するが警告表示 | 突合差異、未知ステータス、プルダウン外の値 |

### 6.2 エラーメッセージ一覧

| 発生元 | level | field | message 例 |
|--------|-------|-------|-----------|
| manual | error | `date` | `"日付が空です"` |
| manual | error | `date` | `"日付の形式が不正です: {raw_value}"` |
| manual | error | `amount` | `"金額は1以上を入力してください: {raw_value}"` |
| manual | warn | `channel` | `"プルダウン定義にないチャネルです: {channel}"` |
| spapi | error | — | `"SP-API認証に失敗しました: {detail}"` |
| spapi | error | — | `"SP-API呼び出しに失敗しました（{attempts}回リトライ後）: {detail}"` |
| spapi | error | `order_id` | `"注文データのパースに失敗しました: {order_id}"` |
| spapi | warn | `amount` | `"金額が0の注文です: {order_id}"` |
| spapi | warn | `order_status` | `"想定外の注文ステータスです: {status}"` |
| storage | error | `external_ref` | `"重複エントリ: source={source}, ref={ref}"` |
| storage | error | — | `"データベースアクセスに失敗しました: {detail}"` |
| reconciler | warn | — | `"突合差異: {channel} {period} 資金管理={cash_total}円 仕訳={ledger_total}円 差額={diff}円"` |
| config | error | — | `"設定ファイルの読み込みに失敗しました: {path}"` |
| config | error | — | `"環境変数が未設定です: {var_name}"` |

### 6.3 エラー収集の流れ

```
sources/manual.py  ──→ CashValidationError (入力バリデーション)
sources/spapi.py   ──→ CashValidationError (API/パースエラー)
                        ↓
                   storage.py に保存可否を判定
                   ├─ error → 保存拒否、GUI にエラー表示
                   └─ warn  → 保存実行、GUI に警告表示

reconciler.py      ──→ ReconciliationResult (突合結果)
                        ↓
                   GUI の突合結果エリアに表示（参照のみ）
```

---

## 7. GUI設計

### 7.1 タブ構成（更新後）

```
┌──────────────────────────────────────────────────┐
│ 帳簿作成 │ 資金管理 │                              │
└──────────────────────────────────────────────────┘
```

- **帳簿作成タブ**: 既存の4つのサブ表示（実行ログ / サマリ / エラー警告 / 仕訳確認）をそのまま維持
- **資金管理タブ**: 新規追加

### 7.2 資金管理タブ レイアウト

```
┌────────────────────────────────────────────────────────┐
│ 資金管理                                                │
├────────────────────────────────────────────────────────┤
│                                                        │
│ ┌─ 日次入力 ─────────────────────────────────────────┐ │
│ │ 種別: [売上 ▼]  チャネル: [Amazon ▼]               │ │
│ │ 日付: [2026/02/21]  金額: [15,000]                 │ │
│ │ 決済: [Amazon保留 ▼]  メモ: [__________]           │ │
│ │                                                    │ │
│ │                    [登録]  [SP-API取込]             │ │
│ └────────────────────────────────────────────────────┘ │
│                                                        │
│ ┌─ 現在の残高 ───────────────────────────────────────┐ │
│ │ 普通預金:       ¥  320,000                         │ │
│ │ 売掛金_Amazon:  ¥   85,000                         │ │
│ │ 売掛金_その他:  ¥   12,000                         │ │
│ │ 未払金_クレカ:  ¥ -140,000                         │ │
│ │ 在庫:           ¥  200,000                         │ │
│ │ ──────────────────────────────                     │ │
│ │ 実質キャッシュ: ¥  277,000                         │ │
│ └────────────────────────────────────────────────────┘ │
│                                                        │
│ ┌─ 直近エントリ ──────────────── [全件表示] ──────────┐ │
│ │ 日付       種別  チャネル     金額    決済    ソース │ │
│ │ 2026/02/21 売上  Amazon   ¥15,000 Amazon保留 手入力│ │
│ │ 2026/02/21 仕入  仕入先A  ¥40,000 クレカ     手入力│ │
│ │ 2026/02/20 売上  Amazon   ¥22,000 Amazon保留 SP-API│ │
│ │ ...                                                │ │
│ └────────────────────────────────────────────────────┘ │
│                                                        │
│ ┌─ 突合（仕訳CSV） ─────────── [ファイル選択] ───────┐ │
│ │ 2026-01 Amazon: 資金管理 ¥450,000 / 仕訳 ¥448,500 │ │
│ │                 差額 ¥1,500 ⚠ 軽微な差異           │ │
│ │ 2026-01 銀行:   資金管理 ¥320,000 / 仕訳 ¥320,000 │ │
│ │                 差額 ¥0 ✓ 一致                     │ │
│ └────────────────────────────────────────────────────┘ │
│                                                        │
│ ┌─ 将来: グラフ表示エリア ───────────────────────────┐ │
│ │ (Coming Soon: 日別残高推移グラフ、チャネル別円グラフ) │ │
│ └────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘
```

### 7.3 GUI操作フロー

```
[日次入力フロー]
1. 種別プルダウン選択（売上/仕入/入金/出金）
2. → 種別に応じたチャネルプルダウンが切り替わる
     売上 → 販路リスト (Amazon, 楽天, ...)
     仕入 → 仕入先リスト (仕入先A, 仕入先B, ...)
     入金/出金 → 全チャネル
3. → チャネル選択で決済手段がデフォルト値にセットされる
     Amazon選択 → 決済: Amazon保留
     仕入先A選択 → 決済: クレジットカード
4. 日付・金額・メモを入力
5. [登録] → バリデーション → storage保存 → 残高再計算 → 画面更新

[SP-API取込フロー]
1. [SP-API取込] ボタン押下
2. → spapi_config.yml から設定読み込み
3. → SP-API認証 → 注文取得 → CashEntry変換
4. → 重複チェック（external_ref）→ 新規のみ保存
5. → 取込結果サマリ表示（N件取込、M件重複スキップ）
6. → 残高再計算 → 画面更新

[突合フロー]
1. [ファイル選択] で既存パイプラインの出力ディレクトリを指定
2. → ledger_draft.csv 読み込み → 月別・チャネル別集計
3. → 資金管理側と比較 → ReconciliationResult 生成
4. → 突合結果表示（一致/差異/警告）
```

---

## 8. 拡張ポイント

| 拡張対象 | 必要な作業 |
|----------|-----------|
| **新しい販路の追加** | `cash_config.yml` の `channels.sales` に1項目追加するだけ。コード変更不要 |
| **新しい仕入先の追加** | `cash_config.yml` の `channels.purchase` に1項目追加するだけ。コード変更不要 |
| **新しい決済手段の追加** | `cash_config.yml` の `payment_methods` に1項目追加 + `engine.py` の残高計算ルールに分岐追加 |
| **楽天・Yahoo売上CSV取込** | `cash_config.yml` に `csv_formats` セクション追加 + `csv_import.py` 実装 |
| **クレカ明細CSV取込** | 同上（仕入側の CSV取込） |
| **グラフ表示** | `engine.py` の `daily_summary()` データを `matplotlib` / `plotly` で描画。`cash_tab.py` にグラフ領域追加 |
| **キャッシュフローカレンダー** | `CashEntry.settlement_date` を活用。カレンダーUI追加 |
| **在庫原価計算** | `CashEntry` に `quantity` / `unit_cost` フィールド追加。`engine.py` に売上原価計算ロジック追加 |
| **SP-API Finances 連携** | `spapi_config.yml` の `finances` セクション有効化 + `spapi.py` に Finances API 呼び出し追加 |
| **自動定期取得** | `spapi_config.yml` の `schedule` セクション有効化 + バックグラウンドスケジューラ実装 |
| **他の会計ソフト出力** | 現行は弥生のみ。資金管理データの出力フォーマットを `exporter` 的に追加 |

---

## 9. テスト方針

### 9.1 ユニットテスト

| テストファイル | 対象モジュール | 主要テスト観点 |
|--------------|--------------|--------------|
| `test_cash_models.py` | `cash/models.py` | データクラスの生成・バリデーション・デフォルト値 |
| `test_cash_engine.py` | `cash/engine.py` | 残高計算の正確性、日別集計、エッジケース（エントリ0件、同日複数取引） |
| `test_cash_storage.py` | `cash/storage.py` | CRUD操作、重複チェック、日付範囲検索、インデックス利用 |
| `test_cash_reconciler.py` | `cash/reconciler.py` | 突合ロジック（一致・差異・閾値判定）、仕訳CSV読み込み |
| `test_source_manual.py` | `cash/sources/manual.py` | 入力バリデーション（正常系・異常系）、UUID生成 |
| `test_source_spapi.py` | `cash/sources/spapi.py` | レスポンスパース、重複排除、エラーハンドリング（モック使用） |
| `test_cash_config.py` | `cash/config_loader.py` | YAML読み込み、環境変数展開、必須キーチェック |

### 9.2 統合テスト

| テストファイル | 観点 |
|--------------|------|
| `test_cash_integration.py` | 手入力 → storage保存 → engine残高計算 → 正しい残高が返ること |
| | SP-APIモック → storage保存 → 重複排除 → 残高計算の一連フロー |
| | 仕訳CSV取込 → reconciler突合 → ReconciliationResult の正確性 |

### 9.3 E2Eテスト

| テストファイル | 観点 |
|--------------|------|
| `test_cash_gui_e2e.py` | 資金管理タブの表示、プルダウン切替、入力→登録→残高更新のGUIフロー |

### 9.4 テストで使用するフィクスチャ

```python
# tests/conftest.py に追加

@pytest.fixture
def sample_cash_entries() -> list[CashEntry]:
    """テスト用の CashEntry リスト"""
    ...

@pytest.fixture
def in_memory_storage(tmp_path) -> CashStorage:
    """テスト用の一時 SQLite ストレージ"""
    ...

@pytest.fixture
def mock_spapi_response() -> dict:
    """SP-API getOrders のモックレスポンス"""
    ...

@pytest.fixture
def sample_ledger_csv(tmp_path) -> str:
    """突合テスト用の仕訳CSV"""
    ...
```

---

## 10. 既存コードへの変更（最小限）

既存パイプライン (`core/`) は一切変更しない。変更が必要なのは以下のみ:

| ファイル | 変更内容 |
|---------|---------|
| `gui/app.py` | タブに「資金管理」を追加。`cash_tab.py` を import して配置 |
| `main.py` | `cash/` モジュールの初期化（DB作成等）を起動時に実行 |

**`core/` ディレクトリ内のファイルは一切変更しない。**
