"""Recalculate full-load disinfect timing from retained board observations."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'测试证据/内机实测_20261105/BENCH_V1053_V1239'


def main():
    rows=[]
    for path in sorted(BASE.glob('*serial_loaded_modes_to_disinfect_20261106_*.json')):
        data=json.loads(path.read_text('utf8'))
        if data.get('restored') is not True or data.get('cleanup_error'):continue
        for cid,e in data.get('cases',{}).items():
            if e.get('passed') is not True or e.get('error'):continue
            phases={}
            for s in e['samples']:
                if s['mode']==3:
                    phases.setdefault(s['special_phase'],s)
            spans={name:phases[end]['t']-phases[start]['t']
                for name,start,end in (('valve_wait_s',1,2),('fan_wait_s',2,3),('disinfect_on_s',3,6))}
            # DOs are acquired before the later phase-register read. A phase-6
            # frame can therefore contain the previous scan's DO=1. Retain
            # that observation and qualify the actual output edge separately.
            samples=e['samples']
            on=next(i for i,s in enumerate(samples) if s['do'][10]==1)
            off=next(i for i in range(on+1,len(samples)) if samples[i]['do'][10]==0)
            phase_duration=spans['disinfect_on_s']
            spans['disinfect_on_s']=samples[off]['t']-samples[on]['t']
            edge_window=[samples[off-1]['t']-samples[on]['t'],
                samples[off]['t']-samples[on-1]['t']]
            active=[s for s in e['samples'] if s['mode']==3 and s['special_phase'] in (1,2,3)]
            source=e['source'];want=2 if source==0 else 3
            checks=dict(
                all_four_before=all(v==want for pair in e['before']['outdoor_status'] for v in pair),
                valve_wait_150s=abs(spans['valve_wait_s']-150)<=1.5,
                fan_wait_20s=abs(spans['fan_wait_s']-20)<=1.5,
                disinfect_1min=abs(spans['disinfect_on_s']-60)<=1.5,
                no_compressor_overlap=bool(active) and all(v not in (2,3,4) for s in active for pair in s['outdoor_status'] for v in pair),
                no_thermal_ao_overlap=bool(active) and all(s['ao'][i]==0 for s in active for i in (0,1,2,8,9)),
                disinfect_output_on=phases[3]['do'][10]==1,
                disinfect_output_off=samples[off]['special_phase']==6,
                off_before_normal_restart=samples[off]['mode']==3,
                ending_matches=(e['complete']['state'][9]==0 if e['after']==0 else
                    e['complete']['mode']==source and e['complete']['state'][9]==2 and
                    all(v==want for pair in e['restored_full_load']['outdoor_status'] for v in pair)))
            rows.append(dict(id=cid,source=source,after=e['after'],**spans,checks=checks,
                phase3_to_phase6_s=phase_duration,output_edge_interval_s=edge_window,
                first_phase6_frame_do=phases[6]['do'][10],
                phase6_first_frame_to_do_off_s=samples[off]['t']-phases[6]['t'],
                same_scan_atomicity_qualified=False,
                passed=all(checks.values()),evidence=path.relative_to(ROOT).as_posix()))
    report=dict(scope='已恢复批次独立重算；软件反馈边沿、约0.3秒采样；不替代物理端子或正式档',cases=rows)
    out=BASE/'serial_full_load_disinfect_timing_20261106.json'
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    lines=['# 满载迁移消毒时序复核（2026-11-06）','',report['scope']+'。','',
        '|执行|用例|源模式／结束选择|风阀等待(s)|送风等待(s)|消毒输出(s)|软件范围复核|',
        '|---|---|---|---:|---:|---:|---|']
    for r in rows:
        lines.append(f'|[x]|{r["id"]}|{r["source"]}／{r["after"]}|{r["valve_wait_s"]:.3f}|{r["fan_wait_s"]:.3f}|{r["disinfect_on_s"]:.3f}|{"匹配" if r["passed"] else "待查"}|')
    lines+=['','源模式0=制冷、1=制热；结束0=停机、1=恢复原模式并再次取得四台压机运行反馈。',
        '',f'[逐项检查与原始日志]({out.relative_to(ROOT).as_posix()})。未启用加湿或再热，不据此验收其满载迁移。',
        '', '两例首次阶段6帧的DO仍为1，随后0.656／0.828秒采到0；DO读取先于阶段读取，'
        '这些寄存器不保证同一扫描原子性。本表按实际DO开关边沿计算消毒时长，并确认输出关闭早于普通模式重启；'
        '不据此证明同一扫描立即关闭。原始逐帧数据及首次阶段帧检查保留。']
    (ROOT/'满载切换消毒_时序复核_20261106.md').write_text('\n'.join(lines)+'\n','utf8')
    print(json.dumps(dict(cases=len(rows),all_match=bool(rows) and all(r['passed'] for r in rows),timings=rows),ensure_ascii=False))


if __name__=='__main__':main()
