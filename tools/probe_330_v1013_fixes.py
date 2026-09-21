# -*- coding: utf-8 -*-
"""330 V10.13 三处规格书修正的实机验证（探针）。

V10.13（2026-09-21）改了三处，当时**只编译通过、烧录，行为零实测**（见 §46.2）。
本脚本一次跑完三项。**V10.13 之前的行为也能跑**（会看到 ①②③ 全 FAIL）——
所以它同时是"改前/改后"的对照工具。

## ① §3.3.4 排毒/消排毒**排毒段**的送/排风机顺序

`IndoorSpecialFanStartTimeline()`（`UserAction.c:249`）旧版先取 `abs()` 再把排风机钉在 t=0
⇒ **[328] 的符号被丢掉，顺序永远选不出来**。V10.13 保留符号，约定
**正值排风先开、负值送风先开**（与正常开关机路径同语义）。

排毒段的执行体在 `IndoorDisinfectExhaustAction` step 2（`UserAction.c:1769-1786`）：

    supplyFan  = (count >= phaseSupplyStart)  ? 1 : 0;
    exhaustFan = (phaseExhaustPresent && (count >= phaseExhaustStart)) ? 1 : 0;
    IndoorDisinfectOutputs(2, supplyFan, 0, exhaustFan, 0);

⇒ 顺序完全由 `phaseSupplyStart` / `phaseExhaustStart` 决定，而这两个是 **函数内 static**
（`UserAction.c:1603-1605`）**没有 Modbus 镜像** ⇒ **只能走 SWD 读 `output[]`**：

    output[3] = Y03 = 送风机   (User.h:176  UserPumpY00 = Y03 = output[3])
    output[8] = Y10 = 排风机   (User.h:181  ExhaustFanY10 = Y10 = output[8])
⚠ output[] 按**通道顺序**编号，不是按 Y 号：Y00..Y07->0..7、Y10..Y17->8..15
  (User/wellthinker/inc/io.h)。第一版把排风机写成 output[10]，读到的其实是
  Y12=DisinfectY12(消毒装置)，排毒模式恒 0 —— 白等一轮。

`output[]` 基址 `0x20001364`（`io.o .bss`，见 `tools/_read_heat_io.py`）。
`parameter[926] SupplyFanDemandDisp` 只有送风侧，**排风侧没有**，所以必须读 SWD。

## ② [328] 范围 ±90 → ±60

规格书 §3.3.1/§3.3.3 写的是 `[排风机启动→30s（±60s可调）]`，代码原来允许并钳到 ±90。
判据：写 70 **必须读不回 70**（旧代码会接受）；写 60 必须被接受（边界仍可用）。

## ③ §3.1〖混风阀〗/〖排风阀〗的前置条件

规格书原文（第 139-142 行，两个阀门带**同一个**括号）：

    〖混风阀〗…(此项与新风阀两者之间为1)(此项选择要求新风阀根据CO2浓度及新回风焓差控制)
    〖排风阀〗…(此项与新风阀两者之间为1)(此项选择要求新风阀根据CO2浓度及新回风焓差控制)

旧代码只校了"新风阀是 0-10V"，**漏了"控制依据必须是 CO2/焓差"**。
`FreshValveCtrlBasisSet == 2` 时新风阀走的是**手动电压**（`UserAction.c:690`
`demand = FreshValveManualVoltSet * 10`），此时混风阀没有可跟随的目标却照样动作。
V10.13 补上 `&& (FreshValveCtrlBasisSet == 1)`（`UserAction.c:1178-1185`）。

判据用 AO 的实际输出镜像（**这一批正是 §45 A 项说的十个活镜像**）：

    [917] FinalDA3Disp = 新风阀    [919] FinalDA5Disp = 混风阀    [920] FinalDA6Disp = 排风阀

**为什么"清 0"那一路能盖住**（`AO` 有 5 个写点，只有 2 个补了条件）：

    ExhaustValveAO6 写点： UserAction.c:1036 / 1040 / 1070 / 1211 / 3254
    MixValveAO5   写点： UserAction.c:724  / 729  / 1072 / 1222
    ③ 只补了 1211（exhaustValveAOValid）与 1222（mixValveValid），都在
    IndoorEnforceConfiguredOutputDisable() 里。

成立与否**完全取决于每扫描的调用顺序**（`user.c:2000-2008`）：

    IndoorEnforceConfiguredOutputDisable()   // 2003  ← ③ 的清 0
    IoOutAction();                           // 2005  ← 锁存
    ...
    IndoorSyncFinalAOStatus();               // 2008  ← [917]/[919]/[920] 镜像

SET（在 `UserAction()` 2001 里）→ CLEAR（2003，在锁存之前 ✓）→ MIRROR（2008，最后 ✓）。
⚠ 2007 那次 Enforce 在 `IoOutAction()` **之后**，本扫描锁不进去 —— 真正起作用的是 2003 那次。
**这是"预热 DO 不吸合"那次的同类坑（谁先谁后决定成败）**，所以 ① 的排毒段顺便复验它。

**③ 的两半要在不同工况下判，别混**：

| | 判据 | 为什么 |
|---|---|---|
| **排风阀** `[920]` | 排毒段可判：`ExhaustValveAO6 = exhaustValveOpen ? freshDemand : 0`，排毒段 `freshDemand=1000` ⇒ 修好后必须被清成 **0** | 走的正是**没补条件**的 1036 写点，等于直接验调用顺序 |
| **混风阀** `[919]` | 排毒段**判不了**：`MixValveAO5 = 1000 - freshDemand = 0`，本来就该是 0 | 要**正常运行态**（`forcedDemand=-1`、阀门开）且有**部分**新风需求，`1000-freshDemand ≠ 0` 才有区分度 |

**自证设计**：先让新风阀**真的被驱动**，`[917]` 非 0 才说明"有活的驱动源"。
停机状态下 `[917]` 必为 0（`IndoorApplyFreshAndMixValve` 第 717 行 `if(!valveOpen)freshDemand=0`）
⇒ 本项 **INCONCLUSIVE**，不要报通过。

## ④ ③ 的混风阀那一格（通风模式，需单独跑）

排毒段判不了混风阀（`1000-1000=0`，本来就该是 0），要判得走**正常开机路径**
`IndoorApplyFanValveState`（`UserAction.c:1077`，传 `forcedDemand=-1` ⇒ 需求真算）。

用**通风模式**（不启压缩机）+ `[377]=2`（手动电压）+ `[380]=50` ⇒ `freshDemand=500`
⇒ 放行则混风阀 `[919]=500`、**修好后必须 0**。A/B 对照切 `[377]=1`（合法）⇒ `[919]` 应能动。

⚠ 对照必须拿到**部分**需求：`demand = 500 + (CO2Disp - CO2Set)/2`，
台面 `CO2Disp[903]` 是**探头浮空的越界值 1770** ⇒ 若 `CO2Set` 设低了需求会**饱和到 1000**，
混风阀就又变成"本来就该 0"，对照作废。**脚本会把 `CO2Set` 压到实时 `CO2Disp`。**

## 实测结论（2026-09-21，V10.13 全通过）

    ② 超界写被**拒绝**（回读保持原值，不是钳到 60）；边界 ±60 可用   -> 4/4 PASS
    ① [328]=+30 -> 送风机偏移 +29.9s（排风先）;  [328]=-30 -> 送风机 +0.0s / 排风机 +30.0s
       ⚠ 只有 -30 有区分度：正号时新旧代码走**同一分支**
    ③ 排毒段 [920]=0（走的是**没补条件**的 1036 写点 => 实证 Enforce 调用顺序有效）
       通风模式 依据=手动电压 -> [919]=0；依据=CO2/焓差 -> [919]=500（对照成立，排除混淆）

## ⚠ 坑（写同类探针前先看）

1. **`app.py` 会拦住 ②③ 要写的值**：`min/max` 已收到 ±60（②），且 `app.py:5152/5154`
   早就 raise 拦住 ③ 的组合。所以本脚本用 **`client.write_single_register()` 底层写**，
   绕过工具校验 —— **这是故意的，不是 bug**。
2. **改的是掉电保存的参数**：`[328]/[335]/[338]/[377]/[380]/[381]` 全 < 500 ⇒ 进 EEPROM。
   脚本先落盘快照 `<本脚本名>.restore.txt`，并在 `finally` 里无条件还原。
   **别用 Ctrl-C 之外的方式硬杀**；真被硬杀就照那个文件手工写回。
3. **[328] 的符号语义**要跟正常开关机路径一致（正值排风先开），别只看"有没有延时"。

跑法：
    python.exe tools/probe_330_v1013_fixes.py --dry          # 只读：现状 + 前置条件
    python.exe tools/probe_330_v1013_fixes.py --only=2,3     # 纯寄存器，不动运行模式
    python.exe tools/probe_330_v1013_fixes.py --only=4       # 通风模式判混风阀，约 1 分钟
    python.exe tools/probe_330_v1013_fixes.py --only=1 --sign=-30   # ① 单符号，约 5 分钟
    python.exe tools/probe_330_v1013_fixes.py --only=1 --sign=+30

⚠ ① 一轮 ≈5min（排毒 step1 就要 150s），**别把 ±30 放同一次跑**（会超工具超时上限）。
⚠ ① 需 ST-Link 挂 330 且台面要配排风机（脚本会自动配 `[331]=1` 并还原）。
"""
from __future__ import annotations

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "psc330_monitor_tool" / "psc330_monitor"))

PORT, SLAVE = "COM6", 1
OUT = pathlib.Path(__file__).resolve().with_suffix(".txt")
RESTORE = pathlib.Path(__file__).resolve().with_suffix(".restore.txt")

# ---- 寄存器 ----
R_MODE, R_SYSSTEP, R_ONOFF = 236, 709, 398          # 工作模式 / 系统步 / 开停机命令
R_DISSTEP = 885                                      # DisinfectStepDisp（消排毒内部步 1~6）
R_INTERVAL = 328                                     # 排风机与送风机间隔（带符号！）
R_FRESH_MODE, R_EXH_MODE = 335, 338                  # INDOOR_SPEC_BASE(315)+20 / +23
R_BASIS, R_MANUAL_V, R_MIX_TYPE = 377, 380, 381      # INDOOR_SPEC_EXT_BASE(374)+3 / +6 / +7
R_SUPPLY_DEMAND = 926                                # SupplyFanDemandDisp（只有送风侧）
R_EXH_FAN = 331                                      # ExhaustFanModeSet（0=无 ⇒ ① 的时间轴会早退）
EXHAUST_FAN_DO = 1                                   # User.h:782
R_FRESH_AO, R_MIX_AO, R_EXH_AO = 917, 919, 920       # FinalDA3 / FinalDA5 / FinalDA6

VALVE_NONE, VALVE_DO, VALVE_AO = 0, 1, 2             # User.h:789-791
MODE_VENT = 2                                        # User.h:488 (通风，不启压缩机)
R_CO2SET = 379                                       # INDOOR_SPEC_EXT_BASE(374)+5
R_CO2DISP = 903                                      # CO2Disp 实时浓度（RO；见点位表 md 第 903 行）
WM = {0: "制冷", 1: "制热", 2: "通风", 3: "消毒", 4: "排毒", 5: "自动消排毒"}
BASIS = {0: "无/未用", 1: "CO2+新回风焓差", 2: "手动/按键电压"}

POLL_LIMIT = 330          # ① 单符号轮询上限：>150s(step1 开阀) + 风机相位 + 余量
OUT_BASE = 0x20001364     # io.o .bss -> output[16]
# ⚠ output[] 是按**通道顺序**编号的，不是按 Y 号！(User/wellthinker/inc/io.h:27,33)
#     Y00..Y07 -> output[0..7]      Y10..Y17 -> output[8..15]
#   所以 Y10(排风机) = output[8] —— 写成 10 就读到 Y12(消毒装置)了。
Y_SUPPLY, Y_EXHAUST = 3, 8    # Y03 送风机 / Y10 排风机

# DisinfectStepDisp[885]：消排毒内部步 1~6（UserAction.c:1851）
DIS_HINT = {
    1: "开阀 → **等 150s**（排毒：新风+送风+排风）",
    2: "开风机 ← 顺序在这一步里决定，本脚本正盯这里",
    3: "消毒装置 / 计时", 4: "排毒计时（按【排毒模式运行时间】）",
    5: "关送风机 → 等 30s", 6: "收尾：逆序停风机", 7: "全关输出前等 30s",
}

LINES: list[str] = []
SNAP: dict[int, int] = {}


def say(s: str = "") -> None:
    LINES.append(s)
    try:
        print(s, flush=True)
    except UnicodeEncodeError:
        print(s.encode("gbk", "replace").decode("gbk", "replace"), flush=True)
    flush()          # 增量落盘：① 单符号就要 5 分钟以上，中途被杀也不丢


def flush() -> None:
    OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")


def s16(v: int) -> int:
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def main() -> int:
    import app as m

    args = sys.argv[1:]
    dry = "--dry" in args
    only = "123"
    one_sign = None
    for a in args:
        if a.startswith("--only="):
            only = a.split("=", 1)[1]
        elif a.startswith("--sign="):
            one_sign = int(a.split("=", 1)[1])     # 只跑 ① 的这一个符号（一轮 ≈5min，见下）

    import serial.tools.list_ports as _lp
    have = [p.device for p in _lp.comports()]
    say("=== 330 V10.13 三处规格书修正 —— 实机验证 ===")
    say("端口预检：%s  %s" % (PORT, "在" if PORT in have else "**不在**（现有：%s）" % have))
    if PORT not in have:
        say("✗ %s 不存在，直接退出（不空等）。" % PORT)
        flush()
        return 1

    client = m.ModbusRtuClient()
    client.open(PORT, m.DEFAULT_BAUD)

    def rd(a):
        for _ in range(3):
            try:
                return s16(client.read_holding_registers(SLAVE, a, 1)[0])
            except Exception:  # noqa: BLE001
                time.sleep(0.05)
        return None

    def wr(a, v, chk=True):
        """底层写，**绕过 app.py 的 min/max 与 _validate_mode_config**（见文件头坑 1）。"""
        for _ in range(3):
            try:
                client.write_single_register(SLAVE, a, v & 0xFFFF)
                time.sleep(0.4)
                if not chk:
                    return True
                got = rd(a)
                return got == s16(v)
            except Exception:  # noqa: BLE001
                time.sleep(0.2)
        return False

    def snapshot(regs):
        for r in regs:
            if r not in SNAP:
                v = rd(r)
                if v is not None:
                    SNAP[r] = v

    def dump_restore():
        if not SNAP:
            return
        body = ["# 330 V10.13 探针的快照 / 还原值（原值，掉电保存参数）",
                "# 手工还原： python.exe tools/rw330.py %s" %
                " ".join("%d=%d" % (k, v) for k, v in sorted(SNAP.items())), ""]
        body += ["%d = %d" % (k, v) for k, v in sorted(SNAP.items())]
        RESTORE.write_text("\n".join(body) + "\n", encoding="utf-8")

    # ---------- 现状 ----------
    snapshot([R_MODE, R_INTERVAL, R_FRESH_MODE, R_EXH_MODE, R_BASIS, R_MANUAL_V,
              R_MIX_TYPE, R_ONOFF])
    dump_restore()
    say()
    say("=== 现状（原值已存 %s）===" % RESTORE.name)
    say("  模式[%d]=%s   SysStep[%d]=%s   OnOff[%d]=%s"
        % (R_MODE, WM.get(rd(R_MODE), rd(R_MODE)), R_SYSSTEP, rd(R_SYSSTEP),
           R_ONOFF, rd(R_ONOFF)))
    say("  [%d] 排风-送风间隔 = **%s**（符号决定顺序：正=排风先 / 负=送风先）"
        % (R_INTERVAL, rd(R_INTERVAL)))
    say("  [%d] 新风阀方式=%s   [%d] 排风阀方式=%s"
        % (R_FRESH_MODE, rd(R_FRESH_MODE), R_EXH_MODE, rd(R_EXH_MODE)))
    say("  [%d] 新风控制依据=%s   [%d] 手动电压=%s(=%.1fV)   [%d] 混风阀=%s"
        % (R_BASIS, BASIS.get(rd(R_BASIS), rd(R_BASIS)), R_MANUAL_V, rd(R_MANUAL_V),
           (rd(R_MANUAL_V) or 0) / 10.0, R_MIX_TYPE, rd(R_MIX_TYPE)))
    say("  AO 实际输出： 新风阀[%d]=%s  混风阀[%d]=%s  排风阀[%d]=%s"
        % (R_FRESH_AO, rd(R_FRESH_AO), R_MIX_AO, rd(R_MIX_AO), R_EXH_AO, rd(R_EXH_AO)))
    say("  [%d] 送风 demand=%s（排风侧无此镜像 ⇒ ① 必须走 SWD）"
        % (R_SUPPLY_DEMAND, rd(R_SUPPLY_DEMAND)))
    if dry:
        say()
        say("--dry：到此为止（未写任何寄存器）。")
        client.close()
        flush()
        return 0

    fails: list[str] = []
    incon: list[str] = []          # 未判定 ≠ 失败：工况不具备时不许报通过，也不该报失败
    try:
        # ================= ② [328] ±90 -> ±60 =================
        if "2" in only:
            say()
            say("=== ② [%d] 范围 ±90 -> ±60 ===" % R_INTERVAL)
            orig = rd(R_INTERVAL)
            snapshot([R_INTERVAL])
            cases = [(70, False, "超上限，**必须读不回**"), (-70, False, "超下限，**必须读不回**"),
                     (60, True, "边界上限，必须被接受"), (-60, True, "边界下限，必须被接受")]
            for val, want_accept, why in cases:
                wr(R_INTERVAL, val, chk=False)
                time.sleep(1.2)          # 网关写一次要 12~15s，多给点时间再回读
                got = rd(R_INTERVAL)
                ok = (got == val) if want_accept else (got != val)
                say("  写 %+4d -> 回读 %-6s  %s   (%s)"
                    % (val, got, "PASS" if ok else "**FAIL**", why))
                if not ok:
                    fails.append("② 写 %d 回读 %s" % (val, got))
            wr(R_INTERVAL, orig if orig is not None else 0)

        # ================= ③ 混风阀/排风阀 前置条件 =================
        if "3" in only:
            say()
            say("=== ③ §3.1 混风阀/排风阀 需要 新风依据==CO2/焓差 ===")
            snapshot([R_FRESH_MODE, R_EXH_MODE, R_BASIS, R_MANUAL_V, R_MIX_TYPE])
            say("  步骤 1（自证：让新风阀真的被驱动）")
            say("     [%d]=%d(AO)  [%d]=%d(手动电压)  [%d]=50(5.0V)"
                % (R_FRESH_MODE, VALVE_AO, R_BASIS, 2, R_MANUAL_V))
            wr(R_FRESH_MODE, VALVE_AO)
            wr(R_BASIS, 2)
            wr(R_MANUAL_V, 50)
            time.sleep(2.0)
            fresh = rd(R_FRESH_AO)
            live = (fresh or 0) != 0
            say("     新风阀实际输出[%d] = %s  ->  %s"
                % (R_FRESH_AO, fresh, "有活驱动源，继续" if live else
                   "**为 0 ⇒ 本项 INCONCLUSIVE**（无驱动源，③ 无法判定）"))
            if live:
                say("  步骤 2（本修正的判据：混风阀/排风阀必须被强制归 0）")
                wr(R_MIX_TYPE, 1)
                wr(R_EXH_MODE, VALVE_AO)
                time.sleep(2.0)
                mixv, exhv = rd(R_MIX_AO), rd(R_EXH_AO)
                ok = ((mixv or 0) == 0) and ((exhv or 0) == 0)
                say("     [%d]=1(混风阀选上)  [%d]=%d(排风阀 AO) -> 混风阀[%d]=%s 排风阀[%d]=%s"
                    % (R_MIX_TYPE, R_EXH_MODE, VALVE_AO, R_MIX_AO, mixv, R_EXH_AO, exhv))
                say("     %s  （修前这两个会跟着新风阀动）" % ("PASS" if ok else "**FAIL**"))
                if not ok:
                    fails.append("③ 依据=手动电压时 混风阀=%s 排风阀=%s（应为 0）" % (mixv, exhv))
            else:
                incon.append("③ 混风阀：机组停机、新风阀输出为 0 ⇒ 无驱动源（需正常运行态才能判）")

            say("  步骤 3（对照：依据改回 CO2/焓差，混风阀应恢复可动）")
            wr(R_BASIS, 1)
            time.sleep(2.0)
            mixv = rd(R_MIX_AO)
            say("     [%d]=1 -> 混风阀[%d]=%s  %s"
                % (R_BASIS, R_MIX_AO, mixv,
                   "已恢复可动" if (mixv or 0) != 0 else
                   "仍为 0：无 CO2/焓差需求 ⇒ 本步 inconclusive（不算失败）"))

        # ================= ① 排毒段的风机顺序（需 SWD） =================
        if "1" in only:
            say()
            say("=== ① §3.3.4 排毒段送/排风机顺序（需 ST-Link 挂 330）===")
            say("  排风机 DO（Y10）与送风机 DO（Y03）不在 Modbus 镜像里，" +
                "必须 SWD 读 output[] @0x%X" % OUT_BASE)
            try:
                from pyocd.core.helpers import ConnectHelper
                session = ConnectHelper.session_with_chosen_probe(
                    target_override="stm32f407ze",
                    options={"frequency": 1000000, "connect_mode": "attach"})
                session.open()
                t = session.target
                dev = int.from_bytes(bytes(t.read_memory_block8(0xE0042000, 4)), "little") & 0xFFF
                say("  SWD 已 attach（core state = %s，DEV_ID = 0x%03X）" % (t.get_state(), dev))
                if dev != 0x413:
                    say("  ✗ **DEV_ID 不是 0x413（F407）—— ST-Link 没挂在 330 上，跳过 ①**")
                    say("    （这就是 §46.4 那次误烧的原因：连板前先验 DEV_ID）")
                    session.close()
                    incon.append("① 跳过：ST-Link 未挂在 330（DEV_ID=0x%03X）" % dev)
                else:
                    def fans():
                        b = bytes(t.read_memory_block8(OUT_BASE, 16))
                        return b[Y_SUPPLY], b[Y_EXHAUST]

                    snapshot([R_MODE, R_INTERVAL, R_ONOFF, R_BASIS])
                    # 顺便在同一次排毒里判 ③-排风阀：排毒段强迫 freshDemand=1000，
                    # 而排风阀的写点(UserAction.c:1036)是**没补 FreshValveCtrlBasisSet 条件**的那个，
                    # 全靠 IndoorEnforceConfiguredOutputDisable() 每扫描盖掉它 ⇒ 正好验证调用顺序。
                    # 混风阀在同一次里**判不了**：它是 (1000 - freshDemand) = 0，本来就该是 0。
                    wr(R_BASIS, 2)
                    say("  已把 [%d] 依据改成 2=手动电压（排毒段不依赖它，freshDemand 被钉成 1000）" % R_BASIS)
                    # ⚠ 没配排风机时 IndoorSpecialFanStartTimeline 直接早退、把时间轴全清 0
                    #   （UserAction.c:260-267）⇒ [328] 的符号根本走不到。台面实测就是
                    #   sequenceEnd=0（step2 只 0.1s）+ 排风机 Y10 全程不起。所以这里补配。
                    snapshot([R_EXH_FAN])
                    if (rd(R_EXH_FAN) or 0) == 0:
                        okr = wr(R_EXH_FAN, EXHAUST_FAN_DO)
                        say("  ⚠ 台面未配排风机（[%d]=0）⇒ 时间轴会早退、① 无从成立。"
                            "已临时补配为 1(DO)  回读%s" % (R_EXH_FAN, "OK" if okr else "!! 失败"))
                        dump_restore()
                        if not okr:
                            incon.append("① 排风机补配失败，未测")
                    else:
                        say("  台面已配排风机 [%d]=%s" % (R_EXH_FAN, rd(R_EXH_FAN)))
                    say("  先确认机组是停的：SysStep[%d]=%s" % (R_SYSSTEP, rd(R_SYSSTEP)))
                    signs = [one_sign] if one_sign is not None else [+30, -30]
                    for sign in signs:
                        say()
                        say("  ---- [%d] = %+d（%s先开）----"
                            % (R_INTERVAL, sign, "排风机" if sign > 0 else "送风机"))
                        if not wr(R_INTERVAL, sign):
                            say("     !! 写 [%d]=%+d 失败（回读不符）—— 本符号作废"
                                % (R_INTERVAL, sign))
                            incon.append("① [328]=%+d 写入失败" % sign)
                            continue
                        ok = wr(R_MODE, 4)          # 4 = 排毒
                        say("     进排毒 [%d]=4 回读%s" % (R_MODE, "OK" if ok else "!! 失败"))
                        wr(R_ONOFF, 1)              # 开机
                        t0 = time.time()
                        first = {Y_SUPPLY: None, Y_EXHAUST: None}
                        t_step2 = None
                        last_ds = None
                        # ⚠ 上限必须 > 150s：排毒 **step 1 是"开阀等 150s"**，
                        #   风机相位(step 2) 要等它走完才开始（见 DIS_HINT）。
                        while time.time() - t0 < POLL_LIMIT:
                            now = time.time() - t0
                            ds = rd(R_DISSTEP)
                            if ds != last_ds:
                                say("     t=%6.1fs  [%d]=%s  %s"
                                    % (now, R_DISSTEP, ds, DIS_HINT.get(ds, "")))
                                if ds == 2 and t_step2 is None:
                                    t_step2 = now
                                last_ds = ds
                            su, ex = fans()
                            if su and first[Y_SUPPLY] is None:
                                first[Y_SUPPLY] = now
                                say("     t=%6.1fs  送风机(Y3=output[3]) 起" % now)
                            if ex and first[Y_EXHAUST] is None:
                                first[Y_EXHAUST] = now
                                say("     t=%6.1fs  排风机(Y10=output[8]) 起" % now)
                            if all(v is not None for v in first.values()):
                                break
                            # 已经离开 step 2 ⇒ 不会再起风了，别空等到超时
                            if t_step2 is not None and ds is not None and ds != 2:
                                break
                            time.sleep(0.05)

                        # 排毒段 AO：顺手验 ③-排风阀（freshDemand 被钉成 1000）
                        f17, m19, e20 = rd(R_FRESH_AO), rd(R_MIX_AO), rd(R_EXH_AO)
                        say("     排毒段 AO：新风阀[%d]=%s  混风阀[%d]=%s  排风阀[%d]=%s"
                            % (R_FRESH_AO, f17, R_MIX_AO, m19, R_EXH_AO, e20))
                        if (f17 or 0) == 0:
                            say("     ⚠ 新风阀为 0 ⇒ 本次 ③-排风阀 判据 INCONCLUSIVE")
                            incon.append("③-排风阀：排毒段新风阀=0，无驱动源")
                        else:
                            ok3 = (e20 or 0) == 0
                            say("     => ③-排风阀：依据=手动电压时排风阀必须为 0  %s"
                                % ("PASS" if ok3 else "**FAIL**"))
                            if not ok3:
                                say("        （排毒走的是 UserAction.c:1036 那个**没补条件**的写点，"
                                    "靠 Enforce 每扫描盖掉 —— FAIL 说明调用顺序失效）")
                                fails.append("③-排风阀 排毒段 [%d]=%s（应为 0）" % (R_EXH_AO, e20))
                        say("     （混风阀[%d]=%s 不判：排毒段 1000-1000=0，本来就该是 0）"
                            % (R_MIX_AO, m19))

                        wr(R_ONOFF, 0)              # 停

                        # ---- 判据：用**送风机相对 step 2 起点**的偏移 ----
                        #   ⚠ 新旧代码在 [328] 为正时走**同一分支**（旧版 abs() 后同样是
                        #     exhaustStart=0/supplyStart=fanDelay）⇒ +30 只是基线，
                        #     **只有 -30 有区分度**（旧=排风先 / 新=送风先）。
                        #   用送风机判还顺带绕开"排风机可能不起"的问题。
                        if t_step2 is None or first[Y_SUPPLY] is None:
                            say("     => 没抓到 step 2 或送风机（step2=%s 送=%s）⇒ inconclusive"
                                % (t_step2, first[Y_SUPPLY]))
                            incon.append("① [328]=%+d 未观测到 step2/送风机" % sign)
                        else:
                            off_su = first[Y_SUPPLY] - t_step2
                            off_ex = (None if first[Y_EXHAUST] is None
                                      else first[Y_EXHAUST] - t_step2)
                            say("     相对 step2 的偏移：送风机 %+.1fs   排风机 %s"
                                % (off_su, "未起" if off_ex is None else "%+.1fs" % off_ex))
                            want_su_first = (sign < 0)
                            if want_su_first:
                                ok1 = off_su < 3.0
                                why = "期望送风机**先**开（偏移≈0）"
                            else:
                                ok1 = off_su > abs(sign) - 3.0
                                why = "期望送风机**后**开（偏移≈%d s）" % abs(sign)
                            if off_ex is not None:
                                ok2 = (off_ex > off_su) if want_su_first else (off_ex < off_su)
                            else:
                                ok2 = True      # 排风机没起，只用送风机判
                            say("     => %s   %s%s"
                                % (why, "PASS" if (ok1 and ok2) else "**FAIL**",
                                   "" if ok2 else "（两机先后与期望相反）"))
                            if not (ok1 and ok2):
                                fails.append("① [328]=%+d 送风机偏移 %.1fs / 排风机 %s（%s）"
                                             % (sign, off_su,
                                                "未起" if off_ex is None else "%.1fs" % off_ex,
                                                why))
                        # 等停机序列收尾，避免下一轮带着"运行态"进去（会先跑 210~214）
                        for _ in range(60):
                            if rd(R_SYSSTEP) == 0:
                                break
                            time.sleep(2.0)
                        time.sleep(5)
                    session.close()
            except ImportError:
                say("  ✗ 没装 pyocd ⇒ 跳过 ①（`pip install pyocd`）")
                incon.append("① 跳过：pyocd 不可用")
            except Exception as e:  # noqa: BLE001
                say("  ✗ SWD 打不开（%s）⇒ 跳过 ①" % e)
                say("    多半是 ST-Link 不在 330 上，或没插。先跑 tools/_which_board.py 确认。")
                incon.append("① 跳过：SWD 打不开")

        # ================= ④ ③ 的混风阀那一格（需通风模式） =================
        if "4" in only:
            say()
            say("=== ④ ③ 的混风阀那一格：通风模式（不启压缩机）===")
            say("  混风阀 = 1000 - freshDemand，排毒段是 1000-1000=0 判不了；")
            say("  这里走**正常开机路径** IndoorApplyFanValveState(UserAction.c:1077)，")
            say("  它传 forcedDemand=-1 ⇒ freshDemand 真算：依据=手动电压时 = [%d]*10。" % R_MANUAL_V)
            say("  取 [%d]=50 ⇒ freshDemand=500 ⇒ 若放行 混风阀[%d] 应为 500；**修好后必须 0**。"
                % (R_MANUAL_V, R_MIX_AO))
            snapshot([R_MODE, R_ONOFF, R_BASIS, R_MANUAL_V, R_MIX_TYPE,
                      R_FRESH_MODE, R_EXH_MODE, R_CO2SET, R_CO2DISP])
            wr(R_FRESH_MODE, VALVE_AO)
            wr(R_MIX_TYPE, 1)
            for basis, tag in ((2, "依据=手动电压 ⇒ **修好后必须为 0**"),
                               (1, "依据=CO2/焓差 ⇒ 合法，应能动（对照）")):
                wr(R_BASIS, basis)
                wr(R_MANUAL_V, 50)
                # ⚠ 依据=1 时 demand = 500 + (CO2Disp - CO2Set)/2，若 CO2Set 太低会**饱和到
                #   1000** ⇒ 混风阀 = 1000-1000 = 0 本来就该是 0，对照就废了（第一版踩了这个：
                #   写 CO2Set=400 结果 CO2Disp 是浮空高值、[917] 冲到 1000）。
                #   把 CO2Set 设成**实时 CO2Disp** 才能压出 ≈500 的部分需求。
                co2 = rd(R_CO2DISP)
                wr(R_CO2SET, co2 if co2 is not None else 400)
                say("     [basis=%d] 预置：CO2Set[%d]=%s（实时 CO2Disp[%d]=%s）⇒ 期望 freshDemand≈500"
                    % (basis, R_CO2SET, rd(R_CO2SET), R_CO2DISP, co2))
                t0 = time.time()
                wr(R_MODE, MODE_VENT)
                wr(R_ONOFF, 1)
                f17 = m19 = None
                last = None
                while time.time() - t0 < 180:
                    f17, m19 = rd(R_FRESH_AO), rd(R_MIX_AO)
                    if (f17, m19) != last:
                        say("     [basis=%d] t=%6.1fs 新风阀[%d]=%s 混风阀[%d]=%s SysStep=%s"
                            % (basis, time.time() - t0, R_FRESH_AO, f17,
                               R_MIX_AO, m19, rd(R_SYSSTEP)))
                        last = (f17, m19)
                    if (f17 or 0) != 0:
                        time.sleep(1.5)            # 稳一下，别拿瞬态当结论
                        f17, m19 = rd(R_FRESH_AO), rd(R_MIX_AO)
                        say("     稳定后：新风阀=%s  混风阀=%s   %s" % (f17, m19, tag))
                        break
                    time.sleep(0.5)
                wr(R_ONOFF, 0)
                for _ in range(60):
                    if rd(R_SYSSTEP) == 0:
                        break
                    time.sleep(2.0)
                if (f17 or 0) == 0:
                    incon.append("④ basis=%d：通风模式下新风阀仍为 0（无驱动源）" % basis)
                    continue
                if basis == 2:
                    ok = (m19 or 0) == 0
                    say("     => %s   （未修的话这里会是非 0，约 %d）"
                        % ("PASS" if ok else "**FAIL**", 1000 - (f17 or 0)))
                    if not ok:
                        fails.append("④ 依据=手动电压 混风阀[%d]=%s（应为 0）" % (R_MIX_AO, m19))
                elif (m19 or 0) != 0:
                    say("     => 对照成立：依据合法时混风阀能动（=%s）" % m19)
                else:
                    say("     => 对照 inconclusive：依据合法（新风阀=%s）但混风阀仍 0"
                        % f17)
                    if (f17 or 0) >= 1000:
                        say("        ⚠ 新风阀已**饱和到 1000** ⇒ 混风阀 1000-1000=0 本来就该是 0，"
                            "这条对照无效（要压 CO2Set≈CO2Disp 拿部分需求）")
                time.sleep(3)

    finally:
        # 无条件还原（改的都是掉电保存参数，见文件头坑 2）
        if SNAP:
            say()
            say("=== 还原 ===")
            for k, v in sorted(SNAP.items()):
                if k == R_ONOFF:
                    continue
                now = rd(k)
                if now != v:
                    okr = wr(k, v)
                    say("  [%d] %s -> %s  %s" % (k, now, v, "OK" if okr else "!! 请手工核对"))
            client.close()
            flush()

    say()
    if fails:
        say("!! **失败** %d 项：" % len(fails))
        for f in fails:
            say("   - %s" % f)
    if incon:
        say("-- 未判定 %d 项（工况不具备，**不算通过也不算失败**）：" % len(incon))
        for f in incon:
            say("   - %s" % f)
    if not fails and not incon:
        say("全部通过。")
    say("原值快照： %s" % RESTORE)
    flush()
    return 1 if fails else (2 if incon else 0)


if __name__ == "__main__":
    sys.exit(main())
