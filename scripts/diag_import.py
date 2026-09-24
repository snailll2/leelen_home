"""诊断:在容器内直接 import leelen_home 包,复现 bootstrap 卡死。"""
import sys
import time

sys.path.insert(0, "/config")
t0 = time.time()
try:
    import custom_components.leelen_home
    print(f"IMPORT OK after {time.time()-t0:.1f}s ->",
          custom_components.leelen_home.__file__)
except Exception as e:
    print(f"IMPORT FAILED after {time.time()-t0:.1f}s: {e!r}")