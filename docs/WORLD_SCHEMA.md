# 世界設定資料格式（草案 v0.2）

建立日期：2026-11-12；同日依研究者對 §10 的決定修訂為 v0.2。對應 [BENCHMARK_SPEC.md](BENCHMARK_SPEC.md) v0.3。本文件只定格式，不含程式。欄位名稱用英文，說明用中文。

## 1. 設計原則

1. **先有世界設定，再有對話**：世界設定由程式依 `seed` 產生，可完全重現。對話由本機模型依世界設定生成。題目、答案、計分鍵都從世界設定推得，不從生成的對話反推。
2. **公開與隱藏分開**：記憶系統只看得到對話流（和依實驗條件給的訊號）。所有 gold 欄位放在隱藏檔，只給計分程式。
3. **所有會被計分的東西都有代碼**：人、場景、情境、事實、植入值、題目都有固定代碼。計分、翻譯包、檢查程式都靠代碼對應。
4. **語言層與內容層分開**：植入值、人名、地名等需要逐字比對的東西，各語言的寫法都存在世界設定裡；對話文字是生成結果，另存。

## 2. 一個案例的檔案

```
case_<case_id>/
├── world.json          隱藏：完整世界設定（人、場景、事實、時間軸、段落計畫）
├── stream.en.jsonl     公開：英文對話流，一輪一行（記憶系統的輸入）
├── stream.zh.jsonl     公開：中文對話流（翻譯後產生）
├── signals.json        公開：依實驗條件給的訊號（label / boundary；none 時為空）
├── probes.en.jsonl     公開：題目與作答時附上的當下對話範圍
├── probes.zh.jsonl     公開：中文題目
├── gold.json           隱藏：每題的答案、計分鍵、每段的真實情境
└── manifest.json       產生器版本、seed、生成模型名稱與版本、檢查結果、剔除紀錄
```

## 3. 代碼規則

| 物件 | 格式 | 例子 |
|---|---|---|
| 案例 | `<規模>-<seed>` | `M-0007` |
| 場景 | `S` + 兩位數 | `S01` |
| 人 | `P` + 三位數 | `P012` |
| 情境 | `C-<人>-<場景>` | `C-P012-S01` |
| 屬性 | 小寫英文 | `report_format` |
| 事實 | `F` + 四位數 | `F0031` |
| 植入值 | `V` + 四位數 | `V0031` |
| 段落 | `E` + 四位數（依時間排序） | `E0042` |
| 題目 | `Q` + 四位數 | `Q0108` |

代碼本身**不能**出現在公開檔的任何文字中，檢查程式會確認。

## 4. `world.json`（隱藏）

### 4.1 案例層級

| 欄位 | 型態 | 說明 |
|---|---|---|
| `case_id` | 字串 | |
| `seed` | 整數 | 世界設定完全由它決定 |
| `generator_version` | 字串 | 世界設定產生器的版本 |
| `cue_level` | `weak` / `medium` / `strong` | 線索強度（規格 §5） |
| `names` | `on` / `off` | 只對 `strong` 有效：是否允許對話中出現人名（§4.3.1）。`medium`、`weak` 固定為 `off` |
| `use_demos` | `on` / `off` | 是否放入代理主動使用記憶的示範（§4.6 `use_facts`）。`off` 為消融版本，其餘設定與同 `seed` 的 `on` 版本完全相同 |
| `source_language` | `en` | 原始語言 |
| `time_span` | `{start, end}` | 模擬的時間範圍（ISO 8601 日期） |
| `scenes` | 陣列 | §4.2 |
| `persons` | 陣列 | §4.3 |
| `attributes` | 陣列 | §4.4 |
| `facts` | 陣列 | §4.5 |
| `encounters` | 陣列 | §4.6 |
| `probes` | 陣列 | §4.7（題目的設計；公開題目文字另存） |

### 4.2 場景 `scenes[]`

| 欄位 | 說明 |
|---|---|
| `scene_id` | `S01` 等 |
| `type` | `household` / `open_venue` / `classroom` / `office_secretary` |
| `name` | `{en, zh}`，例如社區中心的名稱 |
| `agent_role` | 代理在這個場景的身分，例如「家庭助理」「服務台員工」「班級助教」「秘書」 |
| `roles` | 這個場景裡人的角色清單，例如家庭：家長、孩子；開放場域：同事、訪客 |
| `conventions` | 場景慣例的事實代碼清單（範圍為「場景限定」的事實，見 §4.5） |

### 4.3 人 `persons[]`

| 欄位 | 說明 |
|---|---|
| `person_id` | `P012` 等 |
| `names` | `{en, zh}`。依線索強度決定會不會在對話中出現 |
| `memberships` | 陣列，每個元素 `{scene_id, role, frequency, active_from, active_to}`。`frequency` 為 `daily` / `weekly` / `occasional` / `once`。同一人可屬於多個場景，這就是**跨場景的人** |
| `transient` | 布林。開放場域的一次性訪客為 `true` |
| `cue_profile` | 身分線索（§4.3.1） |

#### 4.3.1 身分線索 `cue_profile`

依案例的 `cue_level` 決定哪些欄位會被要求寫進對話：

**各級的用途**（2026-11-12 決定）：`medium` 是主要分析層級；`weak` 只剩任務內容，不太真實，作為壓力測試（下限）；`strong` 作為上限參考。名字一出現，歸屬幾乎就解決了，所以 `strong` 另做 `names: on/off` 對照。

| 欄位 | 內容 | 弱 | 中 | 強 |
|---|---|---|---|---|
| `register` | 語氣（正式、口語）、句長傾向 | 所有人相同 | 依角色 | 個人化 |
| `catchphrases` | 口頭禪、慣用語 | 不出現 | 不出現 | 出現 |
| `recurring_refs` | 常提到的人事物（家人、寵物、自己的專案），各語言寫法 | 不出現 | 角色相關的才出現 | 出現 |
| `self_disclosure` | 會主動說出自己的處境（「我今天值晚班」） | 不出現 | 偶爾 | 常出現 |
| `name_mention` | 對話中是否會出現自己或他人的名字 | 不出現 | 不出現 | 偶爾：每人至多 1 段，且不在該人第一次出現的段落；案例 `names: off` 時不出現 |

### 4.4 屬性 `attributes[]`

屬性是「同一類問題」，用來製造混淆。

| 欄位 | 說明 |
|---|---|
| `attribute_id` | 例如 `report_format`、`allergy`、`meeting_room_preference` |
| `description` | `{en, zh}`，給生成模型理解用 |
| `scene_types` | 哪些場景會用到這個屬性 |
| `confusable` | 布林。為 `true` 時，產生器會在不同情境放入同屬性、不同值的事實（陷阱題的來源） |

### 4.5 事實 `facts[]`（核心）

| 欄位 | 說明 |
|---|---|
| `fact_id` | `F0031` |
| `attribute_id` | 屬於哪個屬性 |
| `value` | `{value_id, surface: {en, zh}}`。`surface` 是要在對話中**逐字出現**、計分時逐字比對的寫法 |
| `scope` | `{type, person_id, scene_id}`。`type` 為 `context`（兩者都填）、`person`（只填人）、`scene`（只填場景）、`transferable`（都不填） |
| `origin_context` | 這條事實第一次被說出來的情境 `C-...`。可遷移與場景限定的事實也有來源情境 |
| `introduced_in` | 第一次說出的段落代碼 |
| `reinforced_in` | 之後再被提到的段落代碼清單（可空） |
| `statement_hint` | `{en}`：給生成模型的提示，例如「使用者提到自己對花生過敏」。只給生成用，不直接放進對話 |
| `mutable` | 固定為 `false`。主實驗不處理事實隨時間改變；「依情境過時」（只在某情境中改變的事實）列為延伸，若做，另設獨立分割，不混入主實驗 |

**植入值的限制**（檢查程式會驗證）：

- 同一案例內，任兩個植入值的寫法不能互為子字串，否則字串比對會誤判。
- 植入值要夠特定，例如「週四下午三點的 B2 會議室」而不是「下午」，避免模型憑常識猜中。

### 4.6 段落 `encounters[]`

| 欄位 | 說明 |
|---|---|
| `encounter_id` | `E0042`，依時間排序 |
| `timestamp` | 開始時間 |
| `context_id` | 這段的真實情境（隱藏） |
| `task` | `{en}`：這段互動在做什麼，例如「請代理安排下週的家長會」 |
| `introduce_facts` | 這段要第一次說出的事實代碼 |
| `reinforce_facts` | 這段要再提到的事實代碼 |
| `use_facts` | 代理在這段應該**主動使用**的事實代碼（讓記憶系統看到「記憶被使用」的例子）。限制：只能是這段 `reinforce_facts` 中的事實（不在第一次說出的段落示範）；每個案例的示範段落不超過全部段落的 15%；不得示範任何題目的 `forbidden_facts`；案例 `use_demos: off` 時一律為空 |
| `cue_items` | 這段要帶出的身分線索（從 `cue_profile` 選） |
| `target_turns` | 預計輪數，例如 6–10 |
| `min_cue` | 布林。為 `true` 時刻意讓這段幾乎沒有身分線索（情境不明題的來源） |

### 4.7 題目設計 `probes[]`

| 欄位 | 說明 |
|---|---|
| `probe_id` | `Q0108` |
| `type` | `Q1`–`Q7`（規格 §4） |
| `asked_after` | 在哪一段結束後提問；提問者的情境就是這段的情境 |
| `lead_in_turns` | 作答時附上這段最後幾輪對話，作為「現在是誰」的唯一線索 |
| `required_facts` | 正確回答**必須用到**的事實代碼 |
| `forbidden_facts` | **不能用到**的事實代碼：其他情境中同屬性、不同值的事實 |
| `expected_behavior` | `answer` / `confirm` / `abstain`。`confirm` 表示應先向使用者確認情境 |
| `question_hint` | `{en}`：給題目生成模型的提示 |

## 5. 公開檔

### 5.1 `stream.<lang>.jsonl`：一輪一行

| 欄位 | 說明 |
|---|---|
| `turn_id` | 全案例連續編號 |
| `timestamp` | 這輪的時間 |
| `speaker` | `user` / `assistant`。**不標是哪個使用者** |
| `text` | 對話文字 |

段落代碼、情境都**不**放在這裡，由 `signals.json` 依條件提供。

### 5.2 `signals.json`

| 條件 | 內容 |
|---|---|
| `label` | 每輪對應的人與場景（以不透明代號表示，例如 `u3`、`s2`，不用真實名字） |
| `boundary` | 每輪所屬的不透明段落代號（例如 `b0017`），只能看出哪些輪是同一段 |
| `none` | 空 |

### 5.3 `probes.<lang>.jsonl`

| 欄位 | 說明 |
|---|---|
| `probe_id` | |
| `after_turn_id` | 在哪一輪之後提問；記憶系統只能看到這一輪以前的對話 |
| `lead_in_turn_ids` | 作答時附上的當下對話輪次 |
| `question` | 題目文字 |

題目與作答**不寫回對話流**，避免評估本身改變記憶內容。

## 6. `gold.json`（隱藏）

| 欄位 | 說明 |
|---|---|
| `encounters` | 每段的 `{encounter_id, context_id, turn_ids}`，計算 C1、C2 用 |
| `probes` | 每題的 `{probe_id, type, expected_behavior, must_contain: [value_id], must_not_contain: [value_id], reference_answer: {en, zh}}` |
| `values` | 每個植入值的 `{value_id, surface: {en, zh}}`，計分時逐字比對 |

## 7. 作答格式

依規格 §12 的決定，回答為開放式文字，另外要求兩個機器可讀的標記，放在回答最後：

```
<回答本文>
[USED] <用到的記憶摘要，每條一行；沒用到則寫 none>
[ACTION] answer | confirm | abstain
```

計分：

- **用了該用的**：回答本文出現 `must_contain` 的植入值寫法。
- **誤用**：回答本文出現 `must_not_contain` 的植入值寫法。
- **行為**：`[ACTION]` 與 `expected_behavior` 比對。
- `[USED]` 只用於錯誤分析，不直接計分，因為記憶系統內部的單元沒有統一代碼。

## 8. 世界設定產生後要通過的檢查

| 檢查 | 失敗時 |
|---|---|
| 每條 `required_facts` 都在提問之前的某段被說出 | 重新產生 |
| 陷阱題（Q5）的 `forbidden_facts` 確實存在於其他情境，且屬性相同、值不同 | 重新產生 |
| 無資料題（Q7）的本情境沒有這個屬性的事實，但其他情境有 | 重新產生 |
| 範圍一致：同人跨場景題（Q2）用到的事實範圍是 `person`；同場景跨人題（Q3）是 `scene`；遷移題（Q4）是 `transferable` | 重新產生 |
| 植入值互不為子字串（各語言分別檢查） | 重新產生 |
| 示範段落（`use_facts` 非空）不超過全部段落的 15%；示範的事實都在同段的 `reinforce_facts` 中，且不是任何題目的 `forbidden_facts` | 重新產生 |
| `use_demos: off` 版本和同 `seed` 的 `on` 版本，除 `use_facts` 外完全相同 | 重新產生 |
| 公開檔不含任何代碼、不含超出線索等級的名字 | 生成後檢查，失敗則重新生成該段 |
| 生成的對話中，每條 `introduce_facts` 的植入值逐字出現 | 重新生成該段；記錄剔除率 |
| 不看歷史也答得出的題目（只給題目與當下對話） | 剔除該題；記錄剔除率 |

## 9. 一個極小的例子（家庭場景，2 人，中線索）

```json
{
  "case_id": "XS-0001", "seed": 1, "cue_level": "medium", "names": "off", "use_demos": "on", "source_language": "en",
  "scenes": [{"scene_id": "S01", "type": "household", "agent_role": "home assistant",
              "roles": ["parent", "child"], "conventions": ["F0003"]}],
  "persons": [
    {"person_id": "P001", "names": {"en": "Mia", "zh": "米雅"},
     "memberships": [{"scene_id": "S01", "role": "parent", "frequency": "daily"}],
     "transient": false},
    {"person_id": "P002", "names": {"en": "Leo", "zh": "里歐"},
     "memberships": [{"scene_id": "S01", "role": "child", "frequency": "daily"}],
     "transient": false}],
  "attributes": [{"attribute_id": "snack_rule", "confusable": true}],
  "facts": [
    {"fact_id": "F0001", "attribute_id": "snack_rule",
     "value": {"value_id": "V0001", "surface": {"en": "no sweets after 7 pm", "zh": "晚上七點後不吃甜食"}},
     "scope": {"type": "context", "person_id": "P001", "scene_id": "S01"},
     "introduced_in": "E0001"},
    {"fact_id": "F0002", "attribute_id": "snack_rule",
     "value": {"value_id": "V0002", "surface": {"en": "one granola bar after soccer practice", "zh": "足球練習後一條燕麥棒"}},
     "scope": {"type": "context", "person_id": "P002", "scene_id": "S01"},
     "introduced_in": "E0002"},
    {"fact_id": "F0003", "attribute_id": "trash_day",
     "value": {"value_id": "V0003", "surface": {"en": "recycling goes out on Tuesday nights", "zh": "週二晚上倒回收"}},
     "scope": {"type": "scene", "scene_id": "S01"}, "introduced_in": "E0001"}],
  "probes": [
    {"probe_id": "Q0001", "type": "Q5", "asked_after": "E0005", "lead_in_turns": 2,
     "required_facts": ["F0002"], "forbidden_facts": ["F0001"], "expected_behavior": "answer",
     "question_hint": {"en": "The child asks whether they can have a snack after practice."}}]
}
```

這題是陷阱題：提問的是孩子（P002，從當下對話判斷），正確答案要用他的規則（V0002），不能套用家長的規則（V0001）。

## 10. 已決定事項（2026-11-12，研究者確認）

1. **事實不隨時間改變**：主實驗 `mutable: false`。「依情境過時」列為延伸，另設獨立分割。
2. **題目不寫回記憶**：題目和作答不進入對話流。理由：寫回後各系統看到的記憶不同，無法公平比較；代理自己的錯誤答案會汙染後續。「被糾正後學會」列為未來工作。
3. **身分線索分級**：維持弱／中／強；`medium` 為主要分析層級，`weak` 為壓力測試；`strong` 的名字只偶爾出現，並另做 `names: on/off` 對照（§4.1、§4.3.1）。
4. **代理主動使用記憶的示範**：保留，但只放在強化段落、比例上限 15%、不示範陷阱題要避開的事實；另做 `use_demos: off` 消融（§4.1、§4.6）。示範等於告訴系統「這條記憶屬於這個情境」，消融用來量出這個線索帶來多少好處。
