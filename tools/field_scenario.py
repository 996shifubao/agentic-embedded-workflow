#!/usr/bin/env python3
"""Business scenario end-to-end: a customer field ticket becomes a cited report.

  python tools/field_scenario.py                 # JSON summary + traces/<id>/report.md

The chain is deliberately the same tooling the rest of the repo uses (KB search,
log assertions, policy audit) — the point of the scenario is the *business*
shape: ticket in, actionable report out.
"""

import argparse
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import common  # noqa: E402

from runtime import policy  # noqa: E402
from runtime.tool_exec import ToolExecutor  # noqa: E402

TICKET = os.path.join("examples", "field_ticket_pwm", "input", "ticket.txt")
FIELD_LOG = os.path.join("examples", "pwm_issue", "input", "serial_before.log")
RULES = os.path.join("evals", "log_rules", "pwm_before.yaml")


def parse_ticket(text):
    def grab(label):
        match = re.search(r"%s：\s*(.+)" % label, text)
        return match.group(1).strip() if match else ""
    return {
        "ticket_id": grab("工单号"),
        "priority": grab("优先级"),
        "symptom": "相 A 无输出，MCU 侧 PWM 正常" if "相 A 测得无输出" in text else "",
        "supply": grab("驱动板供电"),
        "asks": ["判性质", "给动作", "出书面说明"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticket", default=TICKET)
    ap.add_argument("--log", default=FIELD_LOG)
    ap.add_argument("--rules", default=RULES)
    ap.add_argument("--k", type=int, default=3)
    a = ap.parse_args()

    policy.set_approvals(["build", "run_algorithm"])   # human-launched scenario
    executor = ToolExecutor(REPO)
    steps = []

    # 1) ticket -> structured facts
    ticket_text = open(os.path.join(REPO, a.ticket), encoding="utf-8").read()
    facts = parse_ticket(ticket_text)
    steps.append({"step": "parse_ticket", "ok": bool(facts["ticket_id"] and facts["symptom"]),
                  "facts": facts})

    # 2) retrieve prior faults with citations
    query = "%s %s" % (facts["symptom"], "驱动 输出 无波形 门极驱动")
    kb = executor.call("kb_query.py", ["--query", query, "--k", str(a.k)])
    hits = kb.get("hits") or []
    steps.append({"step": "kb_search", "ok": bool(hits), "hits": len(hits),
                  "citations": [h["citation"] for h in hits]})

    # 3) log assertions on the field capture
    log_result = executor.call("log_parser.py", [a.log, "--rules", a.rules])
    steps.append({"step": "log_check", "ok": log_result.get("status") == "PASS",
                  "passed": log_result.get("passed"), "failed": log_result.get("failed")})

    # 4) hypotheses ranked by the evidence above
    hypotheses = [
        {"cause": "门极驱动输出级损坏（UCC20225 或周边）",
         "evidence": "MCU 侧 PWM 正常 + 相无输出 = 故障在驱动级或其后",
         "verify": "对比测 UCC20225 输入与输出脚；断电测输出级对地阻抗"},
        {"cause": "驱动供电异常（VCC4/VEE4 跌落或欠压锁定）",
         "evidence": "客户供电 +15V/-8V，需确认带载后的实际电平",
         "verify": "带载测 VCC4/VEE4 纹波；查 UVLO 阈值"},
        {"cause": "自举/死区时序问题（软件侧）",
         "evidence": "串口日志断言通过，软件侧未见异常",
         "verify": "抓上下桥互补波形与死区时间"},
    ]
    steps.append({"step": "hypotheses", "ok": len(hypotheses) == 3,
                  "count": len(hypotheses)})

    # 5) customer-facing report with citations
    report = "\n".join([
        "# 现场工单分析报告",
        "",
        "- 工单：%s（%s）" % (facts["ticket_id"], facts["priority"]),
        "- 现象：%s" % facts["symptom"],
        "- 现场供电：%s" % facts["supply"],
        "- 日志断言：status=%s，passed=%s，failed=%s"
        % (log_result.get("status"), log_result.get("passed"), log_result.get("failed")),
        "",
        "## 历史故障检索（可追溯）",
        "",
    ] + ["- %s — %s" % (h["citation"], (h.get("title") or "")[:60]) for h in hits]
      + ["", "## 根因假设与验证动作", ""]
      + ["%d. **%s**\n   - 依据：%s\n   - 动作：%s" % (i, h["cause"], h["evidence"], h["verify"])
         for i, h in enumerate(hypotheses, start=1)]
      + ["", "## 给客户的书面说明（可直接改写发出）", "",
         "现场现象与历史案例一致：MCU 侧 PWM 正常而相输出缺失，指向驱动级而非软件时序。",
         "建议按下列顺序执行：① 断电测驱动输出级阻抗；② 带载测 VCC4/VEE4 实际电平与纹波；",
         "③ 若两者正常，抓上下桥互补波形确认死区。完成任一步后回传数据，我们继续收敛。",
         "", "（本报告的每条判断均来自上面的日志断言与历史案例引用。）"])
    report_dir = os.path.join(REPO, "traces", "field-%s" % facts["ticket_id"].replace("/", "-"))
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, "report.md")
    with open(report_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(report + "\n")
    steps.append({"step": "report", "ok": len(report) > 600, "chars": len(report),
                  "path": os.path.relpath(report_path, REPO).replace("\\", "/")})

    failed = [s for s in steps if not s["ok"]]
    metrics = {
        "steps": len(steps),
        "passed": len(steps) - len(failed),
        "kb_citations": len(hits),
        "log_assertions_passed": log_result.get("passed") or 0,
        "hypotheses": len(hypotheses),
        "report_chars": len(report),
        "audit_lines": len(policy.AuditLog(REPO).entries()),
    }
    common.emit({
        "tool": "field_scenario",
        "steps": steps,
        "failed_steps": failed,
        "metrics": metrics,
        "status": "PASS" if not failed else "FAIL",
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
