"""Apply ASCII-only byte patches, preserving legacy encodings and line endings."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.codex-tmp/shared_type_v1058_20261110'

def change(path,old,new,count=1):
    data=path.read_bytes();a=old.replace('\n','\r\n').encode('ascii');b=new.replace('\n','\r\n').encode('ascii')
    assert data.count(a)==count,(str(path),old[:100],data.count(a),count)
    path.write_bytes(data.replace(a,b))

def main():
    m=ROOT/'PSC330RK-V10-内机/User/UserSrc/modulecontrol.c'
    h=ROOT/'PSC330RK-V10-内机/User/UserHead/User.h'
    b=ROOT/'PSC330RK-V10-内机/User/modbus/modbus.c'
    change(h,'#define PSC330_VERSION_MINOR        57','#define PSC330_VERSION_MINOR        58')
    change(h,'#define SharedVfdEnd             1342','#define SharedVfdEnd             1342\n#define SharedTypeBase           1343\n#define SharedTypeAddr           1343\n#define SharedTypeEnd            1344')
    change(h,'uint8_t PSC316Gateway_HMIWrite(uint16_t addr, int16_t value);','uint8_t PSC316SharedTypeCanWrite(void);\nuint8_t PSC316Gateway_HMIWrite(uint16_t addr, int16_t value);')
    change(m,'PSC316SharedOffset[3][11]','PSC316SharedOffset[4][11]')
    change(m,'{17,18,19,20,21,22,23,24,25,26,27}\n};','{17,18,19,20,21,22,23,24,25,26,27},\n\t{ 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0}\n};')
    change(m,'PSC316SharedCount[3] = {6, 6, 11}','PSC316SharedCount[4] = {6, 6, 11, 2}')
    change(m,'static uint8_t PSC316SharedVfdSeeded = 0;','''static uint8_t PSC316SharedVfdSeeded = 0;
static uint8_t PSC316SharedTypeSeeded = 0;
uint8_t PSC316SharedTypeCanWrite(void)
{
    uint8_t u,c;
    if(!PSC316SharedTypeSeeded || SysStep != 0)return 0;
    for(u=1; u<=PSC316_HMI_UNIT_NUM; u++)
    {
        if(u >= ModuleNumSet)break;
        for(c=0; c<2; c++)
        {
            int16_t state=UnitReadStatus[u].CompStatus[c];
            if((state==2)||(state==3)||(state==4))return 0;
        }
        if(PSC316UnitDefrostActive(u))return 0;
    }
    return 1;
}''')
    change(m,'if((chunk < 1) || (chunk > 3))return 0;','if((chunk < 1) || (chunk > 4))return 0;')
    change(m,'else                value = Parameter[SharedDefrostBase + j];','else if(chunk == 3) value = Parameter[SharedDefrostBase + j];\n\telse value = Parameter[SharedTypeBase + j];')
    change(m,'\t/* New RAM sources must be seeded before any shared broadcast.', '''    /* Type0/fan0 is legal, so zero RAM cannot indicate initialization.
       Adopt unit1 only, after a complete existing-settings read. */
    if(!PSC316SharedTypeSeeded && PSC316SetValid[0])
    {
        for(i=0; i<2; i++)Parameter[SharedTypeBase+i]=PSC316SetMirror[0][i];
        PSC316SharedTypeSeeded=1;
    }
\t/* New RAM sources must be seeded before any shared broadcast.''')
    change(m,'\tfor(i=0; i<3; i++) Parameter[SharedVfdBase+i]      = PSC316SetMirror[0][11+i];','\tfor(i=0; i<3; i++) Parameter[SharedVfdBase+i]      = PSC316SetMirror[0][11+i];\n\tfor(i=0; i<2; i++) Parameter[SharedTypeBase+i] = PSC316SetMirror[0][i];')
    change(m,'if(((so >= 5) && (so <= 16))','if((so <= 1) || ((so >= 5) && (so <= 16))')
    change(m,'&& (((sharedOffset >= 5) && (sharedOffset <= 16))','&& ((sharedOffset <= 1) || ((sharedOffset >= 5) && (sharedOffset <= 16))')
    change(m,'''\t\t\telse
\t\t\t{
\t\t\t\tAddr = 182; Num = 11; SharedChunk = 3; SendParaAddr1 = 0;
\t\t\t}''','''            else if(SendParaAddr1==11)
            {
                Addr = 182; Num = 11; SharedChunk = 3; SendParaAddr1 = 13;
            }
            else if(PSC316SharedTypeCanWrite())
            {
                Addr = 165; Num = 2; SharedChunk = 4; SendParaAddr1 = 0;
            }
            else
            {
                Addr = 1; Num = 1; SendParaAddr1 = 0;
            }''')
    change(b,'SharedMin[23]','SharedMin[25]');change(b,'SharedMax[23]','SharedMax[25]')
    change(b,'  2,  2, 30,  0,  1};','  2,  2, 30,  0,  1, 0, 0};')
    change(b,'  8,  8, 50, 30, 20};','  8,  8, 50, 30, 20, 2, 4};')
    change(b,'\t\ti = (uint8_t)(20 + (addr - SharedVfdAddr));','\t\ti = (uint8_t)(20 + (addr - SharedVfdAddr));\n\telse if((addr >= SharedTypeAddr) && (addr <= SharedTypeEnd))\n\t\ti = (uint8_t)(23 + (addr - SharedTypeAddr));')
    change(b,'\tif((addr >= SharedVfdAddr) && (addr <= SharedVfdEnd))\n\t\treturn (SharedSyncEnable == 1) && SharedOutdoorValueOK(addr, value);','''\tif((addr >= SharedVfdAddr) && (addr <= SharedVfdEnd))
\t\treturn (SharedSyncEnable == 1) && SharedOutdoorValueOK(addr, value);
    if((addr >= SharedTypeAddr) && (addr <= SharedTypeEnd))
        return (SharedSyncEnable == 1) && PSC316SharedTypeCanWrite() && SharedOutdoorValueOK(addr, value);''')
    change(b,'\t\t|| ((addr >= SharedVfdAddr) && (addr <= SharedVfdEnd)))','\t\t|| ((addr >= SharedVfdAddr) && (addr <= SharedVfdEnd))\n\t\t|| ((addr >= SharedTypeAddr) && (addr <= SharedTypeEnd)))')
    before=json.loads((OUT/'source_before.json').read_text('utf8'))
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==v for p,v in before.items() if p not in [m.relative_to(ROOT).as_posix(),h.relative_to(ROOT).as_posix(),b.relative_to(ROOT).as_posix()])
    print('APPLIED 330 V10.58 shared165/166')

if __name__=='__main__':main()
