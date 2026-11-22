# 庭上見｜F11 單人 AI 模擬法庭（最小可行版）

使用者扮演原告，AI 扮演審判長、被告（對造）與證人，依照
「核對身分 → 陳述訴之聲明／答辯 → 爭點整理 → 調查證據（含詢問證人）→ 言詞辯論 → 宣告辯論終結」
的順序推進。首案為「租屋押金糾紛」（教學用虛構案例）。

## 執行

### 方法一：終端機版（不需要瀏覽器，也不需要安裝套件）

在專案資料夾（有 `app` 資料夾的那層）開啟命令提示字元或 PyCharm 的 Terminal，執行：

```bash
python -m app.cli
```

在 PyCharm 也可以：Run → Edit Configurations → 新增 Python → 選 **Module name** 填 `app.cli`，
Working directory 設為專案資料夾。

### 方法二：網頁版（需要瀏覽器）

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

打開瀏覽器到 http://127.0.0.1:8000 就可以開庭。

預設使用 **mock 模式**（規則式 AI），不需要 API 金鑰，適合開發與 Demo 備案。

## 接上真正的 LLM

任何支援 OpenAI `/chat/completions` 格式的服務都可以用，只要設定環境變數：

```bash
# OpenAI
export LLM_PROVIDER=openai
export LLM_BASE_URL=https://api.openai.com/v1
export LLM_API_KEY=你的金鑰
export LLM_MODEL=gpt-4o-mini

# Google Gemini（OpenAI 相容端點）
export LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
export LLM_MODEL=gemini-2.5-flash   # 型號請依官方目前提供的調整

# 本機 Ollama（免費、不需金鑰）
export LLM_BASE_URL=http://localhost:11434/v1
export LLM_MODEL=qwen2.5:7b
```

Windows PowerShell 請改用 `$env:LLM_PROVIDER="openai"` 的寫法。
若模型不支援 JSON 模式而出錯，可設定 `LLM_JSON_MODE=0`。

## 測試

```bash
python -m unittest -v
```

測試會用 mock AI 跑完整場開庭，並檢查：不存在的證物會被擋、AI 不能讓不該發言的角色說話、
LLM 失敗時不會當掉、卡關時會依回合上限往下走。

## 程式結構

| 檔案 | 內容 |
|---|---|
| `app/stages.py` | **庭審狀態機**：六個階段、各階段可發言的 AI 角色、使用者提示、完成條件、回合上限 |
| `app/engine.py` | **核心引擎**：每回合的流程、F13 簡易規則檢查、過濾 AI 輸出、階段轉移、筆錄紀錄 |
| `app/llm.py` | **多角色提示詞**與 LLM 串接（只用標準函式庫） |
| `app/mock_llm.py` | 離線規則式 AI，輸出格式與 LLM 相同 |
| `app/cases/rent_deposit.json` | **案件資料**：事實、爭點、證物、證人知道的事、被告立場、法條 |
| `app/main.py` | FastAPI API |
| `static/index.html` | 測試用網頁介面（之後由 Flutter App 取代） |

### API

| 方法 | 路徑 | 說明 |
|---|---|---|
| GET | `/api/cases` | 案件列表 |
| POST | `/api/sessions` | 開始一場開庭，body：`{"case_id":"rent_deposit_01"}` |
| POST | `/api/sessions/{id}/turn` | 原告發言，body：`{"text":"..."}` |
| GET | `/api/sessions/{id}` | 取得完整紀錄（給 F14 筆錄、F17 回饋報告用） |

### 設計重點

1. **流程由程式控制**：AI 只回傳 `stage_done` 的建議，真正換階段由 engine 決定，並有回合上限防卡關。
2. **AI 輸出會被過濾**：不屬於目前階段的角色發言會被丟掉；證人未具結前不能作證。
3. **事實只來自案件 JSON**：被告、證人都只能根據案件資料回答，降低 AI 亂編。
4. **AI 回傳固定 JSON**：`{"replies":[{"role":"judge","text":"..."}],"stage_done":false,"violation":null,"witness_sworn":false}`

## 之後可以接的功能

- **F13**：在 `engine._check_rules()` 加更多規則（例如未經許可發言）。
- **F14**：前端加語音輸入（Whisper）→ 轉成文字後呼叫同一個 `/turn` API；`transcript` 可直接轉成筆錄格式。
- **F17**：開庭結束後把 `transcript` 和評分規準送給 LLM 產生回饋報告。
- **新增案件**：在 `app/cases/` 放新的 JSON 即可，格式照 `rent_deposit.json`。
- **資料庫**：`main.py` 的 `SESSIONS` 目前存在記憶體，重啟會消失，之後改存 PostgreSQL。

> 本平台為教育用途，不提供個案法律意見。案例內容與法條摘要上線前須經法律專家審核。
