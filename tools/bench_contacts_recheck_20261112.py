"""316 input-polarity simulations for four protection paths on the isolated bench."""
from joint_v1058_context_20261111 import *
from bench_contact_inputs_20261111 import ContactInputs


CONTACTS = [('O-PROTECT-011',0,606,0,True),('O-PROTECT-011',2,607,1,True),
            ('O-PROTECT-013',1,600,0,False),('O-PROTECT-013',3,601,1,False),
            ('O-PROTECT-015',6,626,0,True),('O-PROTECT-015',7,627,1,True),
            ('O-PROTECT-017',4,621,None,True),('O-PROTECT-017',5,622,None,True)]


def run(recheck=False,manual=False,channels=None):
    b=current_bench_class()('B01_contacts_manual' if manual else 'B01_contacts')
    e=b.log['B01_contacts']=dict(cases=[],manual=manual,scope='1# polarity setting simulates active input while a known inactive physical switch is held fixed; no physical contact/timing acceptance')
    t=b.ot; sy=b.outsy; p=sy['Parameter'][0]
    rd316=lambda a:t.read16(p+2*a)
    old={ch:rd316(ch+2) for _,ch,*_ in CONTACTS}
    fixture=None
    e['original_polarities']=old; b.save()

    def snapshot(ch,alarm):
        assert fixture is not None
        s=fixture.sample();s.update(input=s['inputs'][ch],polarity=s['polarities'][ch],
                    mirror=b.rd(2022+alarm-600)[0],mirror_layer=b.rd(2598)[0],
                    latch=b.rd(2618)[0],other=b.rd(1625,2),phase=b.rd(1550,2))
        if b.extra:
            it=b.extra[1][1].target;isy=b.extra[1][2]
            a,n=isy['PSC316WriteJob'];raw=bytes(it.read_memory_block8(a,n))
            import struct
            s['gateway_job']=dict(zip(('active','phase','unit','retry','count','address'),struct.unpack('<4B2H',raw[:8])))
            s['gateway_job']['values']=list(struct.unpack('<10h',raw[8:]))
            s['poll_rounds']=list(it.read_memory_block8(*isy['PSC316PollRound']))
            s['legacy881_884']=list(struct.unpack('<4h',bytes(it.read_memory_block8(isy['Parameter'][0]+2*881,8))))
        return s

    def observe(row,label,seconds,predicate,ch,alarm):
        end=time.monotonic()+seconds; rows=row.setdefault(label,[])
        while time.monotonic()<end:
            s=snapshot(ch,alarm);rows.append(s)
            if predicate(s): return s
            time.sleep(.15)
        raise TimeoutError(label)

    def set_polarity(ch,value):
        issued=fixture.set(ch,value);end=time.monotonic()+4
        while time.monotonic()<end:
            s=fixture.sample(issued)
            if s['polarities'][ch]==value:return issued
        raise TimeoutError(('polarity readback',ch,value))

    try:
        assert b.rd(398)==[0] and b.rd(709)==[0] and not any(b.rd(2598,2))
        b.setup(1)
        b.config({128:1,127:1,129:1,332:1,333:0,334:0,125:0,126:0,248:0,
                  315:0,327:1,160:250,161:250,120:20,412:1,426:100,427:1,
                  428:0,347:100,348:1,349:0,346:0,320:0,245:1,247:0,
                  329:2,330:0,331:0,365:1,372:350,10:500,12:500})
        b.temperature(0,220);b.start()
        b.wait('contact simulations: ordinary 330 heat starts all four',
               lambda s:all(v==3 for pair in s['outdoor_status'] for v in pair),360 if recheck else 180)
        # Diagnostic reads share the test process and close before its final
        # audit; never leave a separate observer holding the debug probe.
        b.attach_extra()
        if manual:
            # The enable is global; explicitly retain the healthy peer's
            # operator commands as well, instead of silently stopping unit2
            # with its otherwise zero per-unit manual block.
            b.config({1301:1,**{a:1 for a in range(1302,1308)},
                      **{a:1 for a in range(1310,1316)},1300:1})
            end=time.monotonic()+40
            while rd316(1300)!=1 or any(rd316(a)!=1 for a in (1302,1303,1304,1305)):
                assert time.monotonic()<end,'normal HMI manual command did not arrive'
                time.sleep(.2)
        fixture=ContactInputs(b,old)
        e['scope']+='; continuous polarity-setting input fixture, no final DI/fault/output/state forcing'
        selected=[c for c in CONTACTS if c[1] in (0,1,6,4)] if manual else CONTACTS
        if channels is not None:
            selected=sorted([c for c in selected if c[1] in channels],key=lambda c:channels.index(c[1]))
        for cid,ch,alarm,comp,latched in selected:
            if manual:cid='O-PROTECT-018'
            row=dict(id=cid,ch=ch,alarm=alarm,started=now());e['cases'].append(row);b.save()
            print('CONTACT START',cid,ch,flush=True)
            offset=alarm-600
            expected=[0,0] if comp is None else ([0,1] if comp==0 else [1,0])
            changed=False
            try:
                assert old[ch] in (0,1)
                observe(row,'before',190,lambda s:s['output'][:2]==[1,1] and not any(s['alarms'])
                        and s['other']==[3,3] and s['phase']==[0,0] and s['input']==0,ch,alarm)
                if recheck and ch in (1,3):
                    # The low-pressure startup delay is real controller state.
                    # Wait for eligibility; do not change its counter or enable.
                    delay=b.rd(27)[0]  # Broadcast PROTECT(25)+2: HeatLowCheckSet
                    eligible=time.monotonic()+max(180,delay+40)
                    while True:
                        current=fixture.sample();runtime=current['CompRunTime'][comp]
                        # Exact current AXF: unsigned int[5],20 bytes on ARM.
                        assert sy['EnableCheckLow'][1]==20
                        enabled=current['EnableCheckLow'][comp]
                        row.setdefault('low_startup_wait',[]).append(dict(at=now(),runtime_s=runtime,delay_s=delay,enabled=enabled))
                        if runtime>delay and enabled:break
                        if time.monotonic()>eligible:raise TimeoutError('LP startup eligibility not established')
                        time.sleep(.5)
                changed=True;row['stimulus_at']=set_polarity(ch,1-old[ch])
                edge=observe(row,'assertion',55,lambda s:s['input']==s['alarms'][offset]==1,ch,alarm)
                row['alarm_observed_s']=edge['t']-row['stimulus_at']
                s=observe(row,'protected',12,lambda s:s['output'][:2]==expected and s['other']==[3,3],ch,alarm)
                row['protection_seen']=True
                if latched:
                    b.reset_faults()
                    s=observe(row,'reset_with_input_active',18,lambda s:s['t']-edge['t']>=4,ch,alarm)
                    row['active_input_after_reset']=s['input']==s['alarms'][offset]==1 and s['output'][:2]==expected
                try: observe(row,'hold',45 if recheck else 40,lambda s:s['mirror']==1 and s['layer']==s['mirror_layer'] and s['t']-edge['t']>=10,ch,alarm)
                except TimeoutError:
                    # Earlier180/240s trials already retain the ordinary page
                    # failure. Isolate that input while keeping this fault
                    # active; do not force the fault, poll state or gateway.
                    page=b.rd(540)[0]
                    alternate=2 if page==1 else 1
                    row['held_page_isolation']=dict(previous_page=page,alternate_page=alternate,started=now())
                    b.wr(540,alternate)
                    try:
                        observe(row,'hold_other_unit_page',75,lambda s:s['mirror']==1 and s['layer']==s['mirror_layer']
                                and s['input']==1,ch,alarm)
                        row['held_page_isolation']['mirror_seen']=True
                    except TimeoutError:row['held_page_isolation']['mirror_seen']=False
                row['mirror_seen']=any(s['mirror']==1 for s in row.get('hold',[]))
                active_samples=row.get('assertion',[])+row.get('protected',[])+row.get('reset_with_input_active',[])+row.get('hold',[])
                row['source_dropout_samples']=sum(s['input']!=1 for s in active_samples if s['t']>=edge['t'])
                row['source_check_scope']='After first confirmed active alarm/input edge; initial propagation samples retained separately'
                set_polarity(ch,old[ch]); removed=time.monotonic()
                if latched:
                    s=observe(row,'release_before_reset',10,lambda s:s['input']==0 and s['t']-removed>=4,ch,alarm)
                    row['retained_before_reset']=s['alarms'][offset]==1
                row['status']='软件子范围通过' if not row['source_dropout_samples'] and row['mirror_seen'] and (not latched or (row['active_input_after_reset'] and row['retained_before_reset'])) else '实测有待核对'
            except Exception as exc:
                row.update(status='实测有待核对',error=repr(exc))
            finally:
                try:
                    if changed: set_polarity(ch,old[ch])
                    if latched or row.get('error'): b.reset_faults()
                    observe(row,'recovered',180 if recheck else 60,lambda s:s['polarity']==old[ch] and s['input']==0
                            and not any(s['alarms']) and not s['layer'] and not s['mirror_layer'] and not s['mirror'],ch,alarm)
                    row['recovery_verified']=True
                except Exception:
                    row.update(recovery_verified=False,recovery_error=traceback.format_exc())
                    # Preserve the failed ordinary recovery. Selecting the
                    # other installed outdoor page is a normal HMI input,
                    # and can isolate the repeated155-write starvation.
                    page=b.rd(540)[0]
                    alternate=2 if page==1 else 1
                    row['recovery_page_isolation']=dict(previous_page=page,alternate_page=alternate,started=now())
                    try:
                        b.wr(540,alternate)
                        observe(row,'alternate_page_poll_available',35,lambda s:not s['gateway_job']['active']
                                or s['gateway_job']['unit']!=1,ch,alarm)
                        b.reset_faults()
                        observe(row,'recovery_other_unit_page',65,lambda s:s['input']==0 and not any(s['alarms'])
                                and not s['layer'] and not s['mirror_layer'] and not s['mirror'],ch,alarm)
                        row['recovery_verified']=True
                        row['recovery_page_isolation']['verified']=True
                    except Exception:row['recovery_page_isolation']['error']=traceback.format_exc()
                    finally:b.wr(540,page)
                row['finished']=now();b.save()
                if row.get('held_page_isolation'):
                    b.wr(540,row['held_page_isolation']['previous_page'])
                print('CONTACT DONE',cid,ch,row['status'],'restored',row['recovery_verified'],flush=True)
            if not row['recovery_verified']:break
    except BaseException:
        if fixture:
            fixture.close();fixture=None;t=b.ot
        e['precondition_diagnostics']=dict(at=now(),
            outdoor316={str(a):rd316(a) for a in (1,165,166,167,168,169,1400,1403,1406,1420,1421,1422,1501)},
            target330=b.rd(881)[0],actual330=b.rd(119)[0],status330=[b.rd(1555,2),b.rd(1625,2)])
        e['error']=traceback.format_exc();b.save();raise
    finally:
        try:
            if fixture:fixture.close();fixture=None;t=b.ot
            if manual:b.config({1300:0,**{a:0 for a in range(1302,1318)}})
            b.wr(398,0)
            for ch,v in old.items():
                if rd316(ch+2)!=v:t.write16(p+2*(ch+2),v);t.flush()
            e['polarity_restored']=all(rd316(ch+2)==v for ch,v in old.items())
        finally:
            try:b.finish()
            finally:e['finished']=now();b.save();print('EVIDENCE',b.path,flush=True)


if __name__=='__main__':run()
