"""把历史会话 jsonl 抽成可读的时间线（只保留决策、命令、关键数字）。

会话文件在 WorkBuddy 的 projects 目录下：
    C:/Users/<user>/.workbuddy/projects/o-ai修图/<sessionId>.jsonl
每条记录：{type: message, role: user|assistant, content: [blocks]}
block: input_text / text / tool_use / tool_result
"""
from __future__ import annotations

import json
import os
import re
import sys

SRC = os.path.join(os.environ.get("USERPROFILE", r"C:\Users\1"),
                   ".workbuddy", "projects", "o-ai修图")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "timeline")

SESSIONS = {
    "044cf7e8-6b39-4193-bee1-99b9ee4c5341": "曝光",
    "fd505aaf-a4f5-4db7-9db6-b344d2974581": "头部检测",
    "bbbfe70b-e297-4f2b-8f0a-68fc23a6bc89": "白平衡",
}

SYS_RE = re.compile(r"<system-reminder[\s\S]*?</system-reminder>")
TAG_RE = re.compile(r"<[^>]{1,40}>")


def clean(t: str) -> str:
    t = SYS_RE.sub("", t or "")
    t = TAG_RE.sub("", t)
    return t.strip()


def short(t: str, n: int) -> str:
    t = " ".join((t or "").split())
    return t if len(t) <= n else t[:n] + "…"


def blocks(msg):
    c = msg.get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return c or []


def run(sid: str, tag: str):
    src = os.path.join(SRC, sid + ".jsonl")
    if not os.path.exists(src):
        print("missing", src)
        return
    lines = []
    with open(src, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:          # noqa: BLE001
                continue
            if d.get("type") != "message":
                continue
            role = d.get("role")
            for b in blocks(d):
                t = b.get("type")
                if t == "input_text" and role == "user":
                    txt = clean(b.get("text", ""))
                    if len(txt) >= 2:
                        lines.append(f"\n### 用户\n{txt}\n")
                elif t == "text" and role == "assistant":
                    txt = clean(b.get("text", ""))
                    if len(txt) >= 30:
                        lines.append(f"- 助手：{short(txt, 400)}\n")
                elif t == "tool_use":
                    name = b.get("name", "")
                    inp = b.get("input") or {}
                    cmd = inp.get("command") or inp.get("query") or inp.get("prompt") or ""
                    if name in ("Bash", "PowerShell") or cmd:
                        lines.append(f"  - `{name}`: {short(str(cmd), 220)}\n")
    os.makedirs(OUT, exist_ok=True)
    fp = os.path.join(OUT, f"{tag}-{sid[:8]}.md")
    with open(fp, "w", encoding="utf-8") as f:
        f.write(f"# 会话时间线 · {tag}\n\n> 由 `reports/extract_chat.py` 自动抽取，"
                f"源：`{sid}.jsonl`\n")
        f.writelines(lines)
    print(f"{tag}: {len(lines)} 段 → {fp}")


if __name__ == "__main__":
    for sid, tag in SESSIONS.items():
        run(sid, tag)
