"""COM6-only continuation when the indoor debug port is unavailable.

No SWD connection or RAM write. Existing normal parameter/readback/recovery
helpers are retained, with a serial-only constructor and explicit evidence.
"""
from remaining_pid_live_20261106 import *
from run_indoor_bench_20261105 import client,EXPECTED


class SerialHeatBench(HeatBench):
    def __init__(self,name):
        self.c=client();self.original={};self.touched=set();self.swd=None
        self.path=D/('remaining571_heat_dynamic_serial_'+name+'_20261106_'+time.strftime('%H%M%S')+'.json')
        assert not self.path.exists()
        self.full_before={}
        try:
            versions=self.rd(2622,18)
            assert versions==runtime.EXPECTED,(versions,runtime.EXPECTED)
            assert self.rd(1299)[0]==15107
            self.log=dict(started=now(),original=self.original,writes=[],samples=[],cases={},
                versions=versions,profiles=self.rd(1298,2),hardware_access=True,
                firmware_changed=False,debug_port_used=False,output_or_pid_ram_writes=False,
                physical_terminal_measurement=False,
                sensor_stimulus='Normal serial parameter/calibration only; debug port unavailable',
                limitations=LIMITS+'COM6 only; no SWD or instruction/scan-edge state reads.')
            self.log['test_script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            for a,n in ((0,125),(125,125),(250,125),(375,125),(1229,60),(1298,2)):
                self.full_before.update({str(a+i):v for i,v in enumerate(self.rd(a,n))})
            self.log['full_configuration_before']=self.full_before
            for a in (1,236,326):
                self.original[str(a)]=self.rd(a)[0];self.touched.add(a)
            self.polarities={a:self.rd(a)[0] for a in (*range(155,160),*range(389,398))}
            self.save()
        except BaseException:
            self.c.close();raise


def ambient_cool():
    b=SerialHeatBench('environment_cool_targets')
    try:
        points=(219,220,221,252,253,285,317,318,349,350,351)
        b.setup(0)
        b.config({128:1,127:0,332:0,333:0,334:0,125:0,126:0,248:0,
            315:1,327:1,316:350,317:220,320:0,245:1,247:0,
            329:2,330:0,331:0,346:0})
        b.temperature(0,250)
        b.temperature(2,220)
        b.start()
        all_runs={v:[] for v in points}
        cn=b.rd(2678)[0]
        assert cn==4,('installed CN',cn)
        for direction,seq in (('up',points),('down',tuple(reversed(points)))):
            for i,temp in enumerate(seq):
                actual=b.temperature(2,temp)
                # Calibration helper allows one deci-degree settling; boundary
                # acceptance requires the exact requested display value.
                began=time.monotonic()
                while signed16(b.rd(512)[0])!=temp:
                    assert time.monotonic()-began<8,('exact NTC2 boundary unavailable',temp,b.rd(512))
                    time.sleep(.1)
                expected=0 if temp<=220 else cn if temp>=350 else (cn*(temp-220)+129)//130
                s=b.wait(f'ambient cool {direction} {temp/10}',lambda s:b.rd(881)[0]==expected,15)
                rows=[]
                for _ in range(3):
                    target=b.rd(881)[0];fresh=signed16(b.rd(512)[0]);installed=b.rd(2678)[0]
                    assert target==expected and fresh==temp and installed==cn,(temp,target,expected,fresh,installed)
                    rows.append(dict(at=now(),temperature=fresh,target=target,CN=installed,snapshot=b.snapshot('ambient target hold')))
                    time.sleep(.2)
                all_runs[temp].append(dict(direction=direction,expected=expected,rows=rows))
                print('AMBIENT COOL',direction,temp,'target',expected,flush=True)
        for i,temp in enumerate(points):
            cid=f'T09-{i+1:03d}'
            entry=dict(passed=True,CN=cn,temperature=temp,runs=all_runs[temp],scope='Target formula only; per-point compressor feedback convergence not qualified')
            b.record_local(cid,True,f'NTC2实际模拟器已调约26.4℃；合法±10℃校准达到精确{temp/10:.1f}℃，上升/下降两方向均按CN=4、HLC22/HLM35℃向上取整得到目标{all_runs[temp][0]["expected"]}。串口工程量/目标回读；本例未等待每点压机实际收敛或测量端子。',entry)
    except Exception:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:
        b.finish();print('SERIAL AMBIENT RESTORED',b.log.get('restored'),flush=True)


def fan_enums():
    import remaining_compatibility_live_20261106 as checks
    checks.HeatBench=SerialHeatBench
    checks.fan_enums()


def extra_di():
    import remaining_compatibility_live_20261106 as checks
    checks.HeatBench=SerialHeatBench
    checks.extra_di(serial_only=True)


def special_protections():
    import remaining_di_protection_live_20261106 as checks
    checks.HeatBench=SerialHeatBench
    checks.main(modes=(5,),kinds=('filter','phase','supply','valve','fire'),serial_only=True)


def ys_permissions():
    from remaining_serial_boundaries_20261106 import ys_permissions as run
    run()


def heat_upper():
    from remaining_serial_boundaries_20261106 import heat_upper as run
    run()


def qhs(qhs):
    assert qhs in (600,1200)
    b=SerialHeatBench('auto_long_qhs_'+str(qhs))
    cid='T11-104' if qhs==600 else 'T11-105'
    try:
        b.setup(1)
        b.config({128:0,127:0,332:0,333:0,334:1,125:0,126:1,248:1,
            168:0,160:250,161:250,162:500,120:20,361:200,412:1,
            320:0,321:50,322:qhs,315:0,346:0,329:2,330:0,331:0,245:1,247:0})
        b.temperature(0,250);ai_exact(b,601);b.start();b.config({320:1})
        entry=dict(passed=False,qhs=qhs,edges=[],timers_modified=False,debug_port_used=False)
        b.log['cases'][cid]=entry;b.save()
        began=time.monotonic();last=None;marks={}
        while True:
            d=b.rd(872,22)
            s=dict(t=time.monotonic(),mode=b.rd(236)[0],count=d[12],direction=d[11],
                humidity=b.rd(501)[0],humidity_demand=d[20],snapshot=b.snapshot(cid))
            assert not any(s['snapshot']['faults']) and s['humidity']==601 and s['humidity_demand']==0,s
            if s['count']!=last or s['mode']!=1:
                entry['edges'].append(s);marks.setdefault(s['count'],s['t']);last=s['count']
                if last%30==0 or s['mode']!=1:
                    b.save();print('SERIAL LONG QHS',qhs,'count',last,'elapsed',round(time.monotonic()-began,2),flush=True)
            b.log['samples']=b.log['samples'][-3:]
            # The public mode setting changes only AFTER the normal shutdown.
            # Observe the public count reset plus shutdown-step edge first;
            # qualify the new cooling mode separately after orderly shutdown.
            if s['count']==0 and s['direction']==0 and s['snapshot']['state'][9]==3:
                entry['trigger_observation']='public QHS counter/direction reset and normal shutdown step 3'
                break
            assert s['mode']==1,('mode changed before normal shutdown trigger',s)
            assert s['count']<qhs,s
            assert time.monotonic()-began<qhs+5,('QHS shutdown trigger timeout',s)
            time.sleep(.12)
        # No private pending/active reads: the accepted edge is public step 3.
        assert all(n in marks for n in range(1,qhs)),('missing count observations',sorted(set(range(1,qhs))-marks.keys()))
        elapsed=s['t']-marks[2]
        assert qhs-2-.5<=elapsed<=qhs-2+1.0,elapsed
        entry.update(trigger=s,count2_to_normal_shutdown_start_s=elapsed)
        final=b.wait(cid+' new cooling established',lambda s:b.rd(236)[0]==0 and s['state'][9]==2 and s['state'][0]==4,160)
        entry.update(passed=True,final=final)
        b.record_local(cid,True,f'仅COM6、QHS={qhs}秒真实连续计时；1至{qhs-1}逐计数均采到；计数2首次观察至计数清零并开始正常停机步骤3为{elapsed:.3f}s，随后等待正常退出及制冷步骤2正常运行。未改计数或时序RAM；未读取私有pending/active字段。AI1工程映射60.1%RH，非物理湿度/端子验收。',entry)
    except Exception:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:
        b.finish();print('SERIAL LONG QHS RESTORED',qhs,b.log.get('restored'),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',nargs='+',choices=('ambient-cool','fan-enums','extra-di','qhs600','qhs1200','special-protections','ys-permissions','heat-upper'))
    args=p.parse_args()
    for action in args.action:
        try:
            if action.startswith('qhs'):qhs(int(action[3:]))
            else:{'ambient-cool':ambient_cool,'fan-enums':fan_enums,'extra-di':extra_di,'special-protections':special_protections,'ys-permissions':ys_permissions,'heat-upper':heat_upper}[action]()
        except Exception:
            print('SERIAL BATCH ERROR',action,traceback.format_exc(),flush=True)
            latest=max(D.glob('remaining571_heat_dynamic_serial_*.json'),key=lambda p:p.stat().st_mtime)
            record=json.loads(latest.read_text('utf8'))
            if record.get('restored') is not True or record.get('cleanup_error'):raise
