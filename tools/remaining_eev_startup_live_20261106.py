"""Startup, history and upper-cap checks using normal input/configuration.

Invoked inside the existing EEV fixture so pressure mapping and all original
outdoor settings share its confirmed restoration path. No state RAM writes.
"""
from remaining_pid_live_20261106 import *


def run(b,reader,stimulus):
    runs=[]
    for start,motor,maximum in ((0,500,500),(200,500,500),(500,500,500),(500,500,200),(500,200,500)):
        b.stop()
        b.wait('all indoor valves closed before startup',lambda s:all(v==0 for v in b.rd(1153,8)),90)
        # User.h: MotorTotalPulseSet=[10], EEVOpenMaxSizeSet=[12].
        # [14] is a legacy temperature deviation (0..99), not valve maximum.
        # The original rejected [14]=500 attempt remains in its raw journal.
        b.config({411:start,10:motor,12:maximum,16:5,368:100,369:1,370:0,371:50})
        stimulus(50,100)
        cap=min(motor,maximum)
        effective=min(start,cap)
        entry=dict(start=start,motor=motor,maximum=maximum,effective_start=effective,
            effective_cap=cap,rows=[],initial_history=[],passed=False)
        b.log.setdefault('startup_runs',[]).append(entry)
        b.save()
        b.wr(398,1)
        began=time.monotonic();last=None;initial_seen=False
        prior=reader.read()
        while True:
            s=reader.read()
            s['command_on']=reader.t.read16(b.sy['Parameter'][0]+(1212+reader.ch)*2)
            s['compressor_feedback']=signed16(reader.t.read16(reader.unitbase+reader.offsets['CompStatus']+reader.comp*2))
            entry['rows'].append(s)
            assert 0<=s['new']<=cap and 0<=s['current']<=cap,(start,motor,maximum,s)
            assert s['evap']==50 and s['superheat']==100,s
            if s['command_on'] and s['valid']==0 and s['new']==effective and s['current']==effective:
                initial_seen=True
            if s['valid']!=prior['valid'] and s['valid'] in (1,2):
                entry['initial_history'].append(s)
                assert s['new']==effective and s['current']==effective,('initial history changed valve',s)
            marker=(s['command_on'],s['compressor_feedback'],s['new'],s['valid'])
            if marker!=last:
                print('EEV STARTUP',start,motor,maximum,round(time.monotonic()-began,2),marker,flush=True)
                last=marker;b.save()
            if initial_seen and {x['valid'] for x in entry['initial_history']}=={1,2} and s['new']==cap and s['current']==cap and s['valid']==2:
                entry['reached_cap']=s;break
            assert time.monotonic()-began<190,('startup/cap preconditions not achieved',entry['initial_history'],s)
            prior=s
            time.sleep(.03)
        entry.update(passed=True,start_observed=initial_seen,duration_s=time.monotonic()-began)
        runs.append(entry);b.save()
        b.stop()
    initial=[r for r in runs if r['motor']==r['maximum']==500]
    start_ok=len(initial)==3 and all(r['passed'] for r in initial)
    b.record_local('T12-027',start_ok,
        '起始0/200/500三档均从8路内阀软件实际步数归零后正常起机；回路3记录预开目标及实际到位、真实制冷反馈和后续PID加载至最大。未写阀位/PID/请求/反馈/计数RAM；驱动脉冲和阀机械未测。',
        dict(passed=start_ok,runs=initial))
    hist_ok=all({s['valid'] for s in r['initial_history']}=={1,2} and r['passed'] for r in runs)
    b.record_local('T12-023',hist_ok,
        '蒸发5℃、SH10℃条件下，5组重新起机均完整采到前两次真实PID历史建立；常规初始两拍目标与实际保持起始开度，之后才加载。高蒸发优先另见分支矩阵；非物理阀位验收。',
        dict(passed=hist_ok,runs=runs))
    cap_ok=all(r['passed'] for r in runs)
    b.record_local('T12-026',cap_ok,
        '最大开度200/500及电机总步数200/500交叉5组；起始500在有效上限200时先夹限，正误差PID实际加载到每组有效上限，采样目标/软件实际始终未超过上限。物理驱动脉冲及阀体未测。',
        dict(passed=cap_ok,runs=runs))
    cold=next(r for r in runs if r['start']==200 and r['motor']==r['maximum']==500)
    b.log['cold_start200_observed']=cold
    # T12-001 also requires the paired outdoor valve to be closed. That is
    # intentionally not signed off merely from the indoor startup trace.


def main():
    from remaining_eev_live_20261106 import main as fixture
    fixture(startups=True)


if __name__=='__main__':main()
