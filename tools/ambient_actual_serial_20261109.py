"""Ambient target-to-actual software feedback; isolated compressor power bench."""
from remaining_serial_only_live_20261106 import *


def main():
    b=SerialHeatBench('ambient_actual_cool_20261109')
    b.log['test_script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    points=(219,220,221,252,253,285,317,318,349,350,351)
    runs={temp:[] for temp in points}
    try:
        b.setup(0)
        b.config({128:1,127:0,332:0,333:0,334:0,125:0,126:0,248:0,
                  315:1,327:1,316:350,317:220,320:0,245:1,247:0,
                  329:2,330:0,331:0,346:0,335:0,336:0,337:0,338:0})
        b.temperature(0,250);b.temperature(2,219);b.reset_faults();b.start()
        assert b.rd(2678)[0]==4
        for direction,seq in (('up',points),('down',tuple(reversed(points)))):
            for temp in seq:
                b.temperature(2,temp)
                expected=0 if temp<=220 else 4 if temp>=350 else (4*(temp-220)+129)//130
                e=dict(direction=direction,temperature=temp,expected=expected,passed=False,samples=[])
                b.log['current_point']=e;b.save()
                began=time.monotonic();stable=None;last=None;exact_seen=False
                while True:
                    s=b.snapshot('ambient actual '+direction+' '+str(temp))
                    actual_temp=signed16(b.rd(512)[0]);target=b.rd(881)[0]
                    statuses=[v for pair in s['outdoor_status'] for v in pair]
                    actual=sum(v==2 for v in statuses)
                    actual_formula=0 if actual_temp<=220 else 4 if actual_temp>=350 else (4*(actual_temp-220)+129)//130
                    s.update(fresh=actual_temp,target=target,actual_cooling=actual)
                    e['samples'].append(s)
                    assert not any(s['faults']),s
                    marker=(actual_temp,target,tuple(statuses))
                    if marker!=last:
                        print('AMBIENT ACTUAL',direction,temp,'fresh',actual_temp,'target',target,'feedback',statuses,flush=True)
                        b.save();last=marker
                    exact_seen|=actual_temp==temp
                    if abs(actual_temp-temp)<=1 and actual_formula==expected and target==expected and actual==expected:
                        if stable is None:stable=time.monotonic()
                        if time.monotonic()-stable>=3 and exact_seen:break
                    else:stable=None
                    if time.monotonic()-began>=25 and any(x['target']!=expected or abs(x['fresh']-temp)>1 for x in e['samples'][-15:]):
                        e.update(environment_skipped=True,reason='Input drift crosses target-count boundary; cannot qualify stable target')
                        b.log.setdefault('environment_skips',[]).append(e);b.save();break
                    assert time.monotonic()-began<100,('actual convergence timeout',temp,expected,s)
                    time.sleep(.2)
                if not e.get('environment_skipped'):
                    e.update(passed=True,duration_s=time.monotonic()-began)
                    runs[temp].append(e)
                b.log['completed_runs']=runs;b.save()
        for i,temp in enumerate(points):
            cid=f'T09-{i+1:03d}'
            if len(runs[temp])!=2:continue
            entry=dict(passed=True,runs=runs[temp],installed_CN=4,
                       scope='One ascending and one descending traversal; actual 316 software status convergence, no physical contacts or production time qualification')
            b.record_local(cid,True,f'环境制冷CN4、HLC22/HLM35℃；目标输入{temp/10:.1f}℃实际采到精确值，稳定观察允许±0.1℃且公式所得台数不变；上升/下降均完成目标{runs[temp][0]["expected"]}及316制冷运行反馈台数收敛，并稳定3秒；只用正常参数和合法NTC校准。未完成三轮排序复现、实际触点、正式时序验收。',entry)
    except Exception:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:
        b.finish()
        lines=['# 环温制冷目标到压机反馈续测（2026-11-09）','',
               f'330 V10.{runtime.EXPECTED[2]} / 316 V12.39 BENCH；压机动力隔离，软件反馈非实际运行或端子证据。',
               '正常参数和合法NTC校准；一次升程、一次降程。完成点实际采到精确温度，稳定观察允许±0.1℃且按实测输入公式计算的台数不变，目标与实际制冷台数稳定3秒；漂移跨台数边界的点另记环境受限。','',
               '|输入℃|目标|完成方向|','|---|---:|---|']
        for temp,items in runs.items():
            lines.append(f'|{temp/10:.1f}|{items[0]["expected"] if items else "待测"}|{", ".join(v["direction"] for v in items)}|')
        lines+=['',f'恢复：{b.log.get("restored")}；错误：{b.log.get("error","无")}。',
                f'输入漂移跨台数边界而跳过的点：{len(b.log.get("environment_skips",[]))}。',
                '排序三轮复现、生产档时间、物理输出仍待测。',f'\n[原始证据]({b.path.relative_to(R).as_posix()})']
        (R/'环温制冷_实际台数升降复测_20261109.md').write_text('\n'.join(lines)+'\n','utf8')
        print('AMBIENT ACTUAL RESTORED',b.log.get('restored'),flush=True)


if __name__=='__main__':main()
