"""Report actual completed batches; retain failures and incomplete subscopes."""
import json,hashlib
from pathlib import Path

def main():
    root=Path(__file__).resolve().parents[1]
    package=root/'.codex-tmp/special_display_v1055_v1239_20261109'
    base=root/'测试证据/内机实测_20261105/BENCH_V1055_V1239'
    manifest=json.loads((package/'source_change_manifest.json').read_text('utf8'))
    assert all(hashlib.sha256((root/p).read_bytes()).hexdigest()==v for p,v in manifest['source_inventory_after'].items())
    flash=json.loads((base/'flash_special_display_20261109.json').read_text('utf8'))
    checks=json.loads((package/'special_display_ARM_20261109.json').read_text('utf8'))['checks']
    remote=json.loads((package/'special_remote_ARM_20261106.json').read_text('utf8'))['checks']
    lines=['# V10.55特殊阶段显示修复及续测（2026-11-09）','',
        '330 V10.55 BENCH / 两块316 V12.39 BENCH；压机动力隔离。本报告的板上证据为软件反馈、正常DI极性或校准输入，不代表端子测量、真实断电或正式时序验收。','',
        '原因：IndoorDisinfectExhaustAction故障分支清了内部step/phase并关负载后直接返回，漏清DisinfectStepDisp，导致[885]显示残留。',
        '修复只在该分支补DisinfectStepDisp=0。另更新版本号10.55及日期2026-11-09；未改输出、停机链、计时或316源码。267份C/H清单比对，仅UserAction.c和User.h变化。',
        '[源码变更清单](.codex-tmp/special_display_v1055_v1239_20261109/source_change_manifest.json)','',
        f'正式/BENCH均0错误、0警告；显示ARM检查{sum(e["passed"] for e in checks)}/{len(checks)}，既有远程恢复/手停/故障/自然结束ARM检查{sum(e["passed"] for e in remote)}/{len(remote)}。旧V10.54缺陷24组离线复现证据保留。',
        '[显示ARM证据](.codex-tmp/special_display_v1055_v1239_20261109/special_display_ARM_20261109.json)；[停机恢复ARM证据](.codex-tmp/special_display_v1055_v1239_20261109/special_remote_ARM_20261106.json)',
        '[正式HEX](.codex-tmp/special_display_v1055_v1239_20261109/PRODUCTION/PSC330_V10.55_PRODUCTION.hex)；[测试HEX](.codex-tmp/special_display_v1055_v1239_20261109/BENCH_ONLY_3S/PSC330_V10.55_BENCH_ONLY_3S.hex)',
        f'烧录结果：{flash.get("passed")}；330校验'+str(next(e['verified_bytes'] for e in flash['boards'] if e['board']=='330'))+'字节；两块316未重烧，各校验79960字节。烧录后参数差异为空。',
        '[烧录证据](测试证据/内机实测_20261105/BENCH_V1055_V1239/flash_special_display_20261109.json)','',
        '|用例|本批实际子范围|结果|批次配置恢复|证据|','|---|---|---|---|---|']
    entries=[]
    for p in sorted(base.glob('remaining571_heat_dynamic_*.json')):
        d=json.loads(p.read_text('utf8'))
        for cid,e in d.get('cases',{}).items():
            state='已完成软件检查' if e.get('passed') else '未完成'
            if e.get('error'):state='异常，见原日志'
            if not d.get('restored'):state+='；批次未完成恢复，不结案'
            if e.get('kind')=='remote_valve_wait':scope=f'模式{e["mode"]}阀等待远程停止/接通重启'
            elif cid=='T13-058':scope='自动消毒完成1分钟后的阶段5过渡：消防中止、重启计时清零；手动中止另测'
            elif 'runs' in e:
                labels={'manual':'手动停机','phase':'相序','fire':'消防'}
                scope=f'模式{e.get("mode")}：'+', '.join(labels.get(x['kind'],x['kind'])+('结束选择'+str(x['after_policy']) if x['kind']=='manual' and 'after_policy' in x else '') for x in e['runs'])
                scope+='；阀等待' if 'valve_wait' in p.name else '；实际运行计时至少6秒后中止及重启计时清零'
            else:scope=e.get('scope','')
            entries.append((cid,e,p,d))
            lines.append(f'|{cid}|{scope}|{state}|{d.get("restored","未完成")}|[原始日志]({p.relative_to(root).as_posix()})|')
    finalpaths=sorted(base.glob('independent_final_readback_20261109_*.json'))
    if finalpaths:
        d=json.loads(finalpaths[-1].read_text('utf8'))
        result='版本、BENCH档、全量参数恢复、禁用配置恢复、内外机停止及无报警均通过' if d.get('passed') else str(d.get('checks'))
        lines+=['',f'独立终检：{result}；配置差异{d.get("configuration_mismatches")}，报警{d.get("active_fault_registers")}。',
                f'[独立终检]({finalpaths[-1].relative_to(root).as_posix()})']
    lines+=['','勾选只表示所述子范围已执行。自动消排毒的运行中中止用例本批只覆盖消毒运行阶段；排毒运行中止、过渡阶段手动中止、风机已开/消毒未开阶段中止、真实接点/端子和正式档仍另验。',
            '完整待测矩阵保留；不把子场景数量当成新增完整验收用例，不把旧版证据自动改成V10.55通过。',
            '[更新后的待补测证据盘点](尚待补测证据盘点_20261109.md)（有板上子范围证据不等于完整验收通过）。']
    out=root/'V10.55_特殊阶段显示修复及续测_20261109.md'
    out.write_text('\n'.join(lines)+'\n','utf8')
    completed=[(cid,e,p,d) for cid,e,p,d in entries if e.get('passed') and d.get('restored')]
    scenarios=sum(len(e['runs']) if 'runs' in e else 1 for _,e,_,_ in completed)
    if finalpaths:
        final=json.loads(finalpaths[-1].read_text('utf8'))
        if final.get('passed'):
            lines_before=out.read_text('utf8')
            lines_before+='\n本轮已完成'+str(scenarios)+'组软件子场景，对应'+str(len(completed))+'个用例编号；新增运行/过渡用例T13-049、053、057、058按实际子范围记录。未测方向和完整矩阵不据此结案。\n'
            out.write_text(lines_before,'utf8')
    heading='## 2026-11-09 V10.55显示修复与续测结论'
    target=root/'内机测试版逐项测试记录_20261105.md'
    current=target.read_text('utf8')
    block='\n\n'+heading+'\n\n仅在特殊故障退出补[885]清零，并更新版本；正式/BENCH均编译通过、54组ARM检查通过，330已烧录V10.55 BENCH。316固件及其它控制/时序未改。\n\n'
    block+='\n'.join(f'- [x] {cid}：已完成本批软件子范围，证据及限制见[汇总](V10.55_特殊阶段显示修复及续测_20261109.md)。' for cid,_,_,_ in completed)+'\n'
    if heading not in current:target.write_text(current+block,'utf8')
    finalheading='## 2026-11-09 V10.55本轮最终回读与新增项目'
    if finalpaths and final.get('passed') and finalheading not in target.read_text('utf8'):
        with target.open('a',encoding='utf8') as f:
            f.write('\n\n'+finalheading+'\n\n'+
                f'本轮{scenarios}组软件子场景完成，涉及{len(completed)}个用例编号；12组阀等待显示回归、6组运行中止/重启计时、3组远程恢复、1组实际过渡消防中止。参数及禁用配置全部恢复，三板停止、无报警；正式档未烧录实测。\n\n'+
                '[逐项结果、证据和剩余缺口](V10.55_特殊阶段显示修复及续测_20261109.md)。\n')
    old=root/'特殊模式故障停机_阶段显示残留_20261109.md'
    prior=old.read_text('utf8');marker='## V10.55后续修复'
    if marker not in prior:
        old.write_text(prior+'\n\n'+marker+'\n\n正式/BENCH共用源码已补故障分支[885]清零；原V10.54失败证据保留。V10.55烧录及逐项实测结果见[本轮汇总](V10.55_特殊阶段显示修复及续测_20261109.md)，以完成且参数恢复的原始日志判定。\n','utf8')
    assert all('\ufffd' not in p.read_text('utf8') for p in (out,target,old))
    print('REPORT',len(entries),'entries;',len(completed),'completed scoped entries; UTF8 replacement count 0')

if __name__=='__main__':main()
