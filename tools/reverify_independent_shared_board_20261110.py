"""Repeat normal writes without reflashing; verify actual316 RAM after every write."""
import json
import time
import traceback
import shared_vfd_board_20261110 as s
from app import Psc330MonitorApp

def main():
    rt=s.rt
    path=s.DAY/('reverify_'+time.strftime('%H%M%S')+'.json')
    q=dict(started=rt.now(),firmware_changed=False,flashed=False,steps=[],restored=False,
           method='Normal330 protocol, actual monitor one-field writer; independent316 attach reads; no load start')
    def save():rt.dump(path,q)
    m=json.loads((s.PACKAGE/'manifest.json').read_text('utf8'))
    assert all(rt.sha(s.ROOT/p)==h for p,h in m['source_inventory'].items())
    c=rt.client()
    rd=lambda a,n=1:c.read_holding_registers(1,a,n)
    def wr(a,v):c.write_single_register(1,a,v&65535)
    def stopped():
        sample=rt.snap(c)
        assert sample['state'][9]==0 and rt.loads_off(sample) and rd(398)==[0],sample
        return sample
    def actual(unit):
        b=s.BOARDS[unit-1];sy=s.symbols(b)
        with rt.ConnectHelper.session_with_chosen_probe(unique_id=b[1],target_override=b[2],
                 options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}) as ss:
            t=ss.target;base=sy['Parameter'][0]
            row=dict(at=rt.now(),unit=unit,settings=[t.read16(base+2*a) for a in range(165,182)],
                     output=list(t.read_memory_block8(*sy['output'])),layer=t.read16(base+3002))
            assert not any(row['output']),row
            return row
    def verify(unit,pair=None,vfd=None):
        began=time.monotonic();since=None;history=[];base=1830+48*(unit-1)
        while True:
            row=dict(at=rt.now(),mirror=rd(base,17),actual=actual(unit))
            history.append(row)
            good=row['mirror']==row['actual']['settings']
            if pair is not None:good=good and row['mirror'][:2]==pair
            if vfd is not None:good=good and row['mirror'][11:14]==vfd
            if good:
                if since is None:since=time.monotonic()
                if time.monotonic()-since>=2:return history
            else:since=None
            assert time.monotonic()-began<60,(unit,pair,vfd,row)
            time.sleep(.4)
    def record(label,**data):
        q['steps'].append(dict(label=label,at=rt.now(),**data));save();print('VERIFIED',label,flush=True)
    q['versions_before']=rd(2622,18);assert q['versions_before']==s.EXPECTED
    q['snapshot_before']=stopped()
    q['original_switch']=rd(1319)[0]
    q['original_sources']=rd(1340,3)
    q['original_outdoor']=[rd(1830,42),rd(1878,42)]
    q['initial_actual']=[actual(1),actual(2)]
    for i in range(2):assert q['initial_actual'][i]['settings']==q['original_outdoor'][i][:17]
    assert all(x[11:14]==q['original_sources'] for x in q['original_outdoor'])
    save()
    monitor=object.__new__(Psc330MonitorApp);monitor.values={}
    monitor.read_now=lambda a,n:rd(a,n);monitor.write_single=lambda a,v:wr(a,v)
    try:
        for unit in (1,2):
            for order,targets in (((165,166),{165:1,166:2}),((166,165),{165:2,166:4})):
                for p in order:
                    before=actual(unit)['settings'][:2]
                    monitor.write_outdoor_spec_field(unit,p,targets[p])
                    expected=list(before);expected[p-165]=targets[p]
                    samples=verify(unit,pair=expected)
                    assert samples[-1]['actual']['settings'][1-(p-165)]==before[1-(p-165)]
                    record(f'unit{unit}-only{p}-order{order}',before=before,expected=expected,
                           register=1830+48*(unit-1)+p-165,samples=samples)
        wr(1319,1)
        for values in ([40,0,1],[50,5,10],[45,30,20]):
            c.write_multiple_registers(1,1340,values)
            assert rd(1340,3)==values
            samples=[verify(unit,vfd=values) for unit in (1,2)]
            record('shared-'+str(values),source=rd(1340,3),samples=samples)
        q['passed']=True
    except BaseException:q['error']=traceback.format_exc();save();raise
    finally:
        try:
            wr(398,0)
            for unit,settings in enumerate(q['original_outdoor'],1):
                for p in (165,166):
                    before=actual(unit)['settings'][:2]
                    monitor.write_outdoor_spec_field(unit,p,settings[p-165])
                    expected=list(before);expected[p-165]=settings[p-165]
                    record(f'restore-unit{unit}-only{p}',expected=expected,samples=verify(unit,pair=expected))
            wr(1319,1)
            c.write_multiple_registers(1,1340,q['original_sources'])
            for unit in (1,2):
                samples=verify(unit,vfd=q['original_sources'])
                record(f'restore-unit{unit}-shared',samples=samples)
            wr(1319,q['original_switch'])
            q['outdoor_after']=[rd(1830,42),rd(1878,42)]
            q['sources_after']=rd(1340,3)
            assert q['outdoor_after']==q['original_outdoor']
            assert q['sources_after']==q['original_sources']
            q['snapshot_after']=stopped()
            q['restored']=True
        except BaseException:q['cleanup_error']=traceback.format_exc();save();raise
        finally:c.close();q['finished']=rt.now();save();print('EVIDENCE',path,flush=True)

if __name__=='__main__':main()
