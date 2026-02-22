# 帳簿自動作成ツール モジュール設計書
更新日: 2026-02-21

---

## 0. 設計方針サマリ

| 方針 | 内容 |
|------|------|
| **ソース非依存** | 正規化以降は入力ソースの種別を意識しない。すべて `NormalizedTransaction` に集約 |
| **設定駆動 (MVP)** | ヘッダ別名やAmazon集計・科目マッピングなど一部を YAML で設定し、正規化ロジック自体は Python コード側に実装 |(後にYAMLに寄せる予定)
| **パーサ疎結合** | 共通インターフェース (`base_parser`) + レジストリ (`registry`) で新カテゴリをコード最小変更で追加可能 |
| **Amazon揺れ耐性** | unmapped バケット + total-amount 突合で列名変更を自動検出 |
| **弥生出力** | やよいスマート取引取込 (CSV) をメイン出力とする |

---

## 1. ディレクトリ構成

```
src/
├── main.py                         # エントリーポイント / GUI起動
├── gui/
│   └── app.py                      # GUI本体
├── core/
│   ├── pipeline.py                 # パイプライン統括
│   ├── models.py                   # データモデル定義（→ 04_models_and_specs.md）
│   ├── registry.py                 # パーサレジストリ
│   ├── base_parser.py              # パーサ共通インターフェース (ABC)
│   ├── detector.py                 # フォーマット検出
│   ├── parsers/
│   │   ├── bank.py                 # 銀行明細パーサ (YAML駆動)
│   │   ├── amazon.py               # Amazon決済レポートパーサ
│   │   └── creditcard.py           # クレジットカード明細パーサ [将来]
│   ├── normalizer.py               # 正規化変換（MVPではコード実装中心）
│   ├── validator.py                # データバリデーション（NormalizedTransaction）
│   ├── ruleset/
│   │   └── loader.py               # rules/*.yml 読み込み（銀行/Amazon等の軽量ローダ）(YAMLスキーマは余白だけ残す)
│   ├── ledger_generator.py         # 仕訳候補生成
│   └── exporter.py                 # 出力（スマート取引取込CSV等）
├── rules/
│   ├── bank_format_mufj.yml        # 三菱UFJ フォーマット定義
│   ├── bank_format_aichibank.yml   # 愛知銀行 フォーマット定義
│   ├── amazon_summary_map.yml      # Amazon決済レポート集計ルール
│   └── cc_format_*.yml             # [将来] クレジットカードフォーマット
├── tests/                          # → 04_test_spec.md
├── outputs/                        # 実行時出力先 (YYYYMMDD_HHMMSS/)
```

---

## 2. モジュール一覧

### 2.1 main.py — エントリーポイント

| 項目 | 内容 |
|------|------|
| **責務** | GUIの初期化・表示、イベントループの開始 |
| **使用するデータモデル** | なし（GUIに委譲） |
| **参照するSpec/YAML** | なし |
| **主要エラー** | GUI初期化失敗 → アプリ起動中断、ダイアログでエラー表示 |
| **例外処理** | トップレベル try-except でキャッチし、ログ出力 + ユーザー通知 |

---

### 2.2 gui/app.py — GUI本体

| 項目 | 内容 |
|------|------|
| **責務** | ファイル選択、変換実行（`pipeline.run()` 呼出）、サマリ/エラー/仕訳確認テーブル表示、出力ボタン |
| **使用するデータモデル** | `ProcessingSummary`, `LedgerDraft`, `ValidationError` |
| **参照するSpec/YAML** | なし（pipeline 経由で間接取得） |
| **主要エラー** | ファイル未選択で変換押下 → ダイアログ警告 |
| | pipeline 実行中の例外 → エラーダイアログ + ログ出力 |
| **例外処理** | pipeline 呼出を try-except で囲み、想定外例外はスタックトレースをログ表示領域に出力 |

---

### 2.3 core/pipeline.py — パイプライン統括

| 項目 | 内容 |
|------|------|
| **責務** | 検出 → パース → 正規化 → バリデーション → 仕訳生成 → 出力の全ステップを順序制御。複数ファイルの結合。`ProcessingSummary` の集計 |
| **使用するデータモデル** | `DetectionResult`, `RawRecord`, `NormalizedTransaction`, `ValidationError`, `LedgerDraft`, `ProcessingSummary`, `SourceFileInfo` |
| **参照するSpec/YAML** | なし（各モジュールに委譲） |
| **主要エラー** | |
| | `DetectionError` — detector がフォーマートを判定できない → 該当ファイルをスキップし `ValidationError(level="error")` に記録。他ファイルは処理継続 |
| | `ParseError` — パーサが行の解析に失敗 → 該当行を `ValidationError(level="error")` に記録。他の行は処理継続 |
| | 全ファイルが判定失敗 → `ProcessingSummary(total_count=0, error_count=N)` をGUIに返却 |
| **例外処理** | 各ステップを個別に try-except し、ステップ単位で障害を捕捉。致命的エラー（I/O不能等）はそのまま raise して GUI 側でキャッチ |
| **ログ出力** | 実行日時、入力ファイル名、各ステップの件数を `run_log.txt` に記録 |

**データフロー:**
```
ファイルパスリスト
 ├→ detector.py       → DetectionResult
 ├→ registry.py       → Parser インスタンス
 ├→ parsers/*.py      → List[RawRecord]
 ├→ normalizer.py     → List[NormalizedTransaction]
 ├→ validator.py      → (List[有効NormalizedTransaction], List[ValidationError])
 ├→ ledger_generator  → List[LedgerDraft]
 └→ exporter.py       → CSV群 + run_log.txt
                         → ProcessingSummary を GUI に返却
```

---

### 2.4 core/registry.py — パーサレジストリ

| 項目 | 内容 |
|------|------|
| **責務** | `source_kind` をキーにパーサクラスを登録・解決。新カテゴリ追加時の拡張ポイント |
| **使用するデータモデル** | なし（パーサクラスそのものを管理） |
| **参照するSpec/YAML** | なし |
| **登録キー例** | `"bank_statement"` → `BankParser`, `"amazon_settlement_report"` → `AmazonParser`, `"credit_card_statement"` → `CreditCardParser` |
| **主要エラー** | `UnknownSourceKindError` — 未登録の `source_kind` で解決を試みた場合。メッセージに受け取った `source_kind` の値を含める |
| **例外処理** | 即座に例外を raise → pipeline 側でキャッチして `ValidationError` に変換 |

---

### 2.5 core/base_parser.py — パーサ共通インターフェース (ABC)

| 項目 | 内容 |
|------|------|
| **責務** | `parse(file_path: str, config: dict) → List[RawRecord]` のインターフェースを ABC として定義 |
| **使用するデータモデル** | `RawRecord` （戻り値型） |
| **参照するSpec/YAML** | なし（各パーサ実装が個別のYAMLを読む） |
| **契約** | 全パーサはこのインターフェースを実装する。pipeline / normalizer はこのインターフェースのみに依存する |
| **主要エラー** | ABC のため自身はエラーを出さない。実装側が `ParseError` を送出する |

---

### 2.6 core/detector.py — フォーマット検出

| 項目 | 内容 |
|------|------|
| **責務** | ファイルのエンコーディング判定、ヘッダ行取得、`rules/` 配下のYAMLとのテンプレートマッチング |
| **使用するデータモデル** | `DetectionResult` （出力） |
| **参照するSpec/YAML** | `rules/bank_format_*.yml`, `rules/amazon_summary_map.yml`, `rules/cc_format_*.yml` — 各YAMLの `header_aliases` を読み取り突合 |
| **判定ロジック** | (1) UTF-8 → cp932 → Shift-JIS の順でエンコーディング試行 → (2) 先頭行の列名集合を抽出 → (3) 全YAMLの `header_aliases` と完全一致/包含一致で最適テンプレートを判定 |
| **主要エラー** | |
| | `EncodingDetectionError` — 全エンコーディング試行が失敗 → ファイルが読めない。メッセージにファイルパスを含める |
| | `FormatNotMatchedError` — どのテンプレートにも一致しない → 「不明フォーマット」エラー。メッセージに検出されたヘッダ列名を含める |
| | 空ファイル → `FormatNotMatchedError` として処理 |
| **例外処理** | pipeline へ例外を返し、pipeline が `ValidationError` に変換して記録 |
| **補足** | ヘッダ名の表記揺れ（全角半角、（円）の有無など）は `header_aliases` に別名を列挙する方式で吸収（YAML 側で管理） |

---

### 2.7 core/parsers/bank.py — 銀行明細パーサ

> **注意（MVP実装）**: 現在の実装では、銀行明細パーサは「CSV行→RawRecord」の読み取りとヘッダ別名解決に特化し、日付/金額の型変換や入出金方向の判定は `normalizer` 側で行う。

| 項目 | 内容 |
|------|------|
| **責務** | 銀行明細CSVを読み込み、ヘッダ行と `header_aliases` を使って正規列名にマッピングした `List[RawRecord]` を返す（型変換は行わない） |
| **使用するデータモデル** | `RawRecord` （出力） |
| **参照するSpec/YAML** | `rules/bank_format_mufj.yml`, `rules/bank_format_aichibank.yml` — 主に `header_aliases` とテーブル設定を使用 |
| **処理内容** | |
| | **ヘッダ解決**: 先頭行の列名と `header_aliases` を突合し、正規列名 (date/summary/amount_out 等) にマッピング |
| | **行スキップ**: 空行・合計行など、明らかにデータ行でないものをスキップ |
| | **RawRecord生成**: 各行を `row_number`, `fields`（文字列のまま）, `raw_line` に詰めて返す |
| **主要エラー** | CSV読み込み不能など致命的なI/Oエラーのみ例外として送出し、行ごとの内容不正は原則としてこの段階では判定しない（後段の normalizer/validator で検出） |
| **例外処理** | ファイル単位で try-except。読み込み失敗時は `ParseError` 相当を送出し、pipeline 側で `ValidationError` に変換 |

---

### 2.8 core/parsers/amazon.py — Amazon決済レポートパーサ

| 項目 | 内容 |
|------|------|
| **責務** | Amazon決済レポート（TSV）をパースし、`settlement-id` 単位でグルーピング、バケット集計を行い `List[RawRecord]` を返す |
| **使用するデータモデル** | `RawRecord` （出力） |
| **参照するSpec/YAML** | `rules/amazon_summary_map.yml` — `key`, `summary_buckets`（`include`, `formula`, `normalize`）, `ledger_defaults`, `validations` を使用 |
| **処理内容** | |
| | **TSV読み込み**: タブ区切りでパース |
| | **精算単位グルーピング**: `settlement-id` 単位で明細行をグループ化 |
| | **バケット集計**: `amount_type` + `amount_description` で各バケットに金額を振り分け |
| | **数式処理**: `formula` 定義の `add` / `subtract` による複合演算 |
| | **正規化方式**: RAW (符号保持) / ABS (絶対値) / NEGATE (符号反転) を各バケットに適用 |
| | **デフォルト科目付与**: `ledger_defaults` をバケットに紐付け |
| | **未知行の吸収**: `include` リストにマッチしない行は `unmapped` バケットに集約 |
| **主要エラー** | |
| | `total-amount` と各バケット合算値の不一致 → `ValidationError(level="warn", field="total_amount")` |
| | unmapped バケットに行が存在 → `ValidationError(level="warn", field="unmapped_bucket")` メッセージに件数・合計金額を含める |
| | 必須列（settlement-id, amount-type, amount-description, amount）の欠損 → `ValidationError(level="error")` |
| **例外処理** | settlement 単位で try-except。1精算の失敗が他の精算をブロックしない |

---

### 2.9 core/parsers/creditcard.py — クレジットカード明細パーサ [将来]

| 項目 | 内容 |
|------|------|
| **責務** | `rules/cc_format_*.yml` に基づきクレジットカード明細をパースし `List[RawRecord]` を返す |
| **使用するデータモデル** | `RawRecord` （出力） |
| **参照するSpec/YAML** | `rules/cc_format_*.yml` — `header_aliases`, `mapping` セクションを使用 |
| **処理内容** | 列マッピング（利用日・利用先・金額・支払区分）を行い、RawRecord を返す（型変換・正規化は normalizer で実施） |
| **主要エラー** | CSV/TSV 読み込み失敗、必須列欠損、行構造不正 |
| **未確定** | YAML定義の項目・カード会社ごとの列差異の吸収方法 |

> **拡張時の作業**: (1) `rules/cc_format_*.yml` 追加 (2) `parsers/creditcard.py` 実装 (3) `registry.py` に `"credit_card_statement"` → `CreditCardParser` を登録 — pipeline / detector のロジック変更は不要

---

### 2.10 core/normalizer.py — 正規化変換

> **注意（MVP実装）**: 現在の実装では、YAMLの `mapping`/`fields` DSL は未使用であり、日付/金額の型変換や摘要整形、入出金方向の判定は `normalizer` 内の Python コード（`_parse_date` / `_parse_int` / `normalize_bank` / `normalize_amazon` など）が直接行う。YAMLフル駆動の正規化は将来案とする。

| 項目 | 内容 |
|------|------|
| **責務** | 各パーサの `List[RawRecord]` を `NormalizedTransaction` に変換し、日付/金額の型変換や摘要整形、extra/row_id 付与を行う |
| **使用するデータモデル** | `RawRecord` （入力）, `NormalizedTransaction` （出力） |
| **参照するSpec/YAML** | 銀行/Amazonごとのフォーマット差異は主にパーサ側で吸収し、normalizer は必要に応じてルールYAMLの一部を参照する程度（MVPでは多くをコードにベタ書き） |
| **処理内容** | |
| | **row_id 生成**: `"{source_name}_{行番号}"` 形式（MVP）。※複数ファイル結合時の一意性は `SourceFileInfo` を含めた拡張で対応可能 |
| | **摘要整形**: summary + details の連結・空白圧縮・トリム |
| | **YAML駆動の型変換**: 日付/金額/文字列の正規化（trim、replace、regex_extract 等） |
| | **入出金の契約強制**: `amount_out/amount_in` は 0 以上、方向に応じて片側のみが正値になるよう補正（YAMLの指示 + 最終ガード） |
| | **extra マッピング**: テンプレ固有情報を辞書に格納（YAMLの `extra_fields` 等で指定） |
| | **raw 保持**: 元行データをデバッグ/監査用に保持 |
| **主要エラー** | |
| | `RawRecord.fields` に必須キーが存在しない → `ValidationError(level="error")` |
| | 型変換失敗（amount が文字列のまま等） → `ValidationError(level="error")` |
| **例外処理** | 行単位で try-except。変換失敗行は `ValidationError` に記録し、残りは処理を継続 |

---

### 2.11 core/ruleset/loader.py — ルールファイル読込（軽量チェック）

> **注意（MVP実装）**: `ruleset/` 配下には `loader.py` のみが存在し、YAMLスキーマ定義や汎用的な RuleSet バリデータはまだ実装していない。ルールファイルは各モジュールが個別に参照しつつ、loader が最低限の存在チェック・型チェックを行う。

| 項目 | 内容 |
|------|------|
| **責務** | `rules/*.yml` を読み込み、Pythonの辞書として提供する（銀行フォーマット定義やAmazon集計ルールなど）。必要なキーの有無や型を簡易に検証する |
| **構成** | `ruleset/loader.py`（銀行フォーマット/ledgerマッピング等のローダを実装） |
| **参照するSpec/YAML** | `rules/bank_format_*.yml`, `rules/amazon_summary_map.yml`, `rules/ledger_mapping.yml` など |
| **検証観点（例）** | 必須キーの存在、値の基本的な型（dict/list/str 等）の確認、ファイルパスの解決 |
| **主要エラー** | ロード失敗時の例外（ファイル不存在/パース不能/必須キー欠如など）を送出し、呼び出し元で `ValidationError` 等に変換 |

---

### 2.12 core/validator.py — バリデーション

| 項目 | 内容 |
|------|------|
| **責務** | `NormalizedTransaction` のリストを検証し、有効行とエラーリストに分離して返す |
| **使用するデータモデル** | `NormalizedTransaction` （入力）, `ValidationError` （出力） |
| **参照するSpec/YAML** | なし（検証ロジックはコードで固定。将来的にYAML側に検証ルールを移管する可能性あり） |
| **検証ルール** | |
| | **必須フィールド**: `date` が null → `error` |
| | **入出金整合**: `amount_out > 0 AND amount_in > 0` → `warn` / 両方ゼロ → `warn` |
| | **金額フォーマット**: 数値化できない → `error` |
| | **残高照合（任意）**: 前行残高 ± 入出金 と当行残高の大幅な差異 → `warn` |
| **出力** | `(List[有効NormalizedTransaction], List[ValidationError])` — error のある行は有効リストから除外 |
| **主要エラー** | 上記検証ルールで検出された問題をすべて `ValidationError` として蓄積 |
| **例外処理** | 検証自体は例外を出さない設計。想定外の型エラー等はキャッチしてfallback `ValidationError` に変換 |

---

### 2.13 core/ledger_generator.py — 仕訳候補生成

| 項目 | 内容 |
|------|------|
| **責務** | 有効な `NormalizedTransaction` から `LedgerDraft` を生成する |
| **使用するデータモデル** | `NormalizedTransaction` （入力）, `LedgerDraft` （出力） |
| **参照するSpec/YAML** | `rules/ledger_mapping.yml` — 銀行/Amazonそれぞれの科目マッピング・キーワードルールを定義 |
| **処理内容** | |
| | **入出金→借方/貸方変換**: 入金 → 借方:普通預金 / 貸方:売上高等。出金 → 借方:経費科目 / 貸方:普通預金。クレカ → 借方:経費科目 / 貸方:未払金 |
| | **科目推定（キーワードマッチ）**: 摘要テキストのキーワード（振替/カード/手数料等）で仮科目を割り当て |
| | **Amazon仕訳**: `ledger_defaults` に基づきバケット別仕訳（売掛金/売上高/仮受消費税/支払手数料）を生成 |
| | **タグ付与**: `source_type` ベース + 取引性質タグ (fee/refund 等) |
| | **摘要整形**: summary + details を連結、適切な長さに丸め |
| **主要エラー** | |
| | 科目が推定できない取引 → デフォルト科目（`"未分類"` 等）を仮割り当て + `ValidationError(level="warn")` で報告 |
| | `amount_out` と `amount_in` が両方 0 の行が到達した場合 → スキップ + `warn` |
| **例外処理** | 行単位で try-except。仕訳生成失敗行は `ValidationError` に記録し、残りは処理を継続 |
| **未確定** | 科目推定キーワードルールのYAML外出し（現段階はコード内にハードコード想定） |
| **未確定** | ユーザー修正→学習ルール反映の仕組み（将来対応） |

---

### 2.14 core/exporter.py — 出力

| 項目 | 内容 |
|------|------|
| **責務** | パイプラインの成果物をファイルに出力する |
| **使用するデータモデル** | `NormalizedTransaction`, `LedgerDraft`, `ValidationError`, `ProcessingSummary` |
| **参照するSpec/YAML** | なし（出力フォーマットはコード内で定義。将来的にYAML化も検討） |
| **出力ファイル** | |
| | `outputs/YYYYMMDD_HHMMSS/normalized_transactions.csv` — 正規化済み全トランザクション |
| | `outputs/YYYYMMDD_HHMMSS/ledger_draft.csv` — 仕訳候補 |
| | `outputs/YYYYMMDD_HHMMSS/error_report.csv` — エラー/警告一覧（0件でもヘッダ付きで生成） |
| | `outputs/YYYYMMDD_HHMMSS/smart_import.csv` — **スマート取引取込CSV**（やよい用メイン出力、UTF-8 BOM付きで出力） |
| | `outputs/YYYYMMDD_HHMMSS/run_log.txt` — 実行ログ |
| **主要エラー** | |
| | 出力ディレクトリ作成失敗（権限/パス不正） → `IOError` を raise |
| | CSV書き込み失敗 → `IOError` を raise |
| **例外処理** | 出力失敗は pipeline 経由で GUI に通知。部分出力（一部ファイルだけ成功）は行わず、全出力を一括で成否判定 |
| **未確定** | スマート取引取込CSVの列仕様の確定（やよい側の仕様確認待ち） |

---

## 3. エラー/ログ体系

### 3.1 エラーレベル定義

| レベル | 意味 | 行の扱い | 例 |
|--------|------|---------|-----|
| `error` | 致命的。その行は仕訳候補に含めない | 有効行リストから除外 | 日付パース不能、数値変換不能、必須列欠損 |
| `warn` | 注意。処理は継続するが確認が必要 | 有効行リストに残る | 入出金両側入力、unmapped バケット検出、残高差異、科目推定不能 |

### 3.2 エラー収集の流れ

```
detector  ──→ FormatNotMatchedError / EncodingDetectionError
                  ↓ pipeline がキャッチ
parser    ──→ 行単位の ParseError (DateParseError / AmountParseError)
                  ↓ ValidationError に変換
normalizer ──→ 変換失敗行
                  ↓ ValidationError に変換
validator  ──→ 検証ルール違反
                  ↓ ValidationError を直接生成
ledger_gen ──→ 科目推定不能、金額ゼロ行
                  ↓ ValidationError(level="warn") を追加生成

  すべての ValidationError を蓄積 → error_report.csv + GUI表示
```

### 3.3 実行ログ（run_log.txt）の構成

| 項目 | 内容 |
|------|------|
| `run_at` | 実行日時 (YYYY-MM-DD HH:MM:SS) |
| `input_files` | 入力ファイルパスのリスト |
| `per_file` | ファイルごとの format_id, source_kind, 取込行数, error数, warn数 |
| `total_count` | 取り込み総件数 |
| `period` | 対象期間 (最小日付〜最大日付) |
| `total_in` | 入金合計額 |
| `total_out` | 出金合計額 |
| `ledger_count` | 生成仕訳候補件数 |
| `error_count` | error レベル件数 |
| `warn_count` | warn レベル件数 |
| `output_dir` | 出力先ディレクトリパス |

---

## 4. 拡張ポイント

| 拡張対象 | 必要な作業 |
|----------|-----------|
| 新しい銀行の追加 | 基本的には `rules/bank_format_xxx.yml` を追加するだけで対応する想定だが、MVP実装ではフォーマット差が大きい場合にパーサ/normalizer 側のコード拡張が必要になることがある |
| クレジットカード対応 | (1) `rules/cc_format_*.yml` 追加 (2) `parsers/creditcard.py` 実装 (3) `registry.py` に1行登録 |
| 新カテゴリ (PayPal, 楽天等) | (1) `rules/` にYAML追加 (2) `parsers/` にパーサ追加 (3) `registry.py` に登録。pipeline以降は変更不要 |
| Amazonレポート列名変更 | `amazon_summary_map.yml` の `include` リストに追加。コード変更不要 |
| 科目推定の高度化 | `ledger_generator.py` のキーワードマッチをYAML化、または学習ベースに置換 |
| 弥生以外の会計ソフト | `exporter.py` に出力フォーマットを追加 |

---

## 5. Amazon揺れ耐性の設計

| レイヤー | 対策 |
|---------|------|
| **ヘッダ検出** | `detector.py` は必須列 (settlement-id, amount-type, amount-description, amount) の存在だけで判定。余分な列は無視 |
| **バケット振り分け** | `amazon_summary_map.yml` の `include` リストで既知の組み合わせを列挙。新しい組み合わせが来ても他バケットに影響しない |
| **unmapped バケット** | どの `include` にもマッチしない行を `unmapped` に集約し、金額と件数を warn として報告 |
| **YAML更新のみで対応** | 新しい `amount_description` が判明したらYAMLに1行追加するだけ。コード変更不要 |
| **バリデーション** | 現状は `unmapped` バケット有無の warn に留め、`total-amount` と各バケット合算値の突合は将来対応とする |
