"""Run one current-image test and independently audit its restoration."""
import full_queue_context_20261112 as context
import bench_current_20261112 as dispatch
import sys

dispatch.DAY = context.DAY
dispatch.I = context.I
dispatch.BOARDS = context.BOARDS
dispatch.current_bench_class = context.current_bench_class

if __name__ == '__main__':
    if len(sys.argv)>2 and sys.argv[1:3]==['legacy','tools/bench_remaining_defrost_matrix_20261111.py']:
        import bench_remaining_defrost_matrix_20261111 as matrix
        from full_queue_contact_inputs_20261112 import GlobalContactInputs
        matrix.ContactInputs=GlobalContactInputs
    if sys.argv[1:] == ['legacy','tools/bench_remaining_adapter_20261111.py','winter'] and not (context.DAY/'gateway_fast_recheck_executed.json').exists():
        import full_queue_gateway_fast_20261112 as recheck
        recheck.run()
        dispatch.audit('after_gateway_adjacent_recheck_audit')
    if sys.argv[1:] == ['soak']:
        # Finish and audit all BENCH batches first, transition all three boards
        # once, execute real formal timing, then the uninterrupted2h last.
        import subprocess
        result=subprocess.run([sys.executable,'-X','utf8','-u',
            'tools/production_queue_controller_20261112.py'],cwd=context.R)
        assert result.returncode==0,'Formal queue needs review before stability observation'
        result=subprocess.run([sys.executable,'-X','utf8','-u',
            'tools/production_queue_dispatch_20261112.py','soak'],cwd=context.R)
        assert result.returncode==0,'Two-hour observation incomplete; inspect original evidence'
    elif sys.argv[1:] == ['audit'] and (context.DAY/'production_activated.json').exists():
        import subprocess
        result=subprocess.run([sys.executable,'-X','utf8','-u',
            'tools/production_queue_dispatch_20261112.py','audit'],cwd=context.R)
        assert result.returncode==0,'PRODUCTION restoration audit failed'
    elif sys.argv[1:] == ['legacy', 'tools/bench_remaining_adapter_20261111.py', 'manual-contacts']:
        import full_queue_manual_contacts_20261112 as test
        test.run()
        dispatch.audit('after_stable_manual_contacts_audit')
    else:
        dispatch.main()
    import full_queue_progress_20261112 as progress
    progress.summarize()

