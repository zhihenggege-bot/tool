"""Consolidate finished heat evidence; do not operate the hardware."""
import os
os.environ.setdefault('PSC_BENCH_PACKAGE', '.codex-tmp/preheat_stage_display_v1053_v1239_20261106')
os.environ.setdefault('PSC_BENCH_INDOOR_VERSION', '10.53')
from run_indoor_bench_20261105 import R, D, RESULTS, dump, now
import json
import summarize_heat_pid_board_20261106 as pid_report
import summarize_heat_dynamic_20261106 as curves_report


def result(cid, status, actual, evidence, restored='', inputs=''):
    # The old CSV currently has an enterprise-encryption wrapper rather than
    # CSV text. Do not decode, truncate or replace it. Keep native JSON/Markdown
    # evidence updated independently and document the spreadsheet limitation.
    records = json.loads(RESULTS.read_text('utf8'))
    prior = records.get(cid, {})
    history = list(prior.get('history', []))
    if prior:
        history.append({k: v for k, v in prior.items() if k != 'history'})
    records[cid] = {'status': status, 'actual': actual,
                    'evidence': evidence.relative_to(R).as_posix(),
                    'restored': restored, 'inputs': inputs, 'at': now(), 'history': history}
    dump(RESULTS, records)
    print('CONSOLIDATED', cid, status, flush=True)


def latest(pattern):
    files = sorted(D.glob(pattern))
    assert files, pattern
    path = files[-1]
    data = json.loads(path.read_text('utf8'))
    assert data.get('restored') is True and not data.get('cleanup_error'), str(path)
    assert not data.get('error'), str(path)
    return path, data


def main():
    families = {f: latest(f'remaining571_heat_dynamic_pid_{f}_20261106_*.json')
                for f in ('main', 'reheat', 'auxiliary', 'preheat')}
    exact = {f: latest(f'remaining571_heat_dynamic_pid_exact_{f}_20261106_*.json')
             for f in families}
    parallel_path, parallel = latest('remaining571_heat_dynamic_parallel_20261106_*.json')
    assert all(d['all_pid_phases_passed'] for _, d in families.values())
    assert all(d['exact_bx']['passed'] and not d['exact_bx'].get('error') for _, d in exact.values())
    assert all(c['passed'] for c in parallel['parallel']['combinations'])
    assert parallel['parallel']['forbidden_stage_passed']
    pid_report.main()
    curves_report.main()
    # Preserve the whole original per-case history while attaching all three
    # thermal controller modes to the common heating PID requirements.
    data = json.loads(RESULTS.read_text('utf8'))
    for cid in [f'T11-{n:03d}' for n in range(17, 25)]:
        evidence = [{'family': f, 'pid': p.relative_to(R).as_posix(),
                     'exact_bx': exact[f][0].relative_to(R).as_posix()}
                    for f, (p, _) in families.items() if f != 'preheat']
        assert cid in data, cid
        data[cid]['heat_dynamic_family_evidence'] = evidence
    for cid in [f'T11-{n:03d}' for n in range(25, 33)]:
        assert cid in data, cid
        data[cid]['heat_dynamic_family_evidence'] = [{
            'family': 'preheat', 'pid': families['preheat'][0].relative_to(R).as_posix(),
            'exact_bx': exact['preheat'][0].relative_to(R).as_posix()}]
    dump(RESULTS, data)
    limits = ('本批正常停机且参数/校准恢复回读无差异；板上软件回读，'
              '真实端子电压/继电器接点及正式档尚待验收。'
              '各对象的逐拍阶段、精确边界、原失败历史见动态汇总及原始JSON。')
    summary = R / '热量PID及输出占用_动态复测汇总_20261106.md'
    for cid in [f'T11-{n:03d}' for n in range(17, 33)]:
        old = data[cid]
        label = '预热后温度' if int(cid[-3:]) >= 25 else '主热/独立再热/热泵辅热三种场景'
        prefix = f'{label}已完成当前BENCH板上逐拍动态复测；'
        previous_actual = old['actual']
        while previous_actual.startswith(prefix):
            previous_actual = previous_actual[len(prefix):]
        actual = prefix + previous_actual
        if cid in ('T11-021', 'T11-029'):
            actual = (f'{label}BX五档及精确扫描前需求100/101/200/201/400/401/500/501'
                      '均由正常PID动态经过，逐拍公式、增量和AO匹配；首轮未采齐历史保留。')
        result(cid, '部分通过', actual, summary, limits,
               '当前BENCH板上；合法NTC校准及正常参数；SWD只读，不写PID/需求/输出RAM')
    result('T06-023', '部分通过',
           '16组主热×预热方式均达到高需求并同时输出，4组独立再热隔离符合；'
           '20/20组无软件输出抢占，非法双独立分段组合被抑制。'
           '主热和再热按工作模式交接，未声称三套独立PID同时输出。',
           parallel_path, limits, '合法配置与NTC校准，软件AO/DO回读')
    preheat_path, preheat_curves = latest('remaining571_heat_dynamic_curves_20261106_100501.json')
    for cid, entry in preheat_curves['cases'].items():
        assert entry['passed'], cid
        result(cid, '部分通过',
               f'V10.53预热方式{entry["output_mode"]}升降需求0～1000，'
               f'{len(entry["rows"])}组稳定样本；上下行档位、回差与AO/DO软件回读符合；'
               '两个分段方式的需求显示问题已实板复测关闭，原失败历史保留。',
               preheat_path, limits, '正常环境温度及合法NTC校准')
    current = json.loads(RESULTS.read_text('utf8'))
    for cid in [f'T11-{n:03d}' for n in range(17, 33)]:
        current[cid]['heat_dynamic_family_evidence'] = data[cid]['heat_dynamic_family_evidence']
    dump(RESULTS, current)
    p = R / '内机测试版逐项测试记录_20261105.md'
    previous = R / '.codex-tmp/heat_master_before_consolidation_20261106.md'
    if not previous.exists():
        previous.write_bytes(p.read_bytes())
    lines = ['# 内机测试版逐项测试记录（2026-11-05起）', '',
             '勾选表示已执行所列范围；软件回读与ARM离线均不能替代端子或整机验收。'
             '原失败及每次复测历史保存在逐项证据JSON的history中。', '',
             '2026-11-06热量续测：旧总表CSV当前为加密封装，未覆盖或改写；'
             '本轮最新状态以本记录、动态汇总及case_results.json为准。', '',
             '|执行|用例|结论|本次实际结果|恢复/剩余缺口|证据|',
             '|---|---|---|---|---|---|']
    esc = lambda s: str(s).replace('|', '／').replace('\n', ' ')
    for cid, value in sorted(current.items()):
        lines.append(f'|[x]|{cid}|{esc(value["status"])}|{esc(value["actual"])}|'
                     f'{esc(value.get("restored", ""))}|[{cid}]({value["evidence"]})|')
    p.write_text('\n'.join(lines) + '\n', encoding='utf8')
    with p.open('a', encoding='utf8') as f:
        f.write('\n\n2026-11-06热量动态补测：四组PID共576个真实扫描，另四组精确BX边界各16次增量。'
                '16组主热×预热及4组独立再热隔离完成；所有批次参数已恢复。'
                '\n\n[逐拍阶段、精确边界与输出占用明细](热量PID及输出占用_动态复测汇总_20261106.md)；'
                '[16条升降曲线及回差观测](制热曲线_升降回差观测_20261106.md)。\n')
    print('Consolidated finished heat evidence; physical acceptance remains open.')


if __name__ == '__main__':
    main()
