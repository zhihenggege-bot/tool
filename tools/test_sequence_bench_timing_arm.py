"""Execute production/BENCH sequence boundaries in final ARM images; no hardware."""
import json
from test_defrost_lifecycle_arm import Firmware,ROOT,tick
from test_indoor_3133_arm import at,out
D=ROOT/'.codex-tmp/persistence_interlock_v1049_v1239_20261105'
checks=[]
def check(ok,label):
    assert ok,label
    checks.append(label); print('PASS',label)
def image(model,bench):
    profile='BENCH_ONLY_3S' if bench else 'PRODUCTION';v='10.49' if model==330 else '12.39'
    f=Firmware(str((D/profile/f'PSC{model}_V{v}_{profile}.axf').relative_to(ROOT)))
    f.uc.mem_map(0x22000000,0x100000);f.call('ParameterInit')
    for i in range(500):f.p(i,f.var('Parameter_def',index=i,width=2))
    return f

def indoor(bench,mode=2):
    f=image(330,bench)
    for a,v in {38:0,214:3,236:mode,1:mode,700:4,709:1,329:1,330:1,331:1,381:0,386:1,153:0,335:1,336:1,337:1,338:1,328:30,132:30,135:30,377:2,380:0}.items():f.p(a,v)
    for a in range(250,258):f.p(a,1)
    f.var('OilCount',10000);f.var('X_15',1);f.var('X_14',1);f.var('Systick_1ms',30000)
    return f

def cycle(f,sec):
    at(f,sec,'SysBoardAction','SysDataPross','IndoorFanValveOutputs','IndoorEnforceConfiguredOutputDisable','IoOutAction','IndoorEnforceConfiguredOutputDisable')

for bench in [False,True]:
    tag='BENCH' if bench else 'production'
    valve,gap,pressure,close=(5,3,3,3) if bench else (150,30,10,30)
    for mode in [0,1,2]:
        f=indoor(bench,mode)
        for sec,expected in [(0,(0,0,0)),(valve-.001,(0,0,0)),(valve,(0,0,1)),(valve+gap,(1,0,1)),(valve+gap*2,(1,1,1)),(valve+gap*2+pressure-.001,(1,1,1)),(valve+gap*2+pressure,(1,1,1))]:
            cycle(f,sec);check(tuple(out(f,c) for c in [3,6,10])==expected and out(f,14),f'{tag} mode{mode}: ordered valves/fans at {sec}s')
        check(f.p(709)==2 and f.p(888)==f.p(889)==pressure,f'{tag} mode{mode}: requires continuous supply/return pressure qualification')
        check([f.p(a) for a in [328,132,135]]==[30,30,30],f'{tag} mode{mode}: saved delay parameters not rewritten')
        if mode==2:
            stop=valve+gap*2+pressure+2
            f.p(700,0);cycle(f,stop)
            for sec,expected in [(stop,(0,1,1)),(stop+gap-.001,(0,1,1)),(stop+gap,(0,0,1)),(stop+gap*2,(0,0,0)),(stop+gap*2+close-.001,(0,0,0))]:
                cycle(f,sec);check(tuple(out(f,c) for c in [3,6,10])==expected and out(f,14),f'{tag}: reverse fan stop with damper held at {sec}s')
            cycle(f,stop+gap*2+close)
            check(f.p(709)==0 and not any(out(f,c) for c in [3,4,6,7,10,11,14]),f'{tag}: closes dampers only after final fan hold')
    for delay in [-30,0,2,30,90]:
        f=indoor(bench);f.p(328,delay)
        expected=max(-3,min(3,delay)) if bench else delay
        got=f.call('IndoorExhaustFanDelay');got=got-2**32 if got>=2**31 else got
        check(got==expected,f'{tag}: preserves zero/sign and caps configured exhaust delay {delay}')
    f=indoor(bench)
    for a in range(335,339):f.p(a,0)
    f.p(381,0)
    check(f.call('IndoorValveOpenDelay')==(3 if bench else 10),f'{tag}: no-damper opening delay')
    f.var('CompActionTickValid',1,width=1);f.var('CompLastActionTick',1000)
    interval=3 if bench else 30
    f.var('Systick_1ms',1000+interval*1000-1)
    check(f.call('CompActionIntervalReady')==0,f'{tag}: compressor interval rejects one millisecond early')
    f.var('Systick_1ms',1000+interval*1000)
    check(f.call('CompActionIntervalReady')==1,f'{tag}: compressor interval accepts exact boundary')
    # Loss of pressure resets only confirmation; fault wait remains original 60+10s.
    f=indoor(bench);f.p(330,0);f.p(331,0)
    cycle(f,0);cycle(f,valve);cycle(f,valve+pressure-1)
    f.var('X_15',0);cycle(f,valve+pressure-.5)
    check(f.p(709)==1 and f.p(888)==0,f'{tag}: pressure dropout resets confirmation')
    f.var('X_15',1);cycle(f,valve+pressure)
    cycle(f,valve+pressure*2-.001);check(f.p(709)==1,f'{tag}: pressure must close continuously again')
    cycle(f,valve+pressure*2);check(f.p(709)==2,f'{tag}: pressure qualifies after new full window')
    # Active defrost ends on raw high-pressure inputs, then waits the profile duration.
    f=image(316,bench);f.var('BoardAddressSet',1)
    for a,v in {1:1,182:100,183:30,184:4,185:10,186:-20,187:100,188:30,189:35,190:400,191:4,192:3,1409:1,1410:1,1422:50,153:0}.items():f.p(a,v)
    for i in range(2):f.var('output',1,i,1);f.var('Comp',1,i,1)
    f.call('DefrostProcess');f.var('X_00',1);f.var('X_02',1);f.call('DefrostProcess')
    check(f.p(1420)==f.p(1421)==7 and f.var('Comp',index=0,width=1)==f.var('Comp',index=1,width=1)==0,f'{tag}: defrost enters recovery with both compressors stopped')
    recovery=5 if bench else 60;tick(f,recovery-1);f.call('CompErrAction')
    check(f.p(1420)==7 and f.p(606)==f.p(607)==0,f'{tag}: defrost recovery remains masked until {recovery}s')
    tick(f,1);check(f.p(1420)==f.p(1421)==0,f'{tag}: defrost completes at {recovery}s')
    # Equivalent fans retain shortest-start/longest-stop selection and exact action gap.
    f=image(316,bench);f.p(166,1);f.p(179,0);f.p(180,0)
    f.var('Systick_1ms',10000);f.var('OutdoorFanTotalRun',100,0,4);f.var('OutdoorFanTotalRun',200,1,4)
    ptr=0x20070000
    def fan_call(on1,on2):
        f.call('OutdoorFanApplySequential',on1,on2,ptr,ptr+1)
        res=[f.read(ptr,1),f.read(ptr+1,1)];f.p(872,res[0]);f.p(874,res[1]);f.call('OutdoorFanUpdateTimers');return res
    check(fan_call(1,1)==[1,0],f'{tag}: shortest-runtime outdoor fan starts first')
    fan_gap=3 if bench else 15
    f.var('Systick_1ms',10000+fan_gap*1000-1);check(fan_call(1,1)==[1,0],f'{tag}: second fan blocked one millisecond before gap')
    f.var('Systick_1ms',10000+fan_gap*1000);check(fan_call(1,1)==[1,1],f'{tag}: second fan starts at exact gap')
    f.var('Systick_1ms',10000+fan_gap*2000);check(fan_call(0,0)==[1,0],f'{tag}: longest-runtime outdoor fan stops first')
    f.var('Systick_1ms',10000+fan_gap*3000);check(fan_call(0,0)==[0,0],f'{tag}: remaining fan stops after another gap')
    # Inverter run-enable lead is electrical sequencing, unchanged in BENCH.
    f=image(316,bench);f.p(166,2);f.var('output',1,2,1);f.p(872,1);f.p(1463,30);f.var('OutdoorVfdSpeed',300)
    f.var('Systick_1ms',10000);f.call('OutdoorFanSyncVfdAnalogOutput')
    f.var('Systick_1ms',11999);f.call('OutdoorFanSyncVfdAnalogOutput')
    check(f.var('DA',index=0,width=2)==0,f'{tag}: VFD electrical lead still holds analog output before 2s')
    f.var('Systick_1ms',12000);f.call('OutdoorFanSyncVfdAnalogOutput')
    check(f.var('DA',index=0,width=2)>0,f'{tag}: VFD analog output begins only at the original 2s boundary')

print(len(checks),'sequence timing checks passed')
(D/'sequence_test_result.json').write_text(json.dumps({'checks_passed':len(checks),'checks':checks},indent=2)+'\n','utf-8')
