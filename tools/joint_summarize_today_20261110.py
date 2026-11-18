"""Publish only completed, restored test scopes; never convert missing rows to passes."""
from pathlib import Path
import csv,io,json,collections

ROOT=Path(__file__).resolve().parents[1]
DAY=ROOT/'测试证据/内外机联合实测_20261110'


def latest(pattern):
    paths=sorted(p for p in DAY.glob(pattern) if not p.stem.endswith(('_counter_verdict','_independent_verdict')))
    if not paths:return None,None
    p=paths[-1]
    return p,json.loads(p.read_text('utf8'))


def main():
    updates={}
    lowp,low=latest('four_coil_real_300_120_*.json')
    rp,rec=latest('four_coil_120s_recovery_corrected_clock_*.json')
    if low and rec and rec.get('restored') and not rec.get('today_cleanup_error'):
        e=low['cases']['T15-001'];z=rec['priority_case']
        if len(e['trip_times'])==4 and len(z['release_times'])==4 and z.get('running_again') and not z.get('execution_error'):
            for i in range(4):
                trip=e['trip_times'][str(i)]['elapsed_s'];release=z['release_times'][str(i)]['elapsed_from_input_request_s']
                updates[f'T15-{i+1:03d}']=dict(status='新增板上软件子范围证据；物理/正式档另验',paths=[lowp,rp],detail=f'已安装回路{i+1}连续低温300秒置位，首轮温度确认后的读回约{trip:.3f}秒；旧恢复断言起点偏晚的失败保留。补测以合法1分钟低温建立保护，5℃恢复自输入请求起约{release:.3f}秒自动解禁，四台实际制冷反馈恢复。独立输入和只读计数取证；非端子测量，连续性打断/模式切换另验。')
    for pattern,ids in [('T10-018_T10-019_allocation_*.json',['T10-018','T10-019']),('T12-005_refrigerant_bridge_*.json',['T12-005']),('T06-024_DA8_manual_characterization_*.json',['T06-024'])]:
        p,j=latest(pattern)
        if not j or not j.get('restored') or j.get('today_cleanup_error'):continue
        e=j['priority_case']
        if e.get('execution_error'):continue
        if ids[0]=='T10-018':
            if len(e['runs'])!=2 or not all(r.get('software_scope_passed') for r in e['runs']):continue
            detail='实际化霜8及BENCH恢复7、目标压机0/4，两种目标下普通命令保持，化霜实际两压机开，恢复两压机关。精确AXF的int16命令结构只读；BENCH恢复观察不证明正式60秒，非物理端子。'
            status='新增板上软件子范围证据；正式恢复时长另验'
        elif ids[0]=='T12-005':
            if len(e['runs'])!=4 or not all(r.get('bridge_passed') for r in e['runs']):continue
            detail='停机以正常330[39]依次0/1/2/3，两块316[39]均跟随，记录压力/蒸发温度/过热度及330镜像。仅制冷剂参数桥接；PT换算准确度、PID动态、实际制冷剂另验。'
            status='新增桥接子范围证据；换算和PID待测'
        else:
            detail=e['status']+'。记录314=0及245/247手动0→500→0与DA8回读；独立介质许可要求尚未确认，不能据此宣布符合或擅改固件。'
            status='现象已复测；规格口径待确认'
        for cid in ids:updates[cid]=dict(status=status,paths=[p],detail=detail)
    cp,cj=latest('T15-009_coil_continuity_*.json')
    mp,mj=latest('T15-009_coil_mode_async_*.json')
    if cj and cj.get('restored') and not cj.get('today_cleanup_error'):
        ce=cj['priority_case']
        if not ce.get('execution_error') and len(ce.get('events',{}))==8:
            updates['T15-009']=dict(status='新增回路1连续性子范围证据；其余回路另验',paths=[cp],detail='回路1以合法1分钟低温/解禁设定：低温累计15秒后输入等于−2℃使计数归零，重新低温累计至保护；5℃恢复累计15秒后降4.9℃使恢复计数归零且保护保留，再升5℃重新累计至解禁。再次低温累计15秒后请求制热并正常停止，停止阶段低温计数归零。只读计数、原始NTC输入；非八路完整迁移或物理信号源验收。')
        elif len(ce.get('events',{}))==7 and mj and mj.get('restored') and not mj.get('today_cleanup_error') and not mj['priority_case'].get('execution_error') and 'mode_change_stopping_clears_low_count' in mj['priority_case'].get('events',{}):
            updates['T15-009']=dict(status='新增回路1连续性子范围证据；其余回路另验',paths=[cp,mp],detail='回路1以合法1分钟低温/解禁设定：低温累计15秒后输入等于−2℃使计数归零，重新低温累计至保护；5℃恢复累计15秒后降4.9℃使恢复计数归零且保护保留，再升5℃重新累计至解禁。首轮脚本错误要求236立即变更而退出，原轨迹保留；补测正常236制热请求，固件异步停机时低温输入仍为−2.1℃、低温计数已归零。只读计数、原始NTC输入；非八路完整迁移或物理信号源验收。')
    table=ROOT/'内机剩余150项明日安排_20261110.csv.txt'
    rows=list(csv.DictReader(io.StringIO(table.read_text('utf-8-sig'))))
    assert len(rows)==150 and len({r['原用例'] for r in rows})==150
    for r in rows:
        if r['原用例'] in updates:
            u=updates[r['原用例']];r['状态']=u['status'];r['新增证据路径']='; '.join(p.relative_to(ROOT).as_posix() for p in u['paths']);r['步骤与判定']+=' | 2026-11-10实测：'+u['detail'] if '2026-11-10实测：' not in r['步骤与判定'] else ''
    buf=io.StringIO(newline='');w=csv.DictWriter(buf,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows);table.write_text(buf.getvalue(),encoding='utf8')
    out=list(csv.DictReader(io.StringIO((ROOT/'室外机逐项测试表_20261110.csv.txt').read_text('utf-8-sig'))))
    summary=dict(indoor_original_rows=150,new_indoor_scope_ids=sorted(updates),indoor_status_counts=dict(collections.Counter(r['状态'] for r in rows)),outdoor_rows=len(out),outdoor_status_counts=dict(collections.Counter(r['状态'] for r in out)))
    (DAY/'today_result_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    report=ROOT/'内外机联合实测进度与原因_20261110.md';text=report.read_text('utf8');marker='<!-- today-indoor-results -->'
    text=text.split(marker)[0].rstrip()+'\n\n'+marker+'\n\n内机新增软件子范围证据（保留150个原ID，不视作原验收全通过）：\n\n|用例|本轮结果及限制|证据|\n|---|---|---|\n'
    for cid,u in sorted(updates.items()):
        links='、'.join(f'[{p.stem}]({p.relative_to(ROOT).as_posix()})' for p in u['paths'])
        text+=f'|{cid}|{u["detail"]}|{links}|\n'
    text+='\n外机逐项状态统计：'+json.dumps(dict(collections.Counter(r['状态'] for r in out)),ensure_ascii=False)+'。各行为与规格适用关系见[四项原文对照](四项实测问题与规格原文对照_20261110.md)，定时化霜额外固定10℃限制按用户最终确认判不符合；急停清码时机及建议的恢复时序仍未获确认。\n'
    text+='\n150项原内机清单的仪表、正式档、真实断电保存、通风暂缓及3/4台硬件不足等约束继续保留；T15-009其余回路及完整迁移、T16-008正式60秒、T10通讯动态恢复等未被本轮子范围替代。蒸汽/热水的介质区分不能由共用AO电热测试代替，DA8的独立介质许可要求仍待确认。\n'
    fp,fj=latest('final_independent_readback_*.json')
    if fj:
        text+=f'\n独立收尾：[配置/输出/状态/源码回读]({fp.relative_to(ROOT).as_posix()})，通过={fj["passed"]}。当前固件源码{fj["source_count"]}份清单匹配；各项检查见原始文件。未编译、未烧录、未主动复位/暂停MCU。\n'
    report.write_text(text,encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
