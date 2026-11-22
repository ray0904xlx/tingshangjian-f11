"""離線用的規則式 AI（不需要 API 金鑰）。

用途：開發前端、跑測試、Demo 時網路不穩的備案。
輸出格式和真正的 LLM 完全一樣，engine 不用分辨是哪一種。
"""
from .engine import find_evidence_ids


def _has(text, words):
    return any(w in text for w in words)


DONE_WORDS = ["沒有其他", "沒有了", "調查完畢", "無其他", "沒有要提出"]
NO_OPINION = ["沒有意見", "無意見", "沒意見", "同意", "確認", "沒問題"]
NO_MORE = ["沒有補充", "無補充", "沒有其他意見", "辯論完畢", "沒有要補充"]


def mock_respond(s, text: str) -> dict:
    c = s.case
    key = s.stage.key
    r = lambda role, t: {"role": role, "text": t}

    if key == "IDENTITY":
        if c["plaintiff"]["name"] in text:
            return {"replies": [r("judge", "好。")], "stage_done": True}
        return {"replies": [r("judge", "請原告先說出你的姓名，再陳述出生年月日及住所。")],
                "stage_done": False}

    if key == "CLAIMS":
        pc = c["plaintiff_claim"]
        if _has(text, pc["action_keywords"]) and _has(text, pc["object_keywords"]):
            return {"replies": [r("judge", "被告答辯如何？"), r("defendant", c["defendant_answer"])],
                    "stage_done": True}
        return {"replies": [r("judge", "原告，訴之聲明要具體說明你請求法院判決被告做什麼、金額多少，"
                                       f"例如：「{pc['example']}」請再陳述一次。")],
                "stage_done": False}

    if key == "ISSUES":
        if _has(text, NO_OPINION):
            return {"replies": [r("judge", "好，本件爭點確定，記明筆錄。")], "stage_done": True}
        return {"replies": [r("judge", "原告的補充本院記明筆錄。對爭點整理是否還有其他意見？"
                                       "如無意見，請表示「沒有意見」。")],
                "stage_done": False}

    if key == "EVIDENCE":
        replies, sworn = [], False
        ev = {e["id"]: e for e in c["evidence"]}
        new_ids = [i for i in find_evidence_ids(text) if i not in s.presented]
        for eid in new_ids:
            e = ev[eid]
            if e["owner"] == "plaintiff":
                replies.append(r("judge", f"提示{eid}{e['name']}。被告對{eid}有何意見？"))
                replies.append(r("defendant", e["defendant_opinion"]))
            else:
                replies.append(r("judge", f"{eid}{e['name']}為被告提出之證據，本院已提示。"
                                          f"{e.get('plaintiff_prompt', '')}"))
        w = c["witness"]
        wants_witness = "證人" in text or w["name"] in text
        if wants_witness and not s.witness_sworn:
            replies.append(r("judge", f"准許傳喚證人{w['name']}。證人{w['name']}與原告的關係？"
                                      "（證人：大學同學。）本院已告知證人具結義務及偽證處罰，證人已具結。"
                                      "原告可以開始詢問證人。（教學簡化）"))
            sworn = True
        elif s.witness_sworn and not new_ids and not _has(text, DONE_WORDS):
            answer = next((k["answer"] for k in w["knowledge"] if _has(text, k["keywords"])),
                          w["unknown_answer"])
            replies.append(r("witness", answer))
        if _has(text, DONE_WORDS):
            replies.append(r("judge", "被告有無其他證據要調查？"))
            replies.append(r("defendant", "沒有，我已經提出被證1估價單。"))
            return {"replies": replies, "stage_done": True, "witness_sworn": sworn}
        if not replies:
            replies.append(r("judge", "請具體說明要提出的證物編號（例如「原證1」），或聲請詢問證人。"))
        return {"replies": replies, "stage_done": False, "witness_sworn": sworn}

    if key == "ARGUMENT":
        if _has(text, NO_MORE):
            return {"replies": [r("judge", "被告有無補充？"), r("defendant", "沒有補充。")],
                    "stage_done": True}
        used = s.scratch.setdefault("rebutted", [])
        issue = next((i for i in c["issues"] if i["id"] not in used and _has(text, i["keywords"])), None)
        if issue:
            used.append(issue["id"])
            reply = issue["defendant_rebuttal"]
        else:
            reply = "我還是認為原告沒有好好維護房子，押金不應該退。"
        return {"replies": [r("defendant", reply), r("judge", "原告對被告的說法有無回應？說完請表示「沒有補充」。")],
                "stage_done": False}

    return {"replies": [], "stage_done": False}
