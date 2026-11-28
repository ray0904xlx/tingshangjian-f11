"""F11 單人 AI 模擬法庭核心引擎（不依賴 FastAPI，可單獨測試）。

每一回合的流程：
  使用者發言 → 規則檢查（F13 簡易版）→ AI 回應（mock 或 LLM）
  → 檢查 AI 輸出是否合規 → 判斷是否進入下一階段
"""
import json
import re
import uuid
from pathlib import Path

from .stages import STAGES

CASES_DIR = Path(__file__).parent / "cases"

_FULLWIDTH = str.maketrans("０１２３４５６７８９", "0123456789")
_CN_DIGIT = {c: i + 1 for i, c in enumerate("一二三四五六七八九十")}
_EVIDENCE_RE = re.compile(r"(原證|被證)\s*([0-9０-９]+|[一二三四五六七八九十])")


def load_case(case_id: str) -> dict:
    for p in CASES_DIR.glob("*.json"):
        data = json.loads(p.read_text(encoding="utf-8"))
        if data["case_id"] == case_id:
            return data
    raise KeyError(case_id)


def list_cases() -> list:
    out = []
    for p in sorted(CASES_DIR.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        out.append({"case_id": d["case_id"], "title": d["title"], "court": d["court"]})
    return out


def find_evidence_ids(text: str) -> list:
    """把「原證３」「原證三」「原證 3」都轉成「原證3」。"""
    ids = []
    for prefix, num in _EVIDENCE_RE.findall(text):
        n = _CN_DIGIT.get(num) or int(num.translate(_FULLWIDTH))
        eid = f"{prefix}{n}"
        if eid not in ids:
            ids.append(eid)
    return ids


class CourtSession:
    def __init__(self, case: dict, provider):
        self.id = uuid.uuid4().hex[:12]
        self.case = case
        self.provider = provider          # callable(session, user_text) -> dict
        self.stage_idx = 0
        self.stage_turns = 0
        self.transcript = []              # 完整發言紀錄，之後可接 F14 筆錄、F17 回饋
        self.presented = []               # 已提出的證物編號
        self.witness_sworn = False
        self.violations = 0
        self.scratch = {}                 # 給 mock 記錄狀態用
        self.finished = False
        self.evidence_ids = {e["id"] for e in case["evidence"]}

    # ---------- 基本屬性 ----------
    @property
    def stage(self):
        return STAGES[self.stage_idx]

    def label(self, role: str) -> str:
        c = self.case
        return {
            "judge": "審判長",
            "clerk": "書記官",
            "defendant": f"被告 {c['defendant']['name']}",
            "witness": f"證人 {c['witness']['name']}",
            "plaintiff": f"原告 {c['plaintiff']['name']}（你）",
            "system": "系統",
        }.get(role, role)

    def _say(self, role, text, kind="speech"):
        msg = {"role": role, "speaker": self.label(role), "text": text,
               "kind": kind, "stage": self.stage.key}
        self.transcript.append(msg)
        return msg

    # ---------- 對外介面 ----------
    def start(self) -> list:
        return self._enter_stage()

    def turn(self, text: str) -> list:
        text = (text or "").strip()
        if self.finished:
            return [self._say("system", "本次模擬開庭已結束，可以重新開始一場。", "system")]
        if not text:
            return []
        out = [self._say("plaintiff", text)]

        # 1) 規則檢查：違規就由審判長提醒，不呼叫 AI、不算回合
        rule_violation = self._check_rules(text)
        if rule_violation:
            self.violations += 1
            out.append(self._say("judge", rule_violation, "violation"))
            return out

        # 2) 呼叫 AI
        self.stage_turns += 1
        try:
            result = self._sanitize(self.provider(self, text))
        except Exception as e:  # LLM 連線或格式錯誤
            self.stage_turns -= 1
            out.append(self._say("system", f"AI 回應失敗，請再說一次。（{e}）", "system"))
            return out

        if result["notice"]:
            out.append(self._say("system", result["notice"], "system"))
        if result["violation"]:
            self.violations += 1
            out.append(self._say("judge", result["violation"], "violation"))
        if result["witness_sworn"]:
            self.witness_sworn = True
        for r in result["replies"]:
            out.append(self._say(r["role"], r["text"]))

        if self.stage.key == "EVIDENCE":
            for eid in find_evidence_ids(text):
                if eid in self.evidence_ids and eid not in self.presented:
                    self.presented.append(eid)

        # 3) 是否進入下一階段（AI 建議 + 回合上限）
        done = result["stage_done"]
        if not done and self.stage_turns >= self.stage.max_turns:
            out.append(self._say("system", "（教學簡化）本階段已達回合上限，進入下一個程序。", "system"))
            done = True
        if done:
            self.stage_idx += 1
            self.stage_turns = 0
            out += self._enter_stage()
        return out

    def state(self) -> dict:
        return {
            "session_id": self.id,
            "case": {"case_id": self.case["case_id"], "title": self.case["title"],
                     "case_no": self.case["case_no"], "court": self.case["court"],
                     "plaintiff": self.case["plaintiff"]["name"],
                     "defendant": self.case["defendant"]["name"],
                     "teaching_notes": self.case.get("teaching_notes", [])},
            "stage": {"key": self.stage.key, "name": self.stage.name,
                      "hint": self.stage.user_hint, "index": self.stage_idx},
            "stages": [{"key": s.key, "name": s.name} for s in STAGES],
            "evidence": [{"id": e["id"], "name": e["name"], "owner": e["owner"],
                          "presented": e["id"] in self.presented}
                         for e in self.case["evidence"]],
            "witness": self.case["witness"]["name"],
            "witness_sworn": self.witness_sworn,
            "violations": self.violations,
            "finished": self.finished,
        }

    # ---------- 內部 ----------
    def _enter_stage(self) -> list:
        msgs = [self._say("judge", self.stage.opening(self.case))]
        if self.stage.key == "CLOSED":
            self.finished = True
            msgs.append(self._say("system",
                                  "本平台為教育用途，不提供個案法律意見。若真的遇到租屋糾紛，"
                                  "可洽法律扶助基金會、各地方法院訴訟輔導科或鄉鎮市區公所調解委員會。",
                                  "system"))
        return msgs

    def _check_rules(self, text: str):
        """F13 簡易版：用規則抓得到的錯誤，就不交給 AI 判斷。"""
        for eid in find_evidence_ids(text):
            if eid not in self.evidence_ids:
                return (f"原告，卷內沒有「{eid}」這項證物。開庭時只能引用已經提出到法院的證據，"
                        f"不能提出不存在的證物。")
        return None

    def _sanitize(self, result) -> dict:
        """AI 輸出只保留目前階段允許的角色，避免跳脫程序。"""
        if not isinstance(result, dict):
            raise ValueError("AI 輸出格式錯誤")
        allowed = set(self.stage.ai_roles)
        sworn_now = bool(result.get("witness_sworn")) or self.witness_sworn
        replies = []
        for r in result.get("replies") or []:
            role = r.get("role") or r.get("speaker")
            text = str(r.get("text", "")).strip()[:600]
            if not text or role not in allowed:
                continue
            if role == "witness" and not sworn_now:
                continue  # 證人未具結前不能作證
            replies.append({"role": role, "text": text})
        violation = result.get("violation") or None
        if not replies and not violation:
            replies = [{"role": "judge", "text": "請原告繼續陳述。"}]
        return {"replies": replies, "stage_done": bool(result.get("stage_done")),
                "violation": violation, "witness_sworn": bool(result.get("witness_sworn")),
                "notice": result.get("notice")}
