# WorldLineMem：長期記憶實驗環境

碩士論文《無狀態持續型智能體在世界線變動偵測後之選擇性記憶調整》的實驗基礎設施。

本階段**只**準備：官方 benchmark（固定版本）、統一的 runner、不需外部服務的 baseline，以及可重現的紀錄。研究方法本身尚未實作。

| 文件 | 內容 |
|---|---|
| [docs/RESEARCH_SCOPE.md](docs/RESEARCH_SCOPE.md) | 研究問題、暫定假設、相關論文查證 |
| [docs/BENCHMARK_MATRIX.md](docs/BENCHMARK_MATRIX.md) | 各 benchmark 的官方來源、授權、格式、指標、限制、驗證狀態 |
| [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md) | 已驗證的開發環境、本機盤點方式、Windows 注意事項 |
| [docs/EXPERIMENT_PROTOCOL.md](docs/EXPERIMENT_PROTOCOL.md) | 資料隔離、公平比較、judge 驗證、可重現規則 |
| [docs/MIXED_MEMORY_PROTOCOL.md](docs/MIXED_MEMORY_PROTOCOL.md) | 自建的混合記憶庫協定（多人共用一個記憶庫），不是官方 benchmark |
| [docs/DIAGNOSTICS.md](docs/DIAGNOSTICS.md) | 收斂研究問題用的診斷實驗（目前：STALE × 時間衰退、Pragma 的喚醒） |
| [docs/DECISION_GATES.md](docs/DECISION_GATES.md) | 決定研究重心的判斷門檻（已停用） |
| [docs/READING_LIST.md](docs/READING_LIST.md) | 研究者親自閱讀的文獻清單 |
| [docs/VALIDATION_REPORT.md](docs/VALIDATION_REPORT.md) | 已完成、已測通、未完成與阻塞的項目 |
| [configs/README.md](configs/README.md) | 設定檔各欄位說明 |

## 安裝（Windows PowerShell）

需要：Git for Windows、Python 3.13（`py -3.13`）、Ollama（已在執行）。

```powershell
git clone https://github.com/duicn187532/WorldLineMem.git
cd WorldLineMem

# 1) 盤點本機環境（唯讀），結果寫到 env_reports\
powershell -ExecutionPolicy Bypass -File scripts\check_env.ps1

# 2) 建立 .venv、安裝套件、下載固定版本的官方 repo 與資料（約 600 MB），並驗證 sha256
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
.\.venv\Scripts\Activate.ps1

# 3) 檢查資料完整性，並列出已知的資料問題
wlmem verify-data

# 4) 單元測試
pytest -q
```

## Smoke test（工程驗證，分數沒有意義）

smoke test 使用很小的模型（約 1.1 GB），用來確認整條流程能跑通：

```powershell
ollama pull qwen3:0.6b
ollama pull qwen3-embedding:0.6b
wlmem check-ollama --model qwen3:0.6b

wlmem run      configs\smoke\lme_oracle_full_context.toml
wlmem evaluate configs\smoke\lme_oracle_full_context.toml
# 其他：stale_no_memory、stale_rag_bm25、memora_weekly_rag_bm25、lme_s_rag_dense
# 自建協定：mixed_k2_none_rag_global、mixed_k2_label_rag_scoped
```

## 正式實驗（Local Adaptation）

1. 從 `configs\local\` 複製範本，把所有 `CHANGE_ME` 改成 `ollama list` 裡實際存在的模型。沒改完，程式會拒絕執行。
2. 同一組比較只能改 `[memory]`，其餘設定都要相同（見實驗協定 §4）。
3. 開始之前，先完成 judge 驗證（實驗協定 §6）。

```powershell
wlmem run      configs\local\stale__rag_bm25.toml
wlmem evaluate configs\local\stale__rag_bm25.toml
```

## 輸出

每次執行的結果放在 `runs\<run name>\`：

| 檔案 | 內容 |
|---|---|
| `manifest.json` | 標籤、git commit、設定檔 hash、資料 hash、官方 commit、模型 digest |
| `answers.jsonl` | 逐題回答與成本 |
| `cases.jsonl` | 每個案例的 ingest 成本與記憶大小 |
| `errors.jsonl` | 錯誤紀錄 |
| `eval\<judge>\metrics.json` | 指標，以及官方格式的輸出檔 |

中斷後重新執行同一個指令即可續跑。

## 結構

```
external.lock.json         官方 repo 的 commit 與資料的 sha256
scripts/                   check_env.ps1（盤點）、setup.ps1、setup_external.py
src/wlmem/
  types.py                 Session / Query / Case / MemoryContext
  backends.py              Ollama 對話與 embedding、mock、成本計數
  memory/                  MemoryAdapter 介面；no_memory、full_context、rag
  benchmarks/              stale、longmemeval、memora（呼叫官方 prompt 與評分程式）
                           memora_mixed（自建協定：多人交錯成一條對話流）
  runner.py                依時間順序 ingest、續跑、紀錄、評估
  integrity.py             wlmem verify-data
configs/smoke, configs/local
tests/                     隔離、時間順序、續跑、官方 prompt 逐字比對、混合協定的不變量
```

接入新的記憶方法（FadeMem、Zep，或自己的方法），請見實驗協定 §8。
