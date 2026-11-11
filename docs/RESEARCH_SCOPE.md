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

- 不自行設計 benchmark、題目、ground truth 或評分指標。
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

