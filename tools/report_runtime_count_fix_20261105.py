"""Publish evidence after all targeted V10.50 follow-up and final audit pass."""
import json
import hashlib
from pathlib import Path
import run_indoor_bench_20261105 as b


def load(p):return json.loads(p.read_text('utf-8'))


def latest(pattern):
    return max(b.D.glob(pattern),key=lambda p:p.stat().st_mtime)


def link(p,label):return f'[{label}]({str(p.relative_to(b.R)).replace(chr(92),"/")})'


def main():
    package=b.I.parent
    assert b.EXPECTED[2]==50
    source=load(package/'change_manifest.json')
    changed=[a for a,h in source['source_inventory_before'].items()
             if hashlib.sha256((b.R/a).read_bytes()).hexdigest()!=h]
    assert set(changed)==set(source['changed_common_sources'])
    runs=[(p,load(p)) for p in sorted(b.D.glob('runtime_count_[0-9]*.json'))]
    cases={}
    for p,run in runs:
        assert run.get('restored'),p
        assert not any(w['address']==119 for w in run['writes']),p
        for key,case in run['cases'].items():
            if case.get('passed'):cases[key]=(p,case)
    assert all(k in cases for k in ['normal_0','normal_1','bypass_2','bypass_3','bypass_4','bypass_5'])
    ap=latest('runtime_count_autoswitch_*.json');auto=load(ap)
    assert auto['passed'] and auto['restored'] and all(c['passed'] for c in auto['cases'].values())
    hp=latest('heater_humidity_recovery_*.json');heat=load(hp)
    assert heat['passed'] and heat['restored'] and len(heat['cases'])==4
    auditp=latest('independent_audit_*.json');audit=load(auditp)
    assert audit['reset_requested'] and not audit.get('audit_error')
    assert not audit['after_reset_differences_from_preflight']
    assert not audit['differences_from_preflight'] and not audit['parameter_shadow_mismatches']
    assert not audit['ai_shadow_mismatches'] and audit['ai_dirty']==0
    assert audit['config']['119']==audit['after_reset_config']['119']==0
    mode_restore_p=latest('mode_restore_*.json')
    mode_restore=load(mode_restore_p)
    assert mode_restore['restored'] and not mode_restore['after_differences']
    arm=load(package/'runtime_count_ARM.json');fan=load(package/'fan_enable_test_result.json')
    persistence=load(package/'ARM_regression.json')
    assert arm['passed'] and fan['passed'] and all(c['passed'] for c in persistence['checks'])
    assert source['arm_3133']['passed']
    total=len(arm['checks'])+len(fan['checks'])+len(persistence['checks'])+259
    for humidity,cid in [(0,'T11-090'),(1,'T11-091')]:
        case=auto['cases'][str(humidity)]
        observed=sorted({s['count_119'] for s in case['hold_samples']})
        b.result(cid,'部分通过',
                 f"V10.50 BENCH：[119]观察{observed}台、再热>QHB，QHS设60秒，计数达到阈值触发切换（使能写入后采样观察{case['transition_start_elapsed_s']:.2f}s），旧模式正常停完后非热泵制热启动完成",
                 ap,'本次只补受[119]影响的路径；实际1/2台门槛另有当前双档ARM证据；59s撤销条件、端子及正式版实板另测；本批参数已恢复')
    path=b.R/'运行数量反馈修复与复测_330V10.50_20261105.md'
    qhs_times='/'.join(f"{auto['cases'][str(h)]['transition_start_elapsed_s']:.3f}" for h in (0,1))
    lines=['# 运行数量反馈修复与复测（330 V10.50）','',
           f'完成时间：{b.now()}。当前板上330 V10.50 BENCH、两316 V12.39 BENCH。压机动力按用户确认隔离；本报告板上结论为软件状态/输出，不等同物理端子。','',
           '根因：[119] CompNumCur原来只在部分PID/环温加减载分支末尾刷新，正常停机、通风、特殊模式等提前返回时保留旧值。V10.49首次终检残留1及其手动恢复证据原样保留，本轮不用手动写119。','',
           '本次只改330三处文件：NergryAdjust.c新增调用原计数函数的反馈刷新入口；UserAction.c在自动冷热切换前调用一次；User.h加声明及版本号10.50。原计数对运行状态2/3/4、通信异常、配置使用的过滤不变；PID公式、目标台数算法、继电器/AO路由和启停时序均未改。源文件修改前后的SHA256见发布清单，330/316其余C/H与本轮快照一致。','',
           '受影响的关联行为已说明并复测：自动切换使用119判断“运行数量≤1”，现在先读取本次刷新后的反馈；未修改QHB/QHS、模式切换或停机逻辑。','',
           '|检查|结果|证据|','|---|---|---|',
           f'|[x] 正式/BENCH两档编译|均0错误0警告，316沿用原V12.39产物|{link(package,"双档产物、清单及日志")}|',
           f'|[x] 330烧录/316只读核对|330全部有效HEX字节一致；两316未重烧，原HEX逐字节一致|{link(b.D/"flash.json","烧录及身份记录")}|',
           f'|[x] 当前ARM回归|{total}项：数量/提前返回/自动切换{len(arm["checks"])}、启停259、风机162、保存/加湿联锁130；两档参与，部分场景隔离相邻任务|{link(package,"ARM结果与AXF哈希")}|']
    for key,name in [('normal_0','制冷'),('normal_1','热泵制热')]:
        p,case=cases[key]
        seq=[]
        for s in case['shutdown']:
            v=s['count_119']
            if not seq or seq[-1]!=v:seq.append(v)
        lines.append(f'|[x] {name}请求/运行反馈及正常关机|已先建立至少2台压机运行软件反馈；关机119观察序列'+ '→'.join(map(str,seq))+f'；停稳持续6s为0，无119写入|{link(p,"原始连续采样")}|')
    lines += [f'|[x] 通风及消毒/排毒/自动消排毒入口|通风启动及停止为0；特殊模式进入阀等待阶段后中止，119持续0；未等待150s完成整个特殊模式|{link(cases["bypass_5"][0],"模式入口/中止记录")}|',
              f'|[x] 自动冷热切换关联复测|无控湿/有控湿两例，实际≤1台、再热>QHB，QHS设60秒，计数触发后正常转非热泵制热；实际1/2台门槛另有双档ARM检查|{link(ap,"自动切换连续记录")}|',
              f'|[x] 加湿联锁回归|制冷X06/X07×加湿AO/DO四例：故障仍在复位不解锁、去掉输入未复位仍锁存、排除并复位恢复；风机保持|{link(hp,"四例恢复记录")}|',
              f'|[x] 恢复及独立复位终检|所有原参数/AI配置/档位恢复，无119手工写入；ST-Link复位后再次一致，持续30s三板通信正常、内机故障0、负载DO/AO为0|{link(auditp,"独立终检")}|','',
              '测试脚本问题保留：首轮制热完整关机使用100s超时，未覆盖现有30s/室外风机收尾/60s等待总长度；当时压机和119已为0，清理流程正常停机。只将脚本容限延长至240s并重跑通过，未缩短固件等待。烧录完成后的首个串口读遇启动无应答，后续补核版本及档位成功，未重复烧录。','',
              f'首次最终审计另外发现测试脚本漏恢复自动切换生成的1/236/326模式状态，其余参数一致；未进行该次复位。已补齐测试脚本清理名单，并仅通过正常236模式请求恢复原模式，让固件同步1/326；此后全参数比较及独立复位终检通过。119从未手工恢复。{link(mode_restore_p,"模式恢复原始证据")}；原失败审计保留在证据目录。','',
              f'QHS时间口径：两例从使能写入到采样观察切换分别约{qhs_times}秒，现有uc1s累计方式受首个1秒节拍相位及串口采样影响。本轮确认计数门槛及完整切换流程，不据此证明精确60.000秒持续时间；未改这段计时逻辑，精确时序仍待独立测量。','',
              '边界：正式版尚未上板；真实断电、物理端子、特殊模式完整150s过程、本轮未覆盖的保护/PID矩阵仍保留待测。X07恢复用例预热本身未先运行，不据此宣称预热带载切断已验证。[340]/[345]按用户要求保留。','',
              f'原始首轮记录：{link(runs[0][0],"100s脚本中断及正常清理") }。原V10.49发现与手动恢复见[历史报告](加湿联锁复测结果_330V10.49_20261105.md)。']
    path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    phase=b.R/'内机测试版阶段结论_20261105.md'
    old=phase.read_text('utf-8')
    assert '<!-- HISTORY_V1049_START -->' not in old
    prefix=f'''# 内机测试版阶段结论（2026-11-05）

更新时间：{b.now()}。330现为V10.50 BENCH，两316仍V12.39 BENCH。

本轮已修复[119]停机残留：制冷、热泵制热正常关机实际运行数回到0，未手动清119；通风及特殊模式入口/中止检查符合。受影响的自动冷热切换两条再热路径已做板上QHS60s回归；数量1/2台门槛另有双档ARM验证。加湿故障四例锁存/恢复板上回归符合。{total}项当前ARM回归通过，正式/BENCH编译均0错误0警告；316源代码及固件未改。

参数、AI配置及档位全部恢复；独立ST-Link复位后再次一致，连续30秒健康终检通过。正式版尚未烧录实测，真实断电及端子测量未做。

{link(path,'本轮修复范围、逐项勾选、原始异常及证据')}。旧版缺陷和原始失败保留在下方历史，不作为当前仍未修复的结论。

<!-- HISTORY_V1049_START -->
## V10.49及此前阶段记录（保留）

'''
    phase.write_text(prefix+old+'\n<!-- HISTORY_V1049_END -->\n',encoding='utf-8')
    log=b.R/'调试记录_电工房直膨机组_20261015.md'
    with log.open('a',encoding='utf-8') as f:
        f.write(f'\n\n## 2026-11-05 330 V10.50：119运行数量反馈修复与关联复测\n\n仅330公共反馈入口、调用和声明/版本改动；未改PID、IO、时序或316。{total}项当前ARM检查通过；板上冷热正常关机119自动回0，自动切换两路径与加湿四例恢复回归符合；参数恢复及独立复位30s终检通过。首轮脚本100s超时和启动读无应答均留证。详见{link(path,"修复及复测明细")}。\n')
    historical=b.R/'加湿联锁复测结果_330V10.49_20261105.md'
    with historical.open('a',encoding='utf-8') as f:
        f.write(f'\n后续更新（{b.now()}）：上文“119待修/本轮未改”指V10.49批次；现已完成V10.50公共反馈修复及专项复测，无119手动写入。见{link(path,"后续修复与复测")}。\n')
    b.REPORT.write_text(b.REPORT.read_text('utf-8')+f'\n本轮119修复与关联回归：{link(path,"V10.50逐项结果")}；原V10.49中断及手动恢复作为历史保留。\n',encoding='utf-8')
    for p in [path,phase,log,historical,b.REPORT]:
        assert '\ufffd' not in p.read_text('utf-8'),p
    summary={'finished':b.now(),'firmware_sources_changed':changed,'arm_checks':total,
             'normal_count_cases':{k:str(p.relative_to(b.R)) for k,(p,c) in cases.items()},
             'auto_switch':str(ap.relative_to(b.R)),'humidity_recovery':str(hp.relative_to(b.R)),
             'audit':str(auditp.relative_to(b.R)),'report':path.name,'no_manual_119_writes':True,
             'production_built_not_board_tested':True}
    b.dump(b.D/'runtime_count_followup_summary.json',summary)
    manifest_path=b.I/'manifest.json'
    manifest=load(manifest_path)
    manifest.update(flashed=True,hardware_tested=True,
                    programmed_in_this_batch=['330'],retained_unchanged_boards=['316_WJ1','316_WJ2'],
                    hardware_tested_scope='Targeted count feedback, auto-switch and heater/humidity recovery only; not full acceptance',
                    formal_timing_hardware_validated=False,
                    evidence_summary=str((b.D/'runtime_count_followup_summary.json').relative_to(b.R)))
    b.dump(manifest_path,manifest)
    print('REPORT',path.name,'ARM',total,flush=True)


if __name__=='__main__':main()
