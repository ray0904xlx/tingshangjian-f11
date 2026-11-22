"""用 mock AI 從頭到尾跑一場模擬開庭。執行：python -m unittest -v"""
import unittest

from app.engine import CourtSession, find_evidence_ids, load_case
from app.llm import build_system_prompt, build_user_prompt
from app.mock_llm import mock_respond


def new_session():
    s = CourtSession(load_case("rent_deposit_01"), mock_respond)
    s.start()
    return s


class TestF11(unittest.TestCase):
    def test_evidence_id_parsing(self):
        self.assertEqual(find_evidence_ids("提出原證３和原證 一，還有被證1"), ["原證3", "原證1", "被證1"])

    def test_full_hearing(self):
        s = new_session()
        self.assertEqual(s.stage.key, "IDENTITY")

        s.turn("我是林小安，民國93年5月1日生，住新北市淡水區。")
        self.assertEqual(s.stage.key, "CLAIMS")

        s.turn("我覺得房東很過分")             # 沒講訴之聲明 → 留在本階段
        self.assertEqual(s.stage.key, "CLAIMS")
        s.turn("請求被告給付原告新臺幣3萬元押金。")
        self.assertEqual(s.stage.key, "ISSUES")

        s.turn("沒有意見。")
        self.assertEqual(s.stage.key, "EVIDENCE")

        out = s.turn("提出原證9")                # 不存在的證物 → 違規提醒，不算回合
        self.assertEqual(out[-1]["kind"], "violation")
        self.assertEqual(s.stage_turns, 0)

        s.turn("提出原證3入住照片和原證4 LINE 對話。")
        self.assertEqual(s.presented, ["原證3", "原證4"])
        s.turn("聲請傳喚證人王小美。")
        self.assertTrue(s.witness_sworn)
        out = s.turn("請問證人，入住那天紗窗是什麼狀況？")
        self.assertEqual(out[-1]["role"], "witness")
        self.assertIn("破洞", out[-1]["text"])
        s.turn("沒有其他證據要調查。")
        self.assertEqual(s.stage.key, "ARGUMENT")

        out = s.turn("牆面泛黃是正常使用的損耗。")
        self.assertEqual(out[1]["role"], "defendant")
        s.turn("沒有補充。")
        self.assertEqual(s.stage.key, "CLOSED")
        self.assertTrue(s.finished)
        self.assertEqual(s.violations, 1)

    def test_stage_turn_limit(self):
        s = new_session()
        for _ in range(3):
            s.turn("嗯")
        self.assertEqual(s.stage.key, "CLAIMS")   # 卡關也會往下走

    def test_sanitize_blocks_wrong_roles(self):
        """LLM 若在核對身分階段讓證人或被告發言，系統會擋掉。"""
        fake = lambda s, t: {"replies": [{"role": "witness", "text": "我作證"},
                                         {"role": "defendant", "text": "我反對"},
                                         {"role": "judge", "text": "好"}], "stage_done": False}
        s = CourtSession(load_case("rent_deposit_01"), fake)
        s.start()
        out = s.turn("林小安")
        self.assertEqual([m["role"] for m in out], ["plaintiff", "judge"])

    def test_llm_error_is_handled(self):
        def boom(s, t):
            raise TimeoutError("timeout")
        s = CourtSession(load_case("rent_deposit_01"), boom)
        s.start()
        out = s.turn("林小安")
        self.assertEqual(out[-1]["kind"], "system")
        self.assertEqual(s.stage_turns, 0)

    def test_prompts_build(self):
        s = new_session()
        s.turn("我是林小安")
        sp = build_system_prompt(s)
        self.assertIn("陳述訴之聲明與答辯", sp)
        self.assertIn('"role":"judge"', sp)
        self.assertIn("原告本回合發言", build_user_prompt(s, "請求返還押金"))


if __name__ == "__main__":
    unittest.main()
