"""Priority current-firmware board tests. No source edits, flashing or state pokes."""
from nonvent_defrost_v1055_20261109 import *
from joint_precondition_20261110 import DAY,symbols

class TodayBench(DefrostBench):
    def __init__(self,name):
        super().__init__(name)
        self.path=DAY/(name+'_'+time.strftime('%H%M%S')+'.json')
        self.log.update(today=now(),firmware_changed=False,limitations='BENCH software outputs and command/input simulation; no physical terminal measurement or production timing')
        self.extra=[];self.log['gateway_original']=self.gateway_original;self.save()

    def wr(self,a,value):
        try:return super().wr(a,value)
        except AssertionError:
            if a!=236:raise
            began=time.monotonic()
            while self.rd(a)[0]!=(value&65535):
                assert time.monotonic()-began<3,('mode command did not settle',a,value,self.rd(a));time.sleep(.1)
            self.log.setdefault('mode_async_readbacks',[]).append(dict(at=now(),address=a,value=value));self.save()

    def gateway(self,a,value):
        if a not in self.gateway_original:self.gateway_original[a]=self.rd(a)[0]
        assert 1830<=a<1872
        state=1873;began=time.monotonic()
        while self.rd(state)[0]==1:
            assert time.monotonic()-began<45;time.sleep(.2)
        target=165+a-1830
        if self.rd(a)[0]!=value:
            for attempt in range(3):
                try:self.c.write_single_register(1,a,value&65535);break
                except Exception as ex:
                    self.log.setdefault('protocol_write_exceptions',[]).append(dict(at=now(),address=a,value=value,attempt=attempt,error=repr(ex)));self.save()
                    time.sleep(.3)
                    if self.rd(a)[0]==value:break
                    if attempt==2:raise
        began=time.monotonic()
        while True:
            dest=signed16(self.ot.read16(self.outsy['Parameter'][0]+target*2))
            echo=signed16(self.rd(a)[0]);status=self.rd(state)[0]
            if dest==value and echo==value and status!=1:break
            assert time.monotonic()-began<50,('gateway',a,value,echo,dest,status)
            time.sleep(.15)
        self.log.setdefault('gateway_writes',[]).append(dict(at=now(),address=a,value=value,destination_parameter=target,destination=dest,status=status));self.save()

    def attach_extra(self):
        for board in (BOARDS[1],BOARDS[2]):
            ss=ConnectHelper.session_with_chosen_probe(unique_id=board[1],target_override=board[2],options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
            ss.open();self.extra.append((board,ss,symbols(board)))

    def detailed(self,label):
        s=self.sample(label);s['direct']=[]
        for name,ss,sy in [(BOARDS[0],self.outss,self.outsy)]+self.extra:
            t=ss.target;p=sy['Parameter'][0]
            row=dict(board=name[0],params={str(a):t.read16(p+a*2) for a in ((1,1400,1402,1403,1406,1409,1410,1420,1421,1501) if name[0]!='330' else (1,236,398,524,1406))})
            for key in ('Comp','PSC316DefrostState','PSC316DefrostStateTime','PSC316DefrostRunTime','PSC316DefrostEligible','PSC316DefrostEnded','PSC316DefrostStarted','PSC316DefrostOwner','CompRunTime','CompStopTime','DefGapCount','output'):
                if key in sy:
                    addr,n=sy[key];row[key]=list(t.read_memory_block8(addr,n))
            s['direct'].append(row)
        self.log.setdefault('detailed_samples',[]).append(s);return s

    def finish(self):
        self._cleaning_up=True
        try:
            for a,v in self.polarities.items():
                if a in self.touched:self.c.write_single_register(1,a,v)
            self.wr(398,0);self.reset_faults()
            if self.rd(709)[0]!=0 and any(x==8 for x in self.rd(1550,2)):
                indoor_session=self.swd or next((ss for board,ss,_ in self.extra if board[0]=='330'),None)
                manual_defrost(self,False,session=indoor_session)
            self.stop()
            # Valid mode selection clears the lifecycle; never write phase RAM.
            self.config({236:0});began=time.monotonic()
            while True:
                s=self.sample('normal stopped-mode recovery')
                if s['phase']==[0,0] and s['state'][9]==0 and loads_off(s):break
                assert time.monotonic()-began<50,('cleanup lifecycle',s)
                time.sleep(.5)
            for a,v in list(self.gateway_original.items()):self.gateway(a,v)
            self.log['gateway_restored']={str(a):self.rd(a)[0]==v for a,v in self.gateway_original.items()}
            assert all(self.log['gateway_restored'].values())
        except BaseException:self.log['today_cleanup_error']=traceback.format_exc();self.save();raise
        finally:
            for _,ss,_ in self.extra:ss.close()
            self.extra=[]
            if self.outss:self.outss.close();self.outss=None
            # [1] is derived from valid [236], never restore it as a control.
            self.touched.discard(1)
            CheckedBench.finish(self)

def emergency():
    b=TodayBench('O-DEFROST-020_T16-005_emergency')
    e=dict(started=now(),ids=['O-DEFROST-020','T16-005'],status='running',observations=[])
    b.log['priority_case']=e;b.save()
    try:
        e['active']=b.prepare();b.attach_extra();e['before']=b.detailed('active defrost before fire')
        b.wr(156,1-b.polarities[156]);began=time.monotonic();first_off=None
        while time.monotonic()-began<22:
            s=b.detailed('fire emergency, heat mode retained');e['observations'].append(s)
            off=s['state'][9]==0 and loads_off(s) and s['outdoor_comp']==[0,0]
            if off and first_off is None:first_off=time.monotonic()-began
            assert time.monotonic()-began<15 or off,('emergency outputs failed to close',s)
            b.save();time.sleep(.2)
        e['outputs_off_after_s']=first_off
        assert first_off is not None
        last=e['observations'][-1]
        e['status']='不符合：负载关闭后化霜阶段仍为8' if last['phase']==[8,8] else '未复现阶段8残留'
        e['final_fire_sample']=last
        print('CASE RESULT',e['status'],'phase',last['phase'],'Comp',last['outdoor_comp'],'off_after',first_off,flush=True)
    except BaseException:e['execution_error']=traceback.format_exc();b.save();raise
    finally:
        try:b.finish()
        finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)

def parameters():
    b=TodayBench('O-PARAM-008_minfreq')
    e=dict(started=now(),ids=['O-PARAM-008'],status='running',requests=[])
    b.log['priority_case']=e;b.save()
    try:
        assert loads_off(b.snapshot('stopped parameter checks'))
        e['tables']={}
        for k in ('Parameter_min','Parameter_def','Parameter_max'):
            e['tables'][k]=b.ot.read16(b.outsy[k][0]+177*2)
        b.gateway_original[1842]=b.rd(1842)[0]
        for v in (0,5,30):
            began=time.monotonic()
            while b.rd(1873)[0]==1:
                assert time.monotonic()-began<45;time.sleep(.2)
            r=dict(at=now(),requested=v,before=b.rd(1842)[0]);e['requests'].append(r);b.save()
            b.c.write_single_register(1,1842,v)
            began=time.monotonic()
            while True:
                diag=b.rd(1872,6)
                if diag[1]!=1 and time.monotonic()-began>=1:break
                assert time.monotonic()-began<45,diag
                time.sleep(.15)
            time.sleep(.6)
            r.update(at_after=now(),mirror=b.rd(1842)[0],destination=b.ot.read16(b.outsy['Parameter'][0]+177*2),gateway_diag=b.rd(1872,6))
            print('MINFREQ',r,flush=True);b.save()
        e['status']='不符合：板上参数默认及上下限与规格不同'
        e['first_eeprom_default_not_erased']=True
    except BaseException:e['execution_error']=traceback.format_exc();b.save();raise
    finally:
        try:b.finish()
        finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)

def fans(restart_observation=6,minimum_run=10):
    b=TodayBench('O-FANTIME_prestart_six_pairs')
    e=dict(started=now(),status='running',pairs=[],scope='316 normal request INPUT simulation while 330 stopped; runtime/counters/outputs read-only; six legal type pairs')
    b.log['priority_case']=e;b.save()
    def request(value):
        for a in (1400,1403):b.ot.write16(b.outsy['Parameter'][0]+2*a,value)
        b.ot.flush()
    def read():
        t=b.ot;sy=b.outsy;p=sy['Parameter'][0]
        q=dict(at=now(),t=time.monotonic(),tick=t.read32(sy['Systick_1ms'][0]),output=list(t.read_memory_block8(sy['output'][0],8)),params={str(a):t.read16(p+a*2) for a in (1,165,166,179,180,1400,1403,1406,1422,1425,1426,1501)})
        for k in ('OutdoorPrestartOwnsFans','OutdoorFanStopSeconds','OutdoorFanRunSeconds','OutdoorFanStopTick','OutdoorFanStopTickValid','OutdoorVfdOn','OutdoorVfdSpeed'):
            if k in sy:
                a,n=sy[k];q[k]=list(t.read_memory_block8(a,n))
        return q
    def active(s,typ):
        o=s['output']
        return [bool(o[2] or (o[7] if typ==0 else 0)),bool(o[3] or (o[7] if typ==3 else 0))]
    def until(label,typ,predicate,timeout,row):
        began=time.monotonic()
        while True:
            s=read();row.setdefault(label,[]).append(s)
            if predicate(s):return s
            assert time.monotonic()-began<timeout,(label,s)
            time.sleep(.08)
    try:
        b.setup(0);b.config({1333:200,1334:100,1337:minimum_run,1338:30})
        for unit,typ in ((0,0),(0,1),(1,2),(1,3),(2,2),(2,4)):
            r=dict(unit_type=unit,fan_type=typ,minimum_run_s=minimum_run,started=now());e['pairs'].append(r);b.save()
            request(0)
            until('before_off',typ,lambda s:not any(active(s,typ)),45,r)
            b.gateway(1830,unit);b.gateway(1831,typ)
            began=time.monotonic()
            while b.ot.read16(b.outsy['Parameter'][0]+179*2)!=minimum_run or b.ot.read16(b.outsy['Parameter'][0]+180*2)!=30:
                assert time.monotonic()-began<30,'shared fan timing not propagated';time.sleep(.2)
            # Configuration changes may clear a request; submit after settling.
            time.sleep(.5);request(1)
            s=until('initial_start',typ,lambda s:any(active(s,typ)),40,r)
            started=time.monotonic()
            while time.monotonic()-started<11:
                r.setdefault('initial_run',[]).append(read());time.sleep(.15)
            request(0)
            # Record each actual output edge, not the mirrored status latency.
            last_on=[None,None];off_edge=[None,None];began=time.monotonic()
            while True:
                s=read();r.setdefault('normal_stop',[]).append(s);on=active(s,typ)
                for i in range(2):
                    if on[i]:last_on[i]=s['t'];off_edge[i]=None
                    elif last_on[i] is not None and off_edge[i] is None:off_edge[i]=s['t']
                if not any(on):break
                assert time.monotonic()-began<45,('fan normal stop',s)
                time.sleep(.08)
            r['off_edges']=off_edge;r['last_on']=last_on
            run_samples=r['initial_start']+r.get('initial_run',[])+r['normal_stop']
            first_on=[next((q['t'] for q in run_samples if active(q,typ)[i]),None) for i in range(2)]
            r['observed_minimum_runs']=[dict(fan=i,seconds=off_edge[i]-first_on[i])
                for i in range(2) if first_on[i] is not None and off_edge[i] is not None]
            r['minimum_run_violations']=[q for q in r['observed_minimum_runs'] if q['seconds']<minimum_run-.5]
            time.sleep(1);request(1);r['restart_request_t']=time.monotonic()
            began=time.monotonic();violations=[]
            while time.monotonic()-began<restart_observation:
                s=read();r.setdefault('restart_window',[]).append(s);on=active(s,typ)
                for i in range(2):
                    if on[i] and off_edge[i] is not None and s['t']-off_edge[i]<29.5:
                        if not any(x['fan']==i for x in violations):violations.append(dict(fan=i,observed_off_seconds=s['t']-off_edge[i],sample=s))
                time.sleep(.08)
            r.update(violations=violations,restart_observation_s=restart_observation,
                     status='不符合：预启动早于最小停机30秒' if violations else
                     f'本次{restart_observation}秒观察窗未见同一风机提前重启；边沿和未运行风机另见逐值记录',finished=now())
            all_samples=run_samples+r['restart_window']
            r['manual_request_compressor_without_fan']=[q for q in all_samples
                if any(q['output'][:2]) and not any(active(q,typ))]
            r['conflicting_speed_samples']=[q for q in all_samples
                if (typ==0 and q['output'][2] and q['output'][7]) or
                   (typ==3 and q['output'][3] and q['output'][7])]
            print('FAN PAIR',unit,typ,r['status'],[(x['fan'],round(x['observed_off_seconds'],3)) for x in violations],flush=True);b.save()
            request(0);until('after_off',typ,lambda s:not any(active(s,typ)),45,r)
        e.update(status='executed_see_per_pair_scope',finished=now())
    except BaseException:e['execution_error']=traceback.format_exc();b.save();raise
    finally:
        try:
            request(0)
            if e['pairs']:
                typ=e['pairs'][-1]['fan_type'];until('final_fan_off',typ,lambda s:not any(active(s,typ)),50,e)
            b.finish()
        finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=('emergency','parameters','fans'),default='emergency',nargs='?');a=p.parse_args()
    {'emergency':emergency,'parameters':parameters,'fans':fans}[a.action]()
