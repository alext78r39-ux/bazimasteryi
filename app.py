#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author: bazimaster
# CreateDate: 2026-10-03
"""八字排盤 整合啟動器（圖形介面 + 命令列）。

把原本分散在多支腳本的功能整合成單一可執行檔：

  1. 八字排盤        bazi.py        （農曆／公曆輸入）
  2. 直接輸入八字    bazi.py -b     （已有四柱文字時直接排盤）
  3. 大運流年圖表    chart.py       （matplotlib 畫大運／流年走勢）
  4. 盲派暗局做功    mangpai.py     （明局做功、尋藥、飛神、類象、歲運）

排盤邏輯完全沿用原腳本：以 runpy 執行 bazi.py，
不修改任何命理演算法，也不改動任何輸出文字（含三命通會、窮通寶鑑等引文）。
本檔只負責輸入介面、編碼、輸出呈現，以及把圖表接到既有計算結果上。

圖表分頁沿用 bazi.py 的 tables 與權重（gan5 / zhi5 / ten_deities），
所以圖上的分數與文字排盤一致；它讀的是 runpy 回傳的模組 globals，
不是去解析印出來的文字。

sxtwl 是選用依賴：只有「可能出生時間」反推提示需要它，
沒有安裝時四柱排盤照常運作。

用法：
  app.py                 開啟圖形介面
  app.py --cli           命令列互動選單
  app.py 1977 8 11 19 -n   直接以引數排盤並輸出到 stdout
"""

import argparse
import contextlib
import io
import json
import os
import re
import runpy
import sys
import traceback

APP_NAME = '八字排盤大師'
APP_VERSION = '1.3'

# 打包成 onefile 時 PyInstaller 會把資料解到 sys._MEIPASS；未打包則用本檔所在目錄。
BASE = getattr(sys, '_MEIPASS', None) or os.path.dirname(os.path.abspath(__file__))

SCRIPTS = ('bazi.py', 'common.py', 'datas.py', 'ganzhi.py', 'sizi.py', 'yue.py',
           'convert.py', 'chart.py', 'mangpai.py')

# bazi.py 會直接輸出 ANSI 色碼，但從未呼叫 colorama.init()（見 bazi.py:12），
# 在 Tk 的 Text 元件裡沒有終端機可以解譯，所以顯示前一律剝除。
ANSI_RE = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')


# --------------------------------------------------------------------------
# 介面設定（管理員面板）
#
# 打包成 onefile 後 sys._MEIPASS 是唯讀的暫存解壓目錄，而且每次啟動都不一樣，
# 所以設定一律寫到 %APPDATA%\BaziMaster\settings.json。
# --------------------------------------------------------------------------

SETTINGS_FOLDER = 'BaziMaster'

DEFAULT_SETTINGS = {
    'theme': 'vista',
    'ui_font': 'Microsoft JhengHei UI',
    'ui_font_size': 9,
    'out_font': 'NSimSun',
    'out_font_size': 10,
    'text_bg': '#ffffff',
    'text_fg': '#111111',
    'wrap_output': False,
    'win_width': 1180,
    'win_height': 820,
}

# 各整數設定的合法範圍，避免設定檔被改壞後介面開不起來
INT_RANGES = {
    'ui_font_size': (7, 24),
    'out_font_size': (7, 32),
    'win_width': (640, 4000),
    'win_height': (480, 3000),
}

# 排盤靠 chr(12288) 與 15 字元欄寬對齊，輸出字型必須是「中英文等寬」，
# 換成明體以外的比例字型會讓欄位跑掉。這幾個是 Windows 上常見的等寬中文字型。
MONO_FONTS = ['NSimSun', 'MingLiU', 'SimSun', 'PMingLiU', 'DFKai-SB',
              'Batang', 'Gulim', 'KaiTi', 'FangSong', 'Microsoft JhengHei']

# 介面（按鈕、輸入框）用的一般字型
UI_FONTS = ['Microsoft JhengHei UI', 'Microsoft JhengHei', 'Segoe UI',
            'Tahoma', 'Arial', '新細明體', 'DFKai-SB', 'SimSun']


def settings_path():
    base = os.environ.get('APPDATA') or os.path.expanduser('~')
    return os.path.join(base, SETTINGS_FOLDER, 'settings.json')


def _clamp(value, bounds, fallback):
    lo, hi = bounds
    try:
        num = int(str(value).strip())
    except (TypeError, ValueError):
        return fallback
    return max(lo, min(hi, num))


class Settings:
    """介面設定的讀寫與自我修復。

    讀不到或檔案損壞時一律退回預設值；每個值都會被檢查型別與範圍，
    避免手改設定檔造成視窗開不出來。
    """

    def __init__(self, path=None):
        self.path = path or settings_path()
        self.data = dict(DEFAULT_SETTINGS)
        self.load()

    @staticmethod
    def clean(raw):
        out = {}
        for key, fallback in DEFAULT_SETTINGS.items():
            value = raw.get(key, fallback) if isinstance(raw, dict) else fallback
            if isinstance(fallback, bool):
                out[key] = bool(value)
            elif isinstance(fallback, int):
                out[key] = _clamp(value, INT_RANGES.get(key, (1, 10000)), fallback)
            else:
                text = str(value).strip()
                out[key] = text if text else fallback
        return out

    def load(self):
        try:
            with open(self.path, encoding='utf-8') as fh:
                data = self.clean(json.load(fh))
        except (OSError, ValueError):
            data = dict(DEFAULT_SETTINGS)
        # 原地更新：呼叫端（圖形介面）持有 self.data 的參考，不可重新綁定，
        # 否則介面改到的設定不會被存檔。
        self.data.clear()
        self.data.update(data)
        return self.data

    def save(self):
        try:
            folder = os.path.dirname(self.path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            with open(self.path, 'w', encoding='utf-8') as fh:
                json.dump(self.data, fh, ensure_ascii=False, indent=2)
            return True
        except OSError:
            return False

    def reset(self):
        self.data.clear()
        self.data.update(DEFAULT_SETTINGS)


def apply_look(root, style, texts, cfg, geometry=False):
    """把設定套到「已經建好」的介面上，可重複呼叫以支援即時預覽。"""
    try:
        theme = cfg.get('theme')
        if theme in style.theme_names():
            style.theme_use(theme)
    except Exception:
        pass

    try:
        style.configure('.', font=(cfg.get('ui_font'), cfg.get('ui_font_size')))
    except Exception:
        pass

    font = (cfg.get('out_font'), cfg.get('out_font_size'))
    wrap = 'word' if cfg.get('wrap_output') else 'none'
    for text in texts:
        try:
            text.configure(font=font, bg=cfg.get('text_bg'),
                           fg=cfg.get('text_fg'), wrap=wrap)
        except Exception:
            pass

    if geometry:
        try:
            root.geometry('{}x{}'.format(cfg.get('win_width'), cfg.get('win_height')))
        except Exception:
            pass


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
    """sxtwl 是選用依賴，只影響 bazi.py -b 的「可能出生時間」提示。"""
    try:
        import importlib.util
        return importlib.util.find_spec('sxtwl') is not None
    except Exception:
        return False


def run_script_globals(script, args):
    """執行原腳本並同時回傳 stdout 與 runpy 的 globals 字典。

    runpy.run_path() 會回傳該次執行後的模層命名空間，所以就算 bazi.py 是
    「模組層級就跑」的程式，圖表功能還是能直接讀到 scores / yun / ten_deities
    等計算結果，不必去解析它印出來的文字。

    回傳 (stdout文字, globals)。腳本自己 sys.exit() 就當作正常結束
    （bazi.py -b 檢查失敗時會印訊息後 exit(1)，那種情況 globals 可能不完整）。
    """
    path = os.path.join(BASE, script)
    if not os.path.isfile(path):
        return '找不到 {}，請確認檔案是否完整。'.format(script), {}

    buf = io.StringIO()
    old_argv = sys.argv
    namespace = {}
    try:
        sys.argv = [script] + [str(item) for item in args]
        with contextlib.redirect_stdout(buf):
            namespace = runpy.run_path(path, run_name='__main__') or {}
    except SystemExit:
        pass  # bazi.py 檢查失敗會走這裡，訊息已經在 buf 裡
    except Exception:
        buf.write('\n[發生錯誤]\n')
        buf.write(traceback.format_exc())
    finally:
        sys.argv = old_argv

    return ANSI_RE.sub('', buf.getvalue()), namespace


def run_script(script, args, strip_ansi=True, propagate=False):
    """以 runpy 執行原腳本並擷取 stdout。

    這些腳本都是「模組層級就跑」的程式，無法 import 後呼叫函式，
    因此用 runpy 給它們一個乾淨的命名空間與自訂 argv。

    propagate=True 時會把腳本的結束碼往外傳（命令列透傳模式用）；
    圖形介面則維持 False，讓錯誤訊息留在輸出框裡而不是關掉視窗。
    """
    path = os.path.join(BASE, script)
    if not os.path.isfile(path):
        return '找不到 {}，請確認檔案是否完整。'.format(script)

    buf = io.StringIO()
    old_argv = sys.argv
    exit_code = 0
    try:
        sys.argv = [script] + [str(item) for item in args]
        with contextlib.redirect_stdout(buf):
            runpy.run_path(path, run_name='__main__')
    except SystemExit as exc:
        # argparse 的 --help / 參數錯誤，以及 bazi.py -b 的干支檢查都走這裡。
        code = exc.code
        if isinstance(code, int):
            exit_code = code
        elif code is not None:
            exit_code = 1
    except Exception:
        exit_code = 1
        buf.write('\n[發生錯誤]\n')
        buf.write(traceback.format_exc())
    finally:
        sys.argv = old_argv

    out = buf.getvalue()
    if strip_ansi:
        out = ANSI_RE.sub('', out)

    if propagate and exit_code:
        # 內容必須在這裡自己寫出去：redirect_stdout 的目標是 buf，
        # 若直接 raise，錯誤訊息（例如 bazi.py -b 的干支檢查）會跟著被吃掉。
        if out:
            sys.stdout.write(out)
            sys.stdout.flush()
        raise SystemExit(exit_code)

    return out


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

def build_gui(settings=None):
    import tkinter as tk
    from tkinter import colorchooser, filedialog, font as tkfont, messagebox, ttk

    settings = settings if settings is not None else Settings()
    cfg = settings.data

    root = tk.Tk()
    root.title('{} v{}'.format(APP_NAME, APP_VERSION))
    root.geometry('{}x{}'.format(cfg['win_width'], cfg['win_height']))
    root.minsize(860, 600)

    sxtwl_ok = has_sxtwl()
    style = ttk.Style()
    texts = []          # 所有輸出 Text，登記給管理員面板做即時改樣式

    nb = ttk.Notebook(root)
    nb.pack(fill='both', expand=True, padx=8, pady=(8, 0))

    def make_output(parent):
        frame = ttk.Frame(parent)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        text = tk.Text(frame, wrap='none',
                       font=(cfg['out_font'], cfg['out_font_size']),
                       bg=cfg['text_bg'], fg=cfg['text_fg'],
                       undo=True, tabs=('40c',))
        texts.append(text)
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
        path = filedialog.asksaveasfilename(
            parent=root,
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

    # ---------------- 分頁 2：直接輸入八字 ----------------
    tab2 = ttk.Frame(nb, padding=8)
    nb.add(tab2, text='  直接輸入八字  ')

    bar2 = ttk.LabelFrame(tab2, text='四柱（例：丁巳 己酉 癸未 壬戌）', padding=8)
    bar2.pack(fill='x')
    var_pillar = tk.StringVar(value='丁巳 己酉 癸未 壬戌')
    ttk.Entry(bar2, textvariable=var_pillar).pack(side='left', fill='x',
                                                  expand=True, padx=(0, 8))
    out2, text2 = make_output(tab2)
    out2.pack(fill='both', expand=True, pady=8)
    add_buttons(tab2, text2)

    def do_pillar():
        parts = var_pillar.get().split()
        if len(parts) != 4 or any(len(p) != 2 for p in parts):
            messagebox.showwarning(
                APP_NAME, '請輸入四組兩字柱，例：丁巳 己酉 癸未 壬戌')
            return
        show(text2, run_script('bazi.py', ['-b'] + parts))

    ttk.Button(bar2, text='排　盤', command=do_pillar).pack(
        side='left', ipadx=14, ipady=4)

    # ---------------- 分頁 3：大運流年圖表 ----------------
    #
    # 這頁的資料來源不是文字排盤，而是 runpy 回傳的 bazi.py globals
    # （見 run_script_globals），所以圖上的分數與文字排盤是同一套算法。
    tab3 = ttk.Frame(nb, padding=8)
    nb.add(tab3, text='  大運流年圖表  ')

    chart_state = {'data': None, 'photo': None, 'kind': None, 'sig': None}

    def chart_error(message):
        messagebox.showwarning(APP_NAME, message)
        var_chart_status.set('畫圖失敗')

    def do_chart(force=False):
        """把分頁 1 的出生資料畫成圖。

        `force=False` 且已經算過同一份資料時，只重畫不同種類的圖，
        不重跑 bazi.py —— 切換 radio 不必等一次排盤。

        缺 matplotlib 時只提示不安裝，不影響其他分頁。
        """
        try:
            import chart
        except ImportError as exc:
            chart_error('找不到 chart.py 或 matplotlib：\n{}\n\n'
                        '圖表功能需要 matplotlib，其他功能不受影響。'.format(exc))
            return

        args = [entries[key].get().strip() for key in
                ('year', 'month', 'day', 'time')]
        if any(not a for a in args):
            chart_error('出生年、月、日、時都要填。')
            return
        flags = []
        if var_solar.get():
            flags.append('-g')
        if var_leap.get():
            flags.append('-r')
        if var_female.get():
            flags.append('-n')

        kind = var_chart_kind.get()
        signature = (tuple(args), tuple(flags))
        data = chart_state['data']
        if data is not None and not force and chart_state['sig'] == signature:
            var_chart_status.set('重畫中…')
            root.update_idletasks()
        else:
            try:
                var_chart_status.set('計算中…')
                root.update_idletasks()
                _out, namespace = run_script_globals('bazi.py', args + flags)
                data = chart.collect(namespace)
            except chart.ChartError as exc:
                chart_error(str(exc))
                return
            except Exception as exc:
                chart_error('畫圖時發生錯誤：\n{}: {}'.format(
                    type(exc).__name__, exc))
                return

        # matplotlib.use() 必須在 pyplot 被 import 之前呼叫，
        # 否則 backend 已經定死，這行只是看起來沒事而已。
        # chart.png_bytes() 內部會 import pyplot，所以要擺在它前面。
        import matplotlib
        matplotlib.use('Agg', force=True)
        import matplotlib.pyplot as plt
        plt.close('all')

        try:
            blob = chart.png_bytes(kind, data)
        except Exception as exc:
            chart_error('畫圖時發生錯誤：\n{}: {}'.format(
                type(exc).__name__, exc))
            return

        try:
            from PIL import Image, ImageTk
        except ImportError:
            Image = ImageTk = None

        if Image is not None:
            photo = ImageTk.PhotoImage(Image.open(io.BytesIO(blob)))
        else:
            # 沒有 Pillow 就退回 Tk 自己解 PNG。tk.PhotoImage 只吃 bytes，
            # 傳 BytesIO 會在執行期才丟 TclError。
            photo = tk.PhotoImage(data=blob)

        chart_state['photo'] = photo   # 留住參考，否則 GC 會讓圖片變空白
        chart_state['data'] = data
        chart_state['kind'] = kind
        chart_state['sig'] = signature

        chart_canvas.delete('all')
        chart_label.configure(image=photo)
        chart_canvas.create_window(0, 0, window=chart_label, anchor='nw')
        chart_canvas.configure(scrollregion=chart_canvas.bbox('all'))
        chart_meta.set('{}　{}　日主 {}　本命強 {}{}　{} - {}（{} 個流年）'.format(
            dict(chart.KINDS)[kind], data['gans'] + ' ' + data['zhis'],
            data['me'], data['strong_base'],
            '　強根無' if data['weak_base'] else '　強根有',
            data['years'][0]['year'],
            data['years'][-1]['year'], len(data['years'])))
        var_chart_status.set('畫好了')
        btn_save.configure(state='normal')

    def save_chart():
        if not chart_state['data']:
            messagebox.showinfo(APP_NAME, '請先按「畫　圖」。')
            return
        try:
            import chart
        except ImportError:
            chart_error('找不到 chart.py。')
            return
        suggested = '大運流年_{}_{}.png'.format(
            chart_state['data']['years'][0]['year'],
            dict(chart.KINDS).get(chart_state['kind'], 'chart'))
        path = filedialog.asksaveasfilename(
            parent=root, title='存成 PNG', defaultextension='.png',
            initialfile=suggested, filetypes=[('PNG 圖檔', '*.png')])
        if not path:
            return
        try:
            size = chart.save(chart_state['kind'], chart_state['data'], path)
        except Exception as exc:
            chart_error('存檔失敗：\n{}: {}'.format(type(exc).__name__, exc))
            return
        messagebox.showinfo(APP_NAME, '已存到：\n{}\n（{} KB）'.format(
            path, size // 1024))

    top3 = ttk.LabelFrame(tab3, text='出生資料（沿用「八字排盤」分頁的填寫）',
                          padding=8)
    top3.pack(fill='x')
    ttk.Label(top3, text='按下「畫　圖」會依上面出生日期排出大運與流年走勢。'
              ).pack(side='left')
    ttk.Button(top3, text='畫　圖', command=lambda: do_chart(force=True)).pack(
        side='right', ipadx=14, ipady=4)

    picks = ttk.LabelFrame(tab3, text='圖表種類', padding=8)
    picks.pack(fill='x', pady=(8, 0))

    try:
        import chart as _chart_probe
        chart_kinds = list(_chart_probe.KINDS)
        chart_font = _chart_probe.available_cjk_font()
    except Exception:
        chart_kinds = [('wuxing', '五行分數走勢')]
        chart_font = None

    var_chart_kind = tk.StringVar(value=chart_kinds[0][0])
    for idx, (kind_key, kind_label) in enumerate(chart_kinds):
        # command= 換圖種就重畫；已經算過的資料直接重用，不必再排一次盤。
        # 還沒畫過圖時按 radio 不動作，避免一進來就跳錯誤框。
        ttk.Radiobutton(
            picks, text=kind_label, value=kind_key,
            variable=var_chart_kind,
            command=lambda: do_chart() if chart_state['data'] is not None
            else None).grid(row=0, column=idx, padx=(0, 18), sticky='w')

    btn_save = ttk.Button(picks, text='另存 PNG…', command=save_chart,
                          state='disabled')
    btn_save.grid(row=0, column=len(chart_kinds), padx=(12, 0), sticky='e')
    picks.columnconfigure(len(chart_kinds), weight=1)

    ttk.Label(
        picks,
        text=('大運與流年的年份來自 lunar_python 起運時間；'
              + ('找不到中文字型，圖上的中文會是方框。'
                 if chart_font is None
                 else '圖表中文字型：{}。'.format(chart_font))),
        foreground='#555555').grid(row=1, column=0, columnspan=len(chart_kinds) + 1,
                                   sticky='w', pady=(6, 0))

    holder = ttk.Frame(tab3)
    holder.pack(fill='both', expand=True, pady=8)
    holder.rowconfigure(0, weight=1)
    holder.columnconfigure(0, weight=1)

    # 90 年的圖寬可到 1000px 以上，而視窗最小 860px，沒有捲軸會直接被裁掉。
    chart_canvas = tk.Canvas(holder, highlightthickness=0, bd=0,
                             background='#ffffff')
    chart_vsb = ttk.Scrollbar(holder, orient='vertical',
                              command=chart_canvas.yview)
    chart_hsb = ttk.Scrollbar(holder, orient='horizontal',
                              command=chart_canvas.xview)
    chart_canvas.configure(yscrollcommand=chart_vsb.set,
                           xscrollcommand=chart_hsb.set)
    chart_canvas.grid(row=0, column=0, sticky='nsew')
    chart_vsb.grid(row=0, column=1, sticky='ns')
    chart_hsb.grid(row=1, column=0, sticky='ew')
    chart_canvas.create_text(300, 120, text='按「畫　圖」產生走勢圖',
                             fill='#777777', anchor='center',
                             font=(None, 10))

    # Label 只建一次。反覆建立新的會在 canvas 上留下看不到但仍存活的
    # widget（canvas.delete('all') 只刪 canvas 項目，不會銷毀 widget）。
    chart_label = ttk.Label(chart_canvas)

    def _scroll_chart(event):
        """滑鼠滾輪捲圖。Canvas 不像 Text 會自己綁，需要自己接。"""
        if event.num == 4 or getattr(event, 'delta', 0) > 0:
            chart_canvas.yview_scroll(-1, 'units')
        elif event.num == 5 or getattr(event, 'delta', 0) < 0:
            chart_canvas.yview_scroll(1, 'units')

    chart_canvas.bind('<MouseWheel>', _scroll_chart)
    chart_canvas.bind('<Button-4>', _scroll_chart)
    chart_canvas.bind('<Button-5>', _scroll_chart)

    foot3 = ttk.Frame(tab3)
    foot3.pack(fill='x')
    var_chart_status = tk.StringVar(value='尚未畫圖')
    chart_meta = tk.StringVar(value='')
    ttk.Label(foot3, textvariable=var_chart_status,
              foreground='#666666').pack(side='left')
    ttk.Label(foot3, textvariable=chart_meta,
              foreground='#666666').pack(side='right')

    # ---------------- 分頁 4：盲派暗局做功 ----------------
    #
    # 這頁跑 mangpai.py，輸入格式刻意跟「直接輸入八字」一致（四柱），
    # 另外提供出生日期，讓第六步能排大運流年——因為沒有出生日期就沒有
    # 起運年份，第六步只能列大運干支。
    tab4 = ttk.Frame(nb, padding=8)
    nb.add(tab4, text='  盲派暗局做功  ')

    top4 = ttk.LabelFrame(tab4, text='輸入（擇一）', padding=8)
    top4.pack(fill='x')

    var_mp_pillar = tk.StringVar(value='丁巳 己酉 癸未 壬戌')
    var_mp_year = tk.StringVar(value='1977')
    var_mp_month = tk.StringVar(value='8')
    var_mp_day = tk.StringVar(value='11')
    var_mp_time = tk.StringVar(value='19')
    var_mp_solar = tk.BooleanVar(value=False)
    var_mp_leap = tk.BooleanVar(value=False)
    var_mp_female = tk.BooleanVar(value=False)
    var_mp_no_xiang = tk.BooleanVar(value=False)
    var_mp_year_only = tk.StringVar(value='')

    out4, text4 = make_output(tab4)
    out4.pack(fill='both', expand=True, pady=8)
    add_buttons(tab4, text4)

    def _mp_extra_flags():
        flags = []
        if var_mp_female.get():
            flags.append('-n')
        if var_mp_no_xiang.get():
            flags.append('--不印類象')
        year = var_mp_year_only.get().strip()
        if year:
            if not year.isdigit() or len(year) != 4:
                raise ValueError('「只看某年」請填四位西元年，例如 2030。')
            flags += ['--年', year]
        return flags

    def do_mp_pillar():
        try:
            parts = var_mp_pillar.get().split()
            if len(parts) != 4 or any(len(p) != 2 for p in parts):
                messagebox.showwarning(
                    APP_NAME, '請輸入四組兩字柱，例：丁巳 己酉 癸未 壬戌')
                return
            # -b 沒有出生日期就沒有起運年份，第六步無從排流年，
            # 所以「只看某年」在這個模式沒有作用，直接擋掉而不是靜默忽略。
            if var_mp_year_only.get().strip():
                messagebox.showwarning(
                    APP_NAME, '「只看某年」需要出生日期才能排出大運起點，'
                              '請改用「以日期分析」。')
                return
            show(text4, run_script('mangpai.py', ['-b'] + parts + _mp_extra_flags()))
        except ValueError as exc:
            messagebox.showwarning(APP_NAME, str(exc))
        except Exception:
            show(text4, traceback.format_exc())

    def do_mp_date():
        try:
            args = [var_mp_year.get().strip(), var_mp_month.get().strip(),
                    var_mp_day.get().strip(), var_mp_time.get().strip()]
            if not all(a.isdigit() for a in args):
                messagebox.showwarning(APP_NAME, '年、月、日、時請填整數數字。')
                return
            flags = _mp_extra_flags()
            if var_mp_solar.get():
                flags.append('-g')
            elif var_mp_leap.get():
                # -r 只對農曆有意義，勾了公曆就當沒勾，避免送出矛盾引數。
                flags.append('-r')
            show(text4, run_script('mangpai.py', args + flags))
        except ValueError as exc:
            messagebox.showwarning(APP_NAME, str(exc))
        except Exception:
            show(text4, traceback.format_exc())

    row_a = ttk.Frame(top4)
    row_a.pack(fill='x')
    ttk.Label(row_a, text='四柱').pack(side='left', padx=(0, 6))
    ttk.Entry(row_a, textvariable=var_mp_pillar).pack(
        side='left', fill='x', expand=True, padx=(0, 12))
    ttk.Button(row_a, text='以四柱分析', command=do_mp_pillar).pack(
        side='left', ipadx=14, ipady=4)

    row_b = ttk.Frame(top4)
    row_b.pack(fill='x', pady=(8, 0))
    ttk.Label(row_b, text='出生年').pack(side='left', padx=(0, 4))
    ttk.Entry(row_b, textvariable=var_mp_year, width=8).pack(side='left', padx=(0, 12))
    ttk.Label(row_b, text='月').pack(side='left', padx=(0, 4))
    ttk.Entry(row_b, textvariable=var_mp_month, width=6).pack(side='left', padx=(0, 12))
    ttk.Label(row_b, text='日').pack(side='left', padx=(0, 4))
    ttk.Entry(row_b, textvariable=var_mp_day, width=6).pack(side='left', padx=(0, 12))
    ttk.Label(row_b, text='時 0-23').pack(side='left', padx=(0, 4))
    ttk.Entry(row_b, textvariable=var_mp_time, width=6).pack(side='left', padx=(0, 16))
    ttk.Button(row_b, text='以日期分析', command=do_mp_date).pack(
        side='left', ipadx=14, ipady=4)

    chk4 = ttk.Frame(top4)
    chk4.pack(fill='x', pady=(8, 0))
    ttk.Checkbutton(chk4, text='公曆（不加則為農曆）',
                     variable=var_mp_solar).pack(side='left')
    ttk.Checkbutton(chk4, text='閏月（僅農曆）',
                     variable=var_mp_leap).pack(side='left', padx=(16, 0))
    ttk.Checkbutton(chk4, text='女命', variable=var_mp_female).pack(
        side='left', padx=(16, 0))
    ttk.Checkbutton(chk4, text='不印類象（只留理法與歲運）',
                    variable=var_mp_no_xiang).pack(side='left', padx=(16, 0))
    ttk.Label(chk4, text='只看某年（留空＝全排）：',
              foreground='#555555').pack(side='left', padx=(24, 4))
    ttk.Entry(chk4, textvariable=var_mp_year_only, width=8).pack(side='left')

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

    # ---------------- 分頁 6：管理員設定 ----------------
    tab6 = ttk.Frame(nb, padding=8)
    nb.add(tab6, text='  管理員設定  ')

    installed = set(tkfont.families(root))
    preferred = [f for f in MONO_FONTS + UI_FONTS if f in installed]
    others = sorted(f for f in installed
                    if f not in MONO_FONTS and f not in UI_FONTS)
    font_choices = preferred + others

    var_theme = tk.StringVar(value=cfg['theme'])
    var_ui_font = tk.StringVar(value=cfg['ui_font'])
    var_ui_size = tk.StringVar(value=str(cfg['ui_font_size']))
    var_out_font = tk.StringVar(value=cfg['out_font'])
    var_out_size = tk.StringVar(value=str(cfg['out_font_size']))
    var_wrap = tk.BooleanVar(value=bool(cfg['wrap_output']))
    var_bg = tk.StringVar(value=cfg['text_bg'])
    var_fg = tk.StringVar(value=cfg['text_fg'])
    var_width = tk.StringVar(value=str(cfg['win_width']))
    var_height = tk.StringVar(value=str(cfg['win_height']))
    var_status = tk.StringVar(value='設定檔：{}'.format(settings.path))

    def collect(include_geometry=False):
        cfg['theme'] = var_theme.get() or cfg['theme']
        cfg['ui_font'] = var_ui_font.get().strip() or cfg['ui_font']
        cfg['ui_font_size'] = _clamp(var_ui_size.get(),
                                     INT_RANGES['ui_font_size'],
                                     cfg['ui_font_size'])
        cfg['out_font'] = var_out_font.get().strip() or cfg['out_font']
        cfg['out_font_size'] = _clamp(var_out_size.get(),
                                      INT_RANGES['out_font_size'],
                                      cfg['out_font_size'])
        cfg['wrap_output'] = bool(var_wrap.get())
        cfg['text_bg'] = var_bg.get().strip() or cfg['text_bg']
        cfg['text_fg'] = var_fg.get().strip() or cfg['text_fg']
        if include_geometry:
            cfg['win_width'] = _clamp(var_width.get(),
                                      INT_RANGES['win_width'], cfg['win_width'])
            cfg['win_height'] = _clamp(var_height.get(),
                                       INT_RANGES['win_height'], cfg['win_height'])

    # refresh_vars() 會逐項設定變數，而每設定一次就觸發 trace -> collect()。
    # collect() 讀的是「還沒被更新的舊變數值」，再寫回 cfg，會把剛還原的
    # 設定覆蓋掉（於是「還原預設值」會立刻失效）。更新期間必須暫停即時套用。
    busy = [False]

    def live_apply(*_):
        """改任何項目都即時套用，方便直接切到排盤分頁看效果。"""
        if busy[0]:
            return
        collect()
        apply_look(root, style, texts, cfg)

    # 用 StringVar 的 trace 觸發，而不是 <KeyRelease> 之類的事件綁定：
    # 打字、上下箭頭、貼上、程式設定值都會一併生效，
    # 而且 ttk 元件的按鍵事件在測試與部分環境下不會觸發。
    for var in (var_theme, var_ui_font, var_ui_size, var_out_font,
                var_out_size, var_bg, var_fg, var_wrap, var_width, var_height):
        var.trace_add('write', lambda *_: live_apply())

    look = ttk.LabelFrame(tab6, text='外觀', padding=10)
    look.pack(fill='x', pady=(0, 8))

    ttk.Label(look, text='佈景主題').grid(row=0, column=0, sticky='w', pady=4)
    cb_theme = ttk.Combobox(look, textvariable=var_theme,
                            values=style.theme_names(), state='readonly', width=28)
    cb_theme.grid(row=0, column=1, sticky='w', padx=(10, 0))
    ttk.Label(look, text='介面字體').grid(row=1, column=0, sticky='w', pady=4)
    cb_ui_font = ttk.Combobox(look, textvariable=var_ui_font, values=font_choices,
                              width=28)
    cb_ui_font.grid(row=1, column=1, sticky='w', padx=(10, 0))
    ttk.Label(look, text='介面字級').grid(row=2, column=0, sticky='w', pady=4)
    sp_ui = ttk.Spinbox(look, textvariable=var_ui_size, width=8,
                         from_=INT_RANGES['ui_font_size'][0],
                         to=INT_RANGES['ui_font_size'][1])
    sp_ui.grid(row=2, column=1, sticky='w', padx=(10, 0))
    ttk.Label(look, text='輸出字體').grid(row=3, column=0, sticky='w', pady=4)
    cb_out_font = ttk.Combobox(look, textvariable=var_out_font,
                               values=font_choices, width=28)
    cb_out_font.grid(row=3, column=1, sticky='w', padx=(10, 0))
    ttk.Label(look, text='輸出字級').grid(row=4, column=0, sticky='w', pady=4)
    sp_out = ttk.Spinbox(look, textvariable=var_out_size, width=8,
                         from_=INT_RANGES['out_font_size'][0],
                         to=INT_RANGES['out_font_size'][1])
    sp_out.grid(row=4, column=1, sticky='w', padx=(10, 0))
    ttk.Label(look, text='長輸出自動換行').grid(row=5, column=0, sticky='w', pady=4)
    ttk.Checkbutton(look, text='超過視窗寬度時折行（取消則用捲軸）',
                    variable=var_wrap, command=live_apply).grid(
        row=5, column=1, sticky='w', padx=(10, 0))

    swatches = []

    def color_row(row, label, var):
        ttk.Label(look, text=label).grid(row=row, column=0, sticky='w', pady=4)
        btn = tk.Button(look, width=26, relief='sunken', borderwidth=2)
        btn.grid(row=row, column=1, sticky='w', padx=(10, 0))
        swatches.append((var, btn))
        btn.configure(command=lambda v=var: pick_color(v))
        try:
            btn.configure(bg=var.get())
        except Exception:
            pass

    def pick_color(var):
        chosen = colorchooser.askcolor(color=var.get(), parent=tab6)[1]
        if chosen:
            var.set(chosen)
            for target, btn in swatches:
                if target is var:
                    try:
                        btn.configure(bg=chosen)
                    except Exception:
                        pass
            live_apply()

    color_row(6, '輸出背景色', var_bg)
    color_row(7, '輸出行色', var_fg)

    win = ttk.LabelFrame(tab6, text='視窗大小', padding=10)
    win.pack(fill='x', pady=(0, 8))

    ttk.Label(win, text='寬度').grid(row=0, column=0, sticky='w', pady=4)
    sp_w = ttk.Spinbox(win, textvariable=var_width, width=8,
                       from_=INT_RANGES['win_width'][0],
                       to=INT_RANGES['win_width'][1])
    sp_w.grid(row=0, column=1, sticky='w', padx=(10, 0))

    ttk.Label(win, text='高度').grid(row=0, column=2, sticky='w', padx=(20, 4))
    sp_h = ttk.Spinbox(win, textvariable=var_height, width=8,
                       from_=INT_RANGES['win_height'][0],
                       to=INT_RANGES['win_height'][1])
    sp_h.grid(row=0, column=3, sticky='w', padx=(10, 0))
    ttk.Label(win, text='（按「套用並儲存」後生效）',
              foreground='#666666').grid(row=0, column=4, sticky='w', padx=(12, 0))

    def refresh_vars():
        busy[0] = True
        try:
            var_theme.set(cfg['theme'])
            var_ui_font.set(cfg['ui_font'])
            var_ui_size.set(str(cfg['ui_font_size']))
            var_out_font.set(cfg['out_font'])
            var_out_size.set(str(cfg['out_font_size']))
            var_wrap.set(bool(cfg['wrap_output']))
            var_bg.set(cfg['text_bg'])
            var_fg.set(cfg['text_fg'])
            var_width.set(str(cfg['win_width']))
            var_height.set(str(cfg['win_height']))
        finally:
            busy[0] = False
        for var, btn in swatches:
            try:
                btn.configure(bg=var.get())
            except Exception:
                pass

    def do_save(*_):
        collect(include_geometry=True)
        apply_look(root, style, texts, cfg, geometry=True)
        ok = settings.save()
        var_status.set('{}：{}'.format('已儲存' if ok else '儲存失敗',
                                       settings.path))

    def do_reset():
        settings.reset()
        refresh_vars()
        apply_look(root, style, texts, cfg, geometry=True)
        settings.save()
        var_status.set('已還原預設值：{}'.format(settings.path))

    def do_reload():
        settings.load()
        refresh_vars()
        apply_look(root, style, texts, cfg, geometry=True)
        var_status.set('已重新載入：{}'.format(settings.path))

    def open_folder():
        folder = os.path.dirname(settings.path)
        if os.path.isdir(folder):
            os.startfile(folder)

    bar6 = ttk.Frame(tab6)
    bar6.pack(fill='x')
    ttk.Button(bar6, text='套用並儲存', command=do_save).pack(side='left')
    ttk.Button(bar6, text='還原預設值', command=do_reset).pack(side='left', padx=6)
    ttk.Button(bar6, text='重新載入', command=do_reload).pack(side='left')
    ttk.Button(bar6, text='開啟設定檔位置', command=open_folder).pack(
        side='left', padx=6)

    ttk.Label(tab6, textvariable=var_status, foreground='#666666').pack(
        anchor='w', pady=(10, 0))
    ttk.Label(
        tab6, foreground='#8a5a00',
        text='注意：排盤靠全形空格與固定欄寬對齊，'
             '輸出字體請使用等寬中文字型'
             '（新宋體／細明體／DFKai-SB），換成微軟正黑體等比例字型會讓欄位跑掉。'
    ).pack(anchor='w', pady=(4, 0))
    ttk.Label(
        tab6, foreground='#666666',
        text='提示：改完可切到「八字排盤」分頁看排盤對齊情況；'
             '視窗大小按「套用並儲存」才會套用。'
    ).pack(anchor='w')

    # ---------------- 選單列 ----------------
    menubar = tk.Menu(root)

    def go(idx):
        nb.select(idx)

    m_file = tk.Menu(menubar, tearoff=0)
    m_file.add_command(label='關閉', command=root.destroy)
    menubar.add_cascade(label='檔案', menu=m_file)

    m_fun = tk.Menu(menubar, tearoff=0)
    m_fun.add_command(label='八字排盤', command=lambda: go(0))
    m_fun.add_command(label='直接輸入八字', command=lambda: go(1))
    m_fun.add_command(label='大運流年圖表', command=lambda: go(2))
    m_fun.add_command(label='盲派暗局做功', command=lambda: go(3))
    m_fun.add_command(label='命令列模式', command=lambda: go(4))
    m_fun.add_separator()
    m_fun.add_command(label='管理員設定', command=lambda: go(5))
    menubar.add_cascade(label='功能', menu=m_fun)

    m_help = tk.Menu(menubar, tearoff=0)
    m_help.add_command(label='開啟設定檔位置', command=open_folder)
    m_help.add_command(label='還原介面設定', command=do_reset)
    m_help.add_separator()
    m_help.add_command(label='關於', command=lambda: messagebox.showinfo(
        APP_NAME,
        '{} v{}\n\n依賴：bidict、lunar_python、colorama\n'
        '圖表：matplotlib（{}），只影響「大運流年圖表」分頁\n'
        '（選用）sxtwl：{}，只影響「可能出生時間」提示\n\n'
        '排盤邏輯沿用原腳本。'.format(
            APP_NAME, APP_VERSION,
            chart_font or '未安裝', '已安裝' if sxtwl_ok else '未安裝')))
    menubar.add_cascade(label='說明', menu=m_help)
    root.config(menu=menubar)

    # ---------------- 狀態列 ----------------
    status = ttk.Label(
        root, anchor='w', padding=(10, 4),
        text='就緒　|　sxtwl：{}（選用，僅影響「可能出生時間」提示）'.format(
            '已安裝' if sxtwl_ok else '未安裝'))
    status.pack(fill='x', side='bottom')

    # 最後統一套一次外觀，確保自訂主題／字體／大小都生效
    apply_look(root, style, texts, cfg, geometry=True)

    return root


# --------------------------------------------------------------------------
# 命令列介面
# --------------------------------------------------------------------------

def main_cli():
    force_utf8()
    print('=' * 60)
    print('  {} v{}  —  命令列模式'.format(APP_NAME, APP_VERSION))
    print('=' * 60)

    while True:
        print()
        print('-' * 60)
        print('  1) 八字排盤')
        print('  2) 直接輸入八字')
        print('  3) 盲派暗局做功')
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
            pillars = ask('四柱（例：丁巳 己酉 癸未 壬戌）：').split()
            if len(pillars) != 4 or any(len(p) != 2 for p in pillars):
                print('請輸入四組兩字柱。')
                continue
            print(run_script('bazi.py', ['-b'] + pillars, strip_ansi=False))

        elif choice == '3':
            mode = ask('輸入方式：1 四柱　2 出生日期（直接按 Enter＝1）：')
            flags = []
            if ask('是否女命？y/N：').lower().startswith('y'):
                flags.append('-n')
            if ask('不印類象？y/N：').lower().startswith('y'):
                flags.append('--不印類象')
            year = ask('只看某年（留空＝全排）：')
            if year and mode != '2':
                print('「只看某年」需要出生日期才能排出大運起點，已略過。')
            elif year:
                flags += ['--年', year]
            if mode == '2':
                parts = [ask('出生年　　：'), ask('出生月　　：'),
                         ask('出生日　　：'), ask('出生時 0-23：')]
                if not all(p.isdigit() for p in parts):
                    print('請填整數數字。')
                    continue
                if ask('是否公曆？y/N：').lower().startswith('y'):
                    flags.append('-g')
                elif ask('是否閏月？y/N：').lower().startswith('y'):
                    flags.append('-r')
                print(run_script('mangpai.py', parts + flags, strip_ansi=False))
            else:
                pillars = ask('四柱（例：丁巳 己酉 癸未 壬戌）：').split()
                if len(pillars) != 4 or any(len(p) != 2 for p in pillars):
                    print('請輸入四組兩字柱。')
                    continue
                print(run_script('mangpai.py', ['-b'] + pillars + flags,
                                 strip_ansi=False))

        else:
            print('輸入的選項不正確，請重新選擇。')


def chart_selftest(argv):
    """--chart-selftest：不開 Tk，直接驗證圖表能否產出 PNG。

    這是給打包後的環境用的：onefile 內如果漏了 matplotlib 的 backend 或
    資料檔，GUI 分頁只會跳一個警告視窗，很容易被當成沒反應而漏掉。
    用法：
        app.py --chart-selftest                 測預設命盤三種圖
        app.py --chart-selftest -b 丁巳 己酉...  測直接輸入八字（應明確拒絕）
        app.py --chart-selftest --out dir       順便把 PNG 存到 dir
    """
    try:
        import matplotlib
        import chart
    except ImportError as exc:
        print('缺少圖表依賴：{}'.format(exc))
        return 2

    matplotlib.use('Agg', force=True)
    rest = [a for a in argv if a != '--chart-selftest']
    out_dir = None
    if '--out' in rest:
        idx = rest.index('--out')
        rest = rest[:idx] + rest[idx + 2:]
        out_dir = argv[argv.index('--out') + 1] if '--out' in argv else None

    print('matplotlib {}　中文字型 {}'.format(
        matplotlib.__version__, chart.available_cjk_font() or '（找不到）'))

    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    if '-b' in rest:
        args = ['-b'] + [a for a in rest if not a.startswith('-')]
    elif rest:
        args = rest
    else:
        args = ['1977', '8', '11', '19', '-n']

    _out, namespace = run_script_globals('bazi.py', args)
    try:
        data = chart.collect(namespace)
    except chart.ChartError as exc:
        # -b 模式被擋下是預期行為，這裡視為成功
        if '-b' in args:
            print('已正確拒絕 -b 模式：{}'.format(exc))
            return 0
        print('無法產生圖表資料：{}'.format(exc))
        return 1

    print('{}　{} / {}　本命強 {}'.format(
        data['gans'], data['zhis'], data['me'], data['strong_base']))
    failed = 0
    for kind, label in chart.KINDS:
        try:
            blob = chart.png_bytes(kind, data)
            ok = blob[:4] == b'\x89PNG' and len(blob) > 8000
            print('  {} {} bytes {}'.format(
                label, len(blob), 'OK' if ok else '*** 不是有效 PNG ***'))
            if not ok:
                failed += 1
            if out_dir:
                path = os.path.join(out_dir, '{}.png'.format(kind))
                chart.save(kind, data, path)
                print('      -> {}'.format(path))
        except Exception as exc:
            print('  {} *** 失敗：{}: {}'.format(
                label, type(exc).__name__, exc))
            failed += 1
    import matplotlib.pyplot as plt
    plt.close('all')
    return 1 if failed else 0


def main():
    argv = sys.argv[1:]
    our_flags = {'--cli', '--show-console', '--version', '--reset-settings',
                 '--chart-selftest', '--out', '-h', '--help'}

    # 介面被設成無法顯示時的安全出口：不必開視窗就能還原預設值
    if '--reset-settings' in argv:
        force_utf8()
        settings = Settings()
        settings.reset()
        settings.save()
        print('已還原介面設定：' + settings.path)
        return 0

    # 圖表自我檢查：打包後 matplotlib 若漏 backend／字型資料，
    # GUI 分頁只會跳視窗不易察覺，所以提供一個不開 Tk 的驗證入口。
    if '--chart-selftest' in argv:
        force_utf8()
        return chart_selftest(argv)

    # 只要不是本程式自己的旗標，全部原樣交給 bazi.py，
    # 這樣 -g / -n / -r / -b 才能直接透傳（argparse 會吃掉 -n）。
    if argv and not any(arg in our_flags for arg in argv):
        force_utf8()
        sys.stdout.write(run_script('bazi.py', argv, strip_ansi=False,
                                   propagate=True))
        return 0

    parser = argparse.ArgumentParser(
        prog=os.path.basename(sys.argv[0]),
        description='{} v{} — 八字排盤整合程式'.format(APP_NAME, APP_VERSION))
    parser.add_argument('--cli', action='store_true',
                        help='使用命令列互動選單')
    parser.add_argument('--show-console', action='store_true',
                        help='圖形介面模式下不要隱藏主控台視窗')
    parser.add_argument('--reset-settings', action='store_true',
                        help='把介面設定還原成預設值後結束（介面壞掉時使用）')
    parser.add_argument('--chart-selftest', action='store_true',
                        help='不開圖形介面，直接驗證圖表能否產生 PNG')
    parser.add_argument('--version', action='version',
                        version='%(prog)s {}'.format(APP_VERSION))
    options = parser.parse_args()

    if options.cli:
        return main_cli()

    force_utf8()

    if not options.show_console:
        hide_console()

    root = build_gui(Settings())
    root.mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
