# -*- coding: utf-8 -*-
"""规格书 §3.3.5 紧急停机 —— 抓「除电子膨胀阀外所有用电设备均失电」的失电瞬间。

规格书原文（5）：
    紧急停机
    除电子膨胀阀外所有用电设备均失电，电子膨胀阀以20步/秒速度关闭。
    说明：电子膨胀阀关闭步数＝电子膨胀阀当前步数+10

**EEV 那半条 2026-09-18 已实测通过**（调试记录_20260916.md §21.11，跳 X04 → 四路 Δ=+10）。
本脚本补的是**另半条**：「所有用电设备均失电」—— 从来没人抓过 output[]/DA[] 的快照。

================================ 为什么用 ST-Link 而不是跳 X04 ================================

① 上次跳 X04 是物理动作，不可重复、不可控时；而且要人工做故障复位（闩锁）。
② 急停的三个触发门（ErrorCheck.c:620）里，`EnviTempErr` 是**唯一能被软件直接置位**的：
       UserSidePumpOverLoadErr [601] ← X03 送风机/泵过载 DI，只能物理跳
       AntiFreezeErr          [602] ← 全仓无写点，恒 0，**不可能触发**
       EnviTempErr            [605] ← 只由 ErrorCheck.c:380 那一处写 1（火警X01/联锁X04/漏水X13 闩锁汇合）
   而 [605] >= ParameterSaveSize(500) ⇒ Modbus 写不进去，**只能用 ST-Link 写 RAM**。
   全仓 grep `EnviTempErr` 只有「写 1」没有「写 0」⇒ 我写 0 就能干净复原，无残留。
   又因为我不跳 X04，Fire/ValveLink/Leak 三个 Latch 都还是 0，所以 [605] 是唯一置位源 —— 复原可控。

============================== 要定的三个疑点（都只有实测能定论） ==============================

【疑点 1】Y05 综合报警 —— 急停到底有没有做到"全失电"
    ErrorCheck.c:631   `for(i=0;i<TOL_OUTPUT_CHANEL;i++)output[i]=0;`   ← 清 0
    但**同一扫描稍后**（扫描序 UserAction→ErrorCheck→…→DispAction→IoOutAction→…）
    DispAction.c:471-476 `if(ErrTotal){ErrorOutFlag=1;} if(ErrorOutFlag==1)ErrorOutY00=1;`
    （User.h:178 `#define ErrorOutY00 Y05` ⇒ **output[5]**）
    而急停三源全在 ErrTotal 里（DispAction.c:425/426/463-465）⇒ **output[5] 会被拉回 1**。
    ⇒ 稳态下 output[0..15] 若只有 [5] 非 0，则"全失电"**字面不成立**（但有可能是故意的报警例外）。
    本脚本直接报 output[5] 的稳态值。

【疑点 2】急停时 output[] 与 DA[] 是否**同一拍**清干净（有没有先后残留窗口）
    代码是同扫描内两个相邻 for 循环（ErrorCheck.c:631/632），中间只隔几微秒。
    高速采样看过渡拍有没有"output 已 0 而 DA 还非 0"的中间态。

【疑点 3】EEV 关闭语义复核（外机 EEV 由 316 驱动，本脚本只看**内机 8 路**）
    期望 EEVCloseStepTarget()（eevCTRL.c:171-200）：
      · 关模式=NONE 时 `Old/New = current + 10`（急停）／`+20`（普通）
      · 之后每 `uc1s` 一拍 `EEVSpecCloseTarget -= 20` ⇒ **20 步/秒**
    ⇒ 采样里应看到 +10，随后每拍 -20。

================================ 触发链 ================================

⚠ **主触发写的是 `[962] ValveLinkFaultLatchDisp`，不是 `[605]`。**
  为什么：`ErrTotal`（决定 Y05）里装的是三个**闩锁位**（DispAction.c:463-465），
  **`EnviTempErr` 本身不在那张清单里**（DispAction.c:421-469 逐条数过）。
  只写 [605] 会绕开 Y05 报警 —— 触发出来的就不是真实急停。写闩锁位才是忠实复现跳 X04。

    写 Parameter[962] ValveLinkFaultLatchDisp = 1（ST-Link）
      -> ErrorCheck.c:375 `if(ValveLinkFaultCurrentDisp)ValveLinkFaultLatchDisp=1;`（本来就只置不清）
      -> ErrorCheck.c:378-381 `if(Fire||ValveLink||Leak Latch){ EnviTempErr=1; IndoorSpecFaultDisp=1; }`
      -> ErrorCheck.c:620 `if(UserSidePumpOverLoadErr||AntiFreezeErr||EnviTempErr)`
      -> ModUrgencyStop = 1                     ([1406]，ErrorCheck.c:622)
      -> for(...)output[i]=0; for(...)DA[i]=0;  (ErrorCheck.c:631/632)
      -> DispAction.c:464 `if(ValveLinkFaultLatchDisp)ErrTotal++;` -> :475 ErrorOutY00=Y05=1  ← 报警例外
      -> 下一扫描 UserAction -> EEV_ActionAll() 急停分支 (eevCTRL.c:628)
         -> EEVCloseStepTarget(..., EEV_CLOSE_EMERGENCY) -> +10

  加 `--direct` 则改为只写 [605]（用于对照：证明 [605] 单独写**不会**点亮 Y05）。

================================ 地址（V10.12 实测核对过） ================================

    output[16]  .bss 0x20001364   io.o   —— output[i]=Y(i)，output[5]=Y05（io.h:6-30）
    DA[10]      .bss 0x20001872   dac.o  —— DA_CHANEL=10（dac.h:5）
    Parameter[] .bss 0x200030C8

⚠ **基址自检**：脚本开工先拿 ST-Link 读的 [236]/[709]/[872] 和 Modbus 读的对比，
  不一致就**立刻退出**（RAM 布局随固件变动，硬编码基址不能盲信）。

⚠ **必须 attach**（connect_mode="attach"）—— 默认 halt 会把板子冻死。
  本脚本**只读 + 只写 [605] 一个 int16**，不 halt、不复位。

⚠ 复原：写 [605]=0。但急停已经把 SysStep 打到 0、SysStatusLoader=0，机器是停的 ——
  要恢复运行得再发一次开机命令。

跑法：
    python.exe tools/probe_330_emergency.py              # 基线 5s，写 [962] 触发
    python.exe tools/probe_330_emergency.py 10           # 基线 10s
    python.exe tools/probe_330_emergency.py --direct     # 改写 [605]（对照，Y05 不该亮）
    python.exe tools/probe_330_emergency.py --restore    # 只复原，不触发
    python.exe tools/probe_330_emergency.py --force      # 输出全 0 也照样触发

⚠ 触发前**必须让机器带载运行**（output[] 或 DA[] 非 0），否则"失电"无从谈起。
  排毒模式是个好工况：风阀 DO（Y03/Y04）+ 风阀/送风 AO（DA3/DA6/DA7）都带电。
"""
from __future__ import annotations

import pathlib
import sys
import time

from pyocd.core.helpers import ConnectHelper

OUT = pathlib.Path(__file__).resolve().parent / "probe_330_emergency.txt"

OUT_BASE = 0x20001364          # output[0..15]  = Y00..Y07, Y10..Y17
DA_BASE = 0x20001872           # DA[0..9]
PARAM_BASE = 0x200030C8        # int16_t Parameter[]

N_OUT, N_DA = 16, 10
OUT_DA_LEN = (DA_BASE - OUT_BASE) + N_DA * 2      # 1314，一次块读把 output+DA 全拿下

P = lambda i: PARAM_BASE + 2 * i                   # noqa: E731

IDX_ENVI = 605                 # [605] EnviTempErr（HREST+11，User.h:924）
IDX_VLATCH = 962               # [962] ValveLinkFaultLatchDisp（User.h:1155）—— 主触发
IDX_FIRE = 960                 # [960] FireFaultLatchDisp（User.h:1153）
IDX_LEAK = 964                 # [964] LeakFaultLatchDisp（User.h:1157）
IDX_URG = 1406                 # [1406] ModUrgencyStop（PLCctrlPara+6，User.h:1474）
IDX_SYSSTEP = 709              # [709] SysStep
IDX_WM = 236                   # [236] UserWorkModeSetTEMP
IDX_CTRLMODE = 872             # [872] IndoorCtrlModeDisp

EEV_NEW = 1145                 # Parameter[NewAddValue+j]  目标
EEV_OLD = 1153                 # Parameter[OldAddValue+j]  当前/剩余计数器

# 输出点名字（io.h:20-37）
YNAME = ["Y00", "Y01", "Y02", "Y03", "Y04", "Y05", "Y06", "Y07",
         "Y10", "Y11", "Y12", "Y13", "Y14", "Y15", "Y16", "Y17"]
WM = {0: "制冷", 1: "制热", 2: "通风", 3: "消毒", 4: "排风", 5: "自动消排毒"}

LINES: list[str] = []


def say(s: str = "") -> None:
    LINES.append(s)
    try:
        print(s, flush=True)
    except UnicodeEncodeError:
        print(s.encode("gbk", "replace").decode("gbk", "replace"), flush=True)


def s16(v: int) -> int:
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


class Board:
    """ST-Link 直读/直写 RAM。整块读，避免分次读采到撕裂状态。"""

    def __init__(self, tgt):
        self.t = tgt

    def out_da(self):
        """读 output[16] + DA[10]。返回 (output列表, DA列表)。

        ⚠ **两笔小读，不要一次块读 1314 字节** —— 实测（2026-09-21）：
            1314B 单次块读 = 47 Hz（21.1 ms）
            16B + 20B 两笔小读 = ~350 Hz（2.9 ms/三笔）
          大块读慢 7 倍，抓不住"失电瞬间"。
          代价：两笔之间隔约 1 ms，可能采到"output 已清、DA 未清"的**读序假象**。
          由调用方用"连续两拍"过滤掉。
        """
        out = list(bytes(self.t.read_memory_block8(OUT_BASE, N_OUT)))
        daw = bytes(self.t.read_memory_block8(DA_BASE, N_DA * 2))
        da = [int.from_bytes(daw[2 * k: 2 * k + 2], "little") for k in range(N_DA)]
        return out, da

    def param(self, i):
        return s16(int.from_bytes(
            bytes(self.t.read_memory_block8(P(i), 2)), "little"))

    def params(self, idxs):
        return [self.param(i) for i in idxs]

    def eev(self):
        """返回 (New目标[8], Old剩余[8])。"""
        nb = bytes(self.t.read_memory_block8(P(EEV_NEW), 16))
        ob = bytes(self.t.read_memory_block8(P(EEV_OLD), 16))
        rd = lambda b: [s16(int.from_bytes(b[2 * k:2 * k + 2], "little"))  # noqa: E731
                        for k in range(8)]
        return rd(nb), rd(ob)

    def write_param(self, i, v):
        self.t.write_memory_block8(P(i), bytes([v & 0xFF, (v >> 8) & 0xFF]))


def fmt_out(out):
    """非 0 的输出点列成 'Y05=1 Y13=1'；全 0 返回 '(全0)'。"""
    nz = ["%s=%d" % (YNAME[k], out[k]) for k in range(N_OUT) if out[k]]
    return " ".join(nz) if nz else "(全0)"


def fmt_da(da):
    nz = ["DA%d=%d" % (k, da[k]) for k in range(N_DA) if da[k]]
    return " ".join(nz) if nz else "(全0)"


def main() -> int:
    nums = [a for a in sys.argv[1:] if not a.startswith("--")]
    base_sec = float(nums[0]) if nums else 5.0
    restore_only = "--restore" in sys.argv
    force = "--force" in sys.argv
    direct = "--direct" in sys.argv          # 只写 [605]，不写闩锁（对照用）

    session = ConnectHelper.session_with_chosen_probe(
        target_override="stm32f407ze",
        options={"frequency": 1000000, "connect_mode": "attach"},
    )
    if session is None:
        say("✗ 连不上 ST-Link")
        OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
        return 1

    with session:
        tgt = session.target
        b = Board(tgt)
        say("=== 330 §3.3.5 紧急停机 —— 失电瞬间抓取（ST-Link 直读 RAM）===")
        say("内核状态 = %s" % tgt.get_state())
        if tgt.get_state() == tgt.State.HALTED:
            say("!! HALTED，立刻 resume")
            tgt.resume()
            say("   resume 后 = %s" % tgt.get_state())
        say()

        # ---------- 基址自检（关键：RAM 布局随固件变动，硬编码基址不能盲信）----------
        say("--- 基址自检：ST-Link 读的 Parameter[] vs Modbus ---")
        st_vals = b.params([IDX_WM, IDX_SYSSTEP, IDX_CTRLMODE])
        mb_vals, mb_ok = [None] * 3, False
        try:
            sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent
                                   / "psc330_monitor_tool" / "psc330_monitor"))
            import app as m
            c = m.ModbusRtuClient()
            c.open("COM6", m.DEFAULT_BAUD)
            mb_vals = [s16(c.read_holding_registers(1, i, 1)[0])
                       for i in (IDX_WM, IDX_SYSSTEP, IDX_CTRLMODE)]
            c.close()
            mb_ok = True
        except Exception as e:  # noqa: BLE001
            say("  （Modbus 读失败：%s —— 跳过交叉核对）" % e)
        for nm, i, sv, mv in zip(("[236]模式", "[709]SysStep", "[872]CtrlMode"),
                                 (IDX_WM, IDX_SYSSTEP, IDX_CTRLMODE),
                                 st_vals, mb_vals):
            if mb_ok:
                say("  %-14s ST-Link=%s  Modbus=%s  %s"
                    % (nm, sv, mv, "一致" if sv == mv else "**不一致**"))
            else:
                say("  %-14s ST-Link=%s" % (nm, sv))
        if mb_ok and st_vals != mb_vals:
            say()
            say("✗ 基址不对（Parameter[] 布局和 0x%08X 对不上），立刻退出，不写任何东西。"
                % PARAM_BASE)
            OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
            return 1
        say()

        # ---------- 复原模式 ----------
        if restore_only:
            say("--- --restore：清 [962] [960] [964] 闩锁 + [605] EnviTempErr ---")
            say("  清前 [605]=%d [1406]=%d [962]=%d"
                % (b.param(IDX_ENVI), b.param(IDX_URG), b.param(IDX_VLATCH)))
            for i in (IDX_VLATCH, IDX_FIRE, IDX_LEAK, IDX_ENVI):
                b.write_param(i, 0)
            time.sleep(0.5)
            say("  清后 [605]=%d [1406]=%d [962]=%d [709]=%d"
                % (b.param(IDX_ENVI), b.param(IDX_URG), b.param(IDX_VLATCH),
                   b.param(IDX_SYSSTEP)))
            out, da = b.out_da()
            say("  output: %s    DA: %s" % (fmt_out(out), fmt_da(da)))
            tgt.resume() if tgt.get_state() == tgt.State.HALTED else None
            OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
            return 0

        # ---------- 触发前快照 ----------
        out0, da0 = b.out_da()
        en0, ug0, ss0, wm0 = b.params([IDX_ENVI, IDX_URG, IDX_SYSSTEP, IDX_WM])
        new0, old0 = b.eev()
        say("--- 触发前 ---")
        say("  [236]模式=%s  [709]SysStep=%d  [605]EnviTempErr=%d  [1406]ModUrgencyStop=%d"
            % (WM.get(wm0, wm0), ss0, en0, ug0))
        say("  output: %s" % fmt_out(out0))
        say("  DA    : %s" % fmt_da(da0))
        say("  EEV New(目标): %s" % [new0[k] for k in range(8)])
        say("  EEV Old(剩余): %s" % [old0[k] for k in range(8)])
        say()

        live_out = any(out0)
        live_da = any(da0)
        if not live_out and not live_da:
            say("⚠ output[] 和 DA[] **全是 0** —— 现在没有负载可失电，触发它证明不了「全失电」。")
            if not force:
                say("  先让机器跑起来（开机 [398]=1）再跑本脚本；或加 --force 强行触发。")
                OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
                return 2
            say("  --force：照样触发。")
        else:
            say("  有载：output %s / DA %s" % ("有" if live_out else "无",
                                              "有" if live_da else "无"))
        say()

        # ---------- 基线采样 ----------
        say("--- 基线采样 %.0fs（确认稳定）---" % base_sec)
        base_n, t0 = 0, time.time()
        base_seen: dict[str, int] = {}
        while time.time() - t0 < base_sec:
            o, d = b.out_da()
            key = fmt_out(o) + " | " + fmt_da(d)
            base_seen[key] = base_seen.get(key, 0) + 1
            base_n += 1
        for k, v in sorted(base_seen.items(), key=lambda x: -x[1]):
            say("  %4d/%d 拍  %s" % (v, base_n, k))
        say()

        # ---------- 触发 ----------
        if direct:
            say("--- 触发：写 Parameter[605] EnviTempErr = 1（--direct 对照）---")
            say("  ⚠ 这条**绕开** ValveLink 闩锁 ⇒ ErrTotal 不增 ⇒ 预期 Y05 **不亮**。")
            trigs = [(IDX_ENVI, 1)]
        else:
            say("--- 触发：写 Parameter[962] ValveLinkFaultLatchDisp = 1 ---")
            say("  忠实复现跳 X04：闩锁 → EnviTempErr → ModUrgencyStop → Y05")
            trigs = [(IDX_VLATCH, 1)]
        t_trig = time.time()
        for i, v in trigs:
            b.write_param(i, v)
            back = b.param(i)
            say("  写 [%d]=%d 回读 %d  %s" % (i, v, back, "OK" if back == v else "!! 失败"))
        # ⚠ 不要在这里 sleep/读参数 —— 那是死时间，会把"写→失电"的响应延迟遮掉。
        #   派生结果（[605]/[1406]）挪到采样结束后再读。
        say("  t=0 = 写完那一刻，紧接着进高速采样。")
        say()

        # ---------- 高速采样抓失电瞬间 ----------
        say("--- 高速采样（整块读 output+DA，看过渡拍）---")
        # ⚠ 判"失电"要**排除 output[5]（Y05 综合报警）** —— 它在急停稳态下仍然带电
        #   （DispAction.c:475 按 ErrTotal 拉高）。若把 Y05 算进"载"，
        #   就永远等不到"全 0"，过渡时刻也标不对。
        samples: list[tuple[float, str, str, bool]] = []   # (t, output, DA, 还有载吗)
        def has_load(o, d):
            return any(o[k] for k in range(N_OUT) if k != 5) or any(d)

        last_load = None                 # 最后一个"还有用电设备带电"的样本
        first_off = None                 # 第一个"用电设备全断"的样本
        t_end = t_trig + 8.0
        while time.time() < t_end:
            ts = time.time()
            o, d = b.out_da()
            so, sd = fmt_out(o), fmt_da(d)
            ld = has_load(o, d)
            samples.append((ts - t_trig, so, sd, ld))
            if ld:
                last_load = samples[-1]
            elif first_off is None and len(samples) > 1:
                first_off = samples[-1]
            # ⚠ 两边都要用**相对时间**（samples 里存的是 ts-t_trig）。
            #   拿绝对 ts 去减相对 t 会恒大于 3.0 ⇒ 第二拍就 break（踩过）。
            if first_off is not None and (ts - t_trig) - first_off[0] > 3.0:
                break

        ev, uv = b.param(IDX_ENVI), b.param(IDX_URG)
        say("  采了 %d 拍，平均间隔 %.1f ms，覆盖 t=+%.0f ~ +%.0f ms"
            % (len(samples),
               (samples[-1][0] - samples[0][0]) / max(1, len(samples) - 1) * 1000,
               samples[0][0] * 1000, samples[-1][0] * 1000))
        say("  派生：[605]EnviTempErr=%d  [1406]ModUrgencyStop=%d  %s"
            % (ev, uv, "链路通" if uv == 1 else "!! ModUrgencyStop 没起来"))
        say()
        say("  口径：'用电设备' = output[] 除 output[5](Y05) 外的 15 路 + DA[10] 全部。")
        say("        （Y05 是综合报警，急停下本来就还亮着，不能算进'失电'判据。）")
        if last_load:
            say("  最后一拍【还有设备带电】 t=+%.0fms" % (last_load[0] * 1000))
            say("      output: %s" % last_load[1])
            say("      DA    : %s" % last_load[2])
        else:
            say("  （触发后就没采到带电状态？）")
        if first_off:
            say("  第一拍【设备全断】     t=+%.0fms" % (first_off[0] * 1000))
            say("      output: %s" % first_off[1])
            say("      DA    : %s" % first_off[2])
            if last_load:
                say("  ⇒ 掉电发生在 (+%.0f, +%.0f] ms 之间，窗口 %.0f ms"
                    % (last_load[0] * 1000, first_off[0] * 1000,
                       (first_off[0] - last_load[0]) * 1000))
        else:
            say("  ✗ 8 秒内没采到【设备全断】—— 有设备没被清掉，见下面稳态。")
        # 顺便报一下 output[5] 的瞬态（同一扫描内先清后拉回的痕迹）
        dips = [t for (t, so, sd, ld) in samples if so == "(全0)"]
        if dips:
            say("  ⚠ 另采到 %d 拍 output[] **含 Y05 在内全为 0** 的瞬态（t=+%.0f ~ +%.0f ms）"
                % (len(dips), dips[0] * 1000, dips[-1] * 1000))
            say("     = ErrorCheck.c:631 清掉 output[5] 之后、DispAction.c:475 把它拉回之前的")
            say("       那个窗口。同一扫描内，微秒级，能被 3.5ms 的采样撞上说明它确实存在。")
        say()

        # ---------- 触发后稳态（这里才是判"全失电"的地方）----------
        time.sleep(1.0)
        out1, da1 = b.out_da()
        en1, ug1, ss1 = b.params([IDX_ENVI, IDX_URG, IDX_SYSSTEP])
        new1, old1 = b.eev()
        say("--- 触发后稳态 ---")
        say("  [709]SysStep=%d  [605]EnviTempErr=%d  [1406]ModUrgencyStop=%d"
            % (ss1, en1, ug1))
        say("  output: %s" % fmt_out(out1))
        say("  DA    : %s" % fmt_da(da1))
        say()

        # ---------- 判据 1：全失电 ----------
        say("=== 判据①「除电子膨胀阀外所有用电设备均失电」===")
        bad_out = [YNAME[k] for k in range(N_OUT) if out1[k]]
        bad_da = ["DA%d" % k for k in range(N_DA) if da1[k]]
        # 代码预测：除 Y05 外应全 0。Y05 由 DispAction.c:475 按 ErrTotal 拉高。
        others = [YNAME[k] for k in range(N_OUT) if out1[k] and k != 5]
        if not bad_out and not bad_da:
            if direct:
                say("  ✅ output[16] 与 DA[10] 全为 0，**且 Y05 也没亮** —— 符合 --direct 的预期")
                say("     （[605] 单独置位不进 ErrTotal，所以 Y05 不亮）。")
            else:
                say("  ✅ output[16] 与 DA[10] 全为 0。")
                say("     ⚠ 但 Y05 也没亮 —— 与代码预测（DispAction.c:475 应拉高）**不符**，")
                say("        需复查 ErrTotal 是否真的累加到了。")
        else:
            say("  ❌ 触发后仍有输出未失电：")
            if bad_out:
                say("     output 残留：%s" % " ".join(
                    "%s=%d" % (YNAME[k], out1[k]) for k in range(N_OUT) if out1[k]))
            if bad_da:
                say("     DA 残留：%s" % " ".join(
                    "DA%d=%d" % (k, da1[k]) for k in range(N_DA) if da1[k]))
            if out1[5] and not others and not bad_da:
                say()
                say("     ⇒ **除 Y05 外全部失电。** 唯一残留 Y05=%d。" % out1[5])
                say("        代码路径（三处，按扫描序）：")
                say("          ErrorCheck.c:631  `for(...)output[i]=0;`      ← 先清掉了 output[5]")
                say("          DispAction.c:464  `if(ValveLinkFaultLatchDisp)ErrTotal++;`")
                say("          DispAction.c:475  `if(ErrorOutFlag==1)ErrorOutY00=1;`  ← 同一扫描又拉回 1")
                say("          （User.h:178 `#define ErrorOutY00 Y05` ⇒ output[5]）")
                say("        排查过：IndoorEnforceConfiguredOutputDisable()（扫描尾调两次）")
                say("          **不碰** ErrorOutY00/Y05（全仓 grep 只在 DispAction.c:471-476 写），")
                say("          所以拉高之后没人再清。")
                say("        性质：代码事实上**没做到字面『全失电』**。但 Y05 按点表是干接点")
                say("          『综合报警输出』，急停继电器线圈算不算『用电设备』规格书没写 ——")
                say("          可能是**有意保留的报警例外**，需规格方一句话确认。")
            elif out1[5]:
                say("     （Y05 也亮了，但还有其他残留，见上。）")
        say()

        # ---------- 判据 2：过渡拍（output 与 DA 是否同一拍清）----------
        say("=== 判据②「output[] 与 DA[] 是否同一拍清干净」===")
        # ⚠ output 与 DA 是两笔小读、中间隔约 1 ms，所以单拍出现"一清一未清"
        #   很可能只是**我自己的读序**造成的假象。要求**连续两拍**同向才认。
        runs = []
        for idx, (ts, so, sd, dead) in enumerate(samples):
            if (so == "(全0)") != (sd == "(全0)"):
                if runs and idx - runs[-1][-1][0] == 1:
                    runs[-1].append((idx, ts, so, sd))
                else:
                    runs.append([(idx, ts, so, sd)])
        real = [r for r in runs if len(r) >= 2]
        if real:
            say("  采到 %d 段**连续 ≥2 拍**的中间态（可信）：" % len(real))
            for r in real[:6]:
                for idx, ts, so, sd in r[:3]:
                    say("      t=+%.0fms  output=%s  DA=%s" % (ts * 1000, so, sd))
                say("      …共 %d 拍" % len(r))
            say("  ⇒ output[] 与 DA[] **不是**同一瞬间失电。")
        elif runs:
            say("  只采到 %d 个**孤立单拍**中间态（len<2）—— 判为读序假象，不算。"
                % len(runs))
            say("  ⇒ 视为 output[] 与 DA[] 在同一拍内一起归 0。")
        else:
            say("  没采到任何中间态 —— output[] 与 DA[] 一起归 0。")
        say("  （采样间隔 %.1f ms；ErrorCheck.c:631/632 是同扫描内两个相邻 for，"
            "间隔微秒级，采不到是正常的。）"
            % ((samples[-1][0] - samples[0][0]) / max(1, len(samples) - 1) * 1000))
        say()

        # ---------- 判据 3：EEV +10 ----------
        say("=== 判据③「关闭步数＝当前步数 + 10」（内机 8 路）===")
        say("  触发前 Old(剩余): %s" % [old0[k] for k in range(8)])
        say("  触发后 Old(剩余): %s" % [old1[k] for k in range(8)])
        say("  触发前 New(目标): %s" % [new0[k] for k in range(8)])
        say("  触发后 New(目标): %s" % [new1[k] for k in range(8)])
        ok_any = False
        for k in range(8):
            d = old1[k] - old0[k]
            if old0[k] or old1[k]:
                mark = "✅ +10" if d == 10 else ("%+d" % d)
                say("  EEV%d: 触发前 %4d → 触发后 %4d   Δ=%s" % (k + 1, old0[k], old1[k], mark))
                ok_any = True
        if not ok_any:
            say("  8 路 EEV 全为 0 —— 本次没抓到（阀本来就在 0 位，Δ 无意义）。")
            say("  要复现 §21.11 的 +10，需先让 EEV 停在非 0 步（制冷/制热运行中）再触发。")
        say("  注：`Old` 是**剩余计数**，写入即 current+10，随后每 `uc1s` 一拍 -20 ⇒ 20 步/秒。")
        say("      本次触发后已过 1s+，看到的值低于 +10 属正常。要抓写入瞬间需看上面的过渡采样。")
        say()

        # ---------- 复原 ----------
        # ⚠ 四个都要清：闩锁位固件只置不清，EnviTempErr 也是只置不清
        #   （全仓 grep EnviTempErr 只有 ErrorCheck.c:380 一处写 1）。
        say("--- 复原：清 [962] [960] [964] 闩锁 + [605] EnviTempErr ---")
        for i in (IDX_VLATCH, IDX_FIRE, IDX_LEAK, IDX_ENVI):
            b.write_param(i, 0)
        time.sleep(0.6)
        en2, ug2, vl2 = b.params([IDX_ENVI, IDX_URG, IDX_VLATCH])
        say("  [605]=%d  [1406]=%d  [962]=%d  %s"
            % (en2, ug2, vl2,
               "OK 已解除" if (en2 == 0 and ug2 == 0 and vl2 == 0) else "!! 仍有残留"))
        out2, da2 = b.out_da()
        say("  output: %s    DA: %s" % (fmt_out(out2), fmt_da(da2)))
        say("  ⚠ 机器现在是**停机**状态（SysStep 已被打到 0）。恢复运行：")
        say("      python.exe tools/rw330.py 398=1")
        if tgt.get_state() == tgt.State.HALTED:
            say("  !! HALTED，resume")
            tgt.resume()
        say("  内核状态 = %s" % tgt.get_state())

    OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    print("\n→ %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
