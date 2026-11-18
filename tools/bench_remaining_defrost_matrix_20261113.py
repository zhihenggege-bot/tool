import full_queue_context_20261113
"""Additional defrost/LP input paths, unchanged firmware and read-only lifecycle."""
from bench_remaining_outdoor_20261111 import *
from remaining529_manual_defrost_input_20261105 import manual_defrost
from bench_contact_inputs_20261111 import ContactInputs


def whole_unit_defrost_finished(sample):
    """Fault/disable phase6 may persist after the lifecycle and grant finish."""
    return (sample['PSC316DefrostState']==[0] and sample['owner']==0
            and all(v in (0,6) for v in sample['phase'])
            and all(v in (0,6) for v in sample['mirror_phase'])
            and not any(sample['SysHaveDef']))


def qualified_lp_mask_sample(sample):
    return (sample['inputs'][1]==1 and sample['qualified_inputs'][1]==1
            and sample['phase']==[8,8] and sample['alarms'][0]==0)


def run(kind):
    b=current_bench_class()('remaining_defrost_matrix_'+kind)
    cid=('O-PROTECT-014' if kind.startswith('lp-') else
         'O-LINK-004' if kind=='mirror-unit2' else
         'O-DEFROST-010' if kind=='hp2' else
         'O-DEFROST-018' if kind.startswith('disable') else 'O-DEFROST-019')
    e=b.log['remaining_functional']=dict(kind='defrost_matrix_'+kind,cases=[],
        scope='Legacy HMI manual defrost entrance and ordinary330 demand/settings; contact-polarity INPUT simulation, actual316 and330 software feedback; BENCH recovery, no physical terminals or formal60s acceptance')
    e['driver']='tools/bench_remaining_defrost_matrix_20261113.py'
    old={};fixture=None;polarity_original={}
    row=dict(id=cid,label=kind,samples=[]);e['cases'].append(row)
    unit=2 if kind=='mirror-unit2' else 1

    def sample():
        target=b.extra[0][1].target if unit==2 else b.ot
        sy=b.extra[0][2] if unit==2 else b.outsy
        p=sy['Parameter'][0];it=b.extra[1][1].target;isy=b.extra[1][2]
        s=fixture.sample() if fixture else dict(at=now(),t=time.monotonic(),output=list(target.read_memory_block8(*sy['output'])),
            alarms=[target.read16(p+2*a) for a in range(600,628)],
            phase=[target.read16(p+2*a) for a in (1420,1421)],
            layer=target.read16(p+2*1501))
        s.update(mirror_phase=b.rd(1550+(unit-1)*70,2),
            mirror_faults=b.rd(2022+(unit-1)*128,28),mirror_layer=b.rd(2598+(unit-1))[0],
            other_phase=b.rd(1620 if unit==1 else 1550,2),
            owner=it.read8(isy['PSC316DefrostOwner'][0]))
        for name in ('PSC316DefrostState','PSC316DefrostEligible','PSC316DefrostEnded',
                     'PSC316DefrostStarted','PSC316DefrostRunTime','CompRunTime','EnableCheckLow','SysHaveDef'):
            if fixture:continue
            a,n=sy[name];raw=bytes(target.read_memory_block8(a,n))
            s[name]=list(struct.unpack('<'+'I'*(n//4),raw)) if name in ('CompRunTime','EnableCheckLow','PSC316DefrostRunTime','SysHaveDef') else list(raw)
        row['samples'].append(s);return s

    def wait(label,predicate,seconds):
        end=time.monotonic()+seconds;heartbeat=0
        while time.monotonic()<end:
            paused();s=sample()
            if predicate(s):row[label]=s;b.save();return s
            if time.monotonic()-heartbeat>=25:
                heartbeat=time.monotonic();b.save()
                print('DEFROST MATRIX',kind,label,s['phase'],s['output'][:2],s['owner'],flush=True)
            time.sleep(.12)
        raise TimeoutError(label)

    def polarity(ch,active):
        a=ch+2;p=b.outsy['Parameter'][0]
        assert fixture is not None
        if a not in old:old[a]=polarity_original[ch]
        v=1-old[a] if active else old[a]
        fixture.set(ch,v)

    def start_fixture():
        nonlocal fixture,polarity_original
        polarity_original={ch:b.ot.read16(b.outsy['Parameter'][0]+2*(ch+2)) for ch in range(8)}
        fixture=ContactInputs(b,polarity_original)

    try:
        if kind=='lp-startup':
            b.setup(1);b.config({**HEAT,27:150});b.temperature(0,220);b.reset_faults();b.start()
            b.wait('LP startup actual four heating',lambda s:all(v==3 for q in s['outdoor_status'] for v in q),240)
            b.attach_extra()
            assert b.ot.read16(b.outsy['Parameter'][0]+54)==150,'normal330 LP delay did not propagate'
            start_fixture()
            first=sample();assert first['CompRunTime'][0]<135,('startup window already elapsed',first)
            polarity(1,True);began=time.monotonic();held=[]
            while time.monotonic()-began<8:held.append(sample());time.sleep(.15)
            s=held[-1];active=[i for i,q in enumerate(held) if q['inputs'][1]==1]
            continuous=held[active[0]:] if active else []
            row['startup_active_source_seconds']=continuous[-1]['t']-continuous[0]['t'] if continuous else 0
            row['startup_masked']=(bool(continuous) and row['startup_active_source_seconds']>=5 and
                all(q['inputs'][1]==1 and q['alarms'][0]==0 and q['output'][:2]==[1,1] for q in continuous))
            polarity(1,False)
            wait('startup_delay_qualified',lambda s:s['CompRunTime'][0]>150 and s['EnableCheckLow'][0],200)
            polarity(1,True)
            wait('LP_after_startup_trips',lambda s:s['alarms'][0]==1 and s['output'][:2]==[0,1],18)
            polarity(1,False)
            wait('LP_source_auto_clears',lambda s:s['alarms'][0]==0 and not s['layer'],45)
            row['passed']=row['startup_masked']
        else:
            b.prepare();b.attach_extra()
            if kind!='mirror-unit2':start_fixture()
            if kind=='mirror-unit2':
                # Exit1# first, then request2# through the ordinary page/legacy
                # input route; no Owner or phase writes.
                manual_defrost(b,False,session=b.extra[1][1])
                end=time.monotonic()+45
                while any(v in (7,8) for v in b.rd(1550,2)):
                    paused();assert time.monotonic()<end,'unit1 defrost did not finish';time.sleep(.2)
                b.wr(540,2);manual_defrost(b,True,session=b.extra[1][1])
                wait('unit2_active_mirror',lambda s:s['phase']==s['mirror_phase']==[8,8] and s['owner']==2,70)
                manual_defrost(b,False,session=b.extra[1][1])
                # Recovery is very short in BENCH. Keep direct/interface traces
                # and report a missed phase7 as missing coverage, not a fault.
                wait('unit2_owner_released',lambda s:not any(s['phase']) and not any(s['mirror_phase']) and s['owner']==0,50)
                row['recovery7_both_seen']=any(s['phase']==s['mirror_phase']==[7,7] for s in row['samples'])
                row['passed']=row['recovery7_both_seen']
                row['limit']='Phase7 not sampled in the short BENCH window remains missing coverage'
            elif kind=='lp-defrost':
                b.config({27:1})
                confirm=b.rd(60)[0];confirm=confirm if 1<=confirm<=30 else 5
                row['low_pressure_confirm_seconds']=confirm
                polarity(1,True)
                # Broadcast and DI qualification can take several seconds. Start
                # the measured window only after the consumed X01_En is active.
                first=wait('LP_defrost_qualified_source',qualified_lp_mask_sample,35)
                held=[first];end=time.monotonic()+confirm+15
                while held[-1]['t']-first['t']<confirm+1:
                    assert time.monotonic()<end,'qualified LP observation timed out'
                    time.sleep(.15);s=sample();held.append(s)
                    if not qualified_lp_mask_sample(s):
                        raise RuntimeError('LP input/defrost precondition lost during mask window')
                row['defrost_active_source_seconds']=held[-1]['t']-first['t']
                row['masked_during_defrost']=all(qualified_lp_mask_sample(q) for q in held)
                polarity(1,False)
                wait('LP_mask_source_removed',lambda s:s['inputs'][1]==0 and s['qualified_inputs'][1]==0,35)
                manual_defrost(b,False,session=b.extra[1][1])
                wait('defrost_recovery_complete',lambda s:s['PSC316DefrostState']==[0] and s['EnableCheckLow'][0]==1,55)
                wait('LP_postrecovery_running',lambda s:s['output'][:2]==[1,1] and s['CompRunTime'][0]>1,180)
                polarity(1,True);wait('LP_postrecovery_detected',lambda s:s['alarms'][0]==1 and not s['output'][0],18)
                row['passed']=row['masked_during_defrost']
            else:
                if kind=='disable1':b.gateway(1833,1);wanted=[0,1];whole=False
                elif kind=='disable2':b.gateway(1834,1);wanted=[1,0];whole=False
                elif kind=='disable-both':b.gateway(1833,1);b.gateway(1834,1);wanted=[0,0];whole=True
                elif kind=='fault1':polarity(6,True);wanted=[0,1];whole=False
                elif kind=='fault2':polarity(7,True);wanted=[1,0];whole=False
                elif kind=='fan-fault':polarity(4,True);wanted=[0,0];whole=True
                elif kind=='fault-both':polarity(6,True);polarity(7,True);wanted=[0,0];whole=True
                elif kind=='hp2':polarity(2,True);wanted=[1,0];whole=False
                else:raise ValueError(kind)
                s=wait('protected_output',lambda s:s['output'][:2]==wanted,30)
                if whole:
                    s=wait('whole_unit_defrost_finishes',whole_unit_defrost_finished,65)
                    row['passed']=s['output'][:2]==[0,0]
                else:
                    began=time.monotonic();held=[]
                    while time.monotonic()-began<6:held.append(sample());time.sleep(.15)
                    row['passed']=all(s['output'][:2]==wanted and s['phase']==[8,8] for s in held)
                    if kind=='hp2':row['passed'] &= all(s['alarms'][7]==0 for s in held)
        row.update(final=sample(),finished=now());b.save()
        print('DEFROST MATRIX RESULT',kind,row.get('passed'),flush=True)
    except BaseException:
        e['error']=traceback.format_exc();row.setdefault('passed',False);row['finished']=now();b.save();raise
    finally:
        try:
            b.wr(398,0)
            if fixture:fixture.close();fixture=None
            if old:
                b.config(old)
                end=time.monotonic()+40
                while not all(b.ot.read16(b.outsy['Parameter'][0]+2*a)==v for a,v in old.items()):
                    assert time.monotonic()<end,'Normal330 polarity restoration did not settle'
                    time.sleep(.2)
            e['polarities_restored']=all(b.ot.read16(b.outsy['Parameter'][0]+2*a)==v for a,v in old.items())
            assert e['polarities_restored'];b.reset_faults()
        finally:
            try:b.finish()
            finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('kind',choices=('lp-startup','lp-defrost','mirror-unit2','disable1','disable2','disable-both','fault1','fault2','fault-both','fan-fault','hp2'))
    run(p.parse_args().kind)
