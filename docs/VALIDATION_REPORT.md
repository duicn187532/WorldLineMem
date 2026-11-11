# 驗證報告

日期：2026-11-11。驗證環境：雲端開發容器（見 ENVIRONMENT.md §A），Ollama 0.40.16（CPU）。

> 本報告中的所有數字都是 **Smoke Test**（工程驗證）：使用 `qwen3:0.6b`、每個 benchmark 只跑 2–3 個案例。它們**不是**研究結果，不得引用為 baseline 分數。

## 1. 驗收清單

| 項目 | 狀態 | 證據或原因 |
|---|---|---|
| 已盤點並驗證本機推論環境 | **未完成**（不在可存取範圍） | 雲端容器無法存取 Flow Z13。已提供唯讀盤點腳本 `scripts/check_env.ps1`，但它**沒有實際執行過**（容器沒有 Windows／PowerShell，只做過人工檢查） |
| 已查證 P0／P1 benchmark 的官方來源與使用限制 | 完成 | BENCHMARK_MATRIX.md；repo commit 與資料 sha256 已鎖定在 `external.lock.json` |
| P0 資料與官方評分工具已備妥 | 完成 | `setup_external.py` 輸出 ALL OK；`wlmem verify-data` 輸出 DATA OK |
| 已建立模組化的 benchmark runner | 完成 | `src/wlmem/`；記憶方法、benchmark、模型後端都可以替換 |
| 至少一套 P0 benchmark 完成端到端 smoke test | 完成（三套 P0 都完成） | 見 §3 |
| 有可重現的 PowerShell 指令與設定 | 部分完成 | 指令和設定都已提供；PowerShell 腳本尚未在 Windows 上實際執行 |
| 原始測試資料與評估協定未被修改 | 完成 | 官方 repo 必須是鎖定的 commit 且沒有本地修改，否則拒絕執行；資料經 sha256 驗證；prompt 經逐字比對測試 |
| 原論文結果、Local Adaptation、smoke test 有明確區分 | 完成 | `manifest.json` 與 `metrics.json` 都有 `label` 欄位；mock 模型會被強制標記 |
| 所有尚未驗證的項目都已標示 | 完成 | 本報告 §5 |
| 沒有自創 benchmark、題目或評分指標 | 完成 | 只使用官方資料、官方 prompt 和官方評分程式 |

## 2. 已測通的項目

| 檢查 | 結果 |
|---|---|
| 官方 repo checkout（STALE、LongMemEval、Memora、LoCoMo、MemoryAgentBench） | 五個都在鎖定的 commit |
| 資料 sha256（STALE、LongMemEval oracle 與 S）、Memora 資料目錄雜湊（27,644 個檔案） | 全部吻合 |
| `wlmem verify-data`：題數與結構 | STALE 400（T1 200／T2 200）、LongMemEval 500×2、Memora 10 個 persona × 3 種長度 |
| 單元測試 `pytest` | 21 個全部通過 |
| 本框架產生的 STALE prompt 與官方程式產生的逐字相同；Memora 在 `drop_user_turns = true` 時逐字相同 | 通過（`test_official_provenance.py`） |
| LongMemEval 複製過來的 prompt 模板在官方檔案中逐字存在 | 通過 |
| 案例之間記憶隔離、依時間順序 ingest、提問前只看得到已發生的 session | 通過（`test_runner_protocol.py`） |
| 標準答案欄位不會進入記憶方法或 prompt（`has_answer`、`answer_*` id、Memora 的標註欄位） | 通過 |
| 續跑 | 重新執行已完成的設定，新增 0 題（STALE RAG 實測） |
| 可重現性：用存下的 prompt 重新作答（temperature 0、seed 42） | 回答逐字相同，prompt token 數相同（9,604） |
| 混合記憶庫協定：1 人時與官方 Memora prompt 逐字相同；每個人的 session 順序不變；persona 名稱不外露；提問在本人最後一個區塊之後；相同 seed 產生相同對話流 | 通過（`test_memora_mixed.py`） |
| 依訊號隔離（`scope = "context"`）只取到本人的記憶；沒有訊號時報錯 | 通過 |
| 自建協定的結果標籤自動加上 `derived_protocol:` | 通過 |
| 輸入過長的處理：`truncate:false` | Ollama 會回錯誤並附上精確 token 數，不會截斷；`wlmem check-ollama` 可以驗證 |

## 3. Smoke test 結果（工程驗證，分數沒有意義）

作答模型與 judge 都是 `qwen3:0.6b`（Q4_K_M），embedding 是 `qwen3-embedding:0.6b`，在 4 核 CPU 上執行。

| 設定 | 題數 | 錯誤 | prompt token | 平均延遲 | ingest 時間 | 評估 |
|---|---|---|---|---|---|---|
| LongMemEval oracle × full_context | 3 | 0 | 6,176–9,604 | 65 s | < 0.2 s | 官方 judge prompt，3 次呼叫 |
| LongMemEval S × rag（dense，round） | 2 | 0 | 1,499–3,306 | 13 s | 237–246 s（每個案例約 1,500 個 round 的 embedding） | 2 次呼叫 |
| STALE × no_memory | 6 | 0 | 63–87 | 4 s | 0 | 官方 `run_evaluation`，T1 |
| STALE × rag（BM25，round） | 6 | 0 | 4,199–6,331 | 53 s | < 0.1 s | 官方 `run_evaluation`，T1 |
| Memora weekly × rag（BM25） | 3 | 0 | 1,485–1,610 | 18 s | < 0.1 s | 官方 `ModelEvaluator`，32 個子問題 |
| 自建協定：混合 2 人 × 無訊號 × rag（BM25，全部共用） | 4 | 0 | 1,746–1,908 | 14 s | < 0.1 s | 官方 `ModelEvaluator`，46 次 judge 呼叫；誤取率 41.3%，4 題都取到別人的單元 |
| 自建協定：混合 2 人 × 身分標籤 × rag（BM25，依標籤隔離） | 4 | 0 | 1,693–1,901 | 11 s | < 0.1 s | 官方 `ModelEvaluator`，46 次 judge 呼叫；誤取率 0% |

Memora 這一列是修正「讀取程式漏掉使用者發言」之後重跑的結果（2026-11-11）。「自建協定」兩列不是官方 benchmark。

所有測試都確認了：資料可以讀取、session 依時間順序輸入、模型能回答、官方評分程式能輸出、日誌與 manifest 都有寫出。

## 4. smoke test 發現的問題：小型 judge 不可靠

smoke test 裡的分數不能採信，原因不只是題數太少，而是 judge 本身會判錯：

- **LongMemEval oracle**：3 題裡有 2 題答錯，judge 卻全部判「yes」。
  - 例如題目 `gpt4_2487a7cb` 的標準答案是 'Data Analysis using Python' webinar，模型回答 'Effective Time Management' workshop，judge 判為正確。
- **STALE × no_memory**：沒有記憶的模型不可能知道使用者狀態已經改變，卻拿到 0.83。
  - dim1：回答「無法判斷」，官方評分準則明寫這種情況要判不及格，judge 卻判及格。
  - dim2：回答直接順著過時的前提推薦西雅圖的資源，judge 卻判及格，理由還捏造「回答有提到使用者已經搬到 Austin」。

結論：本機 judge 必須先通過與人工標註的一致性驗證（實驗協定 §6），才能用在正式實驗。judge 的人選，要等 Z13 盤點出可用的大模型後再決定。

## 5. 尚未完成或被阻塞的項目

| 項目 | 狀態 | 原因與下一步 |
|---|---|---|
| Flow Z13 環境盤點 | 待辦 | 需要你在本機執行 `scripts\check_env.ps1`，再把 `env_reports\*.json` 提供給我 |
| `check_env.ps1`、`setup.ps1` 實際執行 | 尚未驗證 | 容器沒有 Windows；第一次執行如果出錯，請把錯誤訊息貼給我 |
| 在 Windows 上跑 `pytest` 和 smoke test | 尚未驗證 | 已處理 UTF-8 模式，但沒有實測 |
| 作答模型、judge、embedding 的人選 | 待決定 | 要等盤點結果；`configs/local` 的範本在填好 `CHANGE_ME` 之前不會執行 |
| judge 與人工標註的一致性驗證 | 待辦 | 見實驗協定 §6 |
| LoCoMo、MemoryAgentBench（CR）接入 runner | 待辦（P1） | 官方程式已下載並鎖定版本；loader 與評分轉接層尚未撰寫 |
| FadeMem | 被阻塞 | 找不到官方程式碼，LTI-Bench 沒有公開。不實作「近似版」 |
| Zep／Graphiti | 待評估 | 需要圖資料庫（Neo4j 或 FalkorDB）和 LLM 抽取；要先記錄資源需求，再由你決定是否安裝 |
| CUPMem（STALE 作者的原型） | 可行性已確認，尚未接入 | 官方程式不需修改就能指向 Ollama，用 `qwen3:0.6b` 跑通 1 個案例（14 次 LLM 呼叫，約 5 分鐘）。模型太小，寫入端沒有產生狀態更新，回答沒有意義。它自己產生最終回答，接入本框架的方式要另外設計 |
| 混合記憶庫第二部分（遷移） | 尚未設計 | 等第一部分的對照組結果出來再設計，見 MIXED_MEMORY_PROTOCOL.md §4 |
| MemAlign、*Stale, Misattributed, or Late* 的資料 | 無法取得 | 找不到公開連結 |
| SCALE-QA、GateMem 接入 runner | 待辦（P1） | 官方程式與資料已下載並鎖定版本；loader 與評分轉接層尚未撰寫。runner 目前以 session 為輸入單位，這兩個 benchmark 以 turn 為單位 |
| FedMem | 名稱有歧義 | 需要你提供論文連結 |
| AOEP-v0 | 無法取得 | 論文沒有釋出評估資源 |
| LongMemEval M 版 | 不納入 | 每題約 500 個 session，超出本機的實際能力 |
