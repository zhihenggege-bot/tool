"""Flash only 330; verify unchanged 316 images without programming either board."""
import time
import traceback
import run_indoor_bench_20261105 as b


def main():
    assert b.EXPECTED[1] == 10 and b.EXPECTED[2] >= 50
    assert (b.D / 'preflight.json').exists()
    path = b.D / 'flash.json'
    assert not path.exists(), 'Preserve the existing flash journal'
    report = {'started': b.now(), 'profile':'BENCH_ONLY_3S', 'boards':[],
              'physical_terminal_measurement':False, 'programmed_boards':['330']}
    b.dump(path, report)
    for label, uid, target, device, flash_size, ram_size, stem in b.BOARDS:
        image = b.I / (stem + '.hex'); mem = b.parse_hex(image)
        entry = {'board':label, 'probe_uid':uid, 'target':target,
                 'image':str(image.relative_to(b.R)), 'sha256':b.sha(image),
                 'programmed':False, 'flash_verified':False}
        report['boards'].append(entry); b.dump(path, report)
        with b.ConnectHelper.session_with_chosen_probe(unique_id=uid, target_override=target,
                options={'connect_mode':'attach','resume_on_disconnect':True,
                         'frequency':1000000}) as ss:
            t = ss.target
            assert t.read32(0xE0042000) & 0xfff == device
            if label == '330':
                t.halt(); reg=0xE0042008; old_debug=t.read32(reg)
                try:
                    for suffix, addr, size in [('flash',0x08000000,flash_size),
                                               ('sram',0x20000000,ram_size)]:
                        dst=b.D/(label+'_before_'+suffix+'.bin'); assert not dst.exists()
                        dst.write_bytes(bytes(t.read_memory_block8(addr,size)))
                        entry[suffix+'_backup']={'path':dst.name,'size':size,'sha256':b.sha(dst)}
                    b.dump(path, report)
                    t.write32(reg,old_debug|0x1800); t.reset_and_halt()
                    t.write32(reg,t.read32(reg)|0x1800)
                    entry['programming_started']=b.now(); b.dump(path,report)
                    b.FileProgrammer(ss,chip_erase='sector',trust_crc=False).program(str(image))
                    entry['programmed']=True
                except BaseException:
                    entry['error']=traceback.format_exc(); b.dump(path,report)
                    raise
            try:
                for start,end in b.blocks_of(mem):
                    for addr in range(start,end,4096):
                        n=min(4096,end-addr)
                        assert bytes(t.read_memory_block8(addr,n)) == bytes(mem[addr+i] for i in range(n)), (label,hex(addr))
                entry.update(flash_verified=True,verified_bytes=len(mem),finished=b.now())
                b.dump(path,report)
                print('FLASH MATCH',label,'programmed',entry['programmed'],len(mem),flush=True)
            finally:
                if label=='330':
                    t.write32(reg,old_debug); t.reset()
    finish(report, path)


def finish(report, path):
    assert len(report['boards']) == 3 and all(x['flash_verified'] for x in report['boards'])
    c=b.client()
    try:
        end=time.monotonic()+30
        while True:
            try:
                versions=c.read_holding_registers(1,2622,18)
            except Exception as exc:
                versions=[]
                report.setdefault('boot_read_retries',[]).append({'at':b.now(),'error':repr(exc)})
            if versions==b.EXPECTED:break
            assert time.monotonic()<end,versions
            time.sleep(.5)
        report['versions_after']=versions
        report['profile_after']=c.read_holding_registers(1,1298,2)
        assert report['profile_after'][1]==15107
        report['snapshot_after']=b.snap(c)
        assert report['snapshot_after']['state'][9]==0 and b.loads_off(report['snapshot_after'])
        report['finished']=b.now(); b.dump(path,report)
    finally:c.close()
    b.result('T01-005','通过',f'330已烧录V10.{b.EXPECTED[2]} BENCH并逐字节核对；两316保留V12.39，仅只读验证原HEX一致；三板1299=15107',path,
             f'本次只更新330；正式版V10.{b.EXPECTED[2]}已编译，尚未烧录实测。')


if __name__=='__main__':
    import sys, json
    if '--finish-verified-flash' in sys.argv:
        path=b.D/'flash.json'
        finish(json.loads(path.read_text('utf-8')),path)
    else:main()
