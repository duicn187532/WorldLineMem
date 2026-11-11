# 研究者親自閱讀的文獻清單

建立日期：2026-11-11。對應暫定題目《情境未標註下智能體的情境變動偵測與選擇性記憶利用》。

**閱讀方式**：第一級要讀全文，自己判斷差異點是否成立，不要只依賴本 repo 的摘要；第二級讀方法章節；第三級寫相關研究時再查。每篇讀完後，在「讀後」欄記下一句你自己的判斷。

## 第一級：定位論文必讀（全文）

| # | 論文 | 為什麼要讀 | 讀時特別看 | 讀後 |
|---|---|---|---|---|
| 1 | *Voices as Handles*／SpeakerBind，arXiv:2609.38501 | **和你的設定結構完全相同**（多人分別和同一個代理一對一互動，交錯成共用歷史），但身分來自聲紋 | §3.1 把文字線索當「捷徑」的論證；只給文字時的結果（Transcript only）。你要能說清楚：為什麼在你的情境裡，文字線索是訊號而不是捷徑 | |
| 2 | *From Voiceprints to User Entities*／EvoSpeakerMem，arXiv:2610.36713 | 唯一處理「身分不給定 → 記憶歸屬」的工作（聲音版） | 「切碎與污染的取捨」、因果的線上評估協定（first-seen binding）。你的評估可以直接沿用這套協定 | |
| 3 | *GroupMemBench*，arXiv:2605.14498 | 候選資料來源；多人記憶的失敗分析 | 資料生成方式（人物語氣、角色）、題目類型（尤其是提問者藏在「我」後面的那一類） | |
| 4 | *Reconstructing the Right Episode*／SCALE-QA 與 TSIM，arXiv:2608.25655 | 單一使用者、無邊界長對話的切分方法，是「情境變動偵測」的最近基準 | TSIM 的串流切分規則（附錄 Table 15）、沒有邊界時和有邊界時的差距 | |
| 5 | *PairPref*，arXiv:2609.34526 | 「記憶仍有效、但當下情境不適用」的 benchmark，模型大多照用；沒有提出方法 | 成對設計與兩條評估軌；可作為你方法中「適用性判斷」的外部驗證 | |
| 6 | *When Personal Memory Has No Single Answer*／TANGLE，arXiv:2608.13921 | 情境缺失時，代理應該追問、條件式回答還是直接回答 | 情境分割衝突（CPC）的定義、CAAP 行動策略；對應你設計中「不確定時先確認」那一步 | |
| 7 | *Who Remembers What?*／MixUA，arXiv:2611.10439 | 一週前發表，**最可能延伸到你的題目的競爭者**；記憶分成四種範圍 | 範圍的定義；限制章節中「群組範圍」「身分不給定」是否被列為未來工作 | |
| 8 | *Learning from Others, Acting for You*／ShareMem，arXiv:2609.32511 | 跨使用者共享經驗、偏好只從本人讀取；即使標了來源，仍有約 3.4% 的失敗是套用了別人的偏好 | §4.4 跨使用者偏好干擾的稽核方法 | |
| 9 | *The Memory Trap*，arXiv:2611.07554 | 把「記憶被用在形成它的範圍之外」形式化 | 問題定義、寫入時與讀取時兩種誤用；可直接借用為你論文的問題定義 | |
| 10 | *When Single-User-Oriented LLM-based Assistants Involve Others*（範圍回顧），arXiv:2609.14062 | 研究動機的現實證據：共用帳號、家庭與車用助理 | §5.2.1 共用使用、§6.1 歸屬錯誤；寫第一章時引用 | |

## 第二級：方法背景（讀方法章節）

| # | 文獻 | 用途 |
|---|---|---|
| 11 | Adams & MacKay (2007), *Bayesian Online Changepoint Detection*, arXiv:0710.3742 | 「是否換了」的線上機率模型 |
| 12 | Fox, Sudderth, Jordan & Willsky (2008), *An HDP-HMM for Systems with State Persistence*, ICML | 黏性 HDP-HMM：把「世界線」形式化（數量未知、會持續、會回來） |
| 13 | Teh, Jordan, Beal & Blei (2006), *Hierarchical Dirichlet Processes*, JASA（讀中國餐館過程的部分） | 「換到哪條」的非參數分群 |
| 14 | Kummerfeld 等 (2019), *A Large-Scale Corpus for Conversation Disentanglement*, ACL（arXiv:1810.11118） | 對話分離的標準資料與評估；你要說明自己和它的差異（長期、連到記憶使用） |
| 15 | Elsner & Charniak (2008), *You Talking to Me? A Corpus and Algorithm for Conversation Disentanglement*, ACL | 對話分離的起點 |
| 16 | Hearst (1997), *TextTiling*, Computational Linguistics | 主題切分的經典基準 |
| 17 | *Consistent yet Contextual*，arXiv:2611.07111 | 同一位作者的風格隨情境改變，對應「複合場景」的難點 |
| 18 | Liu, Ting & Zhou (2008), *Isolation Forest*, ICDM | 偵測「新的人或場景出現」 |
| 19 | Domingos & Hulten (2000), *Mining High-Speed Data Streams*（Hoeffding tree）, KDD | 你提的線上決策樹的原始方法 |
| 20 | *Whose Memory Is It?*／CASK，arXiv:2610.09008 | 以「世界」區分記憶的歸屬；可在第一章連結世界線的比喻 |
| 21 | TransMem，arXiv:2611.10683 | 主題路由（巨觀相似度 + 微觀實體一致性），可借用為場景軸 |

## 第三級：寫相關研究時再查（略讀）

- 多人記憶：SpeakerMem-R1（2609.26780）、EverMemBench（2602.01313）。
- 情境適用性與過度個人化：OP-Bench（2601.13722）、CUPID、RPEval、BenchPreS、ConMem（2610.33432）。
- 跨使用者共享：Collaborative Memory（2505.18279）、AIM（2609.12320）、GateMem（2606.18829）。
- 先前方向的背景（第二章相關研究需要）：Memora（2604.20006）、STALE（2605.06527）、Pragma（KBS 353:117193）、MemFSM、StateAuditor（2608.01619）。

## 閱讀順序建議

先讀 1、2、7：確認差異點，也確認有沒有被搶先。再讀 3、4：決定資料和切分基準。接著讀 5、6、9：決定記憶使用那一半的問題定義。10 留到寫第一章時讀。第二級依實作需要再讀。
