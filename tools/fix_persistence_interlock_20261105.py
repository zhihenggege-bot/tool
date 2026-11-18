"""Small byte-preserving edits to the common BENCH/production sources."""
from pathlib import Path
import hashlib,json,shutil

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.codex-tmp/persistence_interlock_v1049_v1239_20261105'
OUT.mkdir(parents=True,exist_ok=True)
changes={}
def edit(rel,fn):
    p=ROOT/rel;before=p.read_bytes()
    backup=OUT/'source_before'/rel
    assert not backup.exists(),backup
    backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,backup)
    after=fn(before)
    assert after!=before,rel
    p.write_bytes(after)
    changes[rel]={'before':hashlib.sha256(before).hexdigest(),'after':hashlib.sha256(after).hexdigest()}
def replace(b,a,c):
    a=a.encode('ascii');c=c.encode('ascii')
    assert b.count(a)==1,(a,b.count(a))
    return b.replace(a,c)

def outdoor(b):
    # Capture once; a later live update must survive both byte writes and verify.
    b=replace(b,'\tint16_t TempPara=0;','\tint16_t TempPara=0;\r\n\tstatic int16_t WriteSnapshot;')
    b=replace(b,'CI2C_WriteByte((u8)((Parameter[t]>>8)&0xff)',
                'WriteSnapshot = Parameter[t];\r\n\t\t\tCI2C_WriteByte((u8)((WriteSnapshot>>8)&0xff)')
    b=replace(b,'CI2C_WriteByte((u8)(Parameter[t]&0xff)','CI2C_WriteByte((u8)(WriteSnapshot&0xff)')
    b=replace(b,'if(TempPara != Parameter[t])','if(TempPara != WriteSnapshot)')
    start=b.index(b'if(TempPara != WriteSnapshot)')
    head,tail=b[:start],b[start:]
    tail=replace(tail,'Parameter[t] = Old_Parameter[t];','if(Parameter[t] == WriteSnapshot)Parameter[t] = Old_Parameter[t];')
    tail=replace(tail,'else Old_Parameter[t]= Parameter[t];','else Old_Parameter[t]= WriteSnapshot;')
    return head+tail

WRITER=r'''
/* V10.49: the supplied sysrun.o writer compares EEPROM with live Parameter[].
   A new command during its two-byte write was incorrectly rolled back. ARM
   linker substitution replaces that entry point while retaining its boot flow.
   Both bytes, verification and saved shadow must refer to one snapshot. */
extern int16_t Old_Parameter[ParameterSaveSize];
extern uint16_t CPURomWriteError;
extern unsigned char IndoorAiStorageBusy(void);
unsigned char IndoorParameterSaveState = 0;
unsigned short IndoorParameterSaveIndex = 0;
static int16_t IndoorParameterSaveSnapshot;
static uint64_t IndoorParameterSaveTick;
static unsigned char IndoorParameterSaveFailed;

unsigned char IndoorParameterStorageBusy(void)
{
    return IndoorParameterSaveState != 0;
}

void $Sub$$WriteParamaterEEprom(void)
{
    unsigned short i;
    unsigned char bytes[2];
    int16_t stored;
    if(IndoorAiStorageBusy())return;
    switch(IndoorParameterSaveState)
    {
    case 0:
        for(i=1;i<ParameterSaveSize;i++)
        {
            if(Old_Parameter[i] != Parameter[i])
            {
                IndoorParameterSaveIndex=i;
                IndoorParameterSaveState=1;
                break;
            }
        }
        break;
    case 1:
        i=IndoorParameterSaveIndex;
        IndoorParameterSaveSnapshot=Parameter[i];
        if(IndoorParameterSaveSnapshot>Parameter_max[i] ||
           IndoorParameterSaveSnapshot<Parameter_min[i])
        {
            Parameter[i]=Old_Parameter[i];
            IndoorParameterSaveState=0;
            return;
        }
        IndoorParameterSaveFailed=!CI2C_WriteByte(
            (uint8_t)((uint16_t)IndoorParameterSaveSnapshot>>8),16+2*i);
        IndoorParameterSaveTick=Systick_1ms;
        IndoorParameterSaveState=2;
        break;
    case 2:
        if(Systick_1ms-IndoorParameterSaveTick<8)return;
        i=IndoorParameterSaveIndex;
        if(!CI2C_WriteByte((uint8_t)IndoorParameterSaveSnapshot,16+2*i+1))
            IndoorParameterSaveFailed=1;
        IndoorParameterSaveTick=Systick_1ms;
        IndoorParameterSaveState=3;
        break;
    case 3:
        if(Systick_1ms-IndoorParameterSaveTick<8)return;
        i=IndoorParameterSaveIndex;
        if(!CI2C_ReadByte(bytes,2,16+2*i))IndoorParameterSaveFailed=1;
        stored=(int16_t)(((uint16_t)bytes[0]<<8)|bytes[1]);
        if(IndoorParameterSaveFailed || stored!=IndoorParameterSaveSnapshot)
        {
            CPURomWriteError=i;
            if(Parameter[i]==IndoorParameterSaveSnapshot)Parameter[i]=Old_Parameter[i];
        }
        else Old_Parameter[i]=IndoorParameterSaveSnapshot;
        IndoorParameterSaveState=0;
        break;
    default:
        IndoorParameterSaveState=0;
        break;
    }
}

'''.replace('\n','\r\n').encode('ascii')

def indoor_sys(b):
    anchor=b'#define EE_CMD_noOK 0'
    assert b.count(anchor)==1
    return b.replace(anchor,WRITER+anchor)

def action(b):
    b=replace(b,'((UserWorkModeSetTEMP == MODE_HEAT) && ((HeatingFaultDisp) || (HeatFaultX6) || (PreHeatFaultX7)))',
                '((HeatingFaultDisp) || (HeatFaultX6) || (PreHeatFaultX7))')
    b=replace(b,'static void IndoorAiCfgTask(void)',
        '/* Serialize normal settings and the AI journal on the same EEPROM. */\r\n'
        'extern unsigned char IndoorParameterStorageBusy(void);\r\n'
        'unsigned char IndoorAiStorageBusy(void)\r\n{\r\n\treturn IndoorAiStState != 0;\r\n}\r\n'
        'static void IndoorAiCfgTask(void)')
    b=replace(b,'if(Systick_1ms < 6000UL)return;',
                'if(Systick_1ms < 6000UL || IndoorParameterStorageBusy())return;')
    b=replace(b,'\tCI2C_ReadByte(IndoorAiVerify, INDOOR_AI_SLOT_SIZE, IndoorAiStAddr);',
        '\tif((now - IndoorAiStTick) < INDOOR_AI_WRITE_GAP_MS)return;\r\n'
        '\tCI2C_ReadByte(IndoorAiVerify, INDOOR_AI_SLOT_SIZE, IndoorAiStAddr);')
    # Completion must acknowledge only the record actually written, never live values.
    start=b.index(b'\tif(IndoorAiRecValid(IndoorAiVerify) &&')
    end=b.index(b'\tIndoorAiStState = 0;',start)
    b=b[:start]+'''\tif(IndoorAiRecValid(IndoorAiVerify) && (IndoorAiVerify[3] == IndoorAiRec[3]))
\t{
\t\tIndoorAiCfgActive = IndoorAiStSlot;
\t\tIndoorAiCfgSeq[IndoorAiStSlot] = IndoorAiRec[3];
\t\tIndoorAiCfgDirty = 0;
\t\tfor(i=0;i<INDOOR_AI_CFG_CHANNELS*INDOOR_AI_CFG_WORDS;i++)
\t\t{
\t\t\tIndoorAiCfgShadow[i] = (int16_t)(((uint16_t)IndoorAiRec[5+2*i] << 8) | IndoorAiRec[6+2*i]);
\t\t\tIndoorAiLastSeen[i] = Parameter[INDOOR_AI_CFG_BASE+i];
\t\t\tif(IndoorAiLastSeen[i] != IndoorAiCfgShadow[i])IndoorAiCfgDirty = 1;
\t\t}
\t\tif(IndoorAiCfgDirty)IndoorAiCfgChangeTick = now;
\t}
'''.replace('\n','\r\n').encode('ascii')+b[end:]
    return b

edit('PSC316RK-V12-外机/SYSTEM/src/sysrun.c',outdoor)
edit('PSC330RK-V10-内机/User/wellthinker/src/sys.c',indoor_sys)
edit('PSC330RK-V10-内机/User/UserSrc/UserAction.c',action)
edit('PSC330RK-V10-内机/User/UserSrc/ErrorCheck.c',lambda b:replace(b,
    'if(HeatingFaultDisp && UserWorkModeSetTEMP==MODE_HEAT)','if(HeatingFaultDisp)'))
edit('PSC330RK-V10-内机/User/UserHead/User.h',lambda b:replace(replace(b,
    '#define PSC330_VERSION_MINOR        48','#define PSC330_VERSION_MINOR        49'),
    '#define PSC330_VERSION_DAY          4','#define PSC330_VERSION_DAY          5'))
edit('PSC316RK-V12-外机/WELLTHINKER/User/User.h',lambda b:replace(replace(b,
    '#define PSC316_VERSION_MINOR 38','#define PSC316_VERSION_MINOR 39'),
    '#define PSC316_VERSION_DAY 4','#define PSC316_VERSION_DAY 5'))
(OUT/'change_manifest.json').write_text(json.dumps({'changes':changes,
    'changed_common_sources':{k:v['after'] for k,v in changes.items()},
    'unchanged_by_user_request':'340 and 345 defaults/ranges/behavior'},ensure_ascii=False,indent=2),'utf-8')
print('PATCHED',len(changes),'files; 340/345 untouched')
