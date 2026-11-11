# 執行環境

本專案有兩個環境，**驗證狀態不同**：

| 環境 | 用途 | 狀態 |
|---|---|---|
| A. 雲端開發容器（Linux，CPU） | 撰寫程式、下載與驗證資料、單元測試、smoke test | **已實測**（見下方） |
| B. ASUS ROG Flow Z13（Windows 11） | 正式實驗 | **尚未盤點**：請先執行 `scripts/check_env.ps1` |

在 B 上的模型清單、ROCm 狀態、可用記憶體，在盤點報告產生之前都**未經確認**，本文件不做任何假設。

## A. 雲端開發容器（已實測，2026-11-11）

| 項目 | 實測值 |
|---|---|
| OS | Linux 6.18（x86_64） |
| CPU／RAM | 4 核心、15 GB；沒有 GPU |
| Python | 3.13.18，專案 `.venv`（與本機的 3.13 同一個大版本） |
| Ollama | 0.40.16（CPU 版） |
| 模型 | `qwen3:0.6b`（Q4_K_M，原生 context 40,960）、`qwen3-embedding:0.6b`（1,024 維） |
| 套件 | numpy、openai、backoff、tqdm、python-dotenv、tiktoken、pytest（版本以 `pip freeze` 為準） |

在 A 上驗證過的項目：資料下載與 sha256、官方 repo 的 commit、`wlmem verify-data`、12 個單元測試，以及五個 smoke test（見 VALIDATION_REPORT.md）。

## B. Flow Z13 的盤點方式（Phase 1）

```powershell
cd <repo>
powershell -ExecutionPolicy Bypass -File scripts\check_env.ps1
```

這個腳本**只讀取資訊**：不安裝任何東西、不啟動任何服務、不修改 Ollama、ROCm、驅動或 PyTorch。唯一的網路存取是本機的 Ollama API。

它會產生 `env_reports/env_<時間>.json`，內容包括：

- OS、CPU、記憶體（含 BIOS 分給 GPU 的部分）、GPU 驅動
- ROCm／HIP SDK 路徑
- 每個 Python 直譯器的 torch（`torch.version.hip`、GPU 是否可用）、faiss、networkx、neo4j
- Ollama 版本、已安裝模型（digest、量化、原生 context）、已載入模型、`OLLAMA_*` 設定
- 是否有 Neo4j 服務或 Docker（只偵測，不啟動）

> 這個腳本在容器中**無法實際執行**（沒有 Windows 和 PowerShell），只經過人工逐行檢查。第一次執行如果出錯，請把錯誤訊息貼給我。

## 與你現有環境的關係

- 本專案的 Python 套件只安裝在 repo 內的 `.venv`（`scripts/setup.ps1`），**不會**動到全域的 Python 或 PyTorch ROCm。
- 本專案**不需要** PyTorch：作答、judge 和 embedding 都透過 Ollama HTTP API。所以 ROCm 只影響 Ollama 本身的 GPU 加速，跟這個 venv 無關。
- **不需要** Neo4j 或 Docker。之後接入 Zep／Graphiti 時才需要圖資料庫，屆時會先記錄資源需求，由你決定要不要安裝。
- FAISS 是選用套件（`pip install -e ".[faiss]"`）。目前的 RAG baseline 用 numpy 做精確內積搜尋；以 STALE 一個案例約 300 個單元的規模，不需要 ANN 索引。

## Windows 注意事項

- **編碼**：繁體中文 Windows 的預設編碼是 cp950，部分官方程式開檔時沒有指定 encoding。`wlmem` 在 Windows 上會自動以 UTF-8 模式（`-X utf8`）重新啟動自己。直接執行官方腳本時，請先設定 `$env:PYTHONUTF8 = "1"`。
- **Python 版本**：所需套件都有 Python 3.13 的 Windows wheel，預設使用 3.13。只有在 pip 安裝失敗時，才改用 `-PythonVersion 3.12`，並把原因記錄在這裡。
- **git**：`setup_external.py` 用 git 取得固定版本，需要安裝 Git for Windows。

## 記憶體與 context 的粗估（尚未在 Z13 上驗證）

KV cache 大小 ≈ 2 × 層數 × KV heads × head_dim × context 長度 × 每個元素的位元組數。各 benchmark 的 full_context baseline 需要的 context：

下表是實際量測的歷史長度（cl100k 估算，各取前 2–3 個案例）。Qwen 和 Gemma 的 tokenizer 結果會有出入，所以設定 `num_ctx` 時要再留 10–20% 餘裕：

| benchmark | 實測歷史長度 | 說明 |
|---|---|---|
| STALE | 146K–161K token | 需要原生支援 ≥ 180K 的模型。若模型的原生上限較小，Ollama 會截斷輸入，runner 會標記 `ctx_overflow` |
| LongMemEval_S | 103K–105K token | 需要 ≥ 128K |
| Memora weekly | 34K–36K token | 64K 就足夠 |
| Memora monthly | 約 132K token | 需要 ≥ 160K |
| Memora quarterly | 約 45 萬 token（推估） | 放不進任何本機模型，只適合跑記憶方法 |

實際的可行模型與速度，要等 Z13 盤點後再填寫。
