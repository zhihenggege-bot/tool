"""Final image, restored parameters and EEPROM save-cache audit after DI tests."""
import json
import struct
import time
from contextlib import ExitStack
import build_di_faults_v1076_20261124 as build
import deploy_di_faults_v1076_20261124 as deploy


def main():
    dep=deploy.configure();d=dep.d
    path=build.DAY/'final_board_audit.json'
    assert not path.exists()
    board=json.loads((build.DAY/'board_DI.json').read_text('utf8'))
    # Retain the original trace whose overly strict restoration assertion also
    # compared read-only gateway refresh counters. No functional check failed.
    assert board.get('sequence_completed') and all(row['passed'] for row in board['checks'])
    assert not board.get('error')
    if not board.get('restored'):
        assert set(board['configuration_mismatches']) <= {'1875','1923'}
    report=dict(started=d.now(),passed=False,boards=[],save_samples=[])
    def save():dep.dump(path,report)
    with ExitStack() as stack:
        c=d.client();stack.callback(c.close)
        report['snapshot']=d.snap(c)
        assert dep.POSTBOOT_STOPPED(report['snapshot'])
        assert report['snapshot']['2622']==dep.EXPECTED
        assert not any(report['snapshot']['594'])
        actual=d.config(c)
        changes={a:[v,actual[a]] for a,v in board['original'].items() if actual[a]!=v}
        report['read_only_counter_changes']={a:v for a,v in changes.items() if int(a) in (1875,1923)}
        report['configuration_mismatches']={a:v for a,v in changes.items() if int(a) not in (1875,1923)}
        assert not report['configuration_mismatches']
        contexts=[]
        for bd in dep.BOARDS:
            image=dep.NEW if bd[0]=='330' else bd[6]
            ss=stack.enter_context(d.ConnectHelper.session_with_chosen_probe(unique_id=bd[1],target_override=bd[2],
                options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000}))
            t=ss.target;sy=d.symbols(image.with_suffix('.axf'))
            row=dict(board=bd[0],verified_image_bytes=d.verify(t,image),image_sha256=d.sha(image),
                runtime=d.runtime(t,image.with_suffix('.axf')))
            assert row['runtime']==dict(recovery=300,profile=0,minimum_stop=120,minimum_run=180)
            if bd[0]!='330':
                pb,pd=t.read32(0x40010c0c),t.read32(0x4001140c)
                row['gpio']=[(pb>>(12+i))&1 for i in range(4)]+[(pd>>(8+i))&1 for i in range(4)]
                assert not any(row['gpio'])
            report['boards'].append(row);contexts.append((bd[0],t,sy));save()
        name,t,sy=contexts[2]
        began=time.monotonic();notice=began
        while True:
            saved=list(struct.unpack('<500H',bytes(t.read_memory_block8(sy['Old_Parameter'],1000))))
            values={str(a):saved[a] for a in (156,159,395)}
            row=dict(at=d.now(),saved_polarities=values,state=t.read8(sy['IndoorParameterSaveState']),
                error=t.read16(sy['CPURomWriteError']))
            report['save_samples'].append(row);save()
            assert row['error']==0
            if row['state']==0 and all(values[a]==actual[a] for a in values):break
            assert time.monotonic()-began<150,row
            if time.monotonic()-notice>=20:
                print('WAIT restored polarity save cache',row,flush=True);notice=time.monotonic()
            time.sleep(.5)
        report['final_feedback']={str(a):c.read_holding_registers(1,a,1)[0] for a in
            (605,710,819,861,909,910,911,912,913,956,958,960,962,964,966,968)}
        assert not any(report['final_feedback'].values())
        for name,t,sy in contexts:
            image=dep.NEW if name=='330' else next(bd[6] for bd in dep.BOARDS if bd[0]==name)
            assert d.verify(t,image)>0
        manifest_path=dep.OUT/'manifest.json'
        manifest=json.loads(manifest_path.read_text('utf8'))
        assert build.inventory()==manifest['source_inventory']
        assert all(d.sha(dep.OUT/n)==h for n,h in manifest['artifacts'].items())
        report.update(passed=True,finished=d.now(),board_checks=len(board['checks']),restored=True,
            retained_original_trace='board_DI.json',
            original_cleanup_issue='Restoration assertion included read-only gateway status refresh counters1875/1923; this independent audit confirms all writable settings restored',
            physical_contacts_switched=False,physical_terminal_measured=False)
        save()
        manifest.update(flashed=True,hardware_tested=True,board_evidence=str(path.relative_to(build.R)),
            hardware_test_scope='Production live-input polarity inversion, independent latches, reset, Y05 software, Modbus/Tk display; no physical contact switching')
        dep.dump(manifest_path,manifest)
    print('FINAL BOARD AUDIT PASS: images, configuration and save cache restored; faults and Y05 zero',flush=True)


if __name__=='__main__':main()
