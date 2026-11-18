"""Recover the exact journal after aborting a test with an invalid premise."""
from remaining_pid_live_20261106 import *


def main():
    source=max(D.glob('*di_protection_matrix_*.json'),key=lambda p:p.stat().st_mtime)
    prior=json.loads(source.read_text('utf8'))
    assert prior.get('restored') is not True, 'Already recovered; inspect before rerunning'
    b=HeatBench('recover_di_precondition')
    b.log['recovery_source']=source.relative_to(R).as_posix()
    for a,v in prior['original'].items():
        b.original[a]=v
        b.touched.add(int(a))
    b.polarities={a:int(prior['full_configuration_before'][str(a)]) for a in b.polarities}
    b.save()
    b.finish()
    assert b.log.get('restored') is True
    prior.update(restored=True,recovery_evidence=b.path.relative_to(R).as_posix(),
        aborted_due_to_test_precondition=True,
        test_error_explanation='制冷模式不允许运行预热；旧测试建立条件错误，未实际执行故障注入，不能作为固件保护失败。')
    dump(source,prior)
    records=json.loads(RESULTS.read_text('utf8'))
    for cid in prior['cases']:
        rec=records.get(cid,{})
        if rec.get('evidence')!=source.relative_to(R).as_posix() or rec.get('status')!='失败': continue
        history=rec.get('history',[])+[{k:v for k,v in rec.items() if k!='history'}]
        records[cid]=dict(rec,status='未测',history=history,at=now(),actual=prior['test_error_explanation'])
    dump(RESULTS,records)
    with (R/'内机测试版逐项测试记录_20261105.md').open('a',encoding='utf8') as f:
        f.write('\n测试方法纠正：'+prior['test_error_explanation']+'参数已逐项恢复，随后按模式修正负载前提重测。恢复证据：'+b.path.relative_to(R).as_posix()+'。\n')
    print('EXPLICIT DI RECOVERY',b.log['restored'],source,flush=True)


if __name__=='__main__':main()
