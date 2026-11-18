"""Real cumulative fan-runtime selection; normal330 load cycles and raw temperatures."""
from bench_remaining_outdoor_20261111 import *


def run(kind):
    b=current_bench_class()('remaining_two_fixed_rotation_'+kind);inp=None
    cid='O-FANCURVE-004' if kind=='cool' else 'O-FANCURVE-021'
    e=b.log['remaining_functional']=dict(kind='two_fixed_rotation_'+kind,pair=[0,1],cases=[],
        scope='Ordinary330 demand cycles, actual316 cumulative software fan seconds; BENCH sequencing, physical terminals and unspecified continuous-rotation period separate')
    try:
        b.setup(0 if kind=='cool' else 1);b.gateway(1830,0);b.gateway(1831,1)
        b.config(HEAT if kind=='heat' else {**HEAT,127:0,416:100,417:1,418:0,411:200})
        b.config({1337:10,1338:10,1333:300,1334:150,1339:0})
        b.temperature(0,220 if kind=='heat' else 290);b.reset_faults()
        inp=Inputs(b,e)
        # Stay below the25C up-stage and above a full-fresh22C LWS.
        temp=121 if kind=='heat' else 249
        inp.temperatures({0:temp,1:250,2:250});b.start()

        def until(label,predicate,seconds):
            at=time.monotonic();end=at+seconds;samples=[]
            while time.monotonic()<end:
                s=inp.sample(at);samples.append(s)
                if predicate(s):return s,samples
            raise TimeoutError(label)

        until('two healthy compressors',lambda s:s['output'][:2]==[1,1] and not any(s['alarms']),210)
        inp.point(cid,'establish_one_fan_stage',temp,36,1)
        if kind=='heat':
            row=dict(id=cid,label='continuous_one_fan20minutes',samples=[])
            e['cases'].append(row);began=time.monotonic();heartbeat=began
            while time.monotonic()-began<1200:
                s=inp.sample();row['samples'].append(s)
                assert not any(s['alarms']) and s['output'][:2]==[1,1],('healthy heat lost',s)
                if time.monotonic()-heartbeat>25:
                    heartbeat=time.monotonic();b.save()
                    print('FAN ROTATION continuous',round(heartbeat-began,1),s['output'][2:4],s.get('OutdoorFanTotalRun'),flush=True)
            row.update(final=s,observed_s=time.monotonic()-began,finished=now(),
                limit='No rotation-period number is specified; this trace alone does not decide compliance if the selected fan stays unchanged')

        for cycle in range(10 if kind=='cool' else 3):
            b.config({127:0});b.temperature(0,280 if kind=='heat' else 240)
            off,offrows=until('ordinary unloading all fans off',lambda s:not any(s['output'][i] for i in (0,1,2,3,7)),220)
            before=off.get('OutdoorFanTotalRun')
            b.temperature(0,220 if kind=='heat' else 290)
            if kind=='heat':b.config({127:1})
            _,startrows=until('ordinary reload compressors',lambda s:s['output'][:2]==[1,1] and not any(s['alarms']),210)
            row=inp.point(cid,f'ordinary_restart_cycle{cycle+1}',temp,36,1)
            output=row['final']['output'];selected=0 if output[2] and not output[3] else 1 if output[3] and not output[2] else None
            row.update(previous_fan_seconds=before,selected_fan=selected,off_samples=offrows,restart_samples=startrows)
            if before is not None and selected is not None:
                row['shorter_runtime_selected']=before[selected]<=before[1-selected]+3
                row['passed'] &= row['shorter_runtime_selected']
            else:row['passed']=False
            row['limit']='Selection compared to stopped cumulative seconds with3s BENCH switch tolerance; no independent physical runtime meter'
            b.save();print('FAN ROTATION',kind,cycle+1,row['passed'],before,selected,flush=True)
    except BaseException:e['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            b.wr(398,0)
            if inp:inp.close()
        finally:
            try:b.finish()
            finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('kind',choices=('cool','heat'));run(p.parse_args().kind)
