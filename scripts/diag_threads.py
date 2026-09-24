"""诊断卡死的 HA python 进程:线程状态 + fd 列表 + 内核等待通道。"""
import glob
import os

# 找 python3 主进程(HA)
pid = None
for p in glob.glob("/proc/[0-9]*/comm"):
    try:
        if open(p).read().strip() == "python3":
            pid = p.split("/")[2]
            break
    except OSError:
        pass
if not pid:
    print("no python3 process")
    raise SystemExit
print("PID =", pid)

states = {}
wchans = {}
for t in glob.glob(f"/proc/{pid}/task/*"):
    tid = t.rstrip("/").split("/")[-1]
    try:
        with open(f"{t}/stat") as fh:
            parts = fh.read().split()
        state = parts[2] if len(parts) > 2 else "?"
        states[state] = states.get(state, 0) + 1
        with open(f"{t}/wchan") as fh:
            wchans.setdefault(fh.read().strip() or "(none)", []).append(tid)
    except OSError:
        pass
print("thread states:", states)
for chan, tids in sorted(wchans.items()):
    print(f"  wchan={chan} tids={tids[:6]}{'...' if len(tids) > 6 else ''}")

# fd 指向 (重点看 socket/reg 文件)
sockets = 0
for f in glob.glob(f"/proc/{pid}/fd/*"):
    try:
        tgt = os.readlink(f)
        if tgt.startswith("socket:"):
            sockets += 1
    except OSError:
        pass
print("open sockets:", sockets)

# 进程自己的 cmdline
print("cmdline:", open(f"/proc/{pid}/cmdline").read().replace("\0", " "))