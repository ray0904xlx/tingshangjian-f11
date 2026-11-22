"""終端機版 F11（不需要瀏覽器，也不需要安裝任何套件）。

執行：python -m app.cli
"""
import sys

from .engine import CourtSession, load_case
from .llm import get_provider

COLORS = {"judge": "33", "defendant": "36", "witness": "32", "clerk": "35"}


def _supports_color():
    return sys.stdout.isatty()


def show(msgs):
    color = _supports_color()
    for m in msgs:
        if m["role"] == "plaintiff":
            continue  # 使用者自己打的字不再重複印
        if m["kind"] == "violation":
            head, code = "⚠ 審判長提醒", "31"
        elif m["kind"] == "system":
            head, code = "（系統）", "90"
        else:
            head, code = m["speaker"], COLORS.get(m["role"], "0")
        line = f"{head}：{m['text']}"
        print(f"\033[{code}m{line}\033[0m" if color else line)
        print()


def show_state(s):
    st = s.state()
    names = [x["name"] for x in st["stages"]]
    bar = " → ".join(f"[{n}]" if i == st["stage"]["index"] else n for i, n in enumerate(names))
    print("-" * 60)
    print(f"程序：{bar}")
    print(f"提示：{st['stage']['hint']}")
    if s.stage.key == "EVIDENCE":
        ev = "、".join(f"{e['id']}{e['name']}{'✓' if e['presented'] else ''}" for e in st["evidence"])
        print(f"證物：{ev}")
        print(f"證人：{st['witness']}（{'已具結' if st['witness_sworn'] else '尚未傳喚'}）")
    print("-" * 60)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")   # Windows 終端機顯示中文
    s = CourtSession(load_case("rent_deposit_01"), get_provider())
    print(f"\n《庭上見》F11 單人 AI 模擬法庭｜{s.case['court']}")
    print(f"你是原告 {s.case['plaintiff']['name']}。輸入 /q 離開，/重來 重新開始。\n")
    show(s.start())
    while not s.finished:
        show_state(s)
        try:
            text = input("原告（你）> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已離開。")
            return
        if text in ("/q", "/quit", "exit"):
            print("已離開。")
            return
        if text == "/重來":
            s = CourtSession(load_case("rent_deposit_01"), get_provider())
            show(s.start())
            continue
        print()
        show(s.turn(text))
    print(f"本次開庭共被提醒 {s.violations} 次。")


if __name__ == "__main__":
    main()
