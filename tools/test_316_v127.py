# -*- coding: utf-8 -*-
"""PSC316 V12.7 验证脚本（AI0/AI1 高压偏移被故障状态字覆盖的修复）

用法（真 Python，不是 PATH 上那个坏别名）：
  "C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python312\\python.exe" ^
      tools\\test_316_v127.py            # 只读一遍，看现状
  ... test_316_v127.py --watch 300      # 另外挂 300 秒写监视点在 Parameter[498]

硬件：ST-Link 接 316；串口 COM6 接 330。
ST-Link 不在也能跑，只是跳过 RAM 部分。

关键地址（V12.7 实测，Parameter 本身没移位）：
  Parameter      = 0x2000164A      Old_Parameter = 0x20001206
  Parameter[498] = 0x20001A2E  AI1 高压偏移    <- 被污染的那个
  Parameter[499] = 0x20001A2C  AI0 高压偏移
  Parameter[1501]= 0x20002204  OutdoorFaultStatusDisp（故障位）  <- 污染源
  Parameter[1500]= 0x20002202  EEV2PidStepDisp
  Parameter[1580]= 0x200022A2  新校准镜像块 1580..1593
"""
import io
import struct
import sys
import time

sys.path.insert(0, r"d:\Companty\WEll thinker\F\code\psc330_monitor_tool\psc330_monitor")
import app  # noqa: E402

P = 0x2000164A
AO = 0x20001206
IDX_CAL = list(range(486, 500))          # 486..499 = 校准块/偏移
IDX_FAULT = [1500, 1501, 1502, 1503]     # 上传块尾部
IDX_NEW = list(range(1580, 1594))        # 新的校准镜像块
RANGE_CAL = 4                            # 496..499 = AI0..AI3 偏移

WD = int(sys.argv[sys.argv.index("--watch") + 1]) if "--watch" in sys.argv else 0
OUT = r"C:\Users\Administrator\AppData\Local\Temp\test_v127.txt"

lines = []


def emit(t=""):
    lines.append(str(t))


# ---------------- 串口部分（330） ----------------
cl = None
try:
    cl = app.ModbusRtuClient()
    cl.open("COM6", 9600, timeout=1.0)
except Exception as exc:  # noqa: BLE001
    emit("串口打不开(%s) —— 只做 ST-Link 部分" % exc)


def g(a, n=1):
    if cl is None:
        return ["--"]
    try:
        return [app.signed16(x) for x in cl.read_holding_registers(1, a, n)]
    except Exception:  # noqa: BLE001
        return ["ERR"]


def w(a, v):
    if cl is None:
        return "无串口"
    try:
        cl.write_single_register(1, a, v & 0xFFFF)
        return "OK"
    except Exception as exc:  # noqa: BLE001
        return str(exc)[:40]


emit("PSC316 V12.7 验证   %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
emit("=" * 76)

if cl is not None:
    emit("【1】版本确认 —— 必须显示 12,7；显示 12,6 就是没烧进去")
    emit("     触发前 330[2652..2653] = %s" % g(2652, 2))
    emit("     写 330[2652]=1 -> %s" % w(2652, 1))
    for _ in range(10):
        time.sleep(2)
        if g(2653, 1) != [1]:
            break
    for n in (1, 2):
        v = g(2628 + 6 * (n - 1), 6)
        ok = (len(v) >= 3 and v[0] == 316 and v[1] == 12 and v[2] == 7)
        emit("     %d# 版本窗口 = %-34s %s" % (n, v, "★ V12.7 已烧录" if ok else "✗ 不是 V12.7"))
    emit("")
    emit("【2】各机在线 + 标定窗口（330 从 316 读回的偏移）")
    for n in (1, 2):
        b = 1830 + 48 * (n - 1)
        emit("     %d# 在线=%s 状态=%s 错误=%s   标定窗口=%s"
             % (n, g(b + 42)[0], g(b + 43)[0], g(b + 44)[0], g(2654 + 4 * (n - 1), 4)))
    emit("     页面 Parameter[740..753] = %s" % g(740, 14))
    emit("")

# ---------------- ST-Link 部分（316） ----------------
sess = None
target = None
try:
    from pyocd.core.helpers import ConnectHelper
    from pyocd.core.target import Target
    sess = ConnectHelper.session_with_chosen_probe(
        options={"target_override": "stm32f103rc", "frequency": 4000000,
                 "connect_mode": "attach"})
    sess.open()
    target = sess.target
except Exception as exc:  # noqa: BLE001
    emit("ST-Link 连不上(%s) —— 跳过 RAM 部分" % str(exc)[:60])
    emit("     提示：ST-Link 是否插在 316 上？")
    emit("")


def rd(a, n):
    target.halt()
    try:
        return bytes(target.read_memory_block8(a, n))
    finally:
        target.resume()


def h16(i):
    return struct.unpack("<h", rd(P + i * 2, 2))[0]


if target is not None:
    emit("【3】316 RAM 实测")
    cal = [h16(i) for i in IDX_CAL]
    old = [struct.unpack("<h", rd(AO + i * 2, 2))[0] for i in IDX_CAL]
    emit("     Parameter[486..499] = %s" % cal)
    emit("     Old_Param [486..499] = %s" % old)
    emit("     其中 AI 偏移  Parameter[499,498,497,496] = %s"
         % [h16(i) for i in (499, 498, 497, 496)])
    emit("")
    fault = [h16(i) for i in IDX_FAULT]
    emit("     上传块尾部 Parameter[1500..1503] = %s" % fault)
    emit("        [1501] = OutdoorFaultStatusDisp(故障位)  现在 = %d = %s"
         % (fault[1], format(fault[1] & 0xFFFF, "016b")))
    emit("")
    newb = [h16(i) for i in IDX_NEW]
    emit("     新校准镜像块 Parameter[1580..1593] = %s" % newb)
    emit("        应与 Parameter[499..486] 一致：%s" % [h16(i) for i in range(499, 485, -1)])
    emit("")
    emit("     ★ 核心判据（静态读数只能报状态，不能下结论）：")
    off = h16(498)
    flt = h16(1501)
    off_old = struct.unpack("<h", rd(AO + 498 * 2, 2))[0]
    emit("        故障字[1501] = %-6d = %s" % (flt, format(flt & 0xFFFF, "016b")))
    emit("        偏移  [498] = %-6d   Old[498] = %-6d   %s"
         % (off, off_old, "（已存进 EEPROM）" if off == off_old else "（Old 尚未同步，存盘进行中）"))
    emit("")
    if off != 0:
        emit("        ⚠ [498] 非 0。这**不能**说明它正被覆盖 —— 它可能只是 EEPROM 里存的旧值。")
        emit("          请先清 0（ST-Link 写 [496..499]=0），再观察它是否变回非 0。")
        emit("          只有「清 0 之后又自己变回来」才算被覆盖。")
    elif flt != 0:
        emit("        [498]=0 且故障字=%d 活跃 —— 与修复后的预期一致。" % flt)
        emit("          但更强的证据是「清 0 → 等故障字出现 → 仍是 0」，用 --watch 观察更可靠。")
    else:
        emit("        [498]=0，故障字也=0（当前无故障位）—— 无从判断。")
        emit("          等故障位出现（上电后约 20 秒）或直接跑 --watch 观察。")
    emit("")

    if WD > 0:
        emit("【4】挂写监视点 Parameter[498]，盯 %d 秒（看谁还在写它）" % WD)
        A = P + 498 * 2
        target.set_watchpoint(A, 2, Target.WatchpointType.WRITE)
        target.resume()
        t0 = time.time()
        hits = 0
        while time.time() - t0 < WD:
            if "HALT" in str(target.get_state()).upper():
                hits += 1
                pc = target.read_core_register("pc")
                lr = target.read_core_register("lr")
                ipsr = target.read_core_register("xpsr") & 0x1FF
                rg = [hex(target.read_core_register(r)) for r in ("r0", "r1", "r2", "r3")]
                emit("     ★ 命中 t=%.0fs PC=0x%08X LR=0x%08X IPSR=%d R=%s"
                     % (time.time() - t0, pc, lr, ipsr, rg))
                emit("        期望：PC 不在 System_Real 里（上次是 System_Real+0x31B = 0x08005822）")
                target.resume()
                time.sleep(0.3)
                if hits >= 6:
                    break
            time.sleep(0.05)
        try:
            target.remove_watchpoint(A, 2, Target.WatchpointType.WRITE)
        except Exception:  # noqa: BLE001
            pass
        emit("     命中 %d 次 —— 0 次才是期望结果" % hits)
        emit("")

if sess is not None:
    try:
        sess.close()
    except Exception:  # noqa: BLE001
        pass
if cl is not None:
    try:
        cl.close()
    except Exception:  # noqa: BLE001
        pass

io.open(OUT, "w", encoding="utf-8").write("\n".join(lines))
print("DONE ->", OUT)
