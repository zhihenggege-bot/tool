"""Normal-mode protection matrix via DI polarity configuration.

The genuine GPIO scan, digital filtering, latches and scheduler act normally.
This does not replace opening the external contact or measuring terminals.
"""
from remaining_pid_live_20261106 import *


def main(modes=(0,1,2), kinds=('filter','phase','supply','valve','fire','remote'),serial_only=False,reuse_recovered=False):
    b=HeatBench('di_protection_matrix')
    sy=None if serial_only else b.sy
    ss=None
    definitions={'phase':(155,1,911,'X_00'), 'remote':(157,7,None,'X_02'),
                 'supply':(158,13,601,'X_03'), 'filter':(389,19,909,'X_05'),
                 'valve':(159,25,605,'X_04'), 'fire':(156,31,605,'X_01')}
    try:
        if not serial_only:
            ss=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1],target_override=BOARDS[2][2],
                options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
            ss.open()
            t=ss.target
        def sample(label):
            s=b.snapshot(label)
            s.update(t=time.monotonic(),filter_alarm=b.rd(909)[0],phase_alarm=b.rd(911)[0],
                     remote_stop=None if serial_only else t.read8(sy['RemoteInterlockStopFlag'][0]),
                     remote_resume=None if serial_only else t.read8(sy['RemoteInterlockResumeFlag'][0]))
            return s
        def established(s,mode):
            if mode>=3:
                actuators=s['do'][10]==1 if mode in (3,5) else s['do'][3]==1 and s['do'][8]==1
                return s['state'][9]==2 and actuators and all(s['ao'][i]==0 for i in (0,1,2,8,9))
            thermal=(mode==2 or s['ao'][0]>0 and s['ao'][2]>0 and (mode!=1 or s['ao'][1]>0))
            return s['state'][9]==2 and s['do'][3]==1 and thermal
        def wait(label, predicate, seconds):
            began=time.monotonic()
            rows=[]
            while True:
                s=sample(label)
                rows.append(s)
                if predicate(s):return s,rows
                assert time.monotonic()-began<seconds,(label,s)
                time.sleep(.1)
        b.log['reuse_recovered_run_between_cases']=reuse_recovered
        for mode in modes:
            prepared=False
            for kind in kinds:
                reg,start,flag,raw=definitions[kind]
                cid=f'T05-{start+mode:03d}'
                entry=dict(started=now(),mode=mode,kind=kind,
                    stimulus='正常DI极性参数翻转；未物理接点开合、未写故障/输出/计数RAM',passed=False)
                b.log['cases'][cid]=entry
                b.save()
                try:
                    thermal_mode=mode in (0,1)
                    if not prepared:
                        b.setup(mode)
                        b.config({128:2 if mode==1 else 0,127:int(thermal_mode),129:1,332:int(thermal_mode),333:int(mode==1),
                              334:int(thermal_mode),125:1,126:1,248:int(thermal_mode),168:1,169:1,
                              160:250,161:250,347:100,348:1,349:0,
                              374:1,375:100,376:40,350:100,351:1,352:0,
                                  346:0,329:2,330:0,331:int(mode>=3),320:0})
                        if thermal_mode:
                            b.temperature(0,220)
                            ai_exact(b,300)
                        b.reset_faults()
                        b.start(special_ready=mode>=3)
                    entry['precondition_source']='preceding case recovered run, independently rechecked' if prepared else 'fresh normal startup'
                    entry['before'],entry['establish_samples']=wait(cid+' loads established',lambda s:established(s,mode),35)
                    original=b.rd(reg)[0]
                    if serial_only:
                        assert kind!='remote','Use dedicated serial remote regression with public-state timing'
                        input_register={'phase':1350,'supply':1353,'filter':1355,'valve':1354,'fire':1351}[kind]
                        raw_before=b.rd(input_register)[0]
                    else:raw_before=t.read8(sy[raw][0])
                    assert raw_before==(1 if kind=='remote' else 0),(kind,raw_before)
                    entry.update(input_raw_before=raw_before,injection_started=now(),injection_t=time.monotonic())
                    b.wr(reg,1-original)
                    if kind=='filter':
                        tripped,rows=wait(cid+' filter15',lambda s:s['filter_alarm']==1,19)
                        assert all(established(s,mode) for s in rows),(cid,'filter must not stop')
                        elapsed=tripped['t']-entry['injection_t']
                        assert 13.8<=elapsed<=16.3,elapsed
                    elif kind=='remote':
                        tripped,rows=wait(cid+' remote request',lambda s:s['remote_stop']==1,6)
                        elapsed=tripped['t']-entry['injection_t']
                        assert 2.6<=elapsed<=3.6,elapsed
                        entry['normal_stop'],entry['normal_stop_samples']=wait(cid+' remote full stop',lambda s:s['state'][9]==0 and loads_off(s),180)
                    else:
                        tripped,rows=wait(cid+' latched protection',lambda s:b.rd(flag)[0]==1 and s['state'][9]==0 and loads_off(s),8)
                        elapsed=tripped['t']-entry['injection_t']
                        assert 2.5<=elapsed<=4.1,elapsed
                    entry.update(trip=tripped,trip_samples=rows,reaction_observed_s=elapsed)
                    b.wr(reg,original)
                    time.sleep(.5)
                    if kind!='remote':
                        entry['restored_contact_no_reset']=sample(cid+' input returned latch remains')
                        assert b.rd(flag)[0]==1,(cid,'latch released without reset')
                        b.reset_faults()
                        if kind!='filter':
                            b.wr(398,0)
                            time.sleep(.15)
                            b.start(special_ready=mode>=3)
                    recovered,recovery=wait(cid+' normal recovery',lambda s:established(s,mode) and
                        (s['remote_stop']==0 if kind=='remote' else b.rd(flag)[0]==0),180 if kind=='remote' else 40)
                    entry.update(recovered=recovered,recovery_samples=recovery,passed=True,finished=now())
                    prepared=bool(reuse_recovered)
                    b.record_local(cid,True,
                        f'模式{mode}/{kind}：负载'+('AO主热/预热/加湿均先建立' if mode==1 else 'AO再热/加湿先建立；制冷预热保持关闭' if mode==0 else '送风先建立' if mode==2 else '消毒或排毒执行器先建立，冷热湿AO保持关闭')+
                        f'；DI极性模拟后约{elapsed:.3f}s保护动作；'+
                        ('只报警、风机与负载继续，输入恢复后锁存、524复位清除。' if kind=='filter' else
                         '正常停机，输入恢复后自动重启，无人工复位。' if kind=='remote' else
                         '整机负载软件输出清零；排除输入后仍锁存，524复位再开机恢复。')+
                        '物理接点及端子未测，未写故障锁存或输出。',entry)
                except Exception:
                    prepared=False
                    entry['error']=traceback.format_exc()
                    b.save()
                    b.record_local(cid,False,entry['error'].splitlines()[-1],entry)
                    # Return all DI settings through normal configuration before
                    # deciding whether the next independent case can run.
                    for a,v in b.polarities.items():
                        if a in b.touched:b.wr(a,v)
                    time.sleep(3.3)
                    b.reset_faults()
                    b.stop()
                    if any(b.snapshot('post-failure recovery')['faults']):raise
                finally:
                    for a,v in b.polarities.items():
                        if a in b.touched:b.wr(a,v)
                    b.reset_faults()
                    if not prepared or kind==kinds[-1]:b.stop()
    finally:
        if ss:ss.close()
        b.finish()
        print('DI MATRIX RESTORED',b.log.get('restored'),b.path,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--modes',nargs='+',type=int,default=[0,1,2])
    p.add_argument('--kinds',nargs='+',default=['filter','phase','supply','valve','fire','remote'])
    args=p.parse_args()
    main(args.modes,args.kinds)
