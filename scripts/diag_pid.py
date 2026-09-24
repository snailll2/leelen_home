"""深度检查卡死的 HA 进程:fd 类型、已连接 TCP、是否有锁文件等待。"""
import os
import re

PID = 72
print("=== /proc/{PID}/status")
try:
    st = {}
    for line in open(f"/proc/{PID}/status"):
        k, _, v = line.partition(":")
        st[k.strip()] = v.strip()
    print(" State:", st.get("State"))
    print(" Threads:", st.get("Threads"))
    print(" voluntary_ctxt_switches:", st.get("voluntary_ctxt_switches"))
    print(" nonvoluntary_ctxt_switches:", st.get("nonvoluntary_ctxt_switches"))
except Exception as e:
    print("ERR", repr(e))

print("\n=== fds (non-regular) ===")
for f in os.listdir(f"/proc/{PID}/fd"):
    try:
        tgt = os.readlink(f"/proc/{PID}/fd/{f}")
        if not tgt.startswith("/home") and not tgt.startswith("/config") or "socket" in tgt or "pipe" in tgt or "anon_inode" in tgt:
            print(f"  {f}: {tgt}")
    except OSError:
        pass

print("\n=== TCP connections (proc net) ===")
for fname in ("tcp", "tcp6"):
    p = f"/proc/{PID}/net/{fname}"
    if not os.path.exists(p):
        continue
    for line in open(p):
        parts = line.split()
        if len(parts) < 4 or not all(c in "0123456789ABCDEFabcdef:" for c in parts[1]):
            continue
        state_hex = parts[3]
        states = {"01": "ESTABLISHED", "0A": "LISTEN", "02": "SYN_SENT", "05": "TIME_WAIT", "06": "CLOSE_WAIT"}
        state = states.get(state_hex, "?"+state_hex)
        local, remote = parts[1], parts[2]
        print(f"  {fname} {state} local={local} remote={remote}")

print("\n=== threads with run states ===")
for t in os.listdir(f"/proc/{PID}/task"):
    try:
        with open(f"/proc/{PID}/task/{t}/stat") as fh:
            s = fh.read()
        # parse: (comm) may contain spaces; find closing paren
        rp = s.rfind(")")
        body = s[rp+2:].split()
        # pid (tcomm) state ppid ...
        # body[0]=state, body[1]=ppid
        st = body[0]
        with open(f"/proc/{PID}/task/{t}/wchan") as fh:
            wchan = fh.read().strip() or "(null)"
        with open(f"/proc/{PID}/task/{t}/comm") as fh:
            comm = fh.read().strip()
        if st != "S":
            print(f"  tid={t} comm={comm!r} state={st} wchan={wchan}")
    except OSError:
        pass
print("(threads in S/sleep state omitted)")

print("\n=== process open file locks / dirs ===")
for mt in ("mountinfo", "cgroup"):
    try:
        print(mt, "->", open(f"/proc/{PID}/{mt}").read().split("\n")[0:2])
    except Exception as e:
        print(mt, "ERR", e)