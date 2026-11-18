"""One hardware writer; wait for the current restored timed-defrost batch.

The controller owns no serial port or probe. Each child cleans up before the
next starts. Stop the queue if cleanup or independent stopped readback fails.
"""
from pathlib import Path
import datetime,json,subprocess,sys,time,traceback

ROOT=Path(__file__).resolve().parents[1]
DAY=ROOT/'测试证据/修复后内外机联合实测_20261110'
def now():return datetime.datetime.now().astimezone().isoformat(timespec='seconds')
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')

def main():
    predecessor=Path(sys.argv[1])
    path=DAY/('continuation_queue_'+time.strftime('%H%M%S')+'.json')
    q=dict(started=now(),dependency=str(predecessor),status='waiting_without_hardware',runs=[])
    write(path,q)
    try:
        began=time.monotonic()
        while True:
            if (DAY/'pause.request').exists():q['status']='paused_before_hardware';return
            try:j=json.loads(predecessor.read_text('utf8'))
            except (ValueError,OSError):j={}
            if j.get('finished'):break
            assert time.monotonic()-began<1800,'predecessor did not finish'
            time.sleep(3)
        assert ((j.get('read_only') and j.get('passed')) or
                (j.get('status')=='completed' and j.get('test_returncode')==0 and j.get('audit_returncode')==0) or
                (j.get('restored') and not any(j.get(k) for k in ('cleanup_error','today_cleanup_error','restore_mismatches')))), 'Predecessor did not restore safely'
        time.sleep(2)
        actions=[('timed2','tools/joint_v1056_tests_20261110.py',['timed2']),
                 ('parameter-matrix','tools/joint_v1056_parameter_matrix_20261110.py',[]),
                 ('indoor-driven-fans','tools/joint_v1056_indoor_driven_fans_20261110.py',[]),
                 *[(a,'tools/joint_v1056_tests_20261110.py',[a]) for a in
                   ('allocation','refrigerant','da8','heatfans','ntc','coils')]]
        if '--skip-timed' in sys.argv[2:]:actions=[a for a in actions if a[0]!='timed2']
        if '--skip-parameters' in sys.argv[2:]:actions=[a for a in actions if a[0]!='parameter-matrix']
        if '--remaining' in sys.argv[2:]:
            actions=[(a,'tools/joint_v1056_remaining_20261110.py',[a]) for a in
                     ('mirrors','continuity','disable0','disable1','disable2','disable3','disable4','disable5')]
        if '--skip-mirrors' in sys.argv[2:]:
            actions=[a for a in actions if a[0]!='mirrors']
        q['status']='running';write(path,q)
        for name,script,args in actions:
            if (DAY/'pause.request').exists():q['status']='paused_between_batches';return
            before=set(DAY.glob('*.json'))
            row=dict(action=name,started=now(),log=f'.codex-tmp/joint_v1056_queue_{name}.log')
            q['runs'].append(row);write(path,q)
            with (ROOT/row['log']).open('w',encoding='utf8') as log:
                proc=subprocess.run([sys.executable,'-X','utf8','-u',script,*args],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            row.update(returncode=proc.returncode,finished=now(),journals=[])
            completed=[]
            for p in sorted(set(DAY.glob('*.json'))-before):
                try:z=json.loads(p.read_text('utf8'))
                except (ValueError,OSError):continue
                if 'original' not in z:continue
                row['journals'].append(p.name)
                if z.get('finished'):completed.append(z)
            write(path,q)
            assert completed and all(z.get('restored') and not any(z.get(k) for k in ('cleanup_error','today_cleanup_error','restore_mismatches')) for z in completed),'Batch restoration not independently established; queue stopped'
            # This read-only child checks the actual boards and settings,
            # not only the restoration flags in the writer's own journal.
            with (ROOT/row['log']).open('a',encoding='utf8') as log:
                audit=subprocess.run([sys.executable,'-X','utf8','-u','tools/joint_v1056_audit_20261110.py'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            row['independent_audit_returncode']=audit.returncode;write(path,q)
            assert audit.returncode==0,'Independent restoration audit failed; queue stopped'
            print('BATCH FINISHED',name,'test exit',proc.returncode,'restoration audit passed',flush=True)
        q['status']='completed'
    except BaseException:q.update(status='stopped_on_error',error=traceback.format_exc());raise
    finally:
        q['finished']=now();write(path,q);print('QUEUE EVIDENCE',path,flush=True)
        subprocess.run([sys.executable,'-X','utf8','tools/joint_v1056_publish_20261110.py'],cwd=ROOT,check=True)

if __name__=='__main__':main()
