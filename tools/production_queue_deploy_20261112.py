"""One authorized profile transition, only after complete normal-stop audit."""
import full_queue_context_20261112 as before

def deploy():
    import bench_current_20261112 as oldaudit
    oldaudit.DAY=before.DAY;oldaudit.I=before.I;oldaudit.BOARDS=before.BOARDS
    oldaudit.audit('before_PRODUCTION_deployment',True)
    # Import only after the BENCH audit, since this binds the production AXFs.
    import production_queue_context_20261112 as prod
    from production_queue_context_20261112 import runtime,DAY,I,R,dump,now,json,time
    assert not (DAY/'flash.json').exists(),'Never overwrite a prior deployment'
    m=json.loads((I/'manifest.json').read_text('utf8'))
    assert all(runtime.sha(R/p)==h for p,h in m['source_inventory'].items())
    assert all(runtime.sha(I/p)==h for p,h in m['artifacts'].items())
    c=runtime.client()
    try:
        snapshot=runtime.snap(c)
        assert c.read_holding_registers(1,398,1)==[0] and snapshot['state'][9]==0 and runtime.loads_off(snapshot)
        dump(DAY/'preflight.json',dict(at=now(),snapshot=snapshot,versions=c.read_holding_registers(1,2622,18),
            authorization='User resumed 53 batches, 2h stability and PRODUCTION timing',source_inventory=m['source_inventory'],artifacts=m['artifacts']))
    finally:c.close()
    flash=prod.adapt(runtime.flash,[("'profile':'BENCH_ONLY_3S'","'profile':'PRODUCTION'"),
        ("report['profile_after'][1]==15107","report['profile_after'][1]==0")],'production_flash')
    # Save deployment-only observations locally instead of editing historical ledgers.
    def record(case,status,actual,evidence,*args):
        dump(DAY/(case+'_deployment_observation.json'),dict(at=now(),status=status,
            note='Adapted legacy flash-driver observation; authoritative profile is flash.json=PRODUCTION/0',evidence=str(evidence)))
    flash.__globals__['result']=record
    flash()
    c=runtime.client()
    try:
        # Formal minima replace BENCH-only short settings; preserve longer originals.
        changed={}
        for a,minimum in ((42,120),(43,180),(1298,300)):
            old=c.read_holding_registers(1,a,1)[0]
            if old<minimum:c.write_single_register(1,a,minimum)
            changed[str(a)]=dict(before=old,after=c.read_holding_registers(1,a,1)[0])
        time.sleep(8)
        assert all(v['after']>=dict([(42,120),(43,180),(1298,300)])[int(k)] for k,v in changed.items())
        prior_path=sorted((R/'测试证据/台架执行_20261112').glob('recover_interrupted_v1058_*.json'))[-1]
        prior=json.loads(prior_path.read_text('utf8'))
        original={a:c.read_holding_registers(1,int(a),1)[0] for a in prior['original']}
        baseline=dict(at=now(),original=original,gateway_original=prior.get('gateway_original',{}),
            source_before_transition=str(prior_path),formal_minima=changed)
        dump(DAY/'recover_interrupted_v1058_production_baseline.json',baseline)
    finally:c.close()
    prod.audit('production_deployed_full_image_audit',True)
    dump(before.DAY/'production_activated.json',dict(at=now(),profile='PRODUCTION',profile_code=0,
        evidence=str(DAY/'flash.json'),firmware_functional_source_changed=False))

if __name__=='__main__':deploy()
