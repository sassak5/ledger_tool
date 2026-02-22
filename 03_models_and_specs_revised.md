# 帳簿自動作成ツール データモデル・Spec・エラーログ詳細
更新日: 2026-02-21

`core/models.py` に定義するデータモデル、YAML Spec の構造、およびエラーログの詳細設計。

---

## 1. データモデル一覧

### 1.1 RawRecord — パース結果レコード

各パーサが `base_parser` の共通インターフェース経由で返す、正規化前の中間データ。

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `source_kind` | `str` | パーサが処理したソース種別。registry のキーと一致する。例: `"bank_statement"`, `"amazon_settlement_report"` |
| `format_id` | `str` | 検出されたフォーマットID。例: `"mufj_table_v1"`, `"aichibank_table_v1"`, `"amazon_settlement_v1"` |
| `row_number` | `int` | 元ファイル上の行番号 (1始まり)。エラー追跡用 |
| `fields` | `dict[str, Any]` | パースされたフィールド群。キーはYAMLの正規列名 (`"date"`, `"amount_out"` 等)、値はパース後の型 (`str` / `int` / `None`) |
| `raw_line` | `dict[str, str]` | 元行データをそのまま保持。キーは元の列名、値は変換前の文字列 |

---

### 1.2 DetectionResult — フォーマット検出結果

`detector.py` が返す検出結果。pipeline がパーサ選択に使う。

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `format_id` | `str` | 一致したフォーマットID。例: `"mufj_table_v1"`, `"aichibank_table_v1"` |
| `source_kind` | `str` | ソース種別。registry のキーになる。例: `"bank_statement"`, `"amazon_settlement_report"` |
| `encoding` | `str` | 検出されたエンコーディング。`"utf-8"` / `"cp932"` / `"shift_jis"` |
| `config_path` | `str` | マッチしたYAMLファイルのパス。パーサに渡す |

---

### 1.3 NormalizedTransaction — 正規化済みトランザクション

入力ソースの差異を吸収した中間表現。正規化以降の全モジュール (validator / ledger_generator / exporter) はこの型のみに依存する。

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `source_type` | `str` | データの種別。`"bank"` / `"amazon"` / `"creditcard"` 等 |
| `source_name` | `str` | データ元の識別名。例: `"mufj"`, `"aichi"`, `"amazon_settlement"`, `"rakuten_card"` |
| `row_id` | `str` | ユニーク識別子。`"{source_name}_{行番号}"` 形式。複数ファイル結合時の衝突防止 |
| `date` | `str` | 取引日。`YYYY-MM-DD` 形式に正規化済み |
| `summary` | `str` | 摘要（短い説明）。銀行の「摘要」列、Amazonのバケット名等 |
| `details` | `str` | 摘要内容（長い説明）。なければ summary と同値 |
| `amount_out` | `int` | 支払金額（出金）。常に 0 以上。該当なしは `0` |
| `amount_in` | `int` | 預り金額（入金）。常に 0 以上。該当なしは `0` |
| `balance` | `int \| None` | 差引残高。銀行明細では通常あり、Amazon/クレカでは `None` |
| `memo` | `str` | メモ欄。なければ空文字 |
| `extra` | `dict[str, Any]` | テンプレ固有の付帯情報。例: `{"未資金化区分": "...", "入払区分": "..."}` (UFJ), `{"settlement_id": "..."}` (Amazon) |
| `raw` | `dict[str, str]` | 元行データ。デバッグ・監査用 |

---

### 1.4 LedgerDraft — 仕訳候補

1件の仕訳（借方/貸方）を表す中間成果物。最終的にスマート取引取込CSVに変換される。

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `date` | `str` | 仕訳日。`YYYY-MM-DD` 形式 |
| `debit_account` | `str` | 借方勘定科目。例: `"普通預金"`, `"支払手数料"`, `"売掛金"` |
| `debit_amount` | `int` | 借方金額。0 以上 |
| `credit_account` | `str` | 貸方勘定科目。例: `"売上高"`, `"普通預金"`, `"未払金"` |
| `credit_amount` | `int` | 貸方金額。0 以上。通常は `debit_amount` と同額 |
| `description` | `str` | 摘要。スマート取引取込の摘要欄に対応 |
| `partner` | `str` | 取引先/相手先名。不明の場合は空文字 |
| `source_row_id` | `str` | 元データへの参照。`NormalizedTransaction.row_id` と対応 |
| `tags` | `list[str]` | 分類タグ。例: `["amazon", "fee"]`, `["bank", "transfer"]` |

---

### 1.5 ValidationError — バリデーションエラー/警告

バリデーションで検出された問題1件。`error_report.csv` の1行に対応する。

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `row_id` | `str` | 問題が発生した行の識別子。`NormalizedTransaction.row_id` と対応。正規化前は `"{source_name}_{行番号}"` を直接生成 |
| `level` | `str` | 深刻度。`"error"` (行除外) / `"warn"` (処理継続) |
| `field` | `str` | 問題のフィールド名。例: `"date"`, `"amount_out"`, `"unmapped_bucket"` |
| `message` | `str` | 人間向けエラーメッセージ。例: `"日付が読めません"`, `"支払と預りが同時に入っています（要確認）"` |
| `raw_value` | `str` | 問題となった元の値。例: `"2026/13/40"`, `"abc"` |

---

### 1.6 ProcessingSummary — パイプライン実行サマリ

パイプライン実行結果の全体サマリ。GUIの結果表示に使う。

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `period_start` | `str` | 処理対象期間の開始日 (`YYYY-MM-DD`) |
| `period_end` | `str` | 処理対象期間の終了日 (`YYYY-MM-DD`) |
| `total_count` | `int` | 取り込み総件数（正規化成功分） |
| `total_in` | `int` | 入金合計額（全ソース合算） |
| `total_out` | `int` | 出金合計額（全ソース合算） |
| `ledger_count` | `int` | 生成された仕訳候補の件数 |
| `error_count` | `int` | error レベルの件数 |
| `warn_count` | `int` | warn レベルの件数 |
| `source_files` | `list[SourceFileInfo]` | 入力ファイルごとの情報リスト |
| `run_at` | `str` | 実行日時 (`YYYY-MM-DD HH:MM:SS`) |

---

### 1.7 SourceFileInfo — 入力ファイル情報

`ProcessingSummary.source_files` の要素。

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `path` | `str` | 入力ファイルのパス |
| `format_id` | `str` | 検出されたフォーマットID |
| `source_kind` | `str` | ソース種別 |
| `row_count` | `int` | 取り込み行数（ヘッダ・スキップ行を除く） |
| `error_count` | `int` | このファイル内の error 件数 |
| `warn_count` | `int` | このファイル内の warn 件数 |

---

## 2. YAML Spec 構造

### 2.1 bank_format_*.yml — 銀行フォーマット定義

> **注意（MVP実装）**: 現時点の実装が実際に参照しているのは、主に `encoding` / `table` / `header_aliases` などの基本情報であり、以下に示す `mapping` / `extra_fields` / `fields` / `normalize` / `rules` / `validations` などのDSL部分は「将来のYAMLフル駆動構想」としての案である。MVPでは、日付/金額の変換や入出金方向の判定は `normalizer` 側のPythonコードで行う。

```yaml
# 例: bank_format_mufj.yml
version: 1                          # int    — YAMLバージョン
format_id: "mufj_table_v1"          # str    — フォーマット識別子（detector返却値）
source_kind: "bank_statement"       # str    — ソース種別（registry キー）

encoding:
  expected: ["utf-8", "cp932", "shift_jis"]  # list[str] — 試行するエンコーディング順

table:
  header_row: 1                     # int    — ヘッダ行の位置（1始まり）
  allow_extra_columns: true         # bool   — 余剰列を許容するか
  trim_whitespace: true             # bool   — セル値の前後空白を除去

header_aliases:                     # dict[str, list[str]] — 正規列名 → エイリアスリスト
  date: ["日付", "年月日"]
  summary: ["摘要", "内容"]
  summary_detail: ["摘要内容", "取引内容詳細"]
  amount_out: ["支払い金額", "支払金額"]
  amount_in: ["預かり金額", "お預り金額"]
  balance: ["差引残高", "残高"]
  memo: ["メモ", "備考"]
  float_flag: ["未資金化区分"]       # UFJ固有
  io_flag: ["入払区分"]             # UFJ固有

mapping:                             # dict[str, dict] — 入力列 → 正規フィールド割当（GUIで編集対象）
  date:       { from: date }
  summary:    { from: summary }
  details:    { from: summary_detail, default: "" }
  amount_out: { from: amount_out, default: "" }
  amount_in:  { from: amount_in,  default: "" }
  balance:    { from: balance,    default: "" }
  memo:       { from: memo,       default: "" }

extra_fields:                        # dict — extra に格納する付帯情報（GUI編集対象外）
  float_flag: { from: float_flag }
  io_flag:    { from: io_flag }

fields:                              # dict[str, list[dict]] — 正規化パイプライン（YAMLが唯一の真実）
  date:
    - { op: "parse_date", formats: ["%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d"], timezone: "Asia/Tokyo" }
  summary:
    - { op: "strip" }
    - { op: "collapse_spaces" }
  details:
    - { op: "strip" }
    - { op: "collapse_spaces" }
  memo:
    - { op: "strip" }
  amount_out:
    - { op: "to_int", thousands_sep: [","], currency_symbols: ["¥", "円"], empty_as_zero: true, allow_parentheses_negative: true }
    - { op: "abs" }
  amount_in:
    - { op: "to_int", thousands_sep: [","], currency_symbols: ["¥", "円"], empty_as_zero: true, allow_parentheses_negative: true }
    - { op: "abs" }
  balance:
    - { op: "to_int", thousands_sep: [","], currency_symbols: ["¥", "円"], empty_as_zero: true, allow_parentheses_negative: true }

normalize:
  output_schema: "normalized_transaction_v1"  # str — 出力スキーマ名
  description:                    # 摘要出力用の合成（LedgerDraft向け）
    concat: [{ from: summary }, " ", { from: details }]
    postprocess:
      - { op: "collapse_spaces" }
      - { op: "strip" }

rules:
  direction:                         # 入出金方向の判定ルール
    # UFJ: io_flag 優先 → 金額ベースfallback
    # 愛知: 金額ベースのみ

validations:                         # list[dict] — 行バリデーションルール
  - id: "both_in_out_positive"       # str  — ルールID
    level: "warn"                    # str  — error / warn
    when: "amount_out > 0 and amount_in > 0"  # str — 条件式
    message: "支払と預りが同時に入っています（要確認）"
```

---

### 2.2 amazon_summary_map.yml — Amazon集計ルール定義

```yaml
version: 1                           # int    — YAMLバージョン
source: "amazon_settlement_report"   # str    — ソース識別子

key:
  settlement_id: "settlement-id"     # str — 精算ID列名
  deposit_date: "deposit-date"       # str — 入金日列名
  total_amount: "total-amount"       # str — 合計金額列名（突合用）

summary_buckets:                     # dict[str, BucketDef] — バケット定義
  商品代金:
    normalize: "RAW"                 # str — RAW / ABS / NEGATE
    include:                         # list[dict] — マッチ条件
      - { amount_type: "ItemPrice", amount_description: "Principal" }

  税金:
    normalize: "RAW"
    formula:                         # dict — 数式定義（include の代わり）
      add:                           # list[dict] — 加算対象
        - { amount_type: "ItemPrice", amount_description: "Tax" }
        - { amount_type: "ItemPrice", amount_description: "ShippingTax" }
      subtract:                      # list[dict] — 減算対象
        - { amount_type: "Promotion", amount_description: "TaxDiscount" }

  # ... 他バケット省略（詳細は amazon_summary_map.yml 本体を参照）

ledger_defaults:                     # dict[str, str] — デフォルト勘定科目
  counterparty: "Amazon.co.jp"       # str — 取引先名
  receivable_account: "売掛金"       # str — 売掛金科目
  revenue_account: "売上高"          # str — 売上高科目
  tax_account: "仮受消費税"          # str — 仮受消費税科目
  fee_account: "支払手数料"          # str — 手数料科目
  fba_fee_account: "支払手数料"      # str — FBA手数料科目

validations:
  require_header_row: true           # bool — ヘッダ行の存在を要求
  require_fields_in_row:             # list[str] — 必須列
    - "settlement-id"
    - "amount-type"
    - "amount-description"
    - "amount"
```

---

### 2.3 cc_format_*.yml — クレジットカードフォーマット定義 [将来]

> **未確定**: 以下は想定構造。カード会社ごとの差異が判明次第確定する。

```yaml
version: 1
format_id: "rakuten_card_v1"        # str — フォーマット識別子
source_kind: "credit_card_statement" # str — ソース種別

header_aliases:
  date: ["利用日", "ご利用日"]
  description: ["利用先", "ご利用先"]
  amount: ["利用金額", "ご利用金額"]
  payment_type: ["支払区分", "お支払い区分"]  # 1回払い/分割/リボ

parsing:
  # bank_format_*.yml と同等の構造
  date:
    formats: ["%Y/%m/%d"]
  number:
    thousands_sep: [","]
    currency_symbols: ["¥"]
    empty_as_zero: true
```

---

## 3. エラーレポート (error_report.csv) 構造

### 3.1 CSVカラム定義

| カラム名 | 型 | 説明 |
|---------|-----|------|
| `row_id` | `str` | 問題行の識別子。`"{source_name}_{行番号}"` 形式 |
| `level` | `str` | `"error"` / `"warn"` |
| `field` | `str` | 問題のフィールド名 |
| `message` | `str` | 人間向けエラーメッセージ |
| `raw_value` | `str` | 問題となった元の値 |

### 3.2 エラーメッセージ一覧（想定）

| 発生元 | level | field | message 例 |
|--------|-------|-------|-----------|
| detector | error | — | `"フォーマットを判定できません (ヘッダ: [列A, 列B, ...])"` |
| detector | error | — | `"エンコーディングを判定できません: {file_path}"` |
| bank parser | error | `date` | `"日付が読めません: {raw_value}"` |
| bank parser | error | `amount_out` | `"金額を数値化できません: {raw_value}"` |
| bank parser | warn | `amount_out, amount_in` | `"支払と預りが同時に入っています（要確認）"` |
| bank parser | warn | `amount_out, amount_in` | `"金額が両方0です（要確認）"` |
| amazon parser | error | `settlement-id` | `"必須列が欠損しています: {column_name}"` |
| amazon parser | warn | `total_amount` | `"total-amountと集計値が一致しません (差額: {diff})"` |
| amazon parser | warn | `unmapped_bucket` | `"未知のamount_description: {desc} ({count}件, 合計: ¥{sum})"` |
| normalizer | error | `{field}` | `"必須フィールド '{field}' が存在しません"` |
| normalizer | error | `{field}` | `"型変換に失敗しました: {field}={raw_value}"` |
| validator | error | `date` | `"日付がnullです"` |
| validator | warn | `balance` | `"残高照合: 前行残高との差異が大きいです (差額: {diff})"` |
| ledger_gen | warn | `debit_account` | `"科目を推定できません。デフォルト科目 '未分類' を仮割当て"` |

---

## 4. 実行ログ (run_log.txt) 構造

### 4.1 出力フォーマット

```text
=== 帳簿自動作成ツール 実行ログ ===
実行日時: 2026-02-07 14:30:00
出力先: outputs/20260207_143000/

--- 入力ファイル ---
[1] C:/Users/user/Downloads/mufj_202601.csv
    フォーマット: mufj_table_v1 (bank_statement)
    取込行数: 48
    エラー: 0件 / 警告: 2件

[2] C:/Users/user/Downloads/amazon_settlement_202601.tsv
    フォーマット: amazon_settlement_v1 (amazon_settlement_report)
    取込行数: 156
    エラー: 0件 / 警告: 3件

--- サマリ ---
対象期間: 2026-01-01 〜 2026-01-31
取込総件数: 204
入金合計: ¥1,234,567
出金合計: ¥567,890
仕訳候補件数: 198
エラー件数: 0
警告件数: 5

--- 出力ファイル ---
normalized_transactions.csv (204行)
ledger_draft.csv (198行)
error_report.csv (5行)
smart_import.csv (198行)
```

---

## 5. スマート取引取込CSV構造

> **未確定**: やよい側の正式仕様を確認次第カラムを確定する。以下は暫定想定。

### 5.1 暫定カラム定義

| カラム名 | 型 | 元データ | 説明 |
|---------|-----|---------|------|
| `取引日` | `str` | `LedgerDraft.date` | `YYYY/MM/DD` 形式（やよい仕様に合わせる） |
| `借方勘定科目` | `str` | `LedgerDraft.debit_account` | 借方科目 |
| `借方金額` | `int` | `LedgerDraft.debit_amount` | 借方金額 |
| `貸方勘定科目` | `str` | `LedgerDraft.credit_account` | 貸方科目 |
| `貸方金額` | `int` | `LedgerDraft.credit_amount` | 貸方金額 |
| `摘要` | `str` | `LedgerDraft.description` | 摘要テキスト |
| `取引先` | `str` | `LedgerDraft.partner` | 取引先名 |
| `備考` | `str` | — | 補足情報（未確定） |

### 5.2 出力エンコーディング
- 現行実装: すべてのCSV出力（smart_import.csv を含む）は UTF-8 (BOM付き; `utf-8-sig`) で出力する
- 将来的に、やよい側の正式要件に合わせて cp932（Shift-JIS）対応を検討する

---

## 6. 例外クラス階層（想定）

```
TaxToolError (基底)
├── DetectionError
│   ├── EncodingDetectionError    # エンコーディング判定失敗
│   └── FormatNotMatchedError     # テンプレート不一致
├── ParseError
│   ├── DateParseError            # 日付パース失敗
│   └── AmountParseError          # 金額パース失敗
├── NormalizationError            # 正規化変換失敗
├── UnknownSourceKindError        # 未登録のsource_kind
└── ExportError                   # 出力失敗 (I/O)
```

> 上記の例外はすべて pipeline 内で `ValidationError` に変換して蓄積する。  
> `ExportError` のみ pipeline を中断し GUI に即時通知する。
