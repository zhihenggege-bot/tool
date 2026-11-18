"""EEV dynamic board checks through normal pressure mapping/NTC calibration.

SWD only reads exact-image symbols. No PID, output, request or timer writes.
Inputs are software engineering maps, not a pressure calibrator/valve terminal.
"""
from remaining_pid_live_20261106 import *


class EevReader:
    def __init__(self, b, channel=2):
        self.b, self.ch = b, channel
        self.sy = b.sy
        self.ss = ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1],target_override=BOARDS[2][2],
            options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
        self.ss.open()
        self.t = self.ss.target
        self.a = dict(history=self.sy['EEVSpecErrHist'][0]+channel*12,
                      count=self.sy['EEVSpecPidCount'][0]+channel*4,
                      valid=self.sy['EEVSpecValidSamples'][0]+channel,
                      residual=self.sy['EEVSpecResidualMilli'][0]+channel*8)
        from elftools.elf.elffile import ELFFile
        from elftools.dwarf.dwarf_expr import DWARFExprParser
        with (I/(BOARDS[2][-1]+'.axf')).open('rb') as f:
            elf = ELFFile(f)
            expr = DWARFExprParser(elf.get_dwarf_info().structs)
            def member_offset(attribute):
                if isinstance(attribute.value, int):
                    return attribute.value
                ops = expr.parse_expr(attribute.value)
                assert len(ops)==1 and ops[0].op_name=='DW_OP_plus_uconst', ops
                return ops[0].args[0]
            for cu in elf.get_dwarf_info().iter_CUs():
                for die in cu.iter_DIEs():
                    n = die.attributes.get('DW_AT_name')
                    if die.tag=='DW_TAG_structure_type' and n and n.value==b'UNIT_STATUS_STRU_Read' and 'DW_AT_byte_size' in die.attributes:
                        self.stride = die.attributes['DW_AT_byte_size'].value
                        self.offsets = {v.attributes['DW_AT_name'].value.decode():member_offset(v.attributes['DW_AT_data_member_location'])
                                        for v in die.iter_children() if v.tag=='DW_TAG_member'}
                        break
                if hasattr(self,'stride'): break
        assert hasattr(self,'stride')
        self.unit = channel//2+1
        self.comp = channel%2
        self.unitbase = self.sy['UnitReadStatus'][0]+self.unit*self.stride
        b.log['eev_reader_symbols'] = dict(fields=self.a, stride=self.stride, offsets=self.offsets)
        b.save()

    def close(self): self.ss.close()

    def read(self):
        t = self.t
        for _ in range(15):
            c = t.read32(self.a['count'])
            raw = bytes(t.read_memory_block8(self.a['history'],12))
            valid = t.read8(self.a['valid'])
            res = struct.unpack('<q',bytes(t.read_memory_block8(self.a['residual'],8)))[0]
            new = signed16(t.read16(self.sy['Parameter'][0]+(1145+self.ch)*2))
            current = signed16(t.read16(self.sy['Parameter'][0]+(1153+self.ch)*2))
            bii = list(struct.unpack('<4h',bytes(t.read_memory_block8(self.unitbase+self.offsets['BII'],8))))
            if c==t.read32(self.a['count']) and raw==bytes(t.read_memory_block8(self.a['history'],12)):
                return dict(t=time.monotonic(),count=c,history=list(struct.unpack('<3i',raw)),valid=valid,
                            residual=res,new=new,current=current,superheat=bii[self.comp],evap=bii[2+self.comp])
        raise AssertionError('EEV coherent acquisition failed')

    def phase(self,label,seconds,kp=5,ti=100,td=0,T=1,dead=20,limit=20):
        b = self.b
        b.config({368:kp,369:ti,370:td,16:T,367:dead,371:limit})
        phase = dict(label=label,parameters=dict(kp=kp,ti=ti,td=td,T=T,dead=dead,limit=limit),ticks=[])
        before = self.read()
        began = time.monotonic()
        while time.monotonic()-began < seconds:
            after = self.read()
            if after['count'] < before['count'] or any(after[k]!=before[k] for k in ('valid','history','residual')):
                e,e1,e2 = after['history']
                raw = F(kp,10)*(e-e1+F(T,ti)*e+F(td,T)*(e-2*(e-e1)+e2))
                acc = before['residual']+trunc(raw*1000)
                step = trunc(F(acc,1000))
                residual = acc-step*1000
                if before['valid']<2:
                    step = -min(limit,5) if after['evap']>120 else 0
                    residual = before['residual']
                elif after['evap']>120 and acc>=0:
                    step,residual = -5,0
                elif 100<=after['evap']<=120 and acc>=0:
                    step,residual = 0,0
                elif abs(e)*2<=dead:
                    step,residual = 0,0
                if step>limit or (step==limit and residual>0): step,residual=limit,0
                if step<-limit or (step==-limit and residual<0): step,residual=-limit,0
                # The driver can move between the last pre-scan read and the
                # first post-scan read. Retain the bracket rather than invent
                # a single instantaneous actual valve position.
                low,high = sorted((before['current'],after['current']))
                expected_range = [max(0,min(500,v+step)) for v in (low,high)]
                output = expected_range[0]<=after['new']<=expected_range[1]
                if (after['new']>=500 and step>0) or (after['new']<=0 and step<0): residual=0
                expected_hist = [e]+before['history'][:2]
                formula = after['residual']==residual and after['history']==expected_hist and after['valid']==min(2,before['valid']+1)
                gap = round((after['t']-before['t']+(before['count']-after['count'])/10)/T) if after['t']-before['t']>.85*T else 1
                tick = dict(before=before,after=after,raw_increment=str(raw),accumulated_milli=acc,step=step,
                            expected_residual=residual,expected_target_range=expected_range,
                            formula_matches=formula,output_matches=output,estimated_scan_edges=gap)
                phase['ticks'].append(tick)
                print('EEV LIVE',label,'SH',after['superheat'],'evap',after['evap'],'step',step,
                      'target',after['new'],'formula',formula,'output',output,flush=True)
            before=after
            time.sleep(.02)
        phase['passed'] = bool(phase['ticks']) and all(t['formula_matches'] and t['output_matches'] and t['estimated_scan_edges']==1 for t in phase['ticks'])
        b.log.setdefault('eev_phases',[]).append(phase)
        b.save()
        return phase


def main(midpoints=False,startups=False):
    b = HeatBench('eev_startup_and_caps' if startups else 'eev_live_midpoints' if midpoints else 'eev_live_matrix')
    reader = outss = None
    originals = {}
    try:
        unit = 2
        from elftools.elf.elffile import ELFFile
        with (I/(BOARDS[1][-1]+'.axf')).open('rb') as f:
            elf=ELFFile(f)
            sy={s.name:(s['st_value'],s['st_size']) for s in elf.get_section_by_name('.symtab').iter_symbols()}
            # Load the selected refrigerant table directly from its ELF segment.
            def load_symbol(name):
                addr,size=sy[name]
                for seg in elf.iter_segments():
                    if seg['p_vaddr']<=addr and addr+size<=seg['p_vaddr']+seg['p_filesz']:
                        raw=seg.data()[addr-seg['p_vaddr']:addr-seg['p_vaddr']+size]
                        return list(struct.unpack('<'+'h'*(size//2),raw))
                raise AssertionError(name)
            tables={n:load_symbol(n) for n in ('R22Temp','R134ATemp','R407CTemp','R410ATemp')}
        outss=ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[1][1],target_override=BOARDS[1][2],
            options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
        outss.open()
        ot=outss.target
        def p16(reg):return signed16(ot.read16(sy['Parameter'][0]+reg*2))
        def gw(addr,value, target_reg):
            if addr not in originals: originals[addr]=dict(value=signed16(b.rd(addr)[0]),target_reg=target_reg)
            if p16(target_reg)==value and signed16(b.rd(addr)[0])==value:return
            state_reg=1830+(unit-1)*48+43
            began=time.monotonic()
            while b.rd(state_reg)[0]==1:
                assert time.monotonic()-began<45
                time.sleep(.2)
            b.log.setdefault('outdoor_configuration_writes',[]).append(dict(at=now(),address=addr,target_register=target_reg,value=value,before=p16(target_reg)))
            b.save()
            b.c.write_single_register(1,addr,value&65535)
            began=time.monotonic()
            while not(p16(target_reg)==value and signed16(b.rd(addr)[0])==value and b.rd(state_reg)[0]!=1):
                assert time.monotonic()-began<50,('gateway confirmation',addr,value,p16(target_reg))
                time.sleep(.2)
        def stimulus(evap,superheat):
            ref=b.rd(39)[0]
            table=tables[('R22Temp','R134ATemp','R407CTemp','R410ATemp')[ref]]
            candidates=[]
            for pressure in range(200,1600):
                j=(pressure+100)//5
                val=table[j]+trunc(F((pressure%5)*(table[j+1]-table[j]),5))
                if val==evap:candidates.append(pressure)
            assert candidates,('temperature not representable in pressure table',evap)
            pressure=candidates[len(candidates)//2]
            base=2680+(unit-1)*49+2*12
            # A legal 1kPa engineering span produces a stable exact pressure using
            # the genuine ADC->scale->filter->saturation->protocol path.
            if pressure >= p16(330):
                gw(base+5,pressure+1,331)
                gw(base+4,pressure,330)
            else:
                gw(base+4,pressure,330)
                gw(base+5,pressure+1,331)
            caladdr=2534+(unit-1)*16+5
            actual=signed16(ot.read16(sy['AI'][0]+11*2))
            offset=p16(488)+(evap+superheat)-actual
            assert -100<=offset<=100,('suction target outside legal NTC calibration',evap+superheat,offset)
            gw(caladdr,offset,488)
            began=time.monotonic()
            while True:
                s=reader.read()
                if s['evap']==evap and s['superheat']==superheat:break
                assert time.monotonic()-began<15,('input chain not settled',evap,superheat,s)
                time.sleep(.1)
            b.log.setdefault('input_chain',[]).append(dict(at=now(),pressure=pressure,evap=evap,superheat=superheat,
                suction=signed16(ot.read16(sy['AI'][0]+11*2)),calibration=offset,received=s))
            b.save()
        b.setup(0)
        b.config({128:1,127:0,332:0,333:0,334:0,125:0,126:0,248:0,315:0,320:0,346:0,
                  160:250,161:250,412:1,416:100,417:1,418:0,329:2,330:0,331:0,
                  365:1,366:50,367:20,368:5,369:100,370:0,16:1,411:200,371:20,12:500,372:350})
        b.temperature(0,290)
        reader=EevReader(b)
        if startups:
            from remaining_eev_startup_live_20261106 import run
            run(b,reader,stimulus)
            return
        b.start()
        b.wait('EEV cold four real compressor feedback',lambda s:all(v==2 for pair in s['outdoor_status'] for v in pair),170)
        began=time.monotonic()
        while reader.read()['valid']<2:
            assert time.monotonic()-began<60
            time.sleep(.1)
        if not midpoints:
            for index,sh in enumerate((39,40,41,50,59,60,61,100,0)):
                stimulus(50,sh)
                phase=reader.phase('SH_'+str(sh),6)
                exact=all(t['after']['superheat']==sh and t['after']['evap']==50 for t in phase['ticks'])
                # The target must be away from end stops to claim the directional
                # part of the acceptance; record saturation explicitly otherwise.
                saturated=any(t['before']['current'] in (0,500) for t in phase['ticks'])
                cid=f'T12-{6+index:03d}'
                b.record_local(cid,phase['passed'] and exact,
                    f'回路3压力映射模拟→316滤波/饱和温度→过热协议→330 PID，蒸发5℃/SH{sh/10:.1f}℃；'
                    f'{len(phase["ticks"])}真实扫描，公式及软件目标步数匹配={phase["passed"]}；曾到端点={saturated}。'
                    '阀机械位置/驱动脉冲未测；中位方向若遇端点仍需补。',
                    {'passed':phase['passed'] and exact,'phase':phase,'exact_input':exact,'saturated':saturated})
        # The positive/negative A/B branches are observed with real retained
        # histories. Do not assign a sign from SH alone.
        for i,evap in enumerate((99,100,120,121)):
            for negative in (False,True):
                if midpoints:
                    stimulus(50,100)
                    prepare=reader.phase('prepare_mid_'+str(evap)+'_'+str(negative),8,kp=100,ti=1,limit=50)
                    assert prepare['passed'], prepare
                    current=reader.read()['current']
                    if not 150<=current<=350:
                        stimulus(50,0)
                        unload=reader.phase('prepare_mid_unload_'+str(evap)+'_'+str(negative),6,kp=100,ti=1,limit=50)
                        assert unload['passed'],unload
                        stimulus(50,50)
                        settle=reader.phase('prepare_mid_hold_'+str(evap)+'_'+str(negative),2)
                        assert settle['passed'],settle
                        current=reader.read()['current']
                    assert 50<current<450, ('not at middle valve position',current)
                stimulus(evap,80 if not negative else 20)
                p=reader.phase('evap_'+str(evap)+('_negative' if negative else '_nonnegative'),7,kp=10,ti=1)
                selected=[t for t in p['ticks'] if (t['accumulated_milli']<0)==negative and t['before']['valid']==2]
                middle=[t for t in selected if 0<t['before']['current']<500]
                passed=p['passed'] and bool(selected) and (not midpoints or bool(middle))
                cid=f'T12-{15+i*2+int(negative):03d}'
                b.record_local(cid,passed,f'蒸发{evap/10:.1f}℃、原增量'+('负' if negative else '非负')+
                    f'分支：实际{len(selected)}拍满足原始增量符号，中位观察{len(middle)}拍；A/B/C覆盖与软件目标匹配={p["passed"]}；压力工程映射和合法吸气NTC校准，非物理信号源。',
                    {'passed':passed,'phase':p,'qualifying_ticks':len(selected)})
        if midpoints:
            limited=[]
            for limit in (3,20,50):
                for sh in (100,0):
                    stimulus(50,sh)
                    phase=reader.phase('limit_'+str(limit)+'_SH_'+str(sh),5,kp=100,ti=1,limit=limit)
                    matches=[t for t in phase['ticks'] if t['step']==(limit if sh==100 else -limit)]
                    assert phase['passed'] and matches, phase
                    limited.append(phase)
            b.record_local('T12-025',True,'每周期限幅3/20/50步分别实测正、负原始增量；6组真实扫描均产生对应限幅步数，公式、余数及软件目标符合。压力工程映射与合法吸气校准，机械步数及脉冲未测。',{'passed':True,'phases':limited})
        if not midpoints:
            stimulus(50,70)
            derivative=[]
            for sh in (50,50,70,60,80,60,50):
                stimulus(50,sh)
                derivative.append(reader.phase('Td10_SH_'+str(sh),5,kp=5,ti=100,td=10))
            ok=all(p['passed'] for p in derivative)
            b.record_local('T12-024',ok,'Td10按原文E−2×(E−E1)+E2逐拍核对，SH5/5/7/6/8/6/5℃；正常输入校准，无PID历史写入；软件步数证据。',{'passed':ok,'phases':derivative})
    except Exception:
        b.log['error']=traceback.format_exc()
        b.save()
        raise
    finally:
        try:
            for addr,item in originals.items():gw(addr,item['value'],item['target_reg'])
            b.log['outdoor_configuration_restored']={str(a):p16(v['target_reg'])==v['value'] and signed16(b.rd(a)[0])==v['value'] for a,v in originals.items()}
            b.save()
            assert all(b.log['outdoor_configuration_restored'].values())
        finally:
            if reader:reader.close()
            if outss:outss.close()
            b.finish()
        print('EEV LIVE RESTORED',b.log.get('restored'),b.path,flush=True)


if __name__=='__main__':main()
