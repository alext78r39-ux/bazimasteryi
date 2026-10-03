# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 設定：產生單一檔案的 BaziMaster.exe。

重點：bazi.py / shengxiao.py / luohou.py 等是「頂層就跑」的腳本，
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
    'common.py',
    'convert.py',
    'datas.py',
    'ganzhi.py',
    'luohou.py',
    'shengxiao.py',
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

# sxtwl 是 C extension，Python 3.13 裝不起來。裝了就一併打包，
# 沒裝也不影響建置 —— app.py 會自行偵測並在畫面上提示。
try:
    sxtwl_datas, sxtwl_binaries, sxtwl_hidden = collect_all('sxtwl')
except Exception:
    sxtwl_datas, sxtwl_binaries, sxtwl_hidden = [], [], []
if sxtwl_datas or sxtwl_hidden:
    datas += sxtwl_datas
    binaries += sxtwl_binaries
    hiddenimports += sxtwl_hidden
    print('[spec] 已找到 sxtwl，六爻與直接輸入八字會一併打包')
else:
    print('[spec] 未安裝 sxtwl，六爻與直接輸入八字將顯示需要 sxtwl')

a = Analysis(
    ['app.py'],
    pathex=[PROJECT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter.test', 'test', 'unittest', 'pydoc_data', 'lib2to3',
        'distutils', 'setuptools', 'pip', 'doctest', 'numpy', 'PIL',
        'pytest', 'IPython', 'notebook', 'sqlite3', 'email', 'http',
        'xml', 'pydoc', 'venv', 'ensurepip', 'idlelib', 'turtledemo',
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