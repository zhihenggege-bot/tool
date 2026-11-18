"""Summarize actual board injection journals without relabeling physical gaps."""
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parents[1]
D = R / '测试证据/内机实测_20261105/BENCH_V1051_V1239'
P = R / '.codex-tmp/ai3_hold_reason_v1051_v1239_20261105'


def main():
    from run_indoor_bench_20261105 import result
    good = {}
    sources = []
    errors = []
    for path in sorted(D.glob('remaining571_ai3_latch_injection_*.json')):
        x = json.loads(path.read_text('utf-8'))
        assert x.get('restored') is True, (path, 'not restored')
        assert x.get('sensor_latch_after_reset') == 0
        sources.append(path)
        if x.get('error'):
            errors.append(path)
        for cid, case in x['cases'].items():
            if case.get('passed'):
                good[cid] = (path, case)
    for cid in ('T03-027', 'T03-029', 'T03-031', 'T03-033', 'T03-035', 'T03-037',
                'AI3-outdoor-0', 'AI3-outdoor-1'):
        assert cid in good, ('Missing completed injection case', cid)
    manifest = json.loads((P / 'change_manifest.json').read_text('utf-8'))
    assert all(hashlib.sha256((R / p).read_bytes()).hexdigest() == digest
               for p, digest in manifest['changed_common_sources'].items())
    audits = sorted(D.glob('independent_audit_*.json'))
    audit = audits[-1]
    a = json.loads(audit.read_text('utf-8'))
    assert not a['differences_from_preflight'] and not a['after_reset_differences_from_preflight']
    assert a['post_reset_health_duration_s'] >= 30
    text = ['# AI3故障手动模拟复测：330 V10.51 BENCH，2026-11-05', '',
        '按用户要求在真实三板台架上模拟AI3故障。只通过对应V10.51 AXF符号写入1字节 `SensorErr[3]=1`，其余报警、负载输出和外机控制由固件原主循环执行。未改固件源码，未写目标/实际台数、需求或DO/AO。', '',
        '**本轮8个模拟场景均通过所列软件联锁判据。** 这是板上故障锁存输入模拟，跳过ADC异常识别及检测延时，不等同于物理拔线或端子测量；正式时序未测。原开路/短路验收用例仍标“部分通过”，未把两种电气故障都勾为完成。', '',
        '| 用例 | 模式/反馈 | 故障前负载软件输出 | 故障后及恢复 | 证据 |',
        '|---|---|---|---|---|']
    names = {0: '制冷', 1: '制热', 2: '通风'}
    for cid in ('T03-027', 'T03-029', 'T03-031', 'T03-033', 'T03-035', 'T03-037'):
        path, c = good[cid]
        mode = c['mode']
        before = c['before']
        basis = '风压' if c['basis'] else '风速'
        load = '无冷热/加湿输出' if mode == 2 else (
            f"主热/再热AO={before['ao'][0]}，预热AO={before['ao'][1]}，" +
            (f"加湿AO={before['ao'][2]}" if c['humidifier'] == 1 else f"加湿DO={before['do'][11]}"))
        state = '热/预热/加湿软件输出全0，送/回/排风机及四个开关风阀保持，送风回退600；4秒锁存，524复位恢复'
        if mode == 2:
            state += '；带故障正常停机再开机通过'
        text.append(f'| {cid} | {names[mode]}/{basis} | {load} | {state} | [{path.name}]({path.relative_to(R).as_posix()}) |')
        result(cid, '部分通过', f'AI3锁存输入模拟：{names[mode]}/{basis}；故障前{load}；{state}。', path,
            '参数与AI3锁存已恢复并独立复位回读；物理开路/短路、ADC异常检测及延时、端子和正式档未测。',
            'ST-Link按当前AXF符号注入SensorErr[3]=1；只写该故障输入字节，不写需求、请求、目标/实际台数或DO/AO。')
    text += ['', '| 外机专项 | 故障前实际运行反馈数 | 故障后反馈数 | 复位后反馈数 | 证据 |',
             '|---|---|---|---|---|']
    for mode in (0, 1):
        path, c = good['AI3-outdoor-' + str(mode)]
        assert c['before']['count_119'] > 0 and c['after']['count_119'] == 0 and c['recovered']['count_119'] > 0
        text.append(f"| {names[mode]} | {c['before']['count_119']} | 0，故障保持期间持续0、风机风阀保持 | {c['recovered']['count_119']} | [{path.name}]({path.relative_to(R).as_posix()}) |")
    text += ['', '外机“运行反馈”来自316回传的压机状态；压机动力已断开，因此是控制板、继电器或模拟负载验证，未证明制冷剂系统运行。', '',
             '注入到软件动作的观察值包含主机采样延迟，不拿它替代原始采样到报警的规格时间。故障恢复使用公开复位参数[524]，没有通过RAM清故障或直接开负载。', '',
             f'参数已恢复，AI3锁存已清除；[独立终检]({audit.relative_to(R).as_posix()})确认参数0～499、新AI配置1229～1288及档位一致，ST-Link复位后再次一致，连续{a["post_reset_health_duration_s"]:.1f}秒版本/通信正常、负载软件DO/AO全0。真实断电另测。', '',
             '原始失败历史保留：第一次通风带故障重启被通用“无故障开机”脚本拦住，已改成允许预期AI3报警的等待并重测通过；外机专项前两次配置脚本向[422]写1，该参数允许5～999，写入无应答。已用合法值5完成重测。均属于脚本问题，每次参数已恢复，固件未修改。']
    report = R / 'AI3故障模拟实测结果_330V10.51_20261105.md'
    report.write_text('\n'.join(text) + '\n', 'utf-8')
    assert '\ufffd' not in report.read_text('utf-8')
    note = '\n\n<!-- AI3_INJECTION_V1051_20261105 -->\n\nAI3已按用户授权完成板上故障锁存输入模拟：风压/风速×制冷/制热/通风6场景，以及冷热外机已有运行反馈后停机/复位恢复2场景，所列软件联锁判据通过。只注入SensorErr[3]，不写输出或台数。ADC检测延时、物理拔线、端子和正式档未覆盖。[证据与恢复终检](AI3故障模拟实测结果_330V10.51_20261105.md)。\n'
    for name in ('内机测试版阶段结论_20261105.md', '内机测试版逐项测试记录_20261105.md',
                 'AI3联锁_Z零目标_原因码修复与复测_330V10.51_20261105.md',
                 '调试记录_电工房直膨机组_20261015.md'):
        path = R / name
        raw = path.read_bytes()
        raw.decode('utf-8-sig')
        if b'AI3_INJECTION_V1051_20261105' not in raw:
            path.write_bytes(raw + note.encode('utf-8'))
    print(report, '8 simulated scenarios; restored and independently audited')


if __name__ == '__main__':
    main()
