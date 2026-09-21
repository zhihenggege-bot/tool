# -*- coding: utf-8 -*-
"""330 §3.4.2 定频压缩机加减载（PID 部分）逐拍对账 —— 制冷与热泵制热。

规格书 §3.4.2（code/scratch_spec.txt）：
    制冷内机能力需求   N(KL)=MIN(1,N(KL-1)+Z(KL))
    Z(KL)=KPL*BX/100*[E(KL)+YS-E(KL-1)+T/TIL*(E(KL)+YS)+KDL/T*(E(KL)+YS-2E(KL-1)+E(KL-2))]
    热泵制热           N(KR)=MIN(1,N(KR-1)+Z(KR))
    Z(KR)=KPR*BX/100*[E(KR)-E(KR-1)+T/TIR*E(KR)+KDR/T*(E(KR)-2E(KR-1)+E(KR-2))]
    当 -WDF/4 < E < WDF/4（制冷还要 YS=0）时 Z=0
    E(K-1)/E(K-2) 无记录 ⇒ N=初始开度（下表）

    初始开度  E∈(-∞,0.5] / (0.5,2] / (2,4] / (4,5] / (5,+∞)  ⇒ N = 0/0.2/0.3/0.4/0.5
    比例修正  N(K-1)∈(0,0.1] / (0.1,0.2] / (0.2,0.4] / (0.4,0.5] / (0.5,1] ⇒ BX = 0.1/0.2/0.4/0.6/1

    台数：Z>0 → ROUNDUP(CN*N)；Z<0 → INT(CN*N)；Z=0 → 保持
          制冷**有再热**时两者都取 MAX(1, ·)      CN = 所有外机压缩机总数

参数下标（已逐个对着 User.h 核过）：
    模式[236] UserWorkModeSetTEMP（0制冷 1制热）
    中间量  [872] IndoorCtrlModeDisp [873] IndoorPidModeDisp
            [874] EK [875] EK1 [876] EK2 [877] YS [878] BX [879] Z [880] N
    台数    [115] FinalChangeHMI [118] CompNumSet [119] CompNumCur
            [881] IndoorTargetCompDisp(=CompNumSet)  [2678] CN
    参数    T=[412]  KPL/TIL/KDL=[416]/[417]/[418]  KPR/TIR/KDR=[426]/[427]/[428]
            WDF=[120] RoomTempDiffSet   制冷有再热判据 再热启用[127] 再热方式[332]
    SysStep=[709]（必须 ==2 才跑 PID）

⚠ 跳拍检测：固件每拍才写一次 [879]Z/[880]N，"Z 或 N 变了"= 刚跳过一拍。
  固件**先写 Z 再写 N**，采样落在中间会看到"同一拍两个事件"，判据要用 ΔN==Z。
⚠ 本脚本**只读**，不写任何寄存器。要扫 E 的档位边界请在两次运行之间手动注入：
      python.exe tools/rw330.py 495=-63      # 读基线（室内温度 = [511]，偏移=[495]）
      python.exe tools/rw330.py 495=-163     # 把室内温度压低 10.0°C
  （注入链见 §30.4：室内温度 [511]/[738] 的校准偏移是 [495]，**叠加不是替换**）
⚠ ⚠ [412] T 现在 =5 ⇒ 一拍 5 秒。扫一个档位至少停 3 拍 = 15 秒。

跑法： python.exe tools/probe_330_outdoor_pid.py 180
"""
from __future__ import annotations

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "psc330_monitor_tool" / "psc330_monitor"))

PORT, SLAVE = "COM6", 1
OUT = pathlib.Path(__file__).resolve().parent / "probe_330_outdoor_pid.txt"

FAST = [879, 880, 874, 881, 118, 738]
CFG = [236, 709, 127, 332, 412, 416, 417, 418, 426, 427, 428, 120, 248, 2678]

WM = {0: "制冷", 1: "制热", 2: "通风", 3: "消毒", 4: "排风", 5: "自动"}
PIDMODE = {0: "无", 1: "制冷", 2: "制热"}

LINES: list[str] = []


def say(s: str = "") -> None:
    """双写：LINES 供 UTF-8 .txt（交付物），print 供控制台。

    ⚠ 控制台是 GBK，有些字符（如 ✓ U+2713）编不出来 —— print 会抛
      UnicodeEncodeError 把整个脚本打死。所以这里兜一层，控制台降级显示，
      **绝不能让打印失败影响采样**。（✗ U+2717 反而能编，所以别的脚本没暴露这个坑。）
    """
    LINES.append(s)
    try:
        print(s, flush=True)
    except UnicodeEncodeError:
        print(s.encode("gbk", "replace").decode("gbk", "replace"), flush=True)


def s16(v: int) -> int:
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def tdiv(a: int, b: int) -> int:
    """C 的向零截断除法 —— 不能直接用 Python //（-1//2 == -1，C 是 0）。"""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def bx10_of(n: int) -> int:
    """规格书 BX 表 ×10。"""
    if n <= 100:
        return 1
    if n <= 200:
        return 2
    if n <= 400:
        return 4
    if n <= 500:
        return 6
    return 10


def initial_n(e: int) -> int:
    """规格书 初始开度表，e 单位 0.1°C，返回 N×1000。"""
    if e <= 5:
        return 0
    if e <= 20:
        return 200
    if e <= 40:
        return 300
    if e <= 50:
        return 400
    return 500


class OutdoorPidSim:
    """§3.4.2 的忠实复刻（照规格书，不照代码）。

    唯一"照代码"的地方是 zsign 的取法 —— 代码用 accumulatedZ（含小数余量）而非 z，
    注释说为防边界抖动。这里两种都算出来，供报告中对比（见"疑点 1"）。
    """

    def __init__(self, n0: int = 0) -> None:
        self.n = n0
        self.res = 0
        self.h = [0, 0, 0]
        self.cnt = 0
        self.z = 0
        self.acc = 0
        self.bx10 = 1
        self.last_z_res = 0      # 代码口径：sign(accumulatedZ)
        self.last_z_raw = 0      # 规格书口径：sign(z)
        self.last_target = 0

    def step(self, cool: bool, e: int, ys: int, kp: int, ti: int, td: int,
             t: int, wdf: int, cn: int, keep_one: bool):
        t, kp, ti, td = clamp(t, 1, 10), clamp(kp, 1, 100), clamp(ti, 1, 1000), clamp(td, 0, 1000)
        self.h[2], self.h[1], self.h[0] = self.h[1], self.h[0], e

        if self.cnt < 2:
            self.n = initial_n(e)
            self.cnt += 1
            self.z, self.res, self.acc = 0, 0, 0
            self.bx10 = bx10_of(self.n)
            self.last_z_res = 1 if self.n > 0 else 0
            self.last_z_raw = 0
        else:
            self.bx10 = bx10_of(self.n)
            dead = (abs(e) * 4 < wdf) and ((not cool) or (ys == 0))
            if dead:
                self.z, self.res, self.acc = 0, 0, 0
                self.last_z_res = 0
                self.last_z_raw = 0
            else:
                if cool:
                    # 规格书：YS 只加在 E(KL) 上，E(KL-1)/E(KL-2) 不加
                    num = (self.h[0] + ys - self.h[1]) * ti * t \
                        + t * t * (self.h[0] + ys) \
                        + td * ti * (self.h[0] + ys - 2 * self.h[1] + self.h[2])
                else:
                    num = (self.h[0] - self.h[1]) * ti * t \
                        + t * t * self.h[0] \
                        + td * ti * (self.h[0] - 2 * self.h[1] + self.h[2])
                scaled = tdiv(kp * self.bx10 * num * 1000, 10 * ti * t)
                self.acc = self.res + scaled
                self.z = tdiv(self.acc, 1000)
                self.res = self.acc - self.z * 1000
                self.n = clamp(self.n + self.z, 0, 1000)
                if (self.n == 0 and self.acc < 0) or (self.n == 1000 and self.acc > 0):
                    self.res = 0
                self.last_z_res = 1 if self.acc > 0 else (-1 if self.acc < 0 else 0)
                self.last_z_raw = 1 if self.z > 0 else (-1 if self.z < 0 else 0)

        # ---- 台数换算 ----
        zs = self.last_z_res
        if zs > 0:
            if self.n <= 0 and cn > 0:
                tgt = 1
            else:
                tgt = tdiv(self.n * cn + 999, 1000)      # ROUNDUP(CN*N)
                if keep_one and tgt == 0:
                    tgt = 1
            self.last_target = tgt
        elif zs < 0:
            if self.n <= 0:
                tgt = 1 if (keep_one and cn > 0) else 0
            else:
                tgt = tdiv(self.n * cn, 1000)            # INT(CN*N)
                if keep_one and tgt == 0:
                    tgt = 1
            self.last_target = tgt
        else:
            tgt = self.last_target
        tgt = clamp(tgt, 0, cn)
        return self.z, self.n, tgt


# 一拍观测：(E, E1, E2, YS, Z, N, 台数)
Obs = tuple[int, int, int, int, int, int, int]


def lock_res(cool, kp, ti, td, t, wdf, cn, keep_one, obs: list[Obs]):
    """用观测到的 Z 钉住积分器余量 res 的相位，返回已推进 len(obs) 拍的 sim。

    res 是 `acc = res + scaled` 里的进位，固件不暴露在任何寄存器里。
    相位猜错时 Z 的大小正确但"落在哪一拍"会差一拍 —— **总和不变**。
    |scaled| 是 1000 整数倍的区间里相位完全不可观测（z 恒定）；
    换 BX 档后显现。

    ⚠ **必须喂连续两拍**：只喂一拍时，能复现该拍 Z 的候选区间往往有一半
      会让**下一拍**翻掉（实测就是这么每拍翻一次的）。两拍就能钉死。

    返回 (sim, 候选相位个数)；无解返回 (None, 0)。
    """
    e0, _e1, _e2, ys0, z0, n0, _t0 = obs[0]
    cands = []
    for r in range(1000):
        s = OutdoorPidSim(n0 - z0)
        s.cnt, s.h, s.res = 2, [e0, _e1, _e2], r
        good = True
        for o in obs:
            zz, _, _ = s.step(cool, o[0], o[3], kp, ti, td, t, wdf, cn, keep_one)
            if zz != o[4]:
                good = False
                break
        if good:
            cands.append(r)
    if not cands:
        return None, 0
    r = cands[len(cands) // 2]
    s = OutdoorPidSim(n0 - z0)
    s.cnt, s.h, s.res = 2, [e0, _e1, _e2], r
    for o in obs:
        s.step(cool, o[0], o[3], kp, ti, td, t, wdf, cn, keep_one)
    s.last_target = obs[-1][6] if obs[-1][6] is not None else 0
    return s, len(cands)


def main() -> int:
    import app as m

    nums = [a for a in sys.argv[1:] if not a.startswith("--")]
    seconds = float(nums[0]) if nums else 180.0
    every = float(nums[1]) if len(nums) > 1 else 30.0   # 无跳拍时也要出行的间隔

    client = m.ModbusRtuClient()
    client.open(PORT, m.DEFAULT_BAUD)

    def rd(addr):
        """读失败返回 None —— 绝不能返回 -1：-1 是 Z/E 的合法值，会被当成真数据。"""
        for _ in range(3):
            try:
                return s16(client.read_holding_registers(SLAVE, addr, 1)[0])
            except Exception:  # noqa: BLE001
                time.sleep(0.05)
        return None

    cfg = {a: rd(a) for a in CFG}
    if None in cfg.values():
        say("✗ 开场配置读失败：%s" % [a for a in CFG if cfg[a] is None])
        client.close(); OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8"); return 1

    cool = (cfg[236] == 0)
    keep_one = cool and (cfg[127] != 0) and (cfg[332] != 0)
    cn = cfg[2678]
    kp, ti, td = (cfg[416], cfg[417], cfg[418]) if cool else (cfg[426], cfg[427], cfg[428])

    say("=== 330 §3.4.2 定频压缩机加减载（PID + 台数）逐拍对账 ===")
    say("模式[236]=%s   SysStep[709]=%d   控制方式[872]=%s（0=PID 1=环温）"
        % (WM.get(cfg[236], cfg[236]), cfg[709], rd(872)))
    say("PID 参数：K=%d T积=%d T微=%d  T[412]=%d（一拍 %.1f 秒）  WDF[120]=%.1fC"
        % (kp, ti, td, cfg[412], cfg[412] * 10 * 0.1, cfg[120] / 10.0))
    say("CN[2678]=%d 台   制冷有再热 keepOne=%s（再热启用[127]=%d 再热方式[332]=%d）"
        % (cn, "是" if keep_one else "否", cfg[127], cfg[332]))
    say("加湿使能[248]=%d（影响 YS）" % cfg[248])
    say()

    if rd(872) == 1:
        say("⚠ 控制方式[872]=1（环温模式）—— 走的是 IndoorEnvTempEnergyAction，不是 §3.4.2 的 PID。")
        say("   要看 PID 请把 [315] CompControlModeSet 置 0。")
        say()

    # 等运行态
    t0 = time.time()
    while time.time() - t0 < 300:
        ss = rd(709)
        if ss is None:
            time.sleep(0.5); continue
        if ss == 2:
            break
        if int(time.time() - t0) % 10 == 0:
            say("  …等 SysStep=2（当前 %s），已等 %.0fs" % (ss, time.time() - t0))
        time.sleep(1.0)
    else:
        say("✗ 300 秒内没进运行态，退出")
        client.close(); OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8"); return 1

    say("已进入运行态（SysStep=2），开始采样 %.0f 秒 …" % seconds)
    say()
    say("  拍 |    t |   E  E1  E2 YS | 实际Z 实际N | 期望Z 期望N | BX实/期 | 台数实/期 | 判定")
    say("     |      |              |             |             |         |           |")

    n0, z0 = rd(880), rd(879)
    if n0 is None or z0 is None:
        say("✗ 首读失败")
        client.close(); OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8"); return 1

    _e, _ys = rd(874), rd(877)
    if _e is None or _ys is None:
        say("✗ 读 E/YS 失败")
        client.close(); OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8"); return 1

    # ---- 标定不可观测的"小数余量" res 的相位 ----
    # 固件的 res（积分器进位）不暴露在任何寄存器里。相位猜错，N 就会在"哪一拍 +1"
    # 上整体错开一拍 —— 逐拍对账会看起来全错（实测过一次，N 吻合率 50%）。
    # 做法：暴力搜 res ∈ [0,1000)，保留能复现**刚过去那一拍**观测 Z 的相位，取中点。
    #   ① 若 |scaled| ≥ 1000，z 与 res 无关 ⇒ 候选集是全部，随便取都对
    #   ② 若 |scaled| < 1000，候选区间很窄 ⇒ 区间内任取都对
    # 所以一拍标定就够。
    # 另外：不能靠"跑两次 step"预热 —— cnt<2 的分支会把 N 直接**赋值**成初始开度，
    # 而固件的 coolCnt 是 static、早 >=2 了。必须直接把 cnt 置过 2。
    # ⚠ 固件在 (SysStep != 2) || (lastMode != mode) 时会把 coolCnt/heatCnt 归零，
    #   于是接下来 **2 拍走「初始开度」分支**而不是 PID 分支 —— 判据是 [875]/[876]
    #   （E(K-1)/E(K-2)）还是 0，说明历史还没记满。
    #   预热不能一味假设 cnt=2（切模式后就是这么栽的：制热那轮拍1 固件给 N=500
    #   而 sim 按 PID 算出 546，从第一拍就错开）。
    _e1, _e2 = rd(875), rd(876)
    if (_e1 == 0) and (_e2 == 0):
        # 固件刚重置过计数器，正在走「初始开度」分支：从 cnt=0 起，消费掉这一拍
        sim = OutdoorPidSim(0)
        sim.cnt, sim.h, sim.res = 0, [_e, _e1, _e2], 0
        n_cand = 0
        _z, _n, _t = sim.step(cool, _e, _ys, kp, ti, td, cfg[412], cfg[120], cn, keep_one)
        sim.last_target = rd(881) if rd(881) is not None else 0
        say("（E(K-1)/E(K-2) 仍为 0 ⇒ 固件在「初始开度」分支；sim 从 cnt=0 起，"
            "这一拍得 Z=%d N=%d，实测 Z=%d N=%d%s）"
            % (_z, _n, z0, n0, "" if _n == n0 else "  ⚠ 不一致 —— 初始开度表可能有偏差"))
    else:
        sim, n_cand = lock_res(cool, kp, ti, td, cfg[412], cfg[120], cn, keep_one,
                               [(_e, _e, _e, _ys, z0, n0, rd(881))])
    if sim is None:
        say("✗ 相位标定无解（观测 Z=%d 无法被任何相位复现）—— 公式可能有偏差" % z0)
    say("标定小数余量 res：候选 %d/1000 个（这一拍 Z=[879]=%d）" % (n_cand, z0))
    say()
    prev_n, prev_z = n0, z0
    prev_obs: Obs = (_e, _e, _e, _ys, z0, n0,
                     rd(881) if rd(881) is not None else 0)
    sum_z_fw = sum_z_m = 0
    relocks = 0

    beat = 0
    ok_z = ok_n = ok_t = 0
    zraw_diff = 0
    last_line = time.time()
    t1 = time.time()
    while time.time() - t1 < seconds:
        z, n, e, tgt, cnset, room = rd(879), rd(880), rd(874), rd(881), rd(118), rd(738)
        e1, e2, ys, bx = rd(875), rd(876), rd(877), rd(878)
        if None in (z, n, e, tgt, cnset, room, e1, e2, ys, bx):
            time.sleep(0.15); continue
        if n != prev_n or z != prev_z:
            ss = rd(709)
            if ss != 2:
                say("  SysStep 变 %s，停止采样" % ss); break
            # ⚠ 固件在一拍内**先写 Z 再写 N**（NygryAdjust.c: 先 IndoorPidZDisp 再 IndoorPidNDisp），
            #   采在两次写之间会拿到 (新Z, 旧N) 的不自洽组合 —— 实测过，会让对账从某一拍起整片错开。
            #   自洽判据就是规格书那句 ΔN == Z：不成立就再采一次，最多等 0.5 秒。
            for _ in range(10):
                if (n - prev_n) == z:
                    break
                time.sleep(0.05)
                _z2, _n2 = rd(879), rd(880)
                if _z2 is None or _n2 is None:
                    break
                z, n = _z2, _n2
            if (e1 == 0) and (e2 == 0) and (sim.cnt >= 2):
                # 固件中途重置了 PID 计数（(SysStep!=2) || (lastMode!=mode)）——
                # 接下来 2 拍它走「初始开度」分支。sim 必须同步，否则从这一拍起全错开。
                say("     （E(K-1)/E(K-2) 归零 ⇒ 固件重置了 PID 计数，sim 同步 cnt=0）")
                sim.cnt, sim.h, sim.res = 0, [e, e1, e2], 0
            expZ, expN, expT = sim.step(cool, e, ys, kp, ti, td, cfg[412], cfg[120], cn, keep_one)
            beat += 1
            judge = ""
            cur_obs: Obs = (e, e1, e2, ys, z, n, tgt)
            if expZ != z and abs(expZ - z) == 1:
                # 积分器余量相位不可观测：整数量都对，只是"落在哪一拍"差一拍。
                # 用**上一拍 + 这一拍**两条观测钉相位（只喂一拍会每拍翻一次），
                # 单列一类：不算命中、也不算失败。
                s2, _n2 = lock_res(cool, kp, ti, td, cfg[412], cfg[120], cn, keep_one,
                                   [prev_obs, cur_obs])
                if s2 is not None:
                    sim = s2
                    relocks += 1
                    judge = "相位重锁"
                    # 重锁即接受固件状态：这一拍模型的 Z 记成固件的值，
                    # 否则"重锁前那个错位的 z"会被算进总和，凭空多出 ±1
                    expZ, expN, expT = z, n, tgt
            sum_z_fw += z
            sum_z_m += expZ
            if not judge:
                okz = (expZ == z)
                okn = (expN == n)
                okt = (expT == tgt)
                ok_z += okz; ok_n += okn; ok_t += okt
                if sim.last_z_raw != sim.last_z_res:
                    zraw_diff += 1
                judge = ("OK" if (okz and okn and okt) else
                         ("Z✓N✗" if okz else ("Z✗N✓" if okn else "✗")))
            prev_obs = cur_obs
            say("  %3d | %5.0f | %4d %4d %4d %2d | %5d %5d | %5d %5d | %2d/%2d | %4d/%4d | %s"
                % (beat, time.time() - t1, e, e1, e2, ys,
                   z, n, expZ, expN, bx, sim.bx10, tgt, expT, judge))
            prev_n, prev_z = n, z
            last_line = time.time()
        elif time.time() - last_line >= every:
            # 无跳拍（典型：N=0 卡在死区/饱和）—— 只报原始值，**不推进 sim**，否则失步
            say("   -- | %5.0f | %4d %4d %4d %2d | %5d %5d |     —     | %2d/— | %4d/— | 无跳拍"
                % (time.time() - t1, e, e1, e2, ys, z, n, bx, tgt))
            last_line = time.time()
        time.sleep(0.15)

    say()
    say("结束（%d 拍，其中相位重锁 %d 拍）" % (beat, relocks))
    cmp_beats = beat - relocks
    if cmp_beats:
        say("  Z 吻合 %d/%d（%.0f%%）   N 吻合 %d/%d（%.0f%%）   台数吻合 %d/%d（%.0f%%）"
            % (ok_z, cmp_beats, 100.0 * ok_z / cmp_beats,
               ok_n, cmp_beats, 100.0 * ok_n / cmp_beats,
               ok_t, cmp_beats, 100.0 * ok_t / cmp_beats))
    say()
    say("  ★ 决定性判据（相位无关，公式对不对看这个）：")
    say("      Z 总和   固件 %+d   模型 %+d   差 %+d  %s"
        % (sum_z_fw, sum_z_m, sum_z_m - sum_z_fw,
           "一致 ✅" if sum_z_m == sum_z_fw else "**不一致 ❌**"))
    say("      相位重锁 %d 次：积分器余量 res 不可观测，|scaled| 是 1000 整数倍的区间里" % relocks)
    say("      相位无影响；换 BX 档后逐拍会差 1（总和不变）。重锁是用观测值钉相位，不是放宽判据。")
    say()
    say("【疑点 1】zsign 口径：代码用 accumulatedZ（含小数余量）而非 z。")
    say("  本次 %d 拍里两种口径会给出**不同** zsign 的有 %d 拍。" % (beat, zraw_diff))
    say("  若这 %d 拍恰好都出现在台数不该变的时候，说明代码的防抖是有意的；" % zraw_diff)
    say("  否则要请用户裁定规格书的「Z(KL)」指哪一个。")
    say()
    say("【疑点 2】台数 N=0 时：代码 `if((n1000<=0)&&(maxComp>0)) target=1` 会强给 1 台。")
    say("  规格书「制冷无再热」按 ROUNDUP(CN*0)=0 应为 0 台。")
    say("  本次 keepOne=%s —— 要验这一条，请把 [127] 再热启用置 0 后重跑。" % ("是" if keep_one else "否"))

    client.close()
    OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
