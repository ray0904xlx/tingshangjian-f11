"""真正的 LLM 串接（多角色提示詞）。

使用 OpenAI 相容的 /chat/completions 介面，所以 OpenAI、Google Gemini、
本機 Ollama 都能用，只要改環境變數：
  LLM_PROVIDER = mock | openai          （預設 mock，不需金鑰）
  LLM_BASE_URL = https://api.openai.com/v1
  LLM_API_KEY  = 你的金鑰
  LLM_MODEL    = gpt-4o-mini
只用 Python 標準函式庫，不需要額外安裝 SDK。
"""
import json
import os
import re
import urllib.error
import urllib.request

ROLE_DESC = {
    "judge": "審判長：語氣莊重中立、用語像臺灣法庭實務（「原告」「被告」「本院」「記明筆錄」）；"
             "主持程序、提示證物、命證人具結、追問不清楚的地方；不評論誰會贏，不給法律建議。",
    "clerk": "書記官：必要時協助點名或記錄，發言極少。",
    "defendant": "被告（對造，房東）：五十多歲、有點固執、講話口語化，會為自己辯護但不會人身攻擊；"
                 "只能依案件資料中被告的立場答辯與反駁，不可新增案件資料沒有的事實。",
    "witness": "證人：原告的大學同學，第一次上法院有點緊張、講話老實；只能回答案件資料中證人知道的事，"
               "不知道的一律說不清楚；必須先由審判長命其具結後才能作證。",
}

def build_system_prompt(s) -> str:
    st = s.stage
    c = s.case
    case_view = {k: c[k] for k in ("title", "court", "background", "undisputed_facts",
                                    "issues", "defendant_answer", "evidence", "witness", "law_refs")}
    case_view["plaintiff"] = c["plaintiff"]
    case_view["defendant"] = c["defendant"]
    roles = "\n".join(f"- {r}｜{ROLE_DESC[r]}" for r in st.ai_roles)
    return f"""你是《庭上見》AI 模擬法庭的多角色演出引擎，用於臺灣民事法庭的教學模擬。使用者扮演原告。

【目前程序階段】{st.name}（{st.key}）
【本階段可以發言的角色（role 只能用以下英文代號）】
{roles}
【本階段完成條件】{st.goal}

【規則】
1. 只做本階段的事，不可以自行跳到其他程序（是否進下一階段由你用 stage_done 建議，系統決定）。
2. 所有事實、證物、證人證詞只能來自下方案件資料，不可編造。
3. 引用法條只能用案件資料 law_refs 中的條文。
4. 使用繁體中文，每位角色一次發言不超過 120 字，口吻符合法庭實務。
5. 若原告的發言不符合目前程序（例如在核對身分時就開始辯論、與爭點無關、情緒性攻擊），
   在 violation 用一兩句話說明原因並引導他回到本階段該做的事；否則 violation 為 null。
6. 證人目前{"已" if s.witness_sworn else "尚未"}具結。若本回合由審判長命證人具結，witness_sworn 設為 true。
7. 這是教育模擬，不提供真實個案的法律意見，也不預測判決結果。
8. replies 的順序就是發言順序。通常 1～3 句：審判長回應或主持，需要時再由被告或證人發言。
9. 原告說得不完整時，由審判長追問或引導，不要直接替原告說出答案（蘇格拉底式引導）。
10. 只要原告大致做到完成條件就把 stage_done 設為 true，不要過度挑剔。

【案件資料】
{json.dumps(case_view, ensure_ascii=False)}

【輸出格式】只輸出一個 JSON 物件，不要有其他文字：
{{"replies":[{{"role":"judge","text":"..."}}],"stage_done":false,"violation":null,"witness_sworn":false}}"""


def build_user_prompt(s, text: str) -> str:
    recent = [m for m in s.transcript if m["kind"] != "system"][-16:]
    log = "\n".join(f"{m['speaker']}：{m['text']}" for m in recent[:-1])  # 最後一句就是本回合發言
    return f"【先前紀錄】\n{log or '（無）'}\n\n【原告本回合發言】\n{text}"


def _extract_json(content: str) -> dict:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", content, re.S)
        if not m:
            raise ValueError("LLM 沒有回傳 JSON")
        return json.loads(m.group(0))


def _post(base: str, body: dict) -> dict:
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {os.getenv('LLM_API_KEY', '')}"},
    )
    with urllib.request.urlopen(req, timeout=float(os.getenv("LLM_TIMEOUT", "45"))) as resp:
        return json.loads(resp.read().decode("utf-8"))


def openai_compatible_respond(s, text: str) -> dict:
    base = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    body = {
        "model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
        "temperature": 0.4,
        "messages": [
            {"role": "system", "content": build_system_prompt(s)},
            {"role": "user", "content": build_user_prompt(s, text)},
        ],
    }
    if os.getenv("LLM_JSON_MODE", "1") == "1":
        body["response_format"] = {"type": "json_object"}
    if os.getenv("LLM_REASONING_EFFORT"):          # 例如 low：思考少一點、回得快一點
        body["reasoning_effort"] = os.getenv("LLM_REASONING_EFFORT")
    try:
        data = _post(base, body)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:300]
        if e.code == 400 and "reasoning_effort" in body and "hinking" in detail:
            body.pop("reasoning_effort")          # 這個模型不支援此思考等級，拿掉再試一次
            data = _post(base, body)
        else:
            raise RuntimeError(f"LLM 回應 HTTP {e.code}：{detail}") from e
    return _extract_json(data["choices"][0]["message"]["content"])


def llm_with_fallback(s, text: str) -> dict:
    """先問真的 AI；沒設金鑰、連線失敗或格式錯誤時，本回合改用規則模式，Demo 不會卡住。"""
    from .mock_llm import mock_respond
    if not os.getenv("LLM_API_KEY"):
        result = mock_respond(s, text)
        result["notice"] = "（尚未設定 AI 金鑰，目前使用規則模式）"
        return result
    try:
        return openai_compatible_respond(s, text)
    except Exception as e:  # noqa: BLE001
        print(f"[LLM] 失敗，改用規則模式：{e}", flush=True)
        result = mock_respond(s, text)
        result["notice"] = "（AI 暫時無法回應，本回合改用規則模式）"
        return result


def get_provider():
    if os.getenv("LLM_PROVIDER", "mock").lower() == "openai":
        return llm_with_fallback
    from .mock_llm import mock_respond
    return mock_respond
