#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 通道配置 —— 串口实机验证工具（只读，默认不改任何值）

用途：把今晚的改动从"编译通过"验证到"硬件可用"。
      连上 330 后，读回新增的配置块与网关镜像，逐字段解码并与固件预期比对。

用法：
    python verify_ai_config_serial.py                 # 自动扫描串口
    python verify_ai_config_serial.py COM9            # 指定串口
    python verify_ai_config_serial.py COM9 --slave 1  # 指定从站号（默认 1）
    python verify_ai_config_serial.py COM9 --unit 2   # 只看 2# 外机的 316 配置

安全：本脚本 **只读**，不写任何寄存器。
"""
from __future__ import annotations

import sys
import time

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("缺少 pyserial，请先执行: pip install pyserial")
    sys.exit(2)

# ---- 与固件/监控软件必须一致的地址常量 --------------------------------------
INDOOR_AI_CFG_BASE = 1229          # 330 内机配置块
INDOOR_AI_CFG_WORDS = 12
CH_WORDS = 12

OUTDOOR_AI_CFG_HMI_BASE = 2680     # 330 网关镜像窗口
OUTDOOR_AI_CFG_UNIT_WORDS = 49     # 每台外机字数
OUTDOOR_AI_CFG_VERSION_MAGIC = 12641
OUTDOOR_AI_CFG_UNITS = 4

INDOOR_CHANNELS = ["AI0 房间压差", "AI1 房间湿度", "AI2 CO2", "AI3 送风压/风量", "AI4 新风湿度"]
OUTDOOR_CHANNELS = ["AI0 1#高压", "AI1 2#高压", "AI2 1#低压", "AI3 2#低压"]

FIELDS = ["使能", "信号类型", "信号下限", "信号上限",
          "工程量下限", "工程量上限", "副下限", "副上限",
          "校准偏移", "断线判据", "单位代码", "小数位"]

ENABLE_MAP = {0: "禁用", 1: "启用"}
TYPE_MAP = {0: "0-10V", 1: "4-20mA"}
UNIT_MAP = {0: "Pa", 1: "C", 2: "%RH", 3: "ppm", 4: "CMH", 5: "Bar"}

# 316 侧每个字段的合法范围（来自 firmware 的 Parameter_min/max 表）
OUT_LIMITS = {0: (0, 1), 1: (0, 1), 2: (0, 2000), 3: (0, 2000),
              4: (-20000, 20000), 5: (-20000, 20000), 6: (-20000, 20000),
              7: (-20000, 20000), 8: (-20000, 20000), 9: (0, 2000),
              10: (0, 4), 11: (0, 3)}


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF


class Modbus:
    def __init__(self, port: str, slave: int, baud: int = 9600, timeout: float = 0.4):
        self.slave = slave
        self.ser = serial.Serial(port, baud, bytesize=8, parity="N",
                                 stopbits=1, timeout=timeout)

    def close(self) -> None:
        try:
            self.ser.close()
        except Exception:
            pass

    def read(self, addr: int, count: int) -> list[int]:
        if not (1 <= count <= 125):
            raise ValueError("count 1..125")
        pdu = bytes([self.slave, 0x03, addr >> 8, addr & 0xFF, count >> 8, count & 0xFF])
        req = pdu + crc16(pdu).to_bytes(2, "little")
        self.ser.reset_input_buffer()
        self.ser.write(req)
        self.ser.flush()
        resp = self.ser.read(5 + count * 2)
        if len(resp) < 5:
            raise IOError("无应答（检查串口/从站号/接线）")
        if resp[1] & 0x80:
            raise IOError("Modbus 异常码 %d（地址可能不被支持）" % resp[2])
        if resp[2] != count * 2:
            raise IOError("字节数异常: %d" % resp[2])
        if crc16(resp[:-2]) != (resp[-2] | (resp[-1] << 8)):
            raise IOError("CRC 校验失败")
        return [(resp[3 + 2 * i] << 8) | resp[4 + 2 * i] for i in range(count)]


def s16(v: int) -> int:
    return v - 0x10000 if v >= 0x8000 else v


def fmt(v: int, field_idx: int) -> str:
    if field_idx == 0:
        return ENABLE_MAP.get(v, str(v))
    if field_idx == 1:
        return TYPE_MAP.get(v, str(v))
    if field_idx == 10:
        return UNIT_MAP.get(v, str(v))
    return str(v)


def dump_block(title: str, values: list[int], channels: list[str],
               check: bool, version_offset: int | None) -> list[str]:
    """打印一个配置块，返回问题清单。"""
    problems: list[str] = []
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)
    for ci, cname in enumerate(channels):
        off = ci * CH_WORDS
        row = values[off:off + CH_WORDS]
        if len(row) < CH_WORDS:
            break
        print("  %-16s" % cname)
        line = []
        for fi, fname in enumerate(FIELDS):
            line.append("%s=%s" % (fname, fmt(s16(row[fi]), fi)))
        print("      " + "  ".join(line[:6]))
        print("      " + "  ".join(line[6:]))
        if check:
            for fi, (lo, hi) in OUT_LIMITS.items():
                v = s16(row[fi])
                if not (lo <= v <= hi):
                    problems.append(
                        "%s 的【%s】=%d 超出范围[%d,%d]（重启会被回退成默认值）"
                        % (cname, FIELDS[fi], v, lo, hi))
    if version_offset is not None:
        v = s16(values[version_offset])
        ok = v == OUTDOOR_AI_CFG_VERSION_MAGIC
        print("  %-16s 版本标记 = %d %s" % ("", v,
              "(0x3161 已就绪)" if ok else "(未迁移/该外机不在线)"))
        if not ok:
            problems.append("版本标记=%d，不等于 %d：该外机可能未上电或未完成迁移"
                            % (v, OUTDOOR_AI_CFG_VERSION_MAGIC))
    return problems


def main() -> int:
    argv = sys.argv[1:]
    slave = int(argv[argv.index("--slave") + 1]) if "--slave" in argv else 1
    only_unit = int(argv[argv.index("--unit") + 1]) if "--unit" in argv else None
    args = [a for a in argv if not a.startswith("--")]

    # 去掉 --slave/--unit 后面的数值参数，剩下的第一个才是串口号
    if "--slave" in argv:
        args = [a for a in args if a != argv[argv.index("--slave") + 1]]
    if "--unit" in argv:
        args = [a for a in args if a != argv[argv.index("--unit") + 1]]

    if args:
        port = args[0]
    else:
        ports = list(serial.tools.list_ports.comports())
        if not ports:
            print("未检测到任何串口。请确认 USB-485 已插好、驱动已装。")
            return 1
        print("检测到串口:")
        for p in ports:
            print("   %-8s %s" % (p.device, p.description))
        port = ports[0].device
        print("自动选用:", port)

    try:
        mb = Modbus(port, slave)
    except Exception as exc:
        print("打开串口失败:", exc)
        return 1

    problems: list[str] = []
    try:
        print("\n连接到 %s (从站 %d, 9600-8-N-1)，正在读取…" % (port, slave))

        # 1) 330 内机配置块
        try:
            v = mb.read(INDOOR_AI_CFG_BASE, INDOOR_AI_CFG_WORDS * len(INDOOR_CHANNELS))
            problems += dump_block(
                "330 内机 AI 配置块  Parameter[%d..%d]"
                % (INDOOR_AI_CFG_BASE, INDOOR_AI_CFG_BASE + 59),
                v, INDOOR_CHANNELS, check=False, version_offset=None)
        except Exception as exc:
            print("\n[330 内机配置块] 读取失败:", exc)
            problems.append("330 内机配置块读取失败: %s" % exc)

        # 2) 316 网关镜像
        units = [only_unit] if only_unit else list(range(1, OUTDOOR_AI_CFG_UNITS + 1))
        for u in units:
            base = OUTDOOR_AI_CFG_HMI_BASE + (u - 1) * OUTDOOR_AI_CFG_UNIT_WORDS
            try:
                v = mb.read(base, OUTDOOR_AI_CFG_UNIT_WORDS)
            except Exception as exc:
                print("\n[%d# 外机] 读取失败: %s" % (u, exc))
                problems.append("%d# 外机读取失败: %s" % (u, exc))
                continue
            problems += dump_block(
                "%d# 外机 AI 配置（330 网关镜像 Parameter[%d..%d]）"
                % (u, base, base + OUTDOOR_AI_CFG_UNIT_WORDS - 1),
                v, OUTDOOR_CHANNELS, check=True, version_offset=48)
    finally:
        mb.close()

    print()
    print("=" * 78)
    if problems:
        print("发现问题 %d 项：" % len(problems))
        for p in problems:
            print("  -", p)
    else:
        print("全部检查通过：配置块可读、字段均在合法范围内、版本标记已就绪。")
    print("=" * 78)
    print("提示：本工具只读。要改值请在监控软件「AI 通道配置」页操作。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
