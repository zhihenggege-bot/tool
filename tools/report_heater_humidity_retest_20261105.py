"""Publish only completed hardware journals; preserve original failure history."""
import json
from run_indoor_bench_20261105 import D, R, RESULTS, result, now


def latest(pattern):
    return max(D.glob(pattern), key=lambda p: p.stat().st_mtime)


def main():
    batch_path = latest('heater_humidity_interlock_*.json')
    recovery_path = latest('heater_humidity_recovery_*.json')
    audit_path = latest('independent_audit_*.json')
    batch = json.loads(batch_path.read_text('utf-8'))
    recovery = json.loads(recovery_path.read_text('utf-8'))
    audit = json.loads(audit_path.read_text('utf-8'))
    assert batch.get('restored') and not batch.get('cleanup_error')
    assert recovery.get('passed') and recovery.get('restored') and not recovery.get('error')
    assert len(recovery['cases']) == 4 and all(v.get('passed') for v in recovery['cases'].values())
    assert not audit.get('audit_error') and not audit['after_reset_differences_from_preflight']
    assert audit['post_reset_health_duration_s'] >= 30
    assert set(batch['cases']) == {f'T03-{i:03d}' for i in range(1, 9)}
    assert all(v.get('software_passed') for v in batch['cases'].values())
    assert batch['finished'] <= audit['at'] and recovery['finished'] <= audit['at']
    rows = []
    count_restore = latest('runtime_count_restore_*.json')
    count_data = json.loads(count_restore.read_text('utf-8'))
    assert count_data['restored'] and count_data['before_119'] == 1 and count_data['after_119'] == 0
    for cid, v in sorted(batch['cases'].items()):
        assert v['before']['mode_1_236'] == [v['mode'], v['mode']], (cid, 'mode feedback')
        x06 = v['stimulus'].startswith('X06')
        samples = v['after_samples']
        other_heat_ok = all(s['ao'][0] > 0 for s in samples) if not x06 else None
        all_fans_ok = all(s['do'][3] == 1 and s['do'][6] == 1 and s['do'][8] == 1
                          and s['ao'][4] == 500 and s['ao'][7] == 500 for s in samples)
        assert all_fans_ok and (x06 or other_heat_ok), (cid, 'unaffected load check')
        active_text = '主热由开转关' if x06 else '主热保持；预热原为0，未覆盖预热由开转关'
        result(cid, '部分通过',
               f"V10.49 BENCH：{'制冷' if v['mode'] == 0 else '制热'}、{'X06' if x06 else 'X07'}、加湿{'AO' if v['humidifier_type'] == 1 else 'DO'}；"
               f"{v['latched_elapsed_s']:.3f}s锁存，加湿AO/DO均归0并连续5秒保持；送/回/排风DO及送/回风AO保持；{active_text}",
               batch_path,
               '本批已停机恢复，独立复位30秒终检通过；物理接点/端子、正式版实板未测。'
               + ('该输入的制冷恢复矩阵另见' + str(recovery_path.relative_to(R)).replace('\\', '/') + '。')
               + ('' if x06 else 'X07的预热负载先开后关仍待低温条件实测。'), v['stimulus'])
        rows.append(f"|[x]|{cid}|{'制冷' if v['mode']==0 else '制热'}|{'X06' if x06 else 'X07'}|{'AO' if v['humidifier_type']==1 else 'DO'}|{v['latched_elapsed_s']:.3f}s|软件联锁符合|{active_text}|")
    record = R / '加湿联锁复测结果_330V10.49_20261105.md'
    ref = lambda p: str(p.relative_to(R)).replace('\\', '/')
    recovery_rows = '\n'.join(f'|[x]|{cid}|锁存保持符合|排除并复位后输出恢复|'
                              for cid in sorted(recovery['cases']))
    record.write_text(f'''# 加湿联锁复测结果（330 V10.49 BENCH）

完成时间：{now()}。依据内机§3.11.9：电热故障持续3秒，电热停止、加湿全关，排除并复位后恢复，不影响其它设备。

用户恢复信号后，AI0～4底层状态连续12秒有效；AI1原始约571～575。此前9999前置中断保留。温度用NTC0合法偏移至22℃，湿度使用正常量程映射至29.9～30.1%，无RAM输出/保护旁路写入；DI以正常极性参数翻转，非物理接点注入。模式请求与反馈逐例相符；[128]=2，制热例采用非热泵AO制热，本批不代替热泵满载/辅热门禁验证。

|执行|用例|模式|故障|加湿|观察到锁存延时|结果|边界|
|---|---|---|---|---|---|---|---|
''' + '\n'.join(rows) + f'''

锁存延时从参数写入开始按软件采样观察，包含扫描及串口取样误差，不能作为精密3.000秒边界测量。

补测四例制冷恢复：X06/X07×AO/DO，均确认“故障仍在时复位不解除；去掉输入但不复位仍锁存；排除并复位后加湿恢复”。X06主热在复位后恢复，X07主热全程保持；送、回、排风保持运行。

|执行|恢复用例|故障仍在/未复位|排除并复位|
|---|---|---|---|
{recovery_rows}

八例均完成加湿切断的软件输出验证；X07四例预热没有先运行，不能把预热原为0当成停机验证。完整用例仍标部分通过：预热带载切断、物理接点/端子及正式版实板另测；真实断电、整套正式秒数不在本批证明范围。

新增待修：首次终检发现[119] CompNumCur仍为1，而两外机压机状态均0、所有负载输出0。源码SysNergryAction_PID/环境控制的停机返回分支没有刷新该缓存；该字位于保存区并被保存。通过普通Modbus恢复119=0后才做最终复位核对，不能把这次手动恢复描述成固件已自动修正。证据：[首次终检](测试证据/内机实测_20261105/BENCH_V1049_V1239/independent_audit_135910.json)、[显式恢复记录]({ref(count_restore)})。本轮没有修改这部分固件。

已停机恢复全部本批参数（含上述119显式恢复）；独立ST-Link复位后参数0～499、新AI1229～1288及1298/1299与烧前一致，持续30秒三板通信正常、内机故障0、负载输出0。

证据：[八例原始时序]({ref(batch_path)})、[四例锁存/恢复]({ref(recovery_path)})、[独立恢复终检]({ref(audit_path)})。旧版失败及环境中断仍在case_results.json的history中。
''', encoding='utf-8')
    data = json.loads(RESULTS.read_text('utf-8'))
    counts = {s: sum(v['status'] == s for v in data.values()) for s in sorted({v['status'] for v in data.values()})}
    stage = R / '内机测试版阶段结论_20261105.md'
    text = stage.read_text('utf-8')
    lines = []
    for line in text.splitlines():
        if line.startswith('<!-- HISTORY_V1048_START -->'):
            break
        if line.startswith('更新时间：'):
            line = f'更新时间：{now()}。当前复测结果如下；旧版历史保留在文末。'
        elif line.startswith('|制冷电热故障→加湿AO/DO关闭|'):
            line = '|电热故障→加湿AO/DO关闭|X06/X07×冷/热×AO/DO八例板上软件切断符合；四例制冷锁存/复位恢复符合|X07预热未先开，预热带载切断仍待测；物理接点/端子、正式版实板待测|'
        elif line.startswith('|AI1前置异常|'):
            line = '|AI1前置异常|用户恢复信号后，连续12秒底层状态有效，八例中未再因AI1故障中断|历史9999及错误地址定位已保留，未靠屏蔽故障通过|'
        elif line.startswith('|停止、恢复、独立复位终检|'):
            line = '|停止、恢复、独立复位终检|手动恢复119缓存后，普通参数、新AI配置及档位与烧前一致；复位后30秒通信正常、负载输出0|新发现119停机缓存未刷新，尚未修改固件；真实断电未测|'
        elif line.startswith('目前逐项表共'):
            line = f'目前逐项表共{len(data)}条：' + '、'.join(f'{s}{n}' for s,n in counts.items()) + '。跨版本证据逐项区分，部分通过不等于完整验收。'
        elif line.startswith('接下来先恢复AI1'):
            line = '本轮八例软件联锁和四例制冷恢复已完成，后续重点补预热实际输出切断、物理端子/接点、真实断电及正式版实板时序。'
        lines.append(line)
    historical = text[text.index('<!-- HISTORY_V1048_START -->'):]
    stage.write_text('\n'.join(lines).rstrip() + f'\n\n**新增待修：[119]当前运行压机数在停机后残留1。实际压机/负载已关闭；已保留首次终检，正常协议显式恢复0后再复位检查，本轮未修固件。**\n\n[本轮八例及恢复明细]({record.name})。最新独立终检见[证据]({ref(audit_path)})。\n\n' + historical, encoding='utf-8')
    log = R / '调试记录_电工房直膨机组_20261015.md'
    with log.open('a', encoding='utf-8') as f:
        f.write(f'\n\n## 2026-11-05 AI1恢复后加湿联锁八例及锁存恢复复测\n\n'
                f'用户恢复AI输入后，330 V10.49 BENCH完成X06/X07×冷/热×加湿AO/DO八例，均加湿全关、风机保持；X06主热由开转关，X07主热保持。另四例制冷恢复确认故障仍在复位不解锁，排除未复位仍锁存，排除并复位恢复输出。八例按软件结果符合记录，物理接点/端子未测；X07预热未先开，不证明预热带载切断。原失败及前置中断留存。\n\n'
                f'首次终检发现119运行压机数缓存残留1，而实际压机状态及负载已0；保留证据后用正常协议显式恢复0，固件停机缓存未刷新尚待修，不能称自动恢复。此后独立复位30秒终检通过。详见《{record.name}》；原始证据{ref(batch_path)}、{ref(recovery_path)}、{ref(audit_path)}、{ref(count_restore)}。时间{now()}。\n')
    result('T17-001', '通过',
           '本批参数/校准已恢复且独立ST-Link复位回读一致；其中119运行压机数缓存曾残留1，已显式用普通Modbus恢复0后再复位，并非固件自动刷新修复',
           audit_path, '保存区0～499、新AI1229～1288、档位1298/1299与烧前一致；119停机缓存问题单列待修；真实掉电未测')
    for p in (record, stage, log, R/'内机测试版逐项测试记录_20261105.md'):
        assert '\ufffd' not in p.read_text('utf-8'), p
    print('REPORT COMPLETE', record, counts, flush=True)


if __name__ == '__main__':
    main()
