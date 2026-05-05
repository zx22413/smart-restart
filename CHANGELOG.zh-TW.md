# Changelog

[English](CHANGELOG.md) | 繁體中文

本檔記錄此專案所有值得注意的變更。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，
版本規範遵循 [Semantic Versioning](https://semver.org/lang/zh-TW/)。

## [Unreleased]

## [0.1.0] - 2026-05-06

首次公開釋出。一個可直接套用的 Python 服務 restart decider：吃 changed file 清單與 YAML 規則集，印出該執行哪些 action。可選地走靜態 AST import graph 反向閉包——當你改了一個 leaf utility，每個 import 它的服務都會被正確觸發 restart。

### Added

#### 核心 decider

- 純函式 rule engine：`decide(changed_files, rules) -> Decision`
- First-match-wins glob 比對，支援 `**` 跨目錄（自訂 regex 翻譯 + per-pattern 快取）
- YAML 宣告 actions，含明確順序（`order: int`，數字小者先跑）
- 對未匹配檔案的三種 fallback 策略：
  - `none` — 未匹配檔案不貢獻任何 action（預設）
  - `all` — 觸發所有宣告過的 action
  - `[action_list]` — 只觸發指定的 action
- rules 或 fallback 引用未宣告的 action 會早早拋 `ValueError`（不靜默吞 typo）

#### Import-chain 擴展 (`--root <path>`)

- 對專案原始碼做 AST 靜態分析
- 反向閉包：改一個檔案會把所有 transitive 上游 importer 一起算進 changed
- 統一處理三種 import 寫法：
  - `import pkg.foo`
  - `from pkg import foo`（foo 是 submodule）
  - `from pkg.foo import X`（X 是名稱）
- 支援相對 import（`from .leaf import X`）
- 跳過 `__pycache__`、`.venv`、dotted 目錄
- 遇到 syntax error 的檔案不 crash（只是不貢獻 edges）
- Path prefix 支援，讓 `git diff` 輸出（project-relative）跟 `--root src`（root-relative）對齊

#### CLI

- `smart-restart -r <rules.yaml>` — 從 stdin 讀 changed 檔案，印出 actions
- `--root <path>` — 啟動 import-chain 擴展
- `--show-unmatched` — 把未匹配檔案清單印到 stderr
- `--show-expanded` — 把 import-chain 擴展加進去的檔案印到 stderr
- 穩定可被 script 消費的輸出：actions 走 stdout、診斷走 stderr

#### 文件

- 雙語 README（英文 + 繁中）——quick start、設定參考、src-layout 陷阱表格
- `docs/architecture.md` — 三大設計支柱、module resolution 演算法、conservative-by-default 哲學、從 upstream 抽出時拔掉了什麼、v0.2 開放問題
- `examples/` 三個情境：
  - `basic` — 單一 web service
  - `multi-service` — 三服務共用 code tree，「為什麼需要 `--root`」的完整示範
  - `monorepo` — 獨立 source trees，每個跑一次然後 union 輸出

#### 專案基礎建設

- 39 個 tests 跨 decider 與 import_graph，全部用 `tmp_path` hermetic
- GitHub Actions CI：ruff lint + pytest 跑 Python 3.11 / 3.12 / 3.13
- PyPI Trusted Publisher（OIDC）已設定

### 備註

- **不執行任何指令**。`smart-restart` 只印出 actions 然後退出；執行交給下游 script。這是有意的設計（見 `docs/architecture.md`）。
- **LLM fallback 延後到 v0.2**。upstream 專案用 Claude 對未匹配檔案分類；v0.1 保持 lib 零依賴（除了 PyYAML）。v0.2 會把它做成可選 plugin。
- **多 root graph 合併延後到 v0.2**。目前 monorepo 對每個 source root 各跑一次 decider。examples 有 bash wrapper 示範如何 union。
- **src-layout 自動偵測延後到 v0.2**。目前 src-layout 專案要手動傳 `--root src`。

[Unreleased]: https://github.com/zx22413/smart-restart/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/zx22413/smart-restart/releases/tag/v0.1.0
