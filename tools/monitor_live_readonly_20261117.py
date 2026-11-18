"""Exercise the real Tk GUI/poll thread on COM6, with writes forbidden."""
import json
import time
import traceback
import tkinter as tk
from tkinter import messagebox
import resume_bench_20261117 as ctx
from app import Psc330MonitorApp

g=ctx.g


def main():
    root=tk.Tk();root.withdraw()
    q=dict(started=g.now(),source_sha256=g.runtime.sha(ctx.R/'psc330_monitor_tool/psc330_monitor/app.py'),
           scope='Real Tk event loop, GUI connect/poll/reconnect; read only, window hidden; no visual layout or write-operation acceptance',
           reads=[],writes=[],dialogs=[],tk_errors=[],sessions=[])
    path=ctx.DAY/('monitor_live_readonly_'+time.strftime('%H%M%S')+'.json')
    for name in ('showwarning','showerror','showinfo'):
        setattr(messagebox,name,lambda *a,kind=name,**kw:q['dialogs'].append(dict(kind=kind,args=a)))
    root.report_callback_exception=lambda typ,value,tb:q['tk_errors'].append(''.join(traceback.format_exception(typ,value,tb)))
    app=Psc330MonitorApp(root)
    read=app.client.read_holding_registers
    def observed(*args,**kw):
        began=time.monotonic()
        try:
            values=read(*args,**kw)
            q['reads'].append(dict(at=g.now(),args=args,elapsed_s=time.monotonic()-began,values=values))
            return values
        except BaseException as exc:
            q['reads'].append(dict(at=g.now(),args=args,error=repr(exc)));raise
    app.client.read_holding_registers=observed
    def forbidden(*args,**kw):
        q['writes'].append(dict(args=args,kwargs=kw));raise AssertionError('GUI read-only test attempted a write')
    app.client.write_single_register=app.client.write_multiple_registers=forbidden
    app.port_var.set('COM6');app.interval_var.set('0.5')
    started=time.monotonic();phase=0;ready_at=None;session_start=0;versions=None
    app.connect()
    def close():
        app.disconnect()
        deadline=time.monotonic()+8
        def finish_close():
            if app.poll_thread and app.poll_thread.is_alive() and time.monotonic()<deadline:
                root.after(100,finish_close);return
            q['poll_thread_stopped']=not app.poll_thread or not app.poll_thread.is_alive()
            q['cache_cleared']=not app.values and not app.value_updated_at
            q['finished']=g.now();g.dump(path,q);root.destroy()
        root.after(100,finish_close)
    def tick():
        nonlocal phase,ready_at,session_start,versions
        try:
            assert not q['dialogs'] and not q['tk_errors'] and not q['writes'],q
            if time.monotonic()-started>85:raise TimeoutError('GUI connection/reconnection deadline')
            # Firmware versions are intentionally fetched on demand by the GUI,
            # not included in its regular POLL_BLOCKS. Bind with a read-only
            # read_now call; do not require nonexistent periodic cache entries.
            synced=all(a in app.values for a in (236,709,1299,1550,1551,1620,1621,2022,2150))
            if synced and versions is None:versions=app.read_now(2622,18)
            if synced and versions==g.runtime.EXPECTED:
                if ready_at is None:ready_at=time.monotonic()
                if time.monotonic()-ready_at>=6:
                    q['sessions'].append(dict(at=g.now(),phase=phase,versions=versions,
                        cached_registers=len(app.values),status=app.status_var.get(),
                        read_count=len(q['reads'])-session_start,mirror_phases=[app.values.get(a) for a in (1550,1551,1620,1621)]))
                    if phase==0:
                        app.disconnect()
                        assert not app.values and not app.value_updated_at
                        phase=1;ready_at=None;versions=None;session_start=len(q['reads'])
                        deadline=time.monotonic()+8
                        def reconnect():
                            if app.poll_thread and app.poll_thread.is_alive():
                                if time.monotonic()>deadline:
                                    q['passed']=False;q['error']='GUI poll thread did not stop before reconnect';close();return
                                root.after(100,reconnect);return
                            app.connect();root.after(250,tick)
                        root.after(100,reconnect);return
                    else:
                        q['passed']=all(not r.get('error') for r in q['reads'])
                        close();return
            root.after(250,tick)
        except BaseException:
            q['passed']=False;q['error']=traceback.format_exc();close()
    root.after(250,tick);root.mainloop()
    assert q.get('passed') and q['poll_thread_stopped'] and q['cache_cleared'],q.get('error',q)
    g.audit_module.audit('after_monitor_readonly',True)
    print('GUI SERIAL READ/RECONNECT PASS',path,flush=True)


if __name__=='__main__':main()
