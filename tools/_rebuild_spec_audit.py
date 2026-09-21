# -*- coding: utf-8 -*-
"""从工作流 journal 确定性重建 §1~§3 规格书对照报告。

为什么要重建：工作流里那个"合成"agent 撞了输出上限，报告只写了一半
（开头断在 §3.1 参数表中间、结尾停在 §3.3.1，末尾还写着"（待续）"）。

但 journal.jsonl 里 **每条审计发现、每条对抗验证结果都是完整结构化数据**，
所以不需要再让 LLM 写一遍 —— 直接 join 出来更准。

join 方法：
  - journal 里 `started` 条目带 agentId/label/phase，`result` 条目带 agentId + 结构化结果
  - 用 agentId 把两者接起来
  - 验证结果 → 发现的映射：一个 section 内，验证 agent 是按「有争议的发现」的顺序
    逐个 spawn 的，每条发现 3 个视角（顺序同 LENSES），所以按 journal 里 started 的
    出现顺序每 3 个一组，依次对应第 i 条有争议发现。

跑法： python.exe tools/_rebuild_spec_audit.py
输出： 调试记录_规格书对照_第1-3章_20260920.md
"""
from __future__ import annotations

import collections
import json
import pathlib

JOURNAL = pathlib.Path(
    r"C:/Users/Administrator/.claude/projects/d--Companty-WEll-thinker-F-code/"
    r"27d9a6cf-18f6-4ad4-b1e3-212f7cb66b27/subagents/workflows/wf_73d0f569-b4a/journal.jsonl"
)
OUT = pathlib.Path(__file__).resolve().parent.parent / "调试记录_规格书对照_第1-3章_20260920.md"

ORDER = ["1.1-1.2", "2-io", "3.1-modes", "3.1-params", "3.1-notes", "3.2-poweron",
         "3.3.1-vent", "3.3.2-cool", "3.3.3-heat", "3.3.4-disinfect", "3.3.5-emergency"]
TITLE = {
    "1.1-1.2": "§1.1 控制器简介 + §1.2 机组简要说明",
    "2-io": "§2 输入输出点",
    "3.1-modes": "§3.1 工作模式（4 种模式的开关定义）",
    "3.1-params": "§3.1 参数设置（15 项 + 2 个时间 + 结束后模式）",
    "3.1-notes": "§3.1 备注 1~4",
    "3.2-poweron": "§3.2 来电自启",
    "3.3.1-vent": "§3.3.1 通风开关机",
    "3.3.2-cool": "§3.3.2 制冷开关机",
    "3.3.3-heat": "§3.3.3 制热开关机",
    "3.3.4-disinfect": "§3.3.4 消排毒开关机",
    "3.3.5-emergency": "§3.3.5 紧急停机",
}
VICON = {"符合": "OK", "不符合": "NG", "未实现": "MISS", "部分符合": "PART", "无法核对": "N/A"}


def main() -> int:
    starts: dict[str, tuple[str, int]] = {}     # agentId -> (label, 出现序号)
    results: dict[str, object] = {}
    seq = 0
    for ln in JOURNAL.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            o = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        aid = o.get("agentId")
        if not aid:
            continue
        if o.get("type") == "started":
            starts[aid] = (str(o.get("label") or ""), seq)
            seq += 1
        elif o.get("type") == "result":
            results[aid] = o.get("result")

    audits: dict[str, list] = {}
    verifies: dict[str, list] = collections.defaultdict(list)
    for aid, (label, order) in starts.items():
        if aid not in results:
            continue
        kind, _, sec = label.partition(":")      # "audit:1.1-1.2" -> ("audit", ":", "1.1-1.2")
        r = results[aid]
        if kind == "audit":
            if isinstance(r, dict) and isinstance(r.get("findings"), list):
                audits.setdefault(sec, []).extend(r["findings"])
        elif kind == "verify":
            verifies[sec].append((order, r))

    L = []
    L.append("# PSC330 内机 —— 规格书 §1~§3 逐句对照固件代码（2026-09-20）")
    L.append("")
    L.append("生成方式：11 节并行审计 → 每条**非「符合」**的发现再上 3 个对抗视角"
             "（代码事实 / 规格书字面 / 运行时后果，**默认立场是「推翻」**）→ "
             "3 个里 ≥2 个没能推翻才算通过。")
    L.append("")
    L.append("判定记号：`符合` / `不符合` / `未实现` / `部分符合` / `无法核对`")
    L.append("")

    stat = collections.Counter()
    for sec in ORDER:
        fs = audits.get(sec, [])
        if not fs:
            continue
        vs = sorted(verifies.get(sec, []), key=lambda x: x[0])
        disputed = [f for f in fs if f.get("verdict") != "符合"]
        # 每 3 个验证结果对应一条有争议发现
        for i, f in enumerate(disputed):
            grp = [v for _, v in vs[i * 3:i * 3 + 3]]
            f["_votes"] = [g for g in grp if isinstance(g, dict)]
            f["_refuted"] = sum(1 for g in f["_votes"] if g.get("refuted"))
            f["_survived"] = f["_refuted"] < 2
        L.append("## %s" % TITLE.get(sec, sec))
        L.append("")
        L.append("| 规格书条款 | 判定 | 依据 | 备注 |")
        L.append("|---|---|---|---|")
        for f in fs:
            stat[f.get("verdict", "?")] += 1
            v = f.get("verdict", "?")
            mark = "**[被推翻]** " if (v != "符合" and not f.get("_survived", True)) else ""
            note = (f.get("note") or "").replace("|", "\\|").replace("\n", " ")
            if f.get("_votes"):
                note += " ／复核 %d/3 推翻" % f["_refuted"]
            L.append("| %s | %s%s | %s | %s |"
                     % ((f.get("clause") or "").replace("|", "\\|").replace("\n", " "),
                        mark, v,
                        (f.get("evidence") or "").replace("|", "\\|").replace("\n", " "),
                        note))
        L.append("")

    L.append("## 统计")
    L.append("")
    for k, v in stat.most_common():
        L.append("- %s：%d 条" % (k, v))
    L.append("")
    L.append("被对抗验证**推翻**的条目在表里标了 `**[被推翻]**`，保留但降级参考。")

    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("已重建 →", OUT)
    print("节数 %d，条目 %d，统计 %s" % (len([s for s in ORDER if audits.get(s)]), sum(stat.values()), dict(stat)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
