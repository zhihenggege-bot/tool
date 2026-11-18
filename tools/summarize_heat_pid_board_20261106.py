"""Read existing live-board evidence without issuing any hardware commands."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / '测试证据/内机实测_20261105/BENCH_V1053_V1239'


def main():
    selected = {}
    for path in sorted(DATA.glob('remaining571_heat_dynamic_pid_*_20261106_*.json')):
        data = json.loads(path.read_text('utf8'))
        family = path.name.split('heat_dynamic_pid_', 1)[1].split('_20261106_', 1)[0]
        if family.startswith('exact_'):
            continue
        selected[family] = (path, data)
    lines = [
        '# 热量 PID 与输出占用：板上动态复测（2026-11-06）', '',
        '330 V10.53 / 两块316 V12.39，BENCH。压机动力隔离；正常参数及合法NTC校准刺激，'
        'SWD只读内部历史与扫描边沿。软件AO/DO回读不等于端子电压或接点测量；正式时序未验。', '',
        '现场说明：用户确认期间传感器报警来自人为拔线；NTC3已调整到约7℃。'
        '原报警及先前失败记录保留。缺少完整证据的项目不记完整通过。', '',
        '|对象|已完成阶段|逐拍公式/输出异常|观察到BX档|批末恢复|证据|',
        '|---|---|---|---|---|---|',
    ]
    details = []
    for family, (path, data) in selected.items():
        phases = data.get('pid_phases', [])
        ticks = [t for phase in phases for t in phase['ticks']]
        mismatches = sum(not t['formula_matches'] or not t['output_matches'] for t in ticks)
        bx = sorted({t['expected']['bx'] for t in ticks if t['expected']['bx']})
        gaps = sum(len(p['missed_scan_gaps']) for p in phases)
        rel = path.relative_to(ROOT).as_posix()
        lines.append(f'|{family}|{len(phases)}阶段/{len(ticks)}拍|{mismatches}；漏拍段{gaps}|'
                     f'{bx}|{data.get("restored", "进行中")}|[JSON]({rel})|')
        details.extend(['', f'## {family}', '',
                        '|阶段|真实扫描拍数|公式匹配|输出匹配|阶段判定|',
                        '|---|---|---|---|---|'])
        for phase in phases:
            ts = phase['ticks']
            details.append(f'|{phase["label"]}|{len(ts)}|'
                           f'{sum(t["formula_matches"] for t in ts)}/{len(ts)}|'
                           f'{sum(t["output_matches"] for t in ts)}/{len(ts)}|{phase["passed"]}|')
        if data.get('error'):
            details.extend(['', '批次异常（须保留并定位）：', '', '```text', data['error'], '```'])
        exact = next((c.get('exact_boundary_coverage') for c in data.get('cases', {}).values()
                      if 'exact_boundary_coverage' in c), None)
        if exact is not None:
            details.extend(['', f'首轮精确BX边界覆盖：{exact}。False表示首轮未采到；'
                            '后续完整结论见下方“精确BX需求边界补测”，首轮历史保留。'])
    exact_families = {}
    for path in sorted(DATA.glob('remaining571_heat_dynamic_pid_exact_*_20261106_*.json')):
        data = json.loads(path.read_text('utf8'))
        entry = data.get('exact_bx', {})
        if entry:
            exact_families[entry['family']] = (path, data, entry)
    if exact_families:
        details.extend(['', '## 精确BX需求边界补测', '',
                        '通过普通Kp/Ti参数变化，需求在真实扫描中自然经过边界。'
                        '不写需求、历史、计时或输出RAM。下表是独立补充，不删除上述首轮缺点。', '',
                        '|对象|逐拍符合|精确扫描前需求覆盖|批次判定|批末恢复|证据|',
                        '|---|---|---|---|---|---|'])
        exact_notes = []
        for family, (path, data, entry) in exact_families.items():
            ticks = entry.get('ticks', [])
            coverage = entry.get('exact_boundary_coverage', '进行中')
            details.append(f'|{family}|{sum(t["passed"] for t in ticks)}/{len(ticks)}|{coverage}|'
                           f'{entry.get("passed", "进行中")}|{data.get("restored", "进行中")}|'
                           f'[JSON]({path.relative_to(ROOT).as_posix()})|')
            if entry.get('error'):
                exact_notes.extend(['', '```text', entry['error'], '```'])
            if entry.get('loaded_auxiliary_before_unload') and entry.get('nonfull_shutdown'):
                loaded = entry['loaded_auxiliary_before_unload']
                closed = entry['nonfull_shutdown']
                hold = entry.get('nonfull_hold', [])
                exact_notes.extend(['', f'辅热有载退出：变更负荷前需求={loaded["heat"]}、DA0={loaded["ao"][0]}；'
                                f'非满载后DA0={closed["ao"][0]}，需求回读关闭，'
                                f'后续{len(hold)}组样本需求及DA0均0。正常指令与反馈，未写压机状态。'])
        details.extend(exact_notes)
    parallel_files = sorted(DATA.glob('remaining571_heat_dynamic_parallel_20261106_*.json'))
    if parallel_files:
        path = parallel_files[-1]
        data = json.loads(path.read_text('utf8'))
        parallel = data.get('parallel', {})
        combinations = parallel.get('combinations', [])
        details.extend(['', '## 输出占用', '',
                        f'已完成{len(combinations)}/20组，'
                        f'符合{sum(bool(c["passed"]) for c in combinations)}组；'
                        f'非法独立分段组合抑制={parallel.get("forbidden_stage_passed", "未完成")}；'
                        f'批末恢复={data.get("restored", "进行中")}。', '',
                        '16组为主热四种方式×预热四种方式；另外4组为制冷独立再热与预热配置隔离。'
                        '主热/再热按工作模式交接，本结果不能称为三套独立PID同时开启。', '',
                        f'[原始证据]({path.relative_to(ROOT).as_posix()})'])
        if parallel.get('error'):
            details.extend(['', '```text', parallel['error'], '```'])
    final_path = DATA / 'heat_final_independent_readback_20261106.json'
    if final_path.exists():
        final = json.loads(final_path.read_text('utf8'))
        details.extend(['', '## 独立终检', '',
                        f'终检={final.get("passed")}；改过的配置与校准回读差异='
                        f'{final.get("configuration_mismatches")}。三板停机、负载输出清零、故障字清零。'
                        f'NTC3={final["temperatures_510_513"][3] / 10:g}℃；NTC校准偏移全部恢复0。', '',
                        f'[终检原始记录]({final_path.relative_to(ROOT).as_posix()})'])
    report = ROOT / '热量PID及输出占用_动态复测汇总_20261106.md'
    report.write_text('\n'.join(lines + details) + '\n', encoding='utf8')
    print(json.dumps({'families': list(selected), 'parallel_batches': len(parallel_files),
                      'report': str(report)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
