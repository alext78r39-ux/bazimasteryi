#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author: bazimaster 整合版
# CreateDate: 2026-10-03
"""建置單一檔案的 BaziMaster.exe。

    python build_exe.py            # 一般建置
    python build_exe.py --clean    # 先清掉 build/ 與 dist/

產物：dist\\BaziMaster.exe
"""

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, 'bazimaster.spec')

for folder in ('build', 'dist'):
    path = os.path.join(HERE, folder)
    if os.path.isdir(path) and '--clean' in sys.argv:
        shutil.rmtree(path)
        print('[build] 已清除 {}'.format(folder))

print('[build] 開始打包 BaziMaster.exe ...')
result = subprocess.run(
    [sys.executable, '-m', 'PyInstaller', SPEC, '--noconfirm', '--clean'],
    cwd=HERE)

exe = os.path.join(HERE, 'dist', 'BaziMaster.exe')
if result.returncode == 0 and os.path.isfile(exe):
    size = os.path.getsize(exe) / 1024 / 1024
    print()
    print('[build] 完成：{}  ({:.1f} MB)'.format(exe, size))
    sys.exit(0)

print()
print('[build] 建置失敗，請看上面的錯誤訊息。')
sys.exit(result.returncode or 1)