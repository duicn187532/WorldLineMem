# 研究範圍（暫定）

> 狀態：研究前置階段。本文件記錄研究問題與待驗證的假設，**尚未提出、也尚未實作任何新方法**。
> 本階段的產出是可重現的比較基準（benchmark 與 baseline），不是研究結果。

## 1. 暫定題目

- 中文：《無狀態持續型智能體在世界線變動偵測後之選擇性記憶調整》
- English: *Selective Memory Adaptation for Stateless Persistent Agents under World-State Changes*

題目會依研究進展調整。

## 2. 研究問題

一個 LLM agent 持續與使用者互動，而環境、使用者狀態、事實或情境不斷改變時，agent 應如何管理長期記憶？

現有記憶系統的已知問題（文獻已有描述，見 §4）：

| 問題 | 說明 | 可用來量測的公開 benchmark（見 BENCHMARK_MATRIX.md） |
|---|---|---|
| 記憶累積 | 只存不刪，造成冗餘與檢索干擾 | LongMemEval_S（干擾 session）、Memora（週／月／季長度） |
| 記憶過期 | 情境改變後，舊資訊不再適用 | STALE、Memora（forgetting_absence）、LongMemEval knowledge-update |
| 衝突處理 | 新舊資訊矛盾，需判斷哪一份有效 | STALE（Type I／II）、MemoryAgentBench Conflict Resolution |
| 過度遺忘 | 已失效的資訊仍可能有歷史價值 | Memora FAMA（同時計回憶與遺忘）、LongMemEval temporal-reasoning |
| 情境轉移 | 同一事實在不同時間、情境下可信度不同 | STALE dim2（前提抵抗）、dim3（隱含策略適應） |
| 跨情境推理 | 利用過往情境的經驗協助目前判斷 | 目前沒有公開 benchmark 直接量測（見 §5） |
| 無會話邊界 | 沒有視窗或 session 標記，agent 要自行判斷目前在處理什麼 | SCALE-QA |
| 多人共用記憶 | 同一個記憶庫服務不同對象 | GateMem 的 utility 子集（提問者身分是給定的） |

## 3. 核心構想（尚未實作、尚未驗證）

構想中的處理流程：

```
互動事件 → 記憶抽取 → 情境／世界狀態變動偵測 → 記憶可信度調整
        → Consolidation / Decay / Selective Forgetting → Retrieval → Reasoning
```

「世界線」在本研究中暫時定義為**帶有時間與情境條件的世界狀態或事實版本**，不預設平行宇宙。

想要回答的子問題（都是待驗證的假設，不是已知結論）：

1. 能否偵測新資訊造成的顯性或隱性狀態變動？
2. 能否區分「已失效」、「不確定」、「仍有效但屬於過去情境」三種記憶？
3. 保留歷史記憶是否優於直接刪除？在哪些任務上？
4. 過往情境的記憶能否在目前情境下被部分採信？
5. 能否在減少「依過時資訊推理」的錯誤的同時，保留跨時期經驗？
6. 記憶品質與儲存、檢索、推論成本之間如何取捨？

記憶重要度、時間衰減、情緒權重、知識圖譜關係、情境相似度等機制，目前**不實作，也不預設有效**。

## 4. 相關研究（已查證的部分）

| 研究 | 正式名稱與版本 | 與本研究的關係 | 公開資源 |
|---|---|---|---|
| FadeMem | *FadeMem: Biologically-Inspired Forgetting for Efficient Agent Memory*，arXiv:2601.18642v2 | 依重要度衰減與遺忘、LLM 衝突消解 | 論文中找不到程式碼連結；LTI-Bench 為作者自建，未公開 |
| Zep | *Zep: A Temporal Knowledge Graph Architecture for Agent Memory*，arXiv:2501.13956 | 雙時間軸知識圖譜，事實帶有效區間 | Graphiti（開源）需要圖資料庫與 LLM；Zep 雲端服務需付費 |
| STALE | *STALE: Can LLM Agents Know When Their Memories Are No Longer Valid?*，arXiv:2605.06527v1 | 隱性衝突 benchmark，以及 CUPMem 原型 | 程式碼與資料集都已公開（見 BENCHMARK_MATRIX.md） |
| Always-On Agents | *Always-On Agents: A Survey of Persistent Memory, State, and Governance in LLM Agents*，arXiv:2606.30306 | 持久狀態治理框架、AOEP-v0 | AOEP-v0 是參考設計加小型試驗，論文沒有釋出程式或資料 |
| ATMS | de Kleer, *An Assumption-based TMS*, Artificial Intelligence 28(2), 1986 | 以假設集合標記信念、同時維護多個一致情境；是「世界線」概念的理論來源之一 | 理論論文，沒有 benchmark |
| Memora | *From Recall to Forgetting: Benchmarking Long-Term Memory for Personalized Agents*，arXiv:2604.20006v1，ACL 2026 | 回憶與遺忘並計的 FAMA 指標 | 資料與評估程式都已公開 |
| FedMem | — | **名稱有歧義，尚未查證** | 需要你提供 arXiv ID 或連結 |
| SCOPE | *Scope Before You Persist: Preventing Cross-Family Interference in Agent Memory*，arXiv:2609.29144v1（已確認） | 在一類任務學到的技能全域套用會傷害其他任務；把檢索範圍限定在來源任務類別後改善。範圍標籤是給定的 | ProcStream-RSI 是程式修復任務流，不是對話記憶 benchmark |
| CUPMem | STALE 論文第 5 節的原型 | 寫入時裁決舊狀態（KEEP／STALE／REPLACE／UNKNOWN）、把失效傳播到受影響的狀態區域、失效記憶保留為歷史。**單一使用者時間軸上的「依賴傳播」已被它涵蓋** | 程式在 STALE repo 內；依賴預先定義的 10 個狀態領域 |
| ShareMem | *Learning from Others, Acting for You: Cross-User Memory Sharing for LLM Agents*，arXiv:2609.32511（只讀過摘要與導論） | 跨使用者共享經驗：做法可以共用，偏好的具體值必須來自當前使用者 | 評估用 Mind2Web、VitaBench 2.0、MemoryCode；尚未查證 |
| GateMem | *GateMem: Benchmarking Memory Governance in Multi-Principal Shared-Memory Agents*，arXiv:2606.18829v1 | 多人共用記憶庫的 benchmark；重點是權限與刪除，不是適用性 | 程式與資料都已公開（見 BENCHMARK_MATRIX.md） |
| SCALE-QA | *Reconstructing the Right Episode*，arXiv:2608.25655v2 | 沒有 session 邊界的混合主題長對話；對應「無會話邊界」設定 | 程式與資料都已公開（見 BENCHMARK_MATRIX.md） |

## 5. 範圍外（本階段）

- 原則上不自行設計 benchmark、題目、ground truth 或評分指標。**例外（2026-11-11 決定）**：為了保留研究特色，允許為「多情境記憶誤用與遷移」自建實驗協定，見 MIXED_MEMORY_PROTOCOL.md。自建協定的結果必須和官方 benchmark 分開報告。
- 不 fine-tune 模型。
- 「跨情境推理」目前沒有公開 benchmark 直接量測。若日後需要自建資料，必須另立研究步驟，並與公開 benchmark 的結果分開報告。

## 6. 2026-11-11 的討論紀錄（方向調整，尚未定案）

研究者對核心構想的補充：

- 世界線會**並存**：同一個記憶庫的 agent 會在不同場景面對不同的人，換環境時不重置記憶。時間不倒流。
- 想避免的失敗是「即視感」：另一個情境的記憶因為相似被取出，並被當成在目前情境也成立。
- 題目中的「無狀態」指**沒有工作視窗或會話邊界**，不是指沒有記憶。文獻中 stateless 通常指後者，題目用詞之後需要調整。
- **隱私洩漏不納入範圍**。關注的是適用性（這條記憶在這裡成不成立），不是權限（能不能說）。

由此得到的暫時判斷：

- 研究主軸從「單一使用者的狀態隨時間改變」移向「多個並存情境之間的記憶誤用與經驗遷移」。
- 只做單一使用者時間軸的空間很小，CUPMem 已經涵蓋主要機制。
- 既有研究的情境標籤都是給定的（SCOPE 的任務類別、GateMem 的提問者身分、ShareMem 的使用者 ID）。「情境需要自行推斷」加上「判斷適用性」的組合，在一輪文獻搜尋中沒有找到直接對應的研究。這只是初步判斷，不是已確認的研究缺口。
- P0 的三個 benchmark 都是單一使用者且 session 邊界給定，只能當作「基本能力沒有退步」的對照，無法支持多情境的主張。
- 「誤用」與「錯失遷移」目前仍然沒有公開 benchmark 直接量測。

## 7. 2026-11-11 採納的研究架構（方法細節尚未定案）

### 7.1 架構

方法的重心從「寫入時偵測世界線變動」移到「讀取時檢查這條記憶在此時此地是否適用」。同一個機制用在兩條軸上：

| 軸 | 檢查的問題 | 評估 | 定位 |
|---|---|---|---|
| 時間軸 | 這條記憶現在還成立嗎 | STALE（官方）；誤殺用 Memora 與 LongMemEval 量測 | 保底，不需要新 benchmark |
| 情境軸 | 這條記憶在這個情境成立嗎 | 混合記憶庫協定（自建） | 特色 |

另外附帶一章：本機模型下的重現與 benchmark 缺陷（LongMemEval 官方 prompt 的證據標記洩漏、Memora 官方 prompt 漏掉使用者發言、Ollama 靜默截斷、小模型 judge 不可靠）。

已決定放掉：時間衰減、重要度、情緒權重、圖資料庫。

### 7.2 這個架構要回答的問題

1. 只對檢索到的記憶做適用性檢查，能不能用遠低於寫入時裁決（CUPMem）的成本，拿到大部分效果？
2. 兩種做法各自會不會把仍然有效的記憶誤判為失效？
3. 情境訊號從「給定」降到「沒有」時，誤用增加多少？讀取時檢查能補回多少？

不論結果往哪個方向，這三個問題都有分析價值。

### 7.3 支持這個架構的文獻證據（2026-11-11 細讀）

| 研究 | 讀到的程度 | 和本研究的關係 |
|---|---|---|
| *The Memory Trap*，arXiv:2611.07554 | 第 2 節、討論、限制 | 把問題形式化為「記憶被用在形成它的範圍之外」，分成寫入時和讀取時兩種；**連原始對話紀錄都會被過度套用，所以只修寫入端不夠**。沒有提出方法；未來工作明列「記憶連同範圍一起儲存」和「跨使用者共用記憶」。程式公開（github.com/safety-research/memory-trap，已確認存在） |
| *ConMem*／MemAlign，arXiv:2610.33432 | 全文 | 寫入前用反事實探測決定要不要存。「情境誤用」一類只抓到 12.9%（31 個案例），作者把情境範圍邊界列為未來方向。單一使用者；**MemAlign 找不到公開的程式或資料** |
| *Stale, Misattributed, or Late*，arXiv:2610.10265 | 第 5、7.3、8 節 | 主張時間有效性主要取決於寫入端，但前提是能把更新歸到正確的欄位；**開放領域下用 7B 本機模型做欄位歸併，召回率不超過 0.062**。這是寫入時裁決在本機模型下可能失效的直接證據。身分消解假設提問者已知；資料在匿名 repo，找不到公開連結 |
| *MemTrim*，arXiv:2610.07311 | 方法與評估段落 | 讀取時移除和提問重複或衝突的證據。處理的是任務經驗重用，不是狀態失效或情境範圍 |
| *CAVE-Mem*，arXiv:2610.00238 | 全文 | 讀取時檢查「經驗操作」能不能套用（記憶類型、答案格式、證據邊界）。對象是單一使用者的問答，不是跨人或跨場景 |
| *MemProbe*，arXiv:2609.30558 | 只讀摘要 | 診斷「該更新還是該保留」的取捨，56 個情節。是診斷工具，不是方法 |

判斷：缺口 1（適用範圍的推斷）和缺口 2（讀取時檢查與寫入時裁決的比較）目前都還成立。這個領域變動很快，動手寫方法前要再查一次。

### 7.4 CUPMem 作為對照組的可行性（已實測）

- 官方程式可以直接指向 Ollama 的 OpenAI 相容端點，不需要修改程式碼。另外需要 `torch`、`transformers` 和本機的 `all-MiniLM-L6-v2`（約 90 MB）。
- 用 `qwen3:0.6b` 在官方資料的第 1 個案例上跑通（只輸入 2 個證據 session）：14 次 LLM 呼叫，約 2.6 萬 token，CPU 上約 5 分鐘。
- 這只是可行性測試：模型太小，寫入端沒有產生任何狀態更新，三個回答都還停留在舊狀態。
- 尚未完成：包成本框架的記憶方法。CUPMem 自己產生最終回答，不只是提供記憶，接入方式要另外設計。

## 8. 2026-11-11 第三輪：對「狀態變動驅動的再活化與重詮釋協同決策」的文獻查核

研究者提出新的暫定題目《動態世界狀態下的智能體選擇性記憶利用》，並要求以原始論文的方法、公式、實驗和消融確認差異。本節只記錄查核結果，**不代表方法已定案**。

### 8.1 已讀到方法層級的論文

| 論文 | 讀的範圍 | 做了什麼（方法層級） | 沒有做什麼 |
|---|---|---|---|
| FadeMem，arXiv:2601.18642 | 第 2 節公式 | 重要度由語意相關性、存取頻率、時間決定；重要度調節衰退率；存取時強化；長短期兩層之間升降；LLM 衝突消解與融合 | 沒有程式碼；狀態變動不影響強度；沒有依賴關係 |
| Oblivion，arXiv:2604.00131 | 第 2 節、5.1、限制 | 衰退只降低可存取性、不刪除：`R = exp(−n/S)`，`S = (U + F + ε)·T`；只強化實際被用到的記憶；不確定性高時才檢索，檢索是全域相似度搜尋，所以衰退的記憶可以被查詢重新取回。程式公開（github.com/nec-research/oblivion） | 再活化由查詢和使用觸發，不由狀態變動觸發；沒有失效傳播或重詮釋（只有「新的取代舊的」） |
| HeLa-Mem，arXiv:2604.16839 | 全文 | 情節圖；檢索時共同被取出的節點邊權增加、其餘衰減；擴散激活把語意不相近但有關聯的記憶帶出來；孤立節點被刪除 | 沒有狀態、有效性或重詮釋；消融顯示在 LoCoMo 上拿掉遺忘幾乎沒有影響 |
| RaMem，arXiv:2606.22844 | 第 3 節、4.3、4.4、限制 | 每條記憶錨定事件時間、提及時間、session 範圍、參與者、地點、實體、主題；從查詢推出回憶條件；條件可靠時優先取條件相容的記憶。程式公開 | 全文沒有衰退或遺忘；沒有狀態變動；條件來自查詢 |
| StateGraph，arXiv:2611.02912 | 第 3–7 節、限制 | 狀態依賴圖；狀態帶時間範圍、條件範圍、證據和五種狀態（CURRENT、STALE、UNCERTAIN、HISTORICAL、NEEDS-RECOMPUTE）；反事實驗證依賴邊；保守的連鎖修訂，保留有獨立支持的狀態；舊版本與來源保留；使用時檢查前提 | 完全沒有記憶強度或衰退；狀態變動只會降低信任，不會提高任何記憶的可存取性；自建的 StateChangeBench 只有 50 題，論文沒有說明是否釋出 |
| *Towards Reversible Forgetting*，arXiv:2608.18177 | 全文 | 立場論文：active／dormant／retired 三態；環境變動後重新評估相關性；遲滯門檻；「條件再現時」把 dormant 恢復為 active | 沒有實作、沒有實驗；再活化針對的是舊環境再現，不是新狀態下的經驗重用；沒有重詮釋 |
| CAVE-Mem、ConMem、*The Memory Trap* | 見 §7.3 | 適用條件檢查、寫入前的反事實探測、範圍的形式化 | 見 §7.3 |

### 8.2 找不到或尚未讀到方法的論文

- **Pragma／*Giving Stateless Agents a Sense of Time***：找不到符合描述的論文。搜尋到的 PRAGMA（arXiv:2609.09664）是個人化引導的 benchmark，內容不符。需要研究者提供連結。
- **MemFSM、ValidMem**：搜尋不到，需要連結。
- **已找到但尚未讀方法**：QUMem（arXiv:2608.16168）、MemConflict（arXiv:2605.20926，benchmark）、PACMI、LifeFuse-Mem、ChronoMem、CAMeR、Scrub Jay、*Use and Disuse*、*Prospective Memory for Proactive LLM Agents*、MINDSET。其中任何一篇都可能推翻 §8.3 的判斷。

### 8.3 目前的判斷

- 研究者列出的五項能力，每一項都已有附公式和實驗的方法。把它們依序串接不構成方法層級的差異。
- 在已讀的論文中沒有找到的只有兩件事：
  1. 狀態變動**提高**已衰退記憶的可存取性（已讀的方法中，狀態變動只用來降低信任；再活化只由查詢或使用觸發）。唯一提出類似想法的是沒有實作的立場論文。
  2. 衰退和依賴修訂之間的**交互作用**。衰退類方法把記憶當成彼此獨立；修訂類方法假設所有狀態都在圖中、隨時可取用。
- 公開 benchmark 的限制：對話都不長，衰退幾乎不會成為限制因素（HeLa-Mem 的消融是直接證據）；也沒有任何一個量測「狀態變動後，舊經驗重新變得有用」。

