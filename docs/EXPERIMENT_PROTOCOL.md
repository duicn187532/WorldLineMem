# 實驗協定

本文件規定所有比較實驗共用的流程。凡是偏離本協定的設定，都必須在結果表格中註明。

## 1. 結果的三種標籤（不可混用）

| 標籤 | 意義 | 能不能和原論文數字並列比較 |
|---|---|---|
| **Original Paper Result** | 原論文報告的數字，照原樣引用並附來源 | 這就是原論文數字本身 |
| **Local Adaptation** | 官方資料、官方 prompt、官方評分程式，但作答模型、judge 或 embedding 換成本機模型 | **不行**。只能在相同本機設定下互相比較 |
| **Smoke Test** | 工程驗證，題數極少、模型極小 | 不行；不是研究結果 |

每次執行的 `manifest.json` 都有 `label` 欄位。使用 mock 模型時，標籤會被強制改成 `PIPELINE_CHECK_MOCK_*`。

## 2. 資料流程

```
官方資料（鎖定版本、sha256 驗證）
  → Loader：只保留記憶方法「可以看到」的欄位；標準答案放進 Case.gold
  → 依時間順序逐個 session 呼叫 MemoryAdapter.ingest()
  → 每題提問前，只輸入「提問當下之前」的 session
  → MemoryAdapter.retrieve(query) → MemoryContext
  → Benchmark.render()：官方作答 prompt
  → 作答模型 → answers.jsonl
  → wlmem evaluate：官方評分程式 ＋ 設定好的 judge → eval/<judge>/metrics.json
```

## 3. 資料隔離規則

1. **案例之間隔離**：每個案例都建立新的 MemoryAdapter 並呼叫 `reset()`（`tests/test_runner_protocol.py` 有驗證）。
2. **不使用未來資訊**：`Query.visible_sessions` 決定提問前能輸入幾個 session；runner 依題目可見範圍由小到大處理。
3. **不使用標準答案**：以下欄位一律不會傳給記憶方法或出現在 prompt 裡：
   - STALE：`M_old`、`M_new`、`explanation`、`relevant_session_index`、`type`
   - LongMemEval：`answer`、`question_type`、`answer_session_ids`、turn 層級的 `has_answer`、原始 session id
   - Memora：`share_memory`、`session_type`、`operation`、`operation_details`、`memory_evidence`、`forgetting_evidence`、評分用的子問題
4. **不使用標準答案做截斷**：STALE 官方的 `--enable-trim` 會依證據位置保留 session，本框架不使用。full_context 超出長度時，一律從最舊的 session 開始捨棄。
5. **不修改官方資料**：資料以 sha256 驗證，官方 repo 必須是鎖定的 commit 且沒有本地修改，否則程式拒絕執行（`check_official_checkout`）。

## 4. 公平比較條件

同一組比較（同一張表）中，以下設定必須完全相同：

- benchmark 版本與子集（`[benchmark]` 整段）
- 作答模型：名稱、Ollama digest、量化、`num_ctx`、`num_predict`、`temperature`、`seed`、`think`
- judge 模型及其設定
- 作答 prompt（由 benchmark 決定，記憶方法無法更改）

只有 `[memory]`（以及記憶方法需要的 `[memory_model]`、`[embedding]`）可以不同。若要比較不同的 embedding 模型，那是另一組實驗。

### 解碼設定

- 作答一律使用 `temperature=0`，`seed=42`。
- 這和部分官方設定不同（Memora Track 1 使用 0.7，STALE 使用 API 預設值）。統一設定是為了可重現，屬於 Local Adaptation 的一部分。
- Qwen3 這類混合推理模型設定 `think=false`。若要測試開啟推理的效果，另外開一組並在表格中註明。

### context 長度

- Ollama 預設會**默默截掉**超過 `num_ctx` 的輸入。實測：輸入約 1.4 萬 token、`num_ctx=512` 時，它只保留 258 個 token，而且回報的 `prompt_eval_count` 也是 258，從回應本身完全看不出有被截斷。
- 因此每次請求都帶 `truncate: false`。輸入過長時，伺服器會直接回錯誤，並附上精確的 token 數。這一題會記進 `errors.jsonl`，不會產生答案，評估時也會顯示 `complete: false`。
- `wlmem check-ollama` 會驗證安裝的 Ollama 是否遵守這個設定（0.40.16 已實測遵守）。若不遵守，指令會回傳錯誤。
- 第二道保險：runner 用 cl100k 估算值計算 `ctx_overflow_risk`，在評估的 `answer_cost.ctx_overflow_risks` 中統計。
- **正式結果要求：沒有任何 context 錯誤，且 `ctx_overflow_risks` 為 0**；否則必須調整 `num_ctx` 或 `max_context_tokens` 後重跑。

## 5. 評估規則

| Benchmark | 使用的官方程式 | 本機替換的部分 |
|---|---|---|
| STALE | `full_eval_performance.run_evaluation`（直接呼叫，T1、T2 各跑一次） | judge 端點改為本機（透過 `AsyncOpenAIShim`） |
| LongMemEval | `evaluate_qa.get_anscheck_prompt`；判定邏輯與 `max_tokens=10` 都照官方 | 官方 `main` 把 judge 寫死，所以迴圈由本框架執行，邏輯逐行對應 |
| Memora | `ModelEvaluator`（judge prompt 與解析）、`fama_score` | 官方用三個 judge 多數決；本機只用單一 judge |

彙總方式：

- STALE 的 Overall 是 6 格準確率的平均。
- LongMemEval 同時報 overall 與 task-averaged。
- Memora 報每個「任務 × 時間長度」格的 FAMA×100。

## 6. judge 驗證（正式實驗前必做）

smoke test 已經證實，小模型當 judge 會把錯誤答案判成正確（見 VALIDATION_REPORT.md §4）。本機 judge 在正式使用前，必須完成以下步驟：

1. 從各 benchmark 抽取作答結果（例如每個 benchmark 50 題，涵蓋各題型）。
2. 由人工依**官方評分準則**標註對錯。
3. 計算本機 judge 與人工標註的一致率和 Cohen's κ，連同 judge 的模型名稱與 digest 一起報告。
4. 一致率不足時改換 judge，並且不得以任何方式修改評分準則。

這一步不會產生新的評分指標；它只驗證「用本機模型執行官方準則」這件事本身是否可靠。

## 7. 可重現性

- 每次執行都會寫出 `manifest.json`，內容包括 git commit、設定檔 sha256、資料 sha256、官方 repo commit、模型 digest、量化等級、原生 context、Ollama 版本、Python 與作業系統版本。
- 設定檔被修改後，同一個執行名稱會拒絕續跑，避免不同設定的結果混在同一個資料夾。
- 中斷後重新執行同一個設定檔即可續跑。未完成的案例會從頭重新 ingest，所以對確定性的方法而言，結果和沒有中斷時一樣。
- 逐題記錄回答、prompt sha256、prompt 估計 token 數、實際 `prompt_tokens`、延遲、檢索到的單元、記憶大小，以及每個案例的 ingest 成本（記憶方法的 LLM 呼叫和 embedding 呼叫分開計）。
- 回報結果時，`runs/<name>/` 整個資料夾連同 `external.lock.json` 一起封存。

## 8. 接入新的記憶方法（FadeMem、Zep、自己的方法）

1. 在 `src/wlmem/memory/` 新增模組，類別加上 `@register("名稱")` 並實作 `reset`、`ingest`、`retrieve`。
2. 方法內需要呼叫 LLM 或 embedding 時，一律透過 `self.services.llm` 和 `self.services.embedder`，成本才會被分開計算。
3. 回傳 `MemoryContext(sessions=...)` 時，會使用 benchmark 官方的歷史格式；回傳 `MemoryContext(text=...)` 時，文字會放在官方 prompt 的歷史位置。
4. 複製 `configs/local/` 裡的範本，只修改 `[memory]`。
5. 原作者有程式碼時，優先包成 adapter；需要付費 API 或特定資料庫時，記錄限制，不得自行寫一個「近似版」並冠上原方法的名稱。
