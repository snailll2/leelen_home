"""查询 dump.db 里智能插座(518)逻辑通道的 logic_type,核对 sensor 建实体依据。"""
import sqlite3
import sys

con = sqlite3.connect("/config/dump.db")
cur = con.cursor()
tables = [r[0] for r in cur.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")]
print("TABLES:", tables)

# 找含 logic_type / logic_addr 的表
for t in tables:
    cols = [r[1] for r in cur.execute(f"PRAGMA table_info({t})")]
    if any("logic" in c.lower() for c in cols):
        print(f"\n=== {t} cols={cols}")
        for row in cur.execute(f"SELECT * FROM {t} LIMIT 3"):
            print(row)

# 直接看 518 / 已知地址的行
for t in tables:
    try:
        rows = cur.execute(
            f"SELECT * FROM {t} WHERE logic_type=518 OR logic_addr IN (33,49,289,353,369)").fetchall()
        if rows:
            print(f"\n=== 518/插座地址 in {t}: {len(rows)} rows")
            for row in rows[:20]:
                print(row)
    except Exception as e:
        pass
con.close()