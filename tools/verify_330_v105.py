# -*- coding: utf-8 -*-
"""PSC330 V10.5 验证：外机号越界保护 + 写任务超时放弃

用法：
  "C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python312\\python.exe" ^
      tools\\verify_330_v105.py              # 基线 + 步2（越界测试）
  ... verify_330_v105.py --timeout           # 另做步4（超时测试，需先把外机2的316断电）

╔══════════════════════════════════════════════════════════════════════════╗
║ ★ 必须先烧 PSC330 V10.5 (Project\\Obj\\PSC330RK-V10.hex) 再跑本脚本！      ║
║   在旧固件上跑步2 = 给不存在的外机排写任务 → 写槽焊死 → 只能给 330 断电。  ║
╚══════════════════════════════════════════════════════════════════════════╝

判据：
  步2  写外机3的窗口(330[2662]) → 期望【立即】出现 错误码5(UNIT_ADDR)，
       且紧接着写外机1(330[2654]) 仍能成功 → 写槽没被占 → 修复生效。
  步4  外机2离线时写它 → 期望写槽【自动释放】（不需要给330断电），
       并可测出实际自愈耗时。
"""
import io
import sys
import time

sys.path.insert(0, r"d:\Companty\WEll thinker\F\code\psc330_monitor_tool\psc330_monitor")
import app  # noqa: E402

OUT = r"C:\Users\Administrator\AppData\Local\Temp\verify_330_v105.txt"
UNIT3_HMI = 2662          # 3号槽 标定窗口首位（系统只有 2 台外机 → 不存在）
UNIT1_HMI = 2654          # 1号槽 标定窗口首位
ERR = {0: "无错误", 1: "超量程", 2: "330与316通信故障", 3: "写槽忙/被占",
       4: "写后回读校验不通过", 5: "外机号非法(UNIT_ADDR)", 6: "机组运行中拒绝",
       7: "规格必须成对写", 8: "必须先写配对参数"}

lines = []


def emit(t=""):
    lines.append(str(t))


cl = app.ModbusRtuClient()
cl.open("COM6", 9600, timeout=1.0)


def g(a, n=1):
    try:
        return [app.signed16(x) for x in cl.read_holding_registers(1, a, n)]
    except Exception:  # noqa: BLE001
        return ["ERR"]


def diag(unit):
    """返回 (在线, 写状态, 错误码)"""
    b = 1830 + 48 * (unit - 1)
    return g(b + 42)[0], g(b + 43)[0], g(b + 44)[0]


def slot_free():
    for u in (1, 2):
        st = diag(u)[1]
        if st == 1:
            return False
    return True


def wr(a, v):
    try:
        cl.write_single_register(1, a, v & 0xFFFF)
        return "OK"
    except Exception as exc:  # noqa: BLE001
        return "无应答(%s)" % str(exc)[:32]


emit("PSC330 V10.5 验证   %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
emit("=" * 78)

# ---------- 基线 ----------
emit("【基线】四个槽")
for u in (1, 2, 3, 4):
    on, st, er = diag(u)
    emit("   %d# 在线=%s 写状态=%s 错误码=%s(%s)"
         % (u, on, st, er, ERR.get(er, "?") if isinstance(er, int) else "?"))
emit("   外机1 窗口=%s   外机2 窗口=%s" % (g(2654, 4), g(2658, 4)))
base_free = slot_free()
emit("   写槽空闲? %s" % ("是" if base_free else "★否 —— 先给 330 断电重启，否则下面的判读无效"))
emit("")

# ---------- 步2：越界测试 ----------
emit("【步2】越界测试 —— 往不存在的外机(3号)写标定窗口")
emit("   >> 注意：这一步在旧固件上会把写槽焊死！")
emit("   写 330[%d] = 0 -> %s" % (UNIT3_HMI, wr(UNIT3_HMI, 0)))
time.sleep(3)
on3, st3, er3 = diag(3)
emit("   3# 槽诊断: 在线=%s 写状态=%s 错误码=%s(%s)"
     % (on3, st3, er3, ERR.get(er3, "?") if isinstance(er3, int) else "?"))
reject_ok = (er3 == 5)
emit("   -> %s" % ("★ 立即被拒(错误码5) —— 越界保护生效"
                   if reject_ok else
                   "✗ 没看到错误码5 —— V10.5 没烧进去，或保护没生效"))
emit("")

emit("【步2-续】紧接着写外机1 —— 验写槽没被占住")
t0 = time.time()
r1 = wr(UNIT1_HMI, 0)
emit("   写 330[%d] = 0 -> %s" % (UNIT1_HMI, r1))
ok1 = False
for _ in range(30):
    time.sleep(2)
    on1, st1, er1 = diag(1)
    if st1 == 2 or (st1 == 0 and er1 == 0):
        ok1 = True
        break
    if st1 == 3 and er1 == 3:
        break
emit("   1# 槽诊断: 在线=%s 写状态=%s 错误码=%s   用时 %.1f 秒"
     % (diag(1) + (time.time() - t0,)))
emit("   -> %s" % ("★ 外机1 写入正常 —— 写槽没被占死" if ok1
                   else "✗ 外机1 写不进去 —— 写槽被占住了（旧固件的行为）"))
emit("")

# ---------- 步4：超时测试 ----------
if "--timeout" in sys.argv:
    emit("【步4】超时测试 —— 需要外机2的 316 已断电")
    on2, st2, er2 = diag(2)
    if on2 != 0:
        emit("   ✗ 外机2 仍在线(在线=%s) —— 请先把外机2的316断电，再跑 --timeout" % on2)
    else:
        emit("   外机2 已离线 ✓  写 330[2658] = 0 -> %s" % wr(2658, 0))
        t0 = time.time()
        freed = None
        while time.time() - t0 < 300:
            time.sleep(3)
            if slot_free():
                freed = time.time() - t0
                break
        emit("   -> %s"
             % ("★ 写槽在 %.0f 秒后自动释放 —— 不需要给330断电" % freed if freed
                else "✗ 300 秒仍未释放 —— 超时没生效（把 PSC316_WRITE_JOB_TIMEOUT 调小）"))
        emit("   （这个秒数就是自愈耗时。若明显偏长，调小 modulecontrol.c 里的 TIMEOUT）")
    emit("")
else:
    emit("【步4】未执行。要做的话：把外机2的 316 断电，然后加 --timeout 再跑一次。")
    emit("")

# ---------- 判决 ----------
emit("=" * 78)
if reject_ok and ok1:
    emit("★ 判决：V10.5 修复生效 —— 越界写入被立即拒绝，且不影响正常写入。")
elif not reject_ok:
    emit("✗ 判决：没有看到越界保护。请确认 330 烧的是 V10.5、且烧录后已重启。")
else:
    emit("⚠ 判决：越界被拒了，但正常写入受阻 —— 写槽可能仍被别的东西占着，先给330断电再试。")

cl.close()
io.open(OUT, "w", encoding="utf-8").write("\n".join(lines))
print("DONE ->", OUT)
