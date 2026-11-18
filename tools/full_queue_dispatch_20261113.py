"""Exact current-image single-writer dispatch; never falls back to old flash."""
import full_queue_context_20261113 as context
import bench_current_20261112 as dispatch
import sys
dispatch.DAY,dispatch.I,dispatch.BOARDS=context.DAY,context.I,context.BOARDS
dispatch.current_bench_class=context.current_bench_class

if __name__=='__main__':
    assert sys.argv[1] not in ('prepare','flash','restore','soak'), 'Use reviewed current-version deployment for profile transitions'
    if sys.argv[1]=='fan30-remaining':
        import bench_remaining_prestart_20261111 as test
        test.run(30, pairs=((0,0),(0,1),(1,2),(1,3),(2,2)))
        dispatch.audit('after_five_fan30_configurations')
    elif sys.argv[1]=='isolation':
        import bench_ambient_isolation_20261113 as test
        test.run(int(sys.argv[2]))
        dispatch.audit('after_isolation_'+sys.argv[2])
    elif sys.argv[1]=='ambient-summary':
        import bench_ambient_summary_20261113 as test
        test.run();dispatch.audit('after_ambient_summary')
    else:
        if sys.argv[1:3]==['legacy','tools/bench_remaining_defrost_matrix_20261111.py']:
            if sys.argv[3:] == ['fault-both']:
                import bench_ambient_isolation_20261113 as isolation
                try:isolation.run(1,exercise_load=True)
                except Exception:
                    context.dump(context.DAY/'R05_execution_exception.json',dict(at=context.now(),error=context.traceback.format_exc()))
                dispatch.audit('after_R05_healthy_demand_cycle')
            import bench_remaining_defrost_matrix_20261113 as matrix
            sys.modules['bench_remaining_defrost_matrix_20261111']=matrix
            from full_queue_contact_inputs_20261112 import GlobalContactInputs
            matrix.ContactInputs=GlobalContactInputs
        if sys.argv[1:]==['legacy','tools/bench_remaining_adapter_20261111.py','manual-contacts']:
            import bench_remaining_outdoor_20261111 as heating
            try:heating.heat_and_dispatch(3)
            except Exception:
                context.dump(context.DAY/'fixed_double_speed_heat_recheck_exception.json',dict(at=context.now(),error=context.traceback.format_exc()))
            dispatch.audit('after_fixed_double_speed_heat_recheck')
            import full_queue_manual_contacts_20261112 as test
            test.run();dispatch.audit('after_manual_contacts')
        elif sys.argv[1:]==['legacy','tools/bench_remaining_adc_20261111.py','pressure']:
            import bench_remaining_pressure_trip_20261111 as threshold
            try:threshold.run()
            except Exception:
                context.dump(context.DAY/'Q03_threshold_execution_exception.json',dict(at=context.now(),error=context.traceback.format_exc()))
            dispatch.audit('after_Q03_analog_threshold')
            import bench_pressure_gateway_20261113 as gateway_threshold
            try:gateway_threshold.run()
            except Exception:
                context.dump(context.DAY/'Q03_gateway_execution_exception.json',dict(at=context.now(),error=context.traceback.format_exc()))
            dispatch.audit('after_Q03_gateway_threshold')
            import bench_remaining_adc_20261111 as test
            test.pressure_sensors();dispatch.audit('after_Q03_pressure_diagnostics')
        elif sys.argv[1:]==['legacy','tools/bench_remaining_adc_20261111.py','ventilation']:
            import bench_pressure_gateway_20261113 as threshold
            try:threshold.run()
            except Exception:
                context.dump(context.DAY/'Q03_gateway_recheck_exception.json',dict(at=context.now(),error=context.traceback.format_exc()))
            dispatch.audit('after_Q03_gateway_recheck')
            import bench_remaining_adc_20261111 as test
            test.ventilation();dispatch.audit('after_indoor_AI')
        else:dispatch.main()
    if sys.argv[1]=='audit':
        hold=context.DAY/'hold_before_formal.request'
        if hold.exists():
            (context.R/'.codex-tmp/continuous_v1055_pause.request').write_text(hold.read_text('utf8'),encoding='utf8')
            print('USER HOLD: restoration verified; formal queue deferred',flush=True)
