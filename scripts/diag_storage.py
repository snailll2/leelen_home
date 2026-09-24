"""设置点对比:检查本容器 .storage 是否有异常条目,可能卡 bootstrap。"""
import json
import glob
import os

base = "/config/.storage"
print("== storage files ==")
for f in sorted(glob.glob(f"{base}/*")):
    name = os.path.basename(f)
    if os.path.isfile(f):
        try:
            d = json.load(open(f, encoding="utf-8"))
            print(f"  {name:44s} v{d.get('version')} ok")
        except Exception as e:
            print(f"  {name:44s} CORRUPT: {e!r}")
    else:
        print(f"  {name:44s} <dir>")

ce_path = f"{base}/core.config_entries"
if os.path.exists(ce_path):
    try:
        ce = json.load(open(ce_path, encoding="utf-8"))
        entries = ce.get("data", {}).get("entries", [])
        print(f"\n== config_entries: {len(entries)} ==")
        for el in entries:
            print("  ENTRY:", el.get("domain"), "| id=", el.get("entry_id"),
                  "| disabled=", el.get("disabled_by"),
                  "| modified=", el.get("modified_at"))
            data = el.get("data") or {}
            safe = {k: ("***" if k in ("username", "password", "token") else v)
                    for k, v in data.items()}
            print("      data:", safe)
    except Exception as e:
        print("config_entries READ ERR", repr(e))

reg_path = f"{base}/core.entity_registry"
if os.path.exists(reg_path):
    try:
        reg = json.load(open(reg_path, encoding="utf-8"))
        ents = reg.get("data", {}).get("entities", [])
        print(f"\n== entity_registry: {len(ents)} entities ==")
        by_domain = {}
        for e in ents:
            p = (e.get("entity_id") or "?").split(".")[0]
            by_domain.setdefault(p, []).append(e)
        for dom, l in sorted(by_domain.items()):
            print(f"  {dom}: {len(l)}")
        # 列出 leelen 相关
        for e in ents:
            uid = e.get("unique_id", "")
            if "leelen" in (e.get("config_entry_id") or "") or uid.startswith("leelen"):
                cap = e.get("capabilities")
                dc = e.get("device_class")
                created = e.get("created_at")
                print(f"  L {e.get('entity_id')} uid={uid} dc={dc} cap={cap} created={created}")
    except Exception as e:
        print("entity_registry READ ERR", repr(e))