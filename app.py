#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author: bazimaster
# CreateDate: 2026-10-03
"""八字排盤 整合啟動器（圖形介面 + 命令列）。

把原本分散在多支腳本的功能整合成單一可執行檔：

  1. 八字排盤      bazi.py        （農曆／公曆輸入）
  2. 生肖合婚      shengxiao.py
  3. 六爻          luohou.py      （需要 sxtwl）
  4. 直接輸入八字  bazi.py -b     （需要 sxtwl）

排盤邏輯完全沿用原腳本：以 runpy 執行 bazi.py / shengxiao.py / luohou.py，
不修改任何命理演算法，也不改動任何輸出文字（含三命通會、窮通寶鑑等引文）。
本檔只負責輸入介面、編碼與輸出呈現。

用法：
  app.py                 開啟圖形介面
  app.py --cli           命令列互動選單
  app.py 1977 8 11 19 -n   直接以引數排盤並輸出到 stdout
"""

import argparse
import contextlib
import io
import os
import re
import runpy
import sys
import traceback

APP_NAME = '八字排盤大師'
APP_VERSION = '1.1'

# 打包成 onefile 時 PyInstaller 會把資料解到 sys._MEIPASS；未打包則用本檔所在目錄。
BASE = getattr(sys, '_MEIPASS', None) or os.path.dirname(os.path.abspath(__file__))

SCRIPTS = ('bazi.py', 'shengxiao.py', 'luohou.py', 'common.py',
           'datas.py', 'ganzhi.py', 'sizi.py', 'yue.py', 'convert.py')

# bazi.py 會直接輸出 ANSI 色碼，但從未呼叫 colorama.init()（見 bazi.py:12），
# 在 Tk 的 Text 元件裡沒有終端機可以解譯，所以顯示前一律剝除。
ANSI_RE = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')

MONO = ('NSimSun', 10)


def _set_console_utf8():
    """把主控台字碼頁改成 UTF-8 (65001)，回傳是否成功。

    這台機器的主控台預設是 cp950，無法編碼部分繁體字（例如 鑑），
    第一次印中文就 UnicodeEncodeError；stdin 也會用同一個字碼頁解讀，
    導致輸入的生肖變成亂碼而查不到。
    """
    if os.name != 'nt':
        return False
    try:
        import ctypes
        kernel = ctypes.windll.kernel32
        out_ok = kernel.SetConsoleOutputCP(65001)
        in_ok = kernel.SetConsoleCP(65001)
        return bool(out_ok) and bool(in_ok)
    except Exception:
        return False


def _isatty(stream):
    try:
        return bool(stream.isatty())
    except Exception:
        return False


def force_utf8():
    """Windows 主控台預設 cp950，第一個中文 print 就會 UnicodeEncodeError。"""
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    console_utf8 = _set_console_utf8()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

    # 只有在主控台已切成 UTF-8，或 stdin 是管線/重導向時才動 stdin，
    # 避免在使用者實際的 cp950 主控台打字時反而解讀錯誤。
    if console_utf8 or not _isatty(sys.stdin):
        try:
            sys.stdin.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

    if BASE not in sys.path:
        sys.path.insert(0, BASE)


def has_sxtwl():
    """sxtwl 在 Python 3.13 無法建置；缺失時要明確告知使用者，而不是丟例外。"""
    try:
        import importlib.util
        return importlib.util.find_spec('sxtwl') is not None
    except Exception:
        return False


def run_script(script, args, strip_ansi=True):
    """以 runpy 執行原腳本並擷取 stdout。

    這些腳本都是「模組層級就跑」的程式，無法 import 後呼叫函式，
    因此用 runpy 給它們一個乾淨的命名空間與自訂 argv。
    """
    path = os.path.join(BASE, script)
    if not os.path.isfile(path):
        return '找不到 {}，請確認檔案是否完整。'.format(script)

    buf = io.StringIO()
    old_argv = sys.argv
    try:
        sys.argv = [script] + [str(item) for item in args]
        with contextlib.redirect_stdout(buf):
            runpy.run_path(path, run_name='__main__')
    except SystemExit:
        pass  # argparse 的 --help / 參數錯誤
    except Exception:
        buf.write('\n[發生錯誤]\n')
        buf.write(traceback.format_exc())
    finally:
        sys.argv = old_argv

    out = buf.getvalue()
    return ANSI_RE.sub('', out) if strip_ansi else out


def hide_console():
    """GUI 模式下藏掉自己那個主控台視窗（--show-console 可停用）。"""
    if os.name != 'nt':
        return
    try:
        import ctypes
        handle = ctypes.windll.kernel32.GetConsoleWindow()
        if handle:
            ctypes.windll.user32.ShowWindow(handle, 0)
    except Exception:
        pass


# --------------------------------------------------------------------------
# 圖形介面
# --------------------------------------------------------------------------

def build_gui():
    import tkinter as tk
    from tkinter import ttk, messagebox

    root = tk.Tk()
    root.title('{} v{}'.format(APP_NAME, APP_VERSION))
    root.geometry('1180x820')
    root.minsize(860, 600)

    sxtwl_ok = has_sxtwl()
    style = ttk.Style()
    if 'vista' in style.theme_names():
        style.theme_use('vista')

    nb = ttk.Notebook(root)
    nb.pack(fill='both', expand=True, padx=8, pady=(8, 0))

    def make_output(parent):
        frame = ttk.Frame(parent)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        text = tk.Text(frame, wrap='none', font=MONO, bg='#ffffff',
                       fg='#111111', undo=True, tabs=('40c',))
        vsb = ttk.Scrollbar(frame, orient='vertical', command=text.yview)
        hsb = ttk.Scrollbar(frame, orient='horizontal', command=text.xview)
        text.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        text.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        return frame, text

    def show(text, content):
        text.delete('1.0', 'end')
        text.insert('1.0', content)
        text.see('1.0')

    def clear(text):
        text.delete('1.0', 'end')

    def copy(text):
        data = text.get('1.0', 'end-1c')
        root.clipboard_clear()
        root.clipboard_append(data)
        root.bell()

    def add_buttons(parent, text):
        bar = ttk.Frame(parent)
        bar.pack(fill='x', pady=(6, 0))
        ttk.Button(bar, text='複製結果',
                   command=lambda: copy(text)).pack(side='left')
        ttk.Button(bar, text='清除',
                   command=lambda: clear(text)).pack(side='left', padx=6)
        ttk.Button(bar, text='存成文字檔', command=lambda: save(text)).pack(
            side='left')

    def save(text):
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            defaultextension='.txt', filetypes=[('文字檔', '*.txt'), ('全部', '*.*')],
            title='存成文字檔')
        if not path:
            return
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(text.get('1.0', 'end-1c'))
        messagebox.showinfo(APP_NAME, '已存到：\n' + path)

    # ---------------- 分頁 1：八字排盤 ----------------
    tab1 = ttk.Frame(nb, padding=8)
    nb.add(tab1, text='  八字排盤  ')

    top = ttk.LabelFrame(tab1, text='出生資料', padding=8)
    top.pack(fill='x')

    entries = {}
    for idx, (key, label, default, width) in enumerate([
            ('year', '出生年', '1977', 8),
            ('month', '出生月', '8', 6),
            ('day', '出生日', '11', 6),
            ('time', '出生時 0-23', '19', 6)]):
        ttk.Label(top, text=label).grid(row=0, column=idx * 2, padx=(0, 4),
                                        sticky='w')
        var = tk.StringVar(value=default)
        ttk.Entry(top, textvariable=var, width=width).grid(
            row=0, column=idx * 2 + 1, padx=(0, 16))
        entries[key] = var

    var_solar = tk.BooleanVar(value=False)
    var_leap = tk.BooleanVar(value=False)
    var_female = tk.BooleanVar(value=False)

    def sync_leap(*_):
        # -r 只對農曆有意義
        if var_solar.get():
            var_leap.set(False)
        chk_leap.state(['!disabled'] if not var_solar.get() else ['disabled'])

    chk_solar = ttk.Checkbutton(top, text='公曆（不加則為農曆）',
                                variable=var_solar, command=sync_leap)
    chk_leap = ttk.Checkbutton(top, text='閏月（僅農曆）', variable=var_leap)
    chk_female = ttk.Checkbutton(top, text='女命', variable=var_female)
    chk_solar.grid(row=1, column=0, columnspan=2, sticky='w', pady=(8, 0))
    chk_leap.grid(row=1, column=2, columnspan=2, sticky='w', pady=(8, 0))
    chk_female.grid(row=1, column=4, columnspan=2, sticky='w', pady=(8, 0))
    sync_leap()

    out1, text1 = make_output(tab1)
    out1.pack(fill='both', expand=True, pady=8)
    add_buttons(tab1, text1)

    def do_bazi():
        try:
            args = [entries[k].get().strip() for k in ('year', 'month', 'day', 'time')]
            if not all(arg.isdigit() for arg in args):
                messagebox.showwarning(APP_NAME, '年、月、日、時請填整數數字。')
                return
            flags = []
            if var_solar.get():
                flags.append('-g')
            if var_leap.get():
                flags.append('-r')
            if var_female.get():
                flags.append('-n')
            show(text1, run_script('bazi.py', args + flags))
        except Exception:
            show(text1, traceback.format_exc())

    ttk.Button(top, text='排　盤', command=do_bazi).grid(
        row=0, column=8, rowspan=2, padx=(24, 0), ipadx=14, ipady=4)

    # ---------------- 分頁 2：生肖合婚 ----------------
    tab2 = ttk.Frame(nb, padding=8)
    nb.add(tab2, text='  生肖合婚  ')

    animals = ['鼠', '牛', '虎', '兔', '龍', '蛇',
               '馬', '羊', '猴', '雞', '狗', '豬']
    try:
        from datas import shengxiaos
        animals = list(shengxiaos.inverse.keys())
    except Exception:
        pass

    bar2 = ttk.LabelFrame(tab2, text='生肖', padding=8)
    bar2.pack(fill='x')
    var_zodiac = tk.StringVar(value=animals[2])
    ttk.Combobox(bar2, textvariable=var_zodiac, values=animals,
                 state='readonly', width=10).pack(side='left')
    ttk.Button(bar2, text='查詢', command=lambda: show(
        text2, run_script('shengxiao.py', [var_zodiac.get()]))).pack(
        side='left', padx=8)

    out2, text2 = make_output(tab2)
    out2.pack(fill='both', expand=True, pady=8)
    add_buttons(tab2, text2)

    # ---------------- 分頁 3：六爻 ----------------
    tab3 = ttk.Frame(nb, padding=8)
    nb.add(tab3, text='  六　爻  ')

    bar3 = ttk.LabelFrame(tab3, text='起卦日期與天數', padding=8)
    bar3.pack(fill='x')
    liao = {}
    for idx, (key, label, default, width) in enumerate([
            ('year', '年', '2019', 8), ('month', '月', '6', 6),
            ('day', '日', '16', 6), ('days', '列印天數', '32', 6)]):
        ttk.Label(bar3, text=label).grid(row=0, column=idx * 2, padx=(0, 4))
        var = tk.StringVar(value=default)
        ttk.Entry(bar3, textvariable=var, width=width).grid(
            row=0, column=idx * 2 + 1, padx=(0, 16))
        liao[key] = var

    out3, text3 = make_output(tab3)
    out3.pack(fill='both', expand=True, pady=8)
    add_buttons(tab3, text3)

    def do_luohou():
        if not sxtwl_ok:
            show(text3, need_sxtwl('六爻'))
            return
        vals = [liao[k].get().strip() for k in ('year', 'month', 'day', 'days')]
        if not all(v.isdigit() for v in vals):
            messagebox.showwarning(APP_NAME, '請填整數數字。')
            return
        show(text3, run_script('luohou.py',
                               ['-d', '{} {} {}'.format(*vals[:3]), '-n', vals[3]]))

    ttk.Button(bar3, text='起　卦', command=do_luohou).grid(
        row=0, column=8, padx=(24, 0), ipadx=14, ipady=4)
    if not sxtwl_ok:
        show(text3, need_sxtwl('六爻'))

    # ---------------- 分頁 4：直接輸入八字 ----------------
    tab4 = ttk.Frame(nb, padding=8)
    nb.add(tab4, text='  直接輸入八字  ')

    bar4 = ttk.LabelFrame(tab4, text='四柱（例：丁巳 己酉 癸未 壬戌）', padding=8)
    bar4.pack(fill='x')
    var_pillar = tk.StringVar(value='丁巳 己酉 癸未 壬戌')
    ttk.Entry(bar4, textvariable=var_pillar).pack(side='left', fill='x',
                                                  expand=True, padx=(0, 8))
    out4, text4 = make_output(tab4)
    out4.pack(fill='both', expand=True, pady=8)
    add_buttons(tab4, text4)

    def do_pillar():
        if not sxtwl_ok:
            show(text4, need_sxtwl('直接輸入八字'))
            return
        parts = var_pillar.get().split()
        if len(parts) != 4 or any(len(p) != 2 for p in parts):
            messagebox.showwarning(
                APP_NAME, '請輸入四組兩字柱，例：丁巳 己酉 癸未 壬戌')
            return
        show(text4, run_script('bazi.py', ['-b'] + parts))

    ttk.Button(bar4, text='排　盤', command=do_pillar).pack(
        side='left', ipadx=14, ipady=4)
    if not sxtwl_ok:
        show(text4, need_sxtwl('直接輸入八字'))

    # ---------------- 分頁 5：命令列 ----------------
    tab5 = ttk.Frame(nb, padding=8)
    nb.add(tab5, text='  命令列模式  ')

    bar5 = ttk.LabelFrame(tab5, text='bazi.py 引數（例：1977 8 11 19 -n）', padding=8)
    bar5.pack(fill='x')
    var_raw = tk.StringVar(value='1977 8 11 19 -n')
    ttk.Entry(bar5, textvariable=var_raw).pack(side='left', fill='x',
                                               expand=True, padx=(0, 8))
    ttk.Button(bar5, text='執行', command=lambda: show(
        text5, run_script('bazi.py', var_raw.get().split()))).pack(
        side='left', ipadx=14, ipady=4)

    out5, text5 = make_output(tab5)
    out5.pack(fill='both', expand=True, pady=8)
    add_buttons(tab5, text5)

    ttk.Label(
        tab5, text='可用旗標：-g 公曆　-r 閏月（僅農曆）　-n 女命',
        foreground='#555555').pack(anchor='w')

    # ---------------- 選單列 ----------------
    menubar = tk.Menu(root)

    def go(idx):
        nb.select(idx)

    m_file = tk.Menu(menubar, tearoff=0)
    m_file.add_command(label='關閉', command=root.destroy)
    menubar.add_cascade(label='檔案', menu=m_file)

    m_fun = tk.Menu(menubar, tearoff=0)
    m_fun.add_command(label='八字排盤', command=lambda: go(0))
    m_fun.add_command(label='生肖合婚', command=lambda: go(1))
    m_fun.add_command(label='六　爻' + ('' if sxtwl_ok else '（需要 sxtwl）'),
                     command=lambda: go(2))
    m_fun.add_command(label='直接輸入八字' + ('' if sxtwl_ok else '（需要 sxtwl）'),
                     command=lambda: go(3))
    m_fun.add_command(label='命令列模式', command=lambda: go(4))
    menubar.add_cascade(label='功能', menu=m_fun)

    m_help = tk.Menu(menubar, tearoff=0)
    m_help.add_command(label='關於', command=lambda: messagebox.showinfo(
        APP_NAME,
        '{} v{}\n\n依賴：bidict、lunar_python、colorama\n'
        'sxtwl：{}\n\n排盤邏輯沿用原腳本，未經修改。'.format(
            APP_NAME, APP_VERSION, '已安裝' if sxtwl_ok else '未安裝')))
    menubar.add_cascade(label='說明', menu=m_help)
    root.config(menu=menubar)

    # ---------------- 狀態列 ----------------
    status = ttk.Label(
        root, anchor='w', padding=(10, 4),
        text='就緒　|　sxtwl：{}　|　八字排盤、生肖合婚可正常使用'.format(
            '已安裝' if sxtwl_ok else '未安裝（Python 3.13 無法安裝）'))
    status.pack(fill='x', side='bottom')

    return root


def need_sxtwl(feature):
    return (
        '【{}】需要 sxtwl 套件，目前未安裝，因此無法執行。\n\n'
        '原因：sxtwl 在 Python 3.13 沒有預先編譯的 wheel，'
        '原始碼也編譯失敗。\n'
        '影響範圍：僅「{}」與「直接輸入八字」；\n'
        '　　　　　八字排盤（農曆／公曆）與生肖合婚不受影響。\n\n'
        '解法：改用 Python 3.11 建立環境後執行 pip install sxtwl，\n'
        '　　　再重新打包本程式。\n'.format(feature, feature)
    )


# --------------------------------------------------------------------------
# 命令列介面
# --------------------------------------------------------------------------

def main_cli():
    force_utf8()
    print('=' * 60)
    print('  {} v{}  —  命令列模式'.format(APP_NAME, APP_VERSION))
    print('=' * 60)

    sxtwl_ok = has_sxtwl()
    if not sxtwl_ok:
        print('提醒：未安裝 sxtwl，六爻與直接輸入八字無法使用。')

    while True:
        print()
        print('-' * 60)
        print('  1) 八字排盤')
        print('  2) 生肖合婚')
        print('  3) 六爻' + ('' if sxtwl_ok else '（需要 sxtwl）'))
        print('  4) 直接輸入八字' + ('' if sxtwl_ok else '（需要 sxtwl）'))
        print('  q) 離開')
        print('-' * 60)

        def ask(prompt):
            try:
                return input(prompt).strip()
            except (EOFError, KeyboardInterrupt):
                return 'q'

        choice = ask('請選擇：').lower()

        if choice in ('q', 'quit', 'exit', ''):
            print('再見。')
            return 0

        if choice == '1':
            parts = [ask('出生年　　：'), ask('出生月　　：'),
                     ask('出生日　　：'), ask('出生時 0-23：')]
            if not all(p.isdigit() for p in parts):
                print('請填整數數字。')
                continue
            flags = []
            if ask('是否公曆？y/N：').lower().startswith('y'):
                flags.append('-g')
            elif ask('是否閏月？y/N：').lower().startswith('y'):
                flags.append('-r')
            if ask('是否女命？y/N：').lower().startswith('y'):
                flags.append('-n')
            print(run_script('bazi.py', parts + flags, strip_ansi=False))

        elif choice == '2':
            animal = ask('生肖（鼠牛虎兔龍蛇馬羊猴雞狗豬）：')
            if not animal:
                continue
            print(run_script('shengxiao.py', [animal], strip_ansi=False))

        elif choice == '3':
            if not sxtwl_ok:
                print(need_sxtwl('六爻'))
                continue
            vals = [ask('年：'), ask('月：'), ask('日：'), ask('列印天數：')]
            if not all(v.isdigit() for v in vals):
                print('請填整數數字。')
                continue
            print(run_script('luohou.py',
                             ['-d', '{} {} {}'.format(*vals[:3]), '-n', vals[3]],
                             strip_ansi=False))

        elif choice == '4':
            if not sxtwl_ok:
                print(need_sxtwl('直接輸入八字'))
                continue
            pillars = ask('四柱（例：丁巳 己酉 癸未 壬戌）：').split()
            if len(pillars) != 4 or any(len(p) != 2 for p in pillars):
                print('請輸入四組兩字柱。')
                continue
            print(run_script('bazi.py', ['-b'] + pillars, strip_ansi=False))

        else:
            print('輸入的選項不正確，請重新選擇。')


def main():
    argv = sys.argv[1:]
    our_flags = {'--cli', '--show-console', '--version', '-h', '--help'}

    # 只要不是本程式自己的旗標，全部原樣交給 bazi.py，
    # 這樣 -g / -n / -r / -b 才能直接透傳（argparse 會吃掉 -n）。
    if argv and not any(arg in our_flags for arg in argv):
        force_utf8()
        sys.stdout.write(run_script('bazi.py', argv, strip_ansi=False))
        return 0

    parser = argparse.ArgumentParser(
        prog=os.path.basename(sys.argv[0]),
        description='{} v{} — 八字排盤整合程式'.format(APP_NAME, APP_VERSION))
    parser.add_argument('--cli', action='store_true',
                        help='使用命令列互動選單')
    parser.add_argument('--show-console', action='store_true',
                        help='圖形介面模式下不要隱藏主控台視窗')
    parser.add_argument('--version', action='version',
                        version='%(prog)s {}'.format(APP_VERSION))
    options = parser.parse_args()

    if options.cli:
        return main_cli()

    force_utf8()

    if not options.show_console:
        hide_console()

    root = build_gui()
    root.mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())