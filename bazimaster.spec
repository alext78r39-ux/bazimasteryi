# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 設定：產生單一檔案的 BaziMaster.exe。

重點：bazi.py 等資料腳本是「頂層就跑」的腳本，
不是可被 import 的模組，所以 app.py 用 runpy 執行它們。
因此這裡必須把原始 .py 當成 *資料* 一起打包，執行期才找得到。

用法：
    python build_exe.py
或
    python -m PyInstaller bazimaster.spec --noconfirm --clean
"""

import os

from PyInstaller.utils.hooks import collect_all

PROJECT = os.path.abspath(SPECPATH)

# 必須隨 EXE 附帶的原始腳本（app.py 以 runpy 執行它們）
SCRIPTS = [
    'bazi.py',
    'chart.py',
    'common.py',
    'convert.py',
    'datas.py',
    'ganzhi.py',
    'mangpai.py',
    'sizi.py',
    'yue.py',
]

datas = [(name, '.') for name in SCRIPTS]
binaries = []
hiddenimports = []

# 這三個套件是被「資料腳本」引用的，PyInstaller 分析不到，必須手動收集。
for pkg in ('lunar_python', 'bidict', 'colorama'):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# 圖表需要 matplotlib + Pillow（把 PNG 貼到 Tk）。
# matplotlib 會把 backend / font manager 的資料放在自己的套件目錄下，
# collect_all 才不會漏掉字型快取或缺 backend 模組。
# 這兩項是選用的：沒裝到時 app.py 只有「大運流年圖表」分頁會提示缺套件，
# 其他分頁照常運作，所以收集失敗就安靜略過。
for pkg in ('matplotlib', 'PIL'):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    except Exception:
        print('[spec] 未找到 {}，圖表分頁在 EXE 裡會提示缺套件'.format(pkg))
        continue
    if pkg_datas or pkg_hidden:
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
        print('[spec] 已打包 {}（圖表分頁可用）'.format(pkg))
    else:
        print('[spec] {} 收集不到內容，略過'.format(pkg))

# sxtwl 是 C extension，Python 3.13 裝不起來，但它是選用依賴：
# 只有 bazi.py -b 的「可能出生時間」提示需要它，沒有它也能正常排盤。
# 裝了就一併打包。
try:
    sxtwl_datas, sxtwl_binaries, sxtwl_hidden = collect_all('sxtwl')
except Exception:
    sxtwl_datas, sxtwl_binaries, sxtwl_hidden = [], [], []
if sxtwl_datas or sxtwl_hidden:
    datas += sxtwl_datas
    binaries += sxtwl_binaries
    hiddenimports += sxtwl_hidden
    print('[spec] 已找到 sxtwl，「可能出生時間」提示會一併打包')
else:
    print('[spec] 未安裝 sxtwl（選用），四柱排盤不受影響')

a = Analysis(
    ['app.py'],
    pathex=[PROJECT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 排除項要保守：matplotlib 會 import unittest / numpy / PIL，
    # 把這些排掉會讓圖表在 EXE 裡直接缺模組（--chart-selftest 抓得到）。
    # 這裡只砍確定用不到、又體積大的東西。
    excludes=[
        'tkinter.test', 'lib2to3', 'distutils', 'setuptools', 'pip',
        'doctest', 'pytest', 'IPython', 'notebook', 'turtledemo',
        'idlelib', 'ensurepip',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='BaziMaster',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    # console=True：雙擊開 GUI 時程式會自行隱藏主控台，
    # 但「帶參數執行」與 --cli 仍然需要 stdout。
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)