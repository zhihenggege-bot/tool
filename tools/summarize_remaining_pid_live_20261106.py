"""Summarise actual live journals; encrypted historical CSV is never read."""
import json
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / '测试证据/内机实测_20261105/BENCH_V1053_V1239'


def main():
    records = json.loads((BASE / 'case_results.json').read_text('utf8'))
    ids = [f'T11-{n:03d}' for n in list(range(1, 17))+list(range(33, 57))+list(range(78, 85))]
    ids += [f'T09-{n:03d}' for n in range(12, 21)]
    ids += ['T11-094', 'T11-097', 'T11-101', 'T11-104', 'T11-105']
    ids += [f'T11-{n:03d}' for n in range(70,78)]
    rows = []
    for cid in ids:
        rec = records.get(cid, {})
        ep = rec.get('evidence', '')
        if '20261106' not in ep or not any(s in ep for s in ('remaining_pid_', 'initial_boundaries_', 'preheat_temperature_boundaries_', 'environment_heat_targets_', 'humidity_exact_deadband_', 'remaining_exact_', 'auto_humidity_continuity_', 'default_ambient_preheat_', 'auto_long_qhs_')):
            continue
        data = json.loads((ROOT / ep).read_text('utf8'))
        rows.append(dict(id=cid, status=rec['status'], actual=rec['actual'], evidence=ep,
                         restored=data.get('restored') is True, batch_error=data.get('error', '')))
    paths = set(r['evidence'] for r in rows)
    batches = []
    for ep in sorted(paths):
        d = json.loads((ROOT / ep).read_text('utf8'))
        phases = d.get('pid_phases', [])
        ticks = [t for p in phases for t in p['ticks']]
        exact = d.get('exact_bx', {}).get('ticks', [])
        batches.append(dict(evidence=ep, restored=d.get('restored'), ticks=len(ticks), exact_ticks=len(exact),
                            formula_mismatches=sum(not t['formula_matches'] for t in ticks),
                            output_mismatches=sum(not t['output_matches'] for t in ticks),
                            missed_scan_gaps=sum(len(p['missed_scan_gaps']) for p in phases),
                            error=d.get('error', '')))
    summary = dict(scope='2026-11-06本轮追加测试；不替代此前热量专项', cases=rows, batches=batches,
                   counts=dict(Counter(r['status'] for r in rows)),
                   limits='330 V10.53/316 V12.39 BENCH。合法NTC校准、AI1工程映射软件模拟；ST-Link只读PID状态。'
                   '软件输出不是端子实测。正式时序、物理输入和真实断电未据此验收。')
    (BASE / 'remaining_pid_live_summary_20261106.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), 'utf8')
    lines = ['# 压机、加湿PID及温度边界续测（2026-11-06）', '', summary['limits'], '',
             f'本轮有逐项记录{len(rows)}例，状态{summary["counts"]}。勾选表示实际执行的软件范围，验收缺口仍保留。', '',
             '|批次|真实扫描|精确BX增量|公式异常|软件输出异常|漏采|参数恢复|', '|---|---:|---:|---:|---:|---:|---|']
    for b in batches:
        lines.append(f'|[{Path(b["evidence"]).name}]({b["evidence"]})|{b["ticks"]}|{b["exact_ticks"]}|{b["formula_mismatches"]}|{b["output_mismatches"]}|{b["missed_scan_gaps"]}|{b["restored"]}|')
    lines += ['', '原始异常及纠正：首轮压机读取器跨大块RAM导致漏采，后改小块一致性读取得到完整重测；'
              '加湿首次误用越界幅差导致拒写，已恢复后改合法参数；工程映射取整造成0.1%RH偏差，精确死区和BX另有专项。'
              '这些属于测试方法问题，保留原始日志，不据此判固件缺陷。本轮未修改固件。', '',
              '|完成|用例|结论及范围|', '|---|---|---|']
    for r in rows:
        lines.append(f'|[x]|{r["id"]}|{r["status"]}；{r["actual"]} [证据]({r["evidence"]})；恢复={r["restored"]}|')
    lines += ['', '仍待补测：压机排序/禁用补位的剩余组合、自动冷热切换连续计时与否决边界、'
              'EEV与盘管保护板上动态矩阵、反复改参/启停和长期稳定性，以及原待补测清单中尚无板上证据的其它项目。'
              '环境制冷高温和预热默认−5℃端点需可达的输入；真实断电、端子、正式档时序需另验。', '',
              '[完整剩余证据盘点](尚待补测证据盘点_20261106.md)。']
    (ROOT / '压机加湿PID及边界_板上续测汇总_20261106.md').write_text('\n'.join(lines)+'\n', 'utf8')
    print(json.dumps(dict(cases=len(rows), counts=summary['counts'], batches=batches), ensure_ascii=False))


if __name__ == '__main__': main()
