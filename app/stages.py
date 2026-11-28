"""F11 庭審程序狀態機：定義各階段、可發言的 AI 角色、提示與轉移順序。

AI 只能在「目前階段」內發言；要不要進到下一階段，最後由 engine 依規則決定。
"""
from dataclasses import dataclass, field
from typing import Callable

CN_NUM = "一二三四五六七八九十"


def _numbered(items):
    return "；".join(f"{CN_NUM[i]}、{x.rstrip('。')}" for i, x in enumerate(items))


@dataclass(frozen=True)
class Stage:
    key: str
    name: str
    ai_roles: tuple            # 這個階段允許哪些 AI 角色發言
    user_hint: str             # F13：「現在是什麼程序、你可以做什麼」
    goal: str                  # 給 LLM 判斷 stage_done 的完成條件
    max_turns: int             # 回合上限，避免卡關
    opening: Callable = field(compare=False)  # 進入階段時審判長的固定台詞


def _open_identity(c):
    return (f"現在開庭。本件{c['case_no']}，原告{c['plaintiff']['name']}與被告"
            f"{c['defendant']['name']}間{c['title']}。被告{c['defendant']['name']}已到庭。"
            f"請原告陳述姓名、出生年月日及住所。")


def _open_claims(c):
    return "身分核對無誤。請原告陳述訴之聲明，也就是你請求法院判決什麼，並說明事實及理由。"


def _open_issues(c):
    issues = [i["text"] for i in c["issues"]]
    return (f"本院整理兩造不爭執事項如下：{_numbered(c['undisputed_facts'])}。"
            f"本件爭點為：{_numbered(issues)}。原告對以上整理有無意見？")


def _open_evidence(c):
    return (f"現在調查證據。原告要提出哪些證物，請說明證物編號；"
            f"如需詢問證人{c['witness']['name']}，請向本院聲請。")


def _open_argument(c):
    return "證據調查完畢。現在進行言詞辯論，請原告就爭點陳述意見。"


def _open_closed(c):
    return "本件言詞辯論終結，宣判日期另行通知（教學模擬，不會產生真實判決）。退庭。"


STAGES = [
    Stage("IDENTITY", "核對身分", ("judge", "clerk"),
          "審判長正在核對你的身分。請陳述你的姓名、出生年月日與住所。",
          "原告說出自己的姓名（與案件資料相符）就算完成，stage_done 設為 true；出生年月日或住所不完整也不用追問門牌，教學上不需要。",
          3, _open_identity),
    Stage("CLAIMS", "陳述訴之聲明與答辯", ("judge", "defendant"),
          "說明你請求法院判決什麼（訴之聲明）與事實理由。例如：「請求被告給付原告新臺幣3萬元。」",
          "原告清楚說出訴之聲明（請求被告返還／給付押金及金額）。完成時由被告陳述答辯聲明與理由。",
          4, _open_claims),
    Stage("ISSUES", "爭點整理", ("judge", "defendant"),
          "審判長已整理不爭執事項與爭點。沒問題就說「沒有意見」，有遺漏可以補充。",
          "原告表示沒有意見、確認，或補充後確認爭點整理。",
          3, _open_issues),
    Stage("EVIDENCE", "調查證據", ("judge", "defendant", "witness"),
          "提出證物請說編號（例如「提出原證3」），也可以聲請詢問證人。調查完畢請說「沒有其他證據」。",
          "原告提出證物後由被告表示意見；原告可聲請詢問證人（審判長先命證人具結）。原告表示沒有其他證據時完成。",
          12, _open_evidence),
    Stage("ARGUMENT", "言詞辯論", ("judge", "defendant"),
          "針對爭點說明你的主張，並回應被告的說法。說完請表示「沒有補充」。",
          "原告就爭點陳述並回應被告反駁。原告表示沒有補充時，審判長詢問被告，被告亦表示沒有補充即完成。",
          8, _open_argument),
    Stage("CLOSED", "宣告辯論終結", (),
          "本次模擬開庭已結束。",
          "", 0, _open_closed),
]

STAGE_KEYS = [s.key for s in STAGES]
