"""Project memory: turn past traces into a searchable record of decisions.

The RAG layer retrieves *repo documents*; this layer retrieves *what already
happened* — the plan that was chosen, the tool layer used, which gates failed
and why. It is rebuilt from `traces/*/summary.json` + `trace.jsonl`, so the
memory can never drift away from the evidence.
"""

import glob
import json
import os

from rag.index import InvertedIndex

# The trace speaks in state ids; a human (or a Chinese query) speaks in domain
# words. Indexing both keeps the memory searchable from either side.
STATE_LABELS = {
    "State.RECEIVED": "接收任务",
    "State.PLANNING": "规划 拆解",
    "State.PLAN_VALIDATED": "规划校验 schema",
    "State.DEVELOPING": "开发 实现 改动",
    "State.SOFTWARE_TESTING": "软件验证 测试 编译",
    "State.WAITING_FOR_HUMAN_HARDWARE_TEST": "人工闸门 实机验证 硬件记录 human-in-the-loop 上电 波形",
    "State.REVIEWING": "评审 复核",
    "State.DONE": "完成 交付",
    "State.FAILED": "失败 报错 迭代上限",
}


def _read_jsonl(path):
    events = []
    if not os.path.exists(path):
        return events
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
    return events


class ProjectMemory:
    def __init__(self, repo):
        self.repo = repo
        self.records = []
        self.index = InvertedIndex()

    # ---------- build ----------
    def build(self):
        self.records = []
        self.index = InvertedIndex()
        pattern = os.path.join(self.repo, "traces", "*", "summary.json")
        for summary_path in sorted(glob.glob(pattern)):
            task_id = os.path.basename(os.path.dirname(summary_path))
            try:
                with open(summary_path, "r", encoding="utf-8") as f:
                    summary = json.load(f)
            except ValueError:
                continue
            events = _read_jsonl(os.path.join(os.path.dirname(summary_path), "trace.jsonl"))
            failures = []
            for event in events:
                payload = event.get("payload") or {}
                blob = json.dumps(payload, ensure_ascii=False)
                if (event.get("state") in ("State.FAILED", "State.HUMAN_GATE")
                        or '"ok": false' in blob or "error" in payload):
                    failures.append("%s %s" % (event.get("state"), blob[:200]))
            knowledge = [k.get("citation", "") for k in (summary.get("knowledge") or [])]
            states = [event.get("state", "") for event in events]
            labels = " ".join(STATE_LABELS.get(s, "") for s in set(states))
            # Memory has to carry the *content* of the run, not just its shape:
            # without the payload excerpts a question like "采样窗口 怎么修的"
            # would never match the trace that answered it.
            excerpts = []
            for event in events:
                payload = event.get("payload")
                if not payload:
                    continue
                blob = json.dumps(payload, ensure_ascii=False)
                if blob in ("{}", "null") or len(blob) < 12:
                    continue
                excerpts.append("%s %s" % (event.get("state", ""), blob[:400]))
            text = "\n".join([
                "task %s status %s iterations %s tool_layer %s hardware %s"
                % (task_id, summary.get("status"), summary.get("iterations"),
                   summary.get("tool_layer"), summary.get("hardware_source")),
                "states: " + " ".join(states),
                "state labels: " + labels,
                "knowledge: " + " ".join(knowledge),
                "review: " + json.dumps(summary.get("review") or {}, ensure_ascii=False),
                "failures: " + (" | ".join(failures) if failures else "none"),
                "event log:\n" + "\n".join(excerpts),
            ])
            record = {
                "task_id": task_id,
                "status": summary.get("status"),
                "iterations": summary.get("iterations"),
                "tool_layer": summary.get("tool_layer"),
                "states": states,
                "failures": failures,
                "knowledge": knowledge,
                "text": text,
            }
            self.records.append(record)
            self.index.add({
                "path": "traces/%s/summary.json" % task_id,
                "title": task_id,
                "text": text,
                "start_line": 1,
                "end_line": max(1, len(events)),
            })
        self.index.finalize()
        return {"tasks": len(self.records)}

    # ---------- query ----------
    def search(self, query, k=3):
        hits = []
        for chunk, score in self.index.search(query, k=k):
            record = next((r for r in self.records
                           if r["task_id"] == chunk.get("title")), None)
            hits.append({
                "task_id": chunk.get("title"),
                "citation": "%s#L%d-L%d" % (chunk["path"], chunk["start_line"], chunk["end_line"]),
                "score": score,
                "status": (record or {}).get("status"),
                "iterations": (record or {}).get("iterations"),
                "failures": (record or {}).get("failures", [])[:3],
                "snippet": chunk["text"][:220],
            })
        return hits

    def format_for_planner(self, query, k=3):
        """Plain-text digest injected into the planner payload."""
        hits = self.search(query, k=k)
        if not hits:
            return ""
        return "\n".join(
            "- [%s] status=%s iterations=%s (%s)"
            % (h["task_id"], h["status"], h["iterations"], h["citation"])
            for h in hits
        )
