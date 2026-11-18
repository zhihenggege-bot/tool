"""Normal330 global polarity input fixture; both316s affected, probes read-only."""
from full_queue_context_20261112 import *
from continuous_special_stages_v1055_20261109 import paused
import struct

class GlobalContactInputs:
    def __init__(self,b,original):
        self.b=b;self.original=original
        self.global_original={ch:b.rd(ch+2)[0] for ch in range(8)}
        b.log['global_contact_fixture']=dict(started=now(),original=self.global_original,
            scope='Normal330 polarity writes broadcast to BOTH316s; no SWD writes, no final input/fault/output/timer forcing',events=[])
        b.save()
    def set(self,ch,value):
        assert 0<=ch<8 and value in (0,1)
        self.b.config({ch+2:value});issued=time.monotonic()
        self.b.log['global_contact_fixture']['events'].append(dict(at=now(),channel=ch,value=value,issued_t=issued))
        self.b.save();return issued
    def sample(self,after=0):
        b=self.b
        if not getattr(b,'_cleaning_up',False):paused()
        t=b.ot;sy=b.outsy;p=sy['Parameter'][0]
        row=dict(at=now(),t=time.monotonic(),inputs=[t.read8(sy[f'X_{ch:02d}'][0]) for ch in range(8)],
            qualified_inputs=[t.read8(sy[f'X{ch:02d}_En'][0]) for ch in range(8)],
            polarities=[t.read16(p+2*(ch+2)) for ch in range(8)],
            alarms=list(struct.unpack('<28H',bytes(t.read_memory_block8(p+1200,56)))),
            output=list(t.read_memory_block8(*sy['output'])),layer=t.read16(p+3002),
            phase=[t.read16(p+2*a) for a in (1420,1421)],lp_start_delay=t.read16(p+54))
        for name in ('CompRunTime','EnableCheckLow','PSC316DefrostRunTime','PSC316DefrostState',
                     'PSC316DefrostEligible','PSC316DefrostEnded','PSC316DefrostStarted','SysHaveDef'):
            raw=bytes(t.read_memory_block8(*sy[name]))
            row[name]=list(struct.unpack('<'+'I'*(len(raw)//4),raw)) if name in ('CompRunTime','EnableCheckLow','PSC316DefrostRunTime','SysHaveDef') else list(raw)
        return row
    def close(self):
        self.b.config({ch+2:value for ch,value in self.global_original.items()})
        self.b.log['global_contact_fixture']['finished']=now();self.b.save()
