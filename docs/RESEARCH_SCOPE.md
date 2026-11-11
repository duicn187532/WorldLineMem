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
| SCOPE | — | **名稱有歧義**，有多篇候選（例如 arXiv:2609.29144 *Scope Before You Persist*），尚未確定是哪一篇 | 需要你提供 arXiv ID 或連結 |

## 5. 範圍外（本階段）

- 不自行設計 benchmark、題目、ground truth 或評分指標。
- 不 fine-tune 模型。
- 「跨情境推理」目前沒有公開 benchmark 直接量測。若日後需要自建資料，必須另立研究步驟，並與公開 benchmark 的結果分開報告。
