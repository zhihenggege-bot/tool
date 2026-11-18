"""Live PID checks against the specification equation, with read-only SWD.

Inputs are legal configuration/temperature calibration. DWARF locates static
PID state from the selected AXF. Reading it identifies real scan edges including
deadband ticks; the core is never halted and PID state is never written.
"""
from heat_dynamic_board_20261106 import *
import struct,sys
from fractions import Fraction as F

def trunc(v):return abs(v.numerator)//v.denominator*(1 if v>=0 else -1)

def expected_step(before,error,kp,ti,td,period,width):
    h=[error,before['history'][0],before['history'][1]]
    if before['valid']<2:return {'n':0,'z':0,'residual':0,'history':h,'valid':before['valid']+1,'bx':None}
    if abs(error)*4<width:
        return {'n':before['n'],'z':0,'residual':0,'history':h,'valid':before['valid'],'bx':None}
    n=before['n'];bx=F(1,10) if n<=100 else F(2,10) if n<=200 else F(4,10) if n<=400 else F(6,10) if n<=500 else F(1)
    # The original equation uses Celsius and normalised demand. Converting
    # deci-Celsius and demand/1000 gives this exact rational increment.
    expression=F(error-before['history'][0])+F(period,ti)*error+F(td,period)*(error-2*before['history'][0]+before['history'][1])
    milli_increment=trunc(1000*kp*bx*expression)
    accumulated=before['residual']+milli_increment
    z=trunc(F(accumulated,1000));n=max(0,min(1000,n+z))
    res=accumulated-z*1000
    if (n==0 and accumulated<0) or (n==1000 and accumulated>0):res=0
    return {'n':n,'z':z,'residual':res,'history':h,'valid':before['valid'],'bx':str(bx)}

class PidReader:
    def __init__(self,b,family):
        self.b=b;self.family=family;self.fn='PreHeatControl' if family=='preheat' else 'HeatControl_UP'
        sys.path.insert(0,str(R/'.codex-tmp/defrost_test_deps'))
        from elftools.elf.elffile import ELFFile
        self.addr={}
        with (I/(BOARDS[2][-1]+'.axf')).open('rb') as f:
            elf=ELFFile(f);di=elf.get_dwarf_info()
            for cu in di.iter_CUs():
                for die in cu.iter_DIEs():
                    name=die.attributes.get('DW_AT_name')
                    if die.tag!='DW_TAG_subprogram' or not name or name.value.decode()!=self.fn:continue
                    for v in die.iter_children():
                        name=v.attributes.get('DW_AT_name');loc=v.attributes.get('DW_AT_location')
                        if name and loc and isinstance(loc.value,list) and len(loc.value)==5 and loc.value[0]==3:
                            self.addr[name.value.decode()]=int.from_bytes(bytes(loc.value[1:]),'little')
        assert all(k in self.addr for k in ('hist','demand','count','validSamples','residualMilli')),self.addr
        self.session=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1],target_override=BOARDS[2][2],
            options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
        self.session.open();self.t=self.session.target
        b.log.setdefault('pid_symbols',{})[family]=self.addr;b.save()

    def close(self):self.session.close()

    def read(self):
        if hasattr(self,'injector'):self.injector.pump()
        base=min(self.addr[k] for k in ('demand','count','validSamples','residualMilli'))
        end=max(self.addr[k]+(8 if k=='residualMilli' else 4) for k in ('demand','count','validSamples','residualMilli'))
        for _ in range(15):
            raw=bytes(self.t.read_memory_block8(base,end-base))
            h=list(struct.unpack('<3i',bytes(self.t.read_memory_block8(self.addr['hist'],12))))
            cnt=self.t.read32(self.addr['count']);n=self.t.read32(self.addr['demand'])
            got=lambda k,fmt:struct.unpack_from(fmt,raw,self.addr[k]-base)[0]
            if cnt==got('count','<I') and n==got('demand','<i'):
                return {'t':time.monotonic(),'n':got('demand','<i'),'count':cnt,'valid':got('validSamples','<B'),
                    'residual':got('residualMilli','<q'),'history':h}
        raise AssertionError('could not obtain coherent live PID state')

    def phase(self,label,seconds,kp,ti,td,period,width):
        phase={'label':label,'started':now(),'parameters':{'kp':kp,'ti':ti,'td':td,'T':period,'width':width},
               'ticks':[],'observations':[],'missed_scan_gaps':[]}
        prior=self.read();start=prior['t'];last_tick=None
        while time.monotonic()-start<seconds:
            s=self.read();phase['observations'].append(s)
            changed=(s['count']<prior['count'] or s['history']!=prior['history'] or s['valid']!=prior['valid'] or s['n']!=prior['n'] or s['residual']!=prior['residual'])
            if changed:
                if s['t']-prior['t']>period*.85:phase['missed_scan_gaps'].append([prior,s])
                want=expected_step(prior,s['history'][0],kp,ti,td,period,width)
                got={k:s[k] for k in ('n','residual','history','valid')}
                match=all(got[k]==want[k] for k in got)
                zreg=930 if self.family=='preheat' else 928
                z=signed16(self.b.rd(zreg)[0]);out=self.b.sample_heat(label)
                if self.family=='preheat':output_match=out['ao'][1]==s['n']
                else:
                    channel=9 if self.b.rd(236)[0]==0 and self.b.rd(129)[0]==0 else 0
                    output_match=out['ao'][channel]==s['n']
                tick={'before':prior,'after':s,'expected':want,'actual_z':z,'formula_matches':match and z==want['z'],
                      'output_matches':output_match,'output':out,
                      'observed_period_s':None if last_tick is None else s['t']-last_tick}
                phase['ticks'].append(tick);last_tick=s['t']
                print('PID',self.family,label,'N',s['n'],'E',s['history'][0],'Z',z,'OK',tick['formula_matches'],flush=True)
            prior=s;time.sleep(.035)
        phase['passed']=bool(phase['ticks']) and not phase['missed_scan_gaps'] and all(x['formula_matches'] and x['output_matches'] for x in phase['ticks'])
        self.b.log.setdefault('pid_phases',[]).append(phase);self.b.save()
        return phase

def run_family(family):
    b=HeatBench('pid_'+family);reader=None
    reg=350 if family=='preheat' else 347
    widthreg=376 if family=='preheat' else 120
    ch=3 if family=='preheat' else 0
    target=100 if family=='preheat' else 250
    first=25 if family=='preheat' else 17
    try:
        b.setup(1 if family!='reheat' else 0)
        b.config({125:0,126:0,127:1 if family in ('reheat','auxiliary') else 0,128:0 if family in ('preheat','reheat') else 1 if family=='auxiliary' else 2,
            129:0 if family=='reheat' else 1,332:1 if family in ('reheat','auxiliary') else 0,333:1 if family=='preheat' else 0,
            334:0,315:0,160:250,161:250,346:0,374:1 if family=='preheat' else 0,
            375:100,376:40,120:20,412:1,reg:10,reg+1:1,reg+2:0,
            329:2,330:0,331:0})
        if family=='auxiliary':b.config({315:1,327:1,318:0,319:120,12:500})
        b.temperature(2,0 if family=='auxiliary' else 50)
        reader=PidReader(b,family)
        b.temperature(ch,target-10)
        b.start()
        if family=='auxiliary':
            b.log['full_load_precondition']=b.wait('auxiliary all four actual compressor feedback',
                lambda s:all(x==3 for pair in s['outdoor_status'] for x in pair),170)
            # Ordinary output selection resets this controller without touching
            # compressor feedback/demand/timers; other equipment keeps running.
            b.config({332:0});time.sleep(.3);b.config({332:1})
        phases=[]
        def phase(label,duration,kp=10,ti=1,td=0,T=1,width=None):
            width=(40 if family=='preheat' else 20) if width is None else width
            b.config({reg:kp,reg+1:ti,reg+2:td,412:T,widthreg:width})
            p=reader.phase(label,duration,kp,ti,td,T,width);phases.append(p);return p
        p=phase('initial_positive_ramp',39,width=20)
        ticks=p['ticks'];init=ticks[:2]
        b.record_local(f'T11-{first:03d}',p['passed'] and len(init)==2 and all(x['after']['n']==0 for x in init),
            f'{family}首次历史建立与第三周期，实际采集{len(ticks)}拍；逐拍按规格公式核算，异常{sum(not x["formula_matches"] for x in ticks)}。',{'phases':[p]})
        b.record_local(f'T11-{first+1:03d}',p['passed'] and max(x['after']['n'] for x in ticks)==1000,
            f'{family}持续正误差真实加载至1000，真实BX分段={sorted({x["expected"]["bx"] for x in ticks if x["expected"]["bx"]})}。',{'phases':[p]})
        # Reduce the gain for reversal to observe the upper unloading states.
        b.config({reg:1});b.temperature(ch,target+10)
        q=phase('negative_unload',36,kp=10,width=20)
        b.record_local(f'T11-{first+2:03d}',q['passed'] and q['ticks'][-1]['after']['n']==0,
            f'{family}负误差减载至0，{len(q["ticks"])}个真实扫描，逐拍公式与输出检查。',{'phases':[q]})
        b.temperature(ch,target-10);a=phase('prepare_nonsaturated_deadband',20,kp=5,ti=1,width=40)
        limits_ok=(p['passed'] and q['passed'] and a['passed'] and
            any(t['after']['n']==1000 for t in p['ticks']) and
            any(t['after']['n']==0 for t in q['ticks']) and
            any(t['after']['n']>0 for t in a['ticks']))
        b.record_local(f'T11-{first+7:03d}',limits_ok,
            f'{family}上限1000保持后负误差卸载、下限0保持后正误差重新加载，逐拍检查夹限及饱和余数回退。',
            {'phases':[p,q,a]})
        boundary=[]
        for error in (0,9,-9,10,-10):
            b.temperature(ch,target-error)
            boundary.append(phase('deadband_E_requested_'+str(error),4,kp=5,ti=100,width=40))
        b.record_local(f'T11-{first+3:03d}',all(x['passed'] for x in boundary),
            f'{family}非饱和死区/等号两侧，实际采到E={sorted({t["after"]["history"][0] for p in boundary for t in p["ticks"]})}；严格abs(E)*4<幅差才冻结，逐拍比较。',{'phases':boundary})
        b.temperature(ch,target-10)
        differential=phase('nonzero_derivative',4,kp=13,ti=41,td=7,width=20)
        for e in (20,-10,0,10):
            b.temperature(ch,target-e)
            differential2=phase('derivative_error_'+str(e),4,kp=13,ti=41,td=7,width=20)
        ds=[p for p in phases if p['parameters']['td']==7]
        b.record_local(f'T11-{first+5:03d}',all(p['passed'] for p in ds),
            f'{family}Kp13/Ti41/Td7，正负及零误差动态共{sum(len(p["ticks"]) for p in ds)}拍，按原始增量公式核对。',{'phases':ds})
        timing=[]
        for period in (1,5,10):
            b.temperature(ch,target-10)
            timing.append(phase('real_scan_period_'+str(period),period*3+1,kp=1,ti=100,T=period,width=20))
        periods=[(p['parameters']['T'],[round(t['observed_period_s'],3) for t in p['ticks'] if t['observed_period_s'] is not None]) for p in timing]
        timing_ok=all(p['passed'] and all(abs(t['observed_period_s']-p['parameters']['T'])<.25 for t in p['ticks'] if t['observed_period_s'] is not None) for p in timing)
        b.record_local(f'T11-{first+6:03d}',timing_ok,f'{family}真实T=1/5/10秒扫描间隔={periods}；未改计数器。',{'phases':timing})
        # BX coverage is based on observed preceding demand, with explicit
        # lists of exact boundaries still missing rather than seeded PID RAM.
        ts=[t for p in phases for t in p['ticks']]
        bx={t['expected']['bx'] for t in ts if t['expected']['bx']}
        seen={t['before']['n'] for t in ts}
        exact={x:x in seen for x in (100,101,200,201,400,401,500,501)}
        b.record_local(f'T11-{first+4:03d}',all(p['passed'] for p in phases) and bx=={'1/10','1/5','2/5','3/5','1'},
            f'{family}真实BX五档={sorted(bx)}，精确需求边界覆盖={exact}；未覆盖的精确点仍待补，未直接写PID状态。',{'phases':phases,'exact_boundary_coverage':exact})
        if family=='auxiliary':
            full=b.sample('auxiliary still full prior to unload')
            full_ok=all(x==3 for pair in full['outdoor_status'] for x in pair)
            b.record_local('T11-085',full_ok and all(p['passed'] for p in phases),
                '两外机四压机真实反馈均3时完成辅热PID正负误差、死区、微分和扫描周期动态；辅热输出按实际PID需求变化。',
                {'full':full,'pid_phases':phases})
            b.temperature(2,60)
            reduced=b.wait('auxiliary non-full must close',lambda s:
                any(x!=3 for pair in s['outdoor_status'] for x in pair) and s['ao'][0]==0 and b.rd(890)[0]==0,100)
            hold=b.observe('auxiliary non-full hold',4)
            ok=all(s['ao'][0]==0 and s['diag'][18]==0 for s in hold)
            b.record_local('T11-086',ok,'正常环境负荷减至非满载后，辅热需求及DA0归零并保持；未写压机状态或辅热需求。',
                {'before':full,'after':reduced,'hold':hold})
        b.log['all_pid_phases_passed']=all(p['passed'] for p in phases)
    except Exception:
        b.log['error']=traceback.format_exc();b.save();raise
    finally:
        if reader:reader.close()
        b.finish();print('PID RESTORED',family,b.log.get('restored'),b.path,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--families',nargs='+',default=['main','reheat','auxiliary','preheat'])
    args=p.parse_args()
    # The first ramp's sign reversal skipped an upper unloading plateau.
    # Repeat only the affected three binary 1:2:4 cases with slower reversal.
    curves(['main','shared','independent'],kinds=(3,))
    if runtime.EXPECTED[2]>=53:
        # Recheck all preheat selections after the shared enforcement-layer fix.
        curves(['preheat'],kinds=(1,2,3,4))
    for family in args.families:run_family(family)
