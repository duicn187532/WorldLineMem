# 研究者親自閱讀的文獻清單

建立日期：2026-11-11。2026-11-12 第三次調整：改成三個階段。先由研究者**親自略讀題目相近的論文**、填比較表、自己整理共同模式並推出概念，之後才精讀方法。前一版直接列出方法論文，那些是 Claude 依自己的構想挑的，會把研究者帶向特定方法，所以移到第三階段當作候選。對應暫定題目《情境未標註下智能體的情境變動偵測與選擇性記憶利用》。

## 引用原則（2026-11-11）

| 用途 | 標準 |
|---|---|
| 新穎性查核、相關研究章節 | **預印本也要納入**。口試委員或審查者知道的預印本若已做過你的方法，差異點就不成立；沒讀到不是理由 |
| 支撐論點的事實與數字 | 優先使用經同儕審查的來源；只有預印本時，在文中標明「預印本」 |
| 對照組（baseline） | 選有公開程式、可重現、已發表或廣為使用的方法 |
| 資料與 benchmark | 選已發表或廣為使用、授權清楚的 |

**判斷可信度看方法，不看機構**：有沒有公開程式與資料、有沒有消融實驗、有沒有多次執行與信賴區間、限制章節是否誠實。**正式交稿前要再查一次發表狀態**，也請向指導教授確認系所對引用來源的規定。

## 第一階段：略讀相近論文（11/13–11/17）

**每篇只看**：摘要、引言最後的貢獻列表、方法總覽圖、實驗設定（資料、指標、對照組）、限制與未來工作。約 30–40 分鐘一篇。

**邊讀邊填** [`landscape_matrix.csv`](landscape_matrix.csv)（可用 Excel 或 Google 試算表開啟）。書目欄位已填好，分析欄位全部空白，由你填。發表狀態只寫 2026-11-12 看到的資訊。

| 組別 | 相近在哪 | 論文（編號對應比較表） |
|---|---|---|
| A 多人共用記憶 | 同一個代理服務多人 | P01 [MixUA](https://arxiv.org/abs/2611.10439)、P02 [ShareMem](https://arxiv.org/abs/2609.32511)、P03 [Collaborative Memory](https://arxiv.org/abs/2505.18279)、P04 [AIM](https://arxiv.org/abs/2609.12320)、P05 [GateMem](https://arxiv.org/abs/2606.18829)、P06 [GroupMemBench](https://arxiv.org/abs/2605.14498)、P07 [EverMemBench](https://arxiv.org/abs/2602.01313)、P08 [SpeakerMem-R1](https://arxiv.org/abs/2609.26780) |
| B 有身分訊號的多人記憶 | 問題結構和你最接近，只是靠聲紋或人臉 | P09 [SpeakerBind](https://arxiv.org/abs/2609.38501)、P10 [EvoSpeakerMem](https://arxiv.org/abs/2610.36713)、P11 [VoxPolyMem](https://arxiv.org/abs/2609.32522)、P12 [Bio-Memory](https://arxiv.org/abs/2609.08558) |
| C 記憶被用錯地方 | 記憶有效但不適用 | P13 [The Memory Trap](https://arxiv.org/abs/2611.07554)、P14 [PairPref](https://arxiv.org/abs/2609.34526)、P15 [OP-Bench](https://arxiv.org/abs/2601.13722)、P16 [PersistBench](https://arxiv.org/abs/2602.01146)、P17 [Scope Before You Persist](https://arxiv.org/abs/2609.29144)、P18 [What to Admit](https://arxiv.org/abs/2610.11188) |
| D 沒有邊界的切分 | 連續對話裡判斷段落 | P19 [SCALE-QA／TSIM](https://arxiv.org/abs/2608.25655)、P20 [ES-Mem](https://arxiv.org/abs/2601.07582)、P21 [HingeMem](https://arxiv.org/abs/2604.06845)、P22 [EM-LLM](https://arxiv.org/abs/2407.09450)、P23 [SeCom](https://arxiv.org/abs/2502.05589) |
| E 情境不明時的處理 | 該問還是該答 | P24 [TANGLE](https://arxiv.org/abs/2608.13921)、P25 [REVOIR](https://arxiv.org/abs/2609.37588) |
| F 其他領域的同類問題 | 混合序列、人數未知 | P26 [DisenReason](https://arxiv.org/abs/2603.03782)（共用帳號推薦） |
| G 研究動機 | 現實中的共用情況 | P27 [單人助理涉及他人的範圍回顧](https://arxiv.org/abs/2609.14062) |

B 組要讀：研究問題不是「聲紋是不是訊號」，但這組的問題結構和你最接近，要拿來比較。

## 第二階段：整理共同模式（11/18）

填完比較表後，在 [`LANDSCAPE_NOTES.md`](LANDSCAPE_NOTES.md) 寫一頁：

1. 大家都假設了什麼（例如身分是否給定、情境是否有標籤）
2. 大家都卡在哪裡（作者自述的限制）
3. 未來工作裡反覆出現的方向
4. 沒有人處理的組合
5. 你的概念初稿
6. 想問老師的問題

這頁是 11/19 面談的主要材料。建議先自己寫完，再對照 `RESEARCH_SCOPE.md` §13–§18（Claude 之前做的文獻查核與候選構想），避免被既有整理帶著走。

## 第三階段：精讀方法（面談後）

依你在第二階段推出的概念，從第一階段的論文中挑方法章節精讀，並補讀下列方法背景。下表是**候選**，不是答案。

| 文獻 | 可能的用途 |
|---|---|
| Adams & MacKay (2007), *Bayesian Online Changepoint Detection*, [arXiv:0710.3742](https://arxiv.org/abs/0710.3742) | 線上偵測「換了沒」的機率模型 |
| Fox 等 (2008) 黏性 HDP-HMM（[ICML 2008](https://doi.org/10.1145/1390156.1390196)）；Teh 等 (2006) 階層狄利克雷過程（[JASA](https://doi.org/10.1198/016214506000000302)，讀中國餐館過程） | 情境數未知、會持續、會回來 |
| *Consistent yet Contextual*，[arXiv:2611.07111](https://arxiv.org/abs/2611.07111) | 同一位作者的風格隨情境改變 |
| Kummerfeld 等 (2019) [ACL](https://aclanthology.org/P19-1374/)；Elsner & Charniak (2008) [ACL](https://aclanthology.org/P08-1095/) | 對話分離的資料與指標 |
| Hearst (1997) [TextTiling](https://aclanthology.org/J97-1003/) | 主題切分的經典對照組 |
| Liu 等 (2008) Isolation Forest（[ICDM](https://doi.org/10.1109/ICDM.2008.17)）；Domingos & Hulten (2000) Hoeffding tree（[KDD](https://doi.org/10.1145/347090.347107)） | 新人／新場景偵測；線上決策樹 |

## 寫相關研究時再查（略讀）

- **情境適用性的其他研究**：CUPID（[2508.01674](https://arxiv.org/abs/2508.01674)）、RPEval（未查到確切出處）、BenchPreS（[2603.16557](https://arxiv.org/abs/2603.16557)）、ConMem（[2610.33432](https://arxiv.org/abs/2610.33432)）。
- **其他事件切分記憶**：Nemori（ES-Mem 引用，未查到確切出處）、Membox（[2601.03785](https://arxiv.org/abs/2601.03785)）。
- **聲紋記憶的其他研究**：AFA（[2604.25022](https://arxiv.org/abs/2604.25022)，只見於 VoxPolyMem 的引用，未讀原文）。
- **世界與歸屬的比喻、場景路由**：CASK（[2610.09008](https://arxiv.org/abs/2610.09008)）、TransMem（[2611.10683](https://arxiv.org/abs/2611.10683)）、LifeMem（[2609.12655](https://arxiv.org/abs/2609.12655)）、STRATA（[2610.19386](https://arxiv.org/abs/2610.19386)）。
- **先前方向的背景**：Memora（[2604.20006](https://arxiv.org/abs/2604.20006)）、STALE（[2605.06527](https://arxiv.org/abs/2605.06527)）、Pragma（[KBS 353:117193](https://doi.org/10.1016/j.knosys.2026.117193)）、MemFSM（[EMNLP 2026](https://aclanthology.org/2026.emnlp-main.260/)）、StateAuditor（[2608.01619](https://arxiv.org/abs/2608.01619)）。
- **時間軸記憶與保留**（說明本研究為何不走這條線）：FadeMem（[2601.18642](https://arxiv.org/abs/2601.18642)）、Zep（[2501.13956](https://arxiv.org/abs/2501.13956)）、A-MEM（[2502.12110](https://arxiv.org/abs/2502.12110)）、RoMem（[2604.11544](https://arxiv.org/abs/2604.11544)）、*Selective Forgetting*（[2608.28978](https://arxiv.org/abs/2608.28978)）、RaMem（[2606.22844](https://arxiv.org/abs/2606.22844)）、EngramRAG（[2609.32049](https://arxiv.org/abs/2609.32049)）。
- **只看過摘要、待確認是否相關**：*Before Bringing It Up*（[2610.09470](https://arxiv.org/abs/2610.09470)）、*Learning Personalized Memory Gating*（[2610.23812](https://arxiv.org/abs/2610.23812)）、*Mitigating Over-Personalization via Structured Memory*（[2608.08300](https://arxiv.org/abs/2608.08300)）、*Clarify, Abstain or Answer?*（[2605.25831](https://arxiv.org/abs/2605.25831)）。
- 未能確認存在、**不得引用**：TSHMem（2026-11-12 查無此文，見 RESEARCH_SCOPE.md §16）。
