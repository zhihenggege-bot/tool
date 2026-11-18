"""Inject only legacy HMI selection/command inputs, never lifecycle or outputs.

Current normal Modbus validation rejects 570/572/573. That interface limitation
is retained separately; this fixture tests downstream DispAction/serial/316
behavior through equivalent command inputs on the isolated control-board bench.
"""
import time
from contextlib import nullcontext
from run_indoor_bench_20261105 import axf_symbols,BOARDS,ConnectHelper,now

def manual_defrost(b,enter,session=None):
    sy=axf_symbols()
    context=nullcontext(session) if session is not None else ConnectHelper.session_with_chosen_probe(unique_id=BOARDS[2][1],target_override=BOARDS[2][2],
            options={'connect_mode':'attach','resume_on_disconnect':True,'frequency':1000000})
    with context as ss:
        t=ss.target
        base=sy['Parameter'][0]
        old={a:t.read16(base+a*2) for a in (570,572,573)}
        assert old[572]==old[573]==0,('Prior manual defrost command still pending',old)
        event={'at':now(),'enter':enter,'previous_inputs':old,'command_input_simulation':True,
            'writes_only_to_legacy_HMI_input_words':True,'commands':[]}
        b.log.setdefault('manual_defrost_stimulus',[]).append(event)
        b.save()
        try:
            for comp in ((1,) if enter else (1,2)):
                a=572 if enter else 573
                t.write16(base+570*2,comp)
                t.write16(base+a*2,1)
                t.flush()
                started=time.monotonic()
                while t.read16(base+a*2):
                    assert time.monotonic()-started<5,('Command not consumed',a,comp)
                    time.sleep(.03)
                event['commands'].append({'at':now(),'compressor':comp,'input_register':a,
                    'consumed_after_s':time.monotonic()-started})
                # Allow its unit command slot to be sent before selecting the
                # other compressor. Both actual feedback paths remain active.
                time.sleep(.5)
        finally:
            for a,value in old.items():t.write16(base+a*2,value)
            t.flush()
            event['restored']={str(a):t.read16(base+a*2)==v for a,v in old.items()}
            b.save()
            assert all(event['restored'].values())
