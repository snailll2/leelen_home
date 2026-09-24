#!/bin/sh
# 找 HA python 进程并 py-spy dump 其堆栈
PID=$(python3 -c "
import glob
for p in glob.glob('/proc/[0-9]*/comm'):
    if open(p).read().strip() == 'python3':
        print(p.split('/')[2])
        break
")
echo "PID=$PID"
py-spy dump --pid "$PID" 2>&1 | head -80