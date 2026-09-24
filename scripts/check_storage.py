"""检查 HA .storage JSON 完整性 + DB 文件状态(诊断 bootstrap 卡死)。"""
import glob
import json
import os

base = "/config/.storage"
bad = 0
for f in sorted(glob.glob(f"{base}/*")):
    if os.path.isdir(f):
        continue
    try:
        with open(f, encoding="utf-8") as fh:
            json.load(fh)
    except Exception as e:
        bad += 1
        print("CORRUPT:", f, "->", repr(e))
print(f"storage check done: {bad} corrupt")

for db in ("/config/home-assistant_v2.db",):
    print(db, "size=", os.path.getsize(db) if os.path.exists(db) else "MISSING",
          "wal=", os.path.getsize(db + "-wal") if os.path.exists(db + "-wal") else 0,
          "shm=", os.path.getsize(db + "-shm") if os.path.exists(db + "-shm") else 0)