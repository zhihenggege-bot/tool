"""Aggregate actual evidence without regenerating or resetting test cases."""
import csv, json
from collections import Counter
from run_indoor_bench_20261105 import R,D,CASECSV,RESULTS,REPORT,now,replace_retry


def readcsv(path):
    with path.open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))


def writecsv(path,rows):
    tmp=path.with_suffix(path.suffix+'.tmp')
    with tmp.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
    replace_retry(tmp,path)


def main():
    cases=readcsv(CASECSV)
    evidence=json.loads(RESULTS.read_text('utf-8'))
    counts=Counter(v['status'] for v in evidence.values())
    assert len(cases)==672 and len({r['用例编号'] for r in cases})==672
    for r in cases:
        if r['用例编号'] in evidence:
            assert r['执行结论']==evidence[r['用例编号']]['status']
    summary=R/'明日实机验收记录表_内机3.1-3.11_20261105.csv'
    groups=readcsv(summary)
    for r in groups:
        subset=[v for v in cases if v['大组']==r['用例']]
        actual=[evidence[v['用例编号']] for v in subset if v['用例编号'] in evidence]
        c=Counter(v['status'] for v in actual)
        r['执行结果']=f"已记录{len(actual)}/{len(subset)}；通过{c['通过']}、部分通过{c['部分通过']}、失败{c['失败']}；其余未执行"
        r['实测数据']='见逐项实际结果及原始样本；部分通过仍须补物理/正式证据' if actual else ''
        r['证据路径']='内机测试版逐项测试记录_20261105.md' if actual else ''
        r['恢复结果']='本批全配置恢复及复位读回见T17-001；保留BENCH' if actual else ''
    writecsv(summary,groups)
    coverage=R/'内机明日待测复测覆盖对照_20261105.csv'
    mapped=readcsv(coverage)
    for r in mapped:
        ids=r['待测复测用例'].split(';')
        actual=[evidence[cid] for cid in ids if cid in evidence]
        c=Counter(v['status'] for v in actual)
        r['验收结果']=(f"关联用例已记录{len(actual)}/{len(ids)}，失败{c['失败']}、部分通过{c['部分通过']}、通过{c['通过']}；条款未完整验收"
                    if actual else '尚未执行本轮实测')
    writecsv(coverage,mapped)
    old=sorted(D.glob('scalar_parameters_*.json'))[-1]
    scalars=json.loads(old.read_text('utf-8'))
    rapid=[cid for cid,v in scalars['cases'].items() if any('默认值复位后不符' in s for s in v.get('failures',[]))]
    audits=[(p,json.loads(p.read_text('utf-8'))) for p in sorted(D.glob('independent_audit_*.json'))]
    audit,checked=[(p,v) for p,v in audits if v.get('post_reset_health_duration_s',0)>=30 and not v.get('audit_error')][-1]
    assert checked.get('post_reset_health_duration_s',0)>=30 and not checked.get('audit_error'), 'Final independent check required'
    assert checked.get('after_reset_differences_from_preflight')=={}
    rel=lambda p:str(p.relative_to(R)).replace('\\','/')
    lines=['# 内机测试版阶段结论（2026-11-05）','',f'更新时间：{now()}。本文件只汇总本轮当前板上证据，不代替672项完整验收。',
      '',f"三板已烧录并逐字节校验：330 V10.48 BENCH、316外机1/2均V12.38 BENCH。[烧录、UID、HEX哈希及备份]({rel(D/'flash.json')})。",
      '',f"已记录{len(evidence)}/672例：通过{counts['通过']}、部分通过{counts['部分通过']}、失败{counts['失败']}；剩余{672-len(evidence)}例未在本批执行。勾选代表执行过，部分通过不是完整合格。",
      '', '|本批项目|实际结论|','|---|---|',
      '|三板版本、烧录及通信|逐字节读回；初始120.2秒334组读取无串口异常；终检见T17-003|',
      '|送／回风手动AO|通风、制冷、制热各0/5/10V，18例软件AO、DO许可、20秒保持及正常关闭符合；物理端子未测|',
      '|新风／送风／回风／排风阀|12例无／DO／AO选择及设定点、正常关闭软件检查完成；排风AO=新风AO=750的跟随点已读到；未证明实物行程和端子|',
      '|标量参数|53例默认/范围及协议边界检查；稳定单值写入后复位回读均正确；2处范围不符；连续边界改参后的保存异常另列|',
      '|新AI偏移|1237/1249/1261/1273/1285逐路改变，NTC0[495]与AI4未见串扰；仅现有有效AI保存区路径，不覆盖初次迁移/物理校准|',
      '|制冷电加热故障联锁|先实际建立热量及加湿软件输出，再翻转X06正常极性；AO/DO两类加湿均未随故障关闭，失败|',
      '|制热同一故障对照|热输出和加湿均关闭，风机保持；DI极性模拟检查符合，物理接点待测|',
      '|通风自动送风|模拟风压及风速反馈均能600→610→600，目标反馈保持12秒，Y03许可及回风手动4V保持；未测真实信号/负载闭环|',
      '', '明确不符合项（尚未修改当前固件）：','',
      '|用例|规格要求|板上实际|','|---|---|---|',
      '|T03-001、T03-002|§3.11.9电加热故障后加湿全关，其他设备不受影响|制冷X06约3.1秒锁存后热AO为0，加湿AO仍1000或Y13仍1；风机继续|',
      '|T07-062|§3.10制冷制热模式送风电压5～10V|[340]范围表0～100，协议允许49即4.9V|',
      '|T07-065|§3.10风压设定0～1500Pa|[345]范围表0～9999，协议允许1501Pa|',
      '', '尚未销项的异常：','',
      f"- 连续边界写入后首次复位有{len(rapid)}个参数读数不符。随后每项只写最终值，并等待EEPROM保存状态稳定，再复位并持续读取8秒，53项均正确。前次异常与复测的写入节奏和启动等待不同，根因未定，不能用稳定复测覆盖首次异常，也不能直接断言EEPROM损坏。首次证据：[标量边界批次]({rel(old)})；后续证据见parameter_persistence_recheck JSON。",
      '- T02-013首轮134=0后软件DA7仍1000持续至超时；后续窄范围复核及完整风机批次均为DA7=0、Y03=1。首次缺少持续配置轨迹，根因未定；保留fan_batch.json和fan_zero_recheck.json。',
      '- AI校准首轮脚本把工程上下限设为相同值，偏移结果被量程夹限，属于测试夹具设置错误；改用非零量程后逐路复测通过。原始异常仍保留，不判为已修复固件缺陷。',
      '- 复位后串口及部分版本信息先恢复，AI配置保存区在上电6秒后才加载。终检脚本曾过早采集AI配置0值，等待IndoorAiCfgLoaded=1后再次读回原值一致；后续脚本已加入启动完成门槛。这次过早采集属于测试时机问题，不作为AI配置丢失结论。',
      '', '本批未完成：真实DI接点、NTC和电压/电流信号源输入、端子电压/接点；真实断电来电自启；正式时序；本轮其余PID、压机排序/环境满空载/禁用故障、EEV、消排毒与迁移、化霜联动、完整保护矩阵、30轮及2小时运行。历史记录不能自动计入本轮通过。',
      '', f"结束状态：正常停机，软件DO/AO全0，三板版本和通信正常；330参数0～499、新AI配置1229～1288及1298/1299与烧前快照一致，ST-Link复位后再次一致。[独立终检]({rel(audit)})。板上保留本轮BENCH，未烧回正式版。", 
      '', '[逐项勾选及全部当前结果](内机测试版逐项测试记录_20261105.md)；[672例明细](内机明日全部待测复测用例_20261105.csv)。']
    stage=R/'内机测试版阶段结论_20261105.md'
    stage.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    with REPORT.open('a',encoding='utf-8') as f:
        f.write('\n[本批缺陷、异常及未测范围](内机测试版阶段结论_20261105.md)。\n')
    plan=R/'明日实机验证方案_内机3.1-3.11_20261105.md'
    text=plan.read_text('utf-8')
    anchor='[逐项勾选、结果与证据](内机测试版逐项测试记录_20261105.md)'
    text=text.replace(anchor,anchor+'；[阶段结论与未销项问题](内机测试版阶段结论_20261105.md)',1)
    plan.write_text(text,encoding='utf-8')
    for p in (CASECSV,summary,coverage,stage,REPORT,plan):
        assert '\ufffd' not in p.read_text('utf-8-sig'),p
    print('SUMMARIZED',len(evidence),dict(counts),'rapid-reset mismatches',len(rapid),'pending',672-len(evidence),flush=True)


if __name__=='__main__':
    main()
