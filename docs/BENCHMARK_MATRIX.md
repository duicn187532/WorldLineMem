# Benchmark Matrix

查證日期：2026-11-11。所有版本都鎖在 `external.lock.json`，由 `scripts/setup_external.py` 下載並驗證 sha256。

狀態定義：

- **Verified**：官方來源、資料、評分程式都已取得並鎖定版本；本框架已完成端到端 smoke test。
- **Partially Verified**：官方來源與資料已取得，但尚未接入 runner，或有未解決的限制。
- **Unavailable**：資料或評估程式沒有公開。
- **Blocked**：資源存在，但本機條件下無法執行。

## 總表

| Benchmark | 優先 | 狀態 | 官方來源（鎖定版本） | 授權 | 資料規模 | 官方指標與 judge | 本機可行性 |
|---|---|---|---|---|---|---|---|
| STALE | P0 | **Verified** | 程式：github.com/icedreamc/STALE @`ea7d391`；資料：HF `STALEproj/STALE` @`617c51d`（論文附錄 G 指定） | 程式 MIT；資料 CC-BY-4.0（干擾 session 取自 LongMemEval，MIT） | 400 個案例（T1 200、T2 200），每個案例 50 個 session、約 15 萬 token，3 個探測問題，共 1,200 題 | 每題一次 all-in-one LLM judge（原論文用 gemini-3.1-flash-lite），報 6 格準確率及平均 | 可行；full_context 需要原生 context ≥ 160K 的模型 |
| Memora | P0 | **Verified** | github.com/geniesinc/Memora @`a649318`（資料在 repo 內） | Apache-2.0 | 10 個 persona × 週／月／季；session 數約 150／600／2,000；每個 persona 15／15／30 題，共 600 題 | FAMA；三個 judge 多數決（GPT-4.1、Claude Haiku 4.5、Gemini 2.5 Flash，經 OpenRouter） | weekly 可行；monthly／quarterly 的完整歷史超過任何本機 context，只能用記憶方法 |
| LongMemEval | P0 | **Verified** | 程式：github.com/xiaowu0162/LongMemEval @`9e0b455`；資料：HF `xiaowu0162/longmemeval-cleaned` @`98d7416`（2025-09 清理版） | MIT | 500 題 × {oracle, S}；S 約 50 個 session、約 11.5 萬 token；M 版約 500 個 session（未納入） | GPT-4o judge，各題型用不同 prompt，`max_tokens=10` | 可行；M 版不納入 |
| LoCoMo | P1 | Partially Verified | github.com/snap-research/locomo @`3eb6f2c` | **CC BY-NC 4.0**（僅限非商業） | 10 段對話、1,986 題 QA（類別 1–5） | token F1（類別 1–4），類別 5 為對抗題 | 可行；尚未接入 runner |
| MemoryAgentBench | P1 | Partially Verified | github.com/HUST-AI-HYZ/MemoryAgentBench @`5380260`；HF `ai-hyz/MemoryAgentBench` | MIT | 四類：AR／TTL／LRU／CR；CR 是作者自建的 FactConsolidation（SH／MH） | CR 用 `substring_exact_match`，不需要 LLM judge | 可行；尚未接入 runner |
| SCALE-QA | P1（新增） | Partially Verified | github.com/LordTARN1SHED/SCALE-QA @`932193c`（v1.1.0，資料在 repo 內；論文結論段指定） | 資料與文件 CC-BY-4.0；TSIM 程式 Apache-2.0；內附的干擾對話取自 UltraChat（MIT） | 3,000 題四選一，10 個領域各 300 題；歷史長度由官方 builder 指定（16k 至 1M） | 選項準確率，**不需要 LLM judge** | 可行；尚未接入 runner |
| GateMem | P1（新增） | Partially Verified | github.com/rzhub/GateMem @`a983828`；HF `Ray368/GateMem`（兩處資料檔大小相同） | 程式 MIT；資料 CC-BY-4.0 | 91 個多人情節、2,218 個檢查點：utility 728、access control 727、active forgetting 763 | GPT-4o judge；主指標 MGS = U·(1−A)·(1−F) | 可行（每個情節平均約 3,900 個英文詞）；尚未接入 runner；本研究只會用到 utility 子集 |
| FadeMem 使用的資料 | — | **Unavailable**（LTI-Bench） | 論文 arXiv:2601.18642v2；找不到程式或資料連結 | — | LTI-Bench 10,780 條序列（自建、未公開）；MSC、LoCoMo 是既有公開資料 | RP@10、TCS、FCR、SRR（作者自訂） | LTI-Bench 無法取得；MSC 與 LoCoMo 可取得，但作者的評分程式未公開 |
| AOEP-v0（Always-On Agents） | 暫不列入 | **Unavailable** | arXiv:2606.30306；論文說明它是「參考設計 + 小型試驗，不是排行榜」 | — | — | 確定性規則檢查（論文描述） | 沒有釋出 harness 或資料 |

## STALE（P0）

- **論文**：Chao et al., *STALE: Can LLM Agents Know When Their Memories Are No Longer Valid?*，arXiv:2605.06527v1（2026-05-07，預印本）。
- **量測的能力**：隱性衝突。Type I 是同屬性被改寫，Type II 是因果傳播造成的失效。每個案例有三個探測維度：
  - dim1 State Resolution：直接問舊狀態是否仍然成立。
  - dim2 Premise Resistance：問題的前提建立在過時狀態上，看模型能不能抵抗。
  - dim3 Implicit Policy Adaptation：問題不提新舊狀態，但安全的回答必須依新狀態行動。

  這是**直接**量測記憶過期與衝突的 benchmark。
- **資料格式**：每個案例包含 `uid, M_old, M_new, explanation, probing_queries{dim1..3}, haystack_session[50], timestamps[50], relevant_session_index, type`；turn 只有 `role` 和 `content`；session 依時間排序（已驗證）。
- **切分**：沒有 train／dev／test 切分，400 題全部是評估集。
- **逐 session 輸入**：可以；資料附有時間戳記。
- **官方作答設定**：`run_target_model.py`。預設送完整 haystack、不截斷；`--enable-trim` 會依 `relevant_session_index` 保留證據 session。**這等於使用標準答案，本框架不使用。**
- **官方評分**：`full_eval_performance.py`，每個案例一次 judge 呼叫，`temperature=0`，`response_format=json_object`。
- **原論文比較對象**：GPT-4o-mini、GPT-5.4、Gemini-3.1、Claude-Opus-4.6、Qwen3.5-9B／27B、Llama-3.3-70B、MiniMax-M2.5；記憶框架 LightMem、Zep、LiCoMemory、A-Mem、Mem0；原型 CUPMem（repo 內有程式，需要 OpenAI 相容 API）。
- **已知限制**：
  - 資料由 LLM 生成，再經人工審核。
  - judge 是單一 LLM（論文報告與人工標註的一致率為 95.8%）。
  - 原論文的 judge 模型在本機無法使用，因此本機結果都是 **Local Adaptation**。

## Memora（P0）

- **論文**：*From Recall to Forgetting: Benchmarking Long-Term Memory for Personalized Agents*，arXiv:2604.20006v1，ACL 2026。
- **量測的能力**：回憶（memory_presence）與遺忘（forgetting_absence，指已被刪除或更新的資訊不應再出現）。三類任務：Remembering、Reasoning、Recommending。
- **資料格式**：
  - session 檔：`session_id, date, conversation[{speaker, message, share_memory}]`，另有標註欄位 `session_type, operation, operation_details`。
  - 題目檔：每題有 `question_date` 和多個是非子問題。
- **切分**：沒有切分。
- **逐 session 輸入**：可以；session 依 id 排序，附有日期。已驗證沒有任何 session 的日期晚於提問日期。
- **官方作答設定**：
  - Track 1 把全部歷史塞進 context（`PromptBuilder`），`temperature=0.7`。
  - Track 2 是六個記憶 agent（A-Mem、LangMem、Mem0、MemoBase、MemOS、Nemori），多數需要雲端 API，作答模型是 gpt-4o-mini。
- **官方評分**：`ModelEvaluator` 逐一判定是非子問題，用 `fama_score` 計算每題分數，再按任務與時間長度取平均後乘以 100。
- **已知問題**：
  - 官方 Track 1 讀的是 `question_data['session_date']`，但公開資料沒有這個欄位，所以官方 prompt 裡實際上沒有「今天日期」。本框架預設照官方行為（`pass_question_date=false`），可切換。
  - 標註欄位 `share_memory`、`session_type`、`operation` 等同部分標準答案，本框架不提供給記憶方法。
  - **官方 Track 1 的 prompt 沒有任何使用者發言。** 公開資料把使用者標成 `user_agent`，但官方 `PromptBuilder` 只輸出 `ai_agent` 和 `user`，所以完整歷史裡只剩助理的發言（academic_researcher weekly：助理 1,296 句，使用者 0 句）。官方 Track 2 的記憶 agent 則有正確對應。本框架的處理：
    - 記憶方法一律收到雙方發言。
    - 作答 prompt 預設顯示雙方發言；設定 `drop_user_turns = true` 可以逐字重現官方 Track 1 的 prompt。
    - 2026-11-11 之前，本框架的讀取程式也漏掉了使用者發言，當時的 Memora smoke test 是在這個錯誤下跑的。

## LongMemEval（P0）

- **論文**：Wu et al., *LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory*，ICLR 2025，arXiv:2410.10813。本框架使用 2025-09 的清理版資料。
- **量測的能力**：Information Extraction、Multi-Session Reasoning、Knowledge Updates（78 題）、Temporal Reasoning（133 題）、Abstention（30 題）。
- **資料格式**：每題有 `question_id, question_type, question, answer, question_date, haystack_dates, haystack_session_ids, haystack_sessions, answer_session_ids`。
- **切分**：沒有切分；oracle、S、M 是三個不同長度的版本，題目相同。
- **官方作答設定**：`run_generation.py`，`temperature=0`，`max_tokens` 為 500（CoT 時 800）。歷史格式預設為 json，閱讀方式預設為 Chain-of-Note。
- **官方評分**：`evaluate_qa.py`，judge 為 gpt-4o-2024-08-06，論文報告與人工標註的一致率超過 97%。
- **已知資料問題**（`wlmem verify-data` 會輸出）：
  1. 每個 turn 都帶有 `has_answer` 欄位（標示是否為答案證據）。官方 json 歷史格式用 `json.dumps` 直接序列化 turn，會把這個欄位放進 prompt。**本框架在載入時就移除它。**
  2. session id `answer_*` 會洩漏哪些是證據 session，本框架改用中性 id。
  3. S 版有 211 題、oracle 版有 34 題的 session 沒有依時間排序；本框架改為依時間戳記穩定排序後輸入。
  4. S 版有 1,475 個 session 的日期晚於提問，其中 75 個是證據 session；oracle 版有 65 個，全部是證據 session。排除它們會讓題目無解，所以**預設保留**；可用 `exclude_future_sessions=true` 做敏感度分析，結果要另外標註。

## LoCoMo（P1，尚未接入）

- **論文**：Maharana et al., *Evaluating Very Long-Term Conversational Memory of LLM Agents*，ACL 2024，arXiv:2402.17753。
- **資料**：`data/locomo10.json`，共 10 段對話、1,986 題 QA。類別分布：1 有 282 題、2 有 321 題、3 有 96 題、4 有 841 題、5 有 446 題。
- **評分**：`task_eval/evaluation.py`，token F1；類別 5 是對抗或無法回答的題目。
- **注意**：
  - 授權是 CC BY-NC，論文使用沒有問題，但不能商用。
  - 各篇論文常用的「LLM-as-judge 版 LoCoMo 分數」（例如 Mem0、APEX-MEM）**不是**官方指標，不可混用。

## MemoryAgentBench（P1，尚未接入）

- **論文**：Hu, Wang, McAuley, *Evaluating Memory in LLM Agents via Incremental Multi-Turn Interactions*，arXiv:2507.05257，ICLR 2026。
- **資料**：HF `ai-hyz/MemoryAgentBench`，parquet 格式。和本研究最相關的是 Conflict Resolution（FactConsolidation-SH／MH，作者自建）。
- **評分**：CR 用 `substring_exact_match`，不需要 LLM judge，對本機實驗有利。
- **注意**：HF 上有第三方的重新包裝版本（例如 `mustbesaltyfish/memoryagentbench-conflict-full`），不是官方來源，**不使用**。

## SCALE-QA（P1，尚未接入）

- **論文**：Feng et al., *Reconstructing the Right Episode: Evaluating Interleaved Conversational Memory Beyond Long Context*，arXiv:2608.25655v2（預印本）。
- **量測的能力**：沒有 session 或主題邊界的單一長對話中，系統能否找回「讓某個限制生效的那一段對話」。這對應本研究的「無會話邊界」設定。
- **資料**：`scale_qa_strict_valid_bundle.json`（3,000 筆）。每題附有精確的證據句（`expected_doc`），只供稽核，不得提供給受測系統。
- **歷史的組成**：官方 `build_eval_dataset.py` 依指定長度把題目的來源對話和干擾對話混成單一對話流，同一組種子會產生相同的 package。
- **評分**：四選一，確定性計分，對本機實驗有利。
- **注意**：
  - 論文數字用的干擾對話來自 WildChat（ODC-BY），repo 沒有附，要用官方腳本在本機重建。repo 內附的 UltraChat 版本可以直接用，但**不是論文的設定**，結果不能和論文數字並列。
  - 資料是反事實建構的單一使用者對話，不含多人情境。
  - 題目是選擇題，量不到開放式回答的品質（作者自述的限制）。

## GateMem（P1，尚未接入）

- **論文**：Ren et al., *GateMem: Benchmarking Memory Governance in Multi-Principal Shared-Memory Agents*，arXiv:2606.18829v1（預印本）。
- **量測的能力**：多人共用一個記憶庫時，agent 能否對有權限的人答對（utility）、對無權限的人不洩漏（access control）、刪除後不再回復（active forgetting）。
- **資料格式**：`bench/data/<領域>/episodes.jsonl` 與 `checkpoints.jsonl`，領域為 medical、office、education、household。每個 turn 有 `speaker{principal_id, role}`、`timestamp`、`turn_kind`、`text`；每個檢查點有 `asker`、`as_of_turn_id`、`query_text`。
- **逐 turn 輸入**：可以；官方協定是每個情節重置記憶、依時間 ingest，到 `as_of_turn_id` 時提問。
- **不得提供給受測系統的欄位**：`query_type`、`expected_action`、`judge_spec`、`leak_targets`（官方 README 明列）。
- **評分**：`bench/eval/`，LLM judge（論文用 GPT-4o）。資料檔中的類別名稱是舊名：`privacy` 對應 access control，`safety` 對應 active forgetting。
- **注意**：
  - 提問者身分是**給定**的，量不到「自行推斷目前情境」。
  - 本研究不納入隱私，只會用到 utility 子集（728 題）。只跑子集就不能報官方的 MGS，結果必須標示為子集。
  - 官方作答 prompt 要求輸出含 `action` 的 JSON，並附上存取政策；這是協定的一部分，不能省略。

## 名稱有歧義或已釐清

- **FedMem**：arXiv 搜尋沒有找到相符的 agent memory 論文。需要你提供連結。
- **SCOPE**：已確認是 *Scope Before You Persist: Preventing Cross-Family Interference in Agent Memory*，arXiv:2609.29144v1。它用的 ProcStream-RSI 是程式修復任務流，不是對話記憶 benchmark，本階段不納入。
