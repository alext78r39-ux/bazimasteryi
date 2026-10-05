# bazi (八字排盤) — agent notes

Pure-Python Chinese fortune-telling CLI scripts. **No package metadata, no tests, no CI, no lint/format config, no requirements.txt.** Flat directory; modules import each other by bare name, so everything must be run from this directory.

There is now an **integrated GUI launcher `app.py`** (added on top of the original scripts, which are otherwise unchanged) plus a chart module `chart.py` and a blind-school module `mangpai.py`. `app.py` has 6 tabs: 八字排盤 / 直接輸入八字 / 大運流年圖表 / 盲派暗局做功 / 命令列模式 / 管理員設定. It wraps the same commands — see "Charts", "Blind school module", and "Integrated launcher" below.

## Removed modules

`shengxiao.py` (生肖合婚) and `luohou.py` (六爻) were **deleted**; the user does not want them. Don't reintroduce them or restore their GUI tabs / CLI menu entries. `ganzhi.py`'s `shengxiaos` bidict and `datas.py`'s zodiac tables were left in place — they are data, not the removed script, and `bazi.py` may reference them.

## Commands

```bash
pip install bidict lunar_python colorama   # what README lists
pip install matplotlib                      # OPTIONAL: 大運流年圖表 tab
pip install sxtwl                           # OPTIONAL, see below

python bazi.py 1977 8 11 19 -n             # 農曆 input (default), 女命
python bazi.py -g 1977 9 23 19 -n          # 公曆 input
python bazi.py -b 丁巳 己酉 癸未 壬戌      # four pillars, no date needed
python convert.py 丁巳己酉 癸未壬戌         # shells out to `python bazi.py -b`

python app.py                               # integrated GUI (tkinter)
python app.py --cli                         # integrated console menu
python app.py 1977 8 11 19 -n               # passthrough to bazi.py
python app.py --chart-selftest              # verify charts without opening Tk
python build_exe.py                         # -> dist/BaziMaster.exe
```

Non-obvious flags:
- `bazi.py` takes **農曆** year/month/day unless `-g`. `bazi.py 1977 8 11 19` = lunar 1977-8-11 19:00 → solar 1977-9-23.
- `-b` switches to "already have the pillars" mode. The four pillars are **four separate positional args**, not one quoted string: `bazi.py -b 丁巳 己酉 癸未 壬戌`. Passing `-b "丁巳 己酉 ..."` makes argparse demand `month day time` and exit 2.
- `-n` means 女命 in `bazi.py`.
- `-r` (閏月) only applies to 農曆 input; the month is negated internally.

## Environment gotchas (verified on this machine)

- Default `sys.stdout.encoding` here is **cp950**, so `python bazi.py ...` dies with `UnicodeEncodeError` on the first CJK print. Export `PYTHONIOENCODING=utf-8` (or use `python -X utf8`) first.
- `sxtwl` is **not installed** here and cannot be built on Python 3.13. It is now a genuinely **optional** dependency: only the `siZhu2Year` "可能出生時間" back-calculation in `bazi.py -b` uses it, wrapped in `try/except ImportError`. **Do not reintroduce a hard sxtwl gate** — the whole chart is computed from the user's four pillar strings via the project's own tables (`bazi.py:146-149`, `dayuns` at `248-254`), so `-b` must keep working without it.
- `convert.py` hardcodes `.decode('gbk')` on the child's stdout. That only works on a GBK console — under `PYTHONIOENCODING=utf-8` it raises `UnicodeDecodeError`. It's Windows-only by construction (`python bazi.py`, `shell=True`).
- The enclosing git repo root is `C:\Users\Nothing User` (the user's home), **not** this project; the project is untracked there. Never run bare `git add -A` / `git commit -a` from this directory.

## Charts (`chart.py` + the 大運流年圖表 tab)

The 3rd tab renders the 大運 / 流年 series with matplotlib. Three kinds, switchable by radio: `wuxing` (五行分數走勢), `strong` (身強弱走勢), `dayun` (大運干支走勢). `chart.py` is pure — no Tk, no interactive backend, it just returns PNG bytes.

- **Data comes from `runpy.run_path()`'s returned globals, not by parsing stdout.** `run_script_globals('bazi.py', args)` returns `(stdout_text, namespace)`; `chart.collect(namespace)` then reads `yun`, `scores`, `gan_scores`, `ten_deities`, `gan5`, `zhi5`, `solar`. That's why the numbers on the chart match the text chart exactly — same tables, same weights. **Don't reimplement the scoring in the chart layer**; reuse `_add()` in `chart.py`, which mirrors `bazi.py:231-239`.
- **`chart.py` is bundled as a `datas` entry in `bazimaster.spec`, like the other scripts**, because `app.py` imports it at runtime inside a function. It is *also* a real importable module (`import chart`), so a normal `pyz` inclusion would work too; keeping it in `SCRIPTS` means one file list to maintain.
- **Renderer choice:** `Agg` backend + `ImageTk` from Pillow, then `ttk.Label.configure(image=...)`. Not `FigureCanvasTkAgg`. The matplotlib canvas backend needs a real Tk display and adds fragility under onefile; PNG bytes work headless and are needed anyway for「另存 PNG…」. **`chart_state['photo']` must be held in a dict** — a bare local `PhotoImage` gets garbage-collected and the label renders blank.
- **`matplotlib.use('Agg')` must come before anything imports `pyplot`**, including the first call into `chart.py` (`png_bytes` → `figure` → `_apply_font` → `from matplotlib import pyplot`). Calling it after `png_bytes()` looks correct but is a no-op; the backend is already latched.
- **The image goes inside a `tk.Canvas`, not directly in a `Label`.** A 90-year figure is ~1000px wide but the window minsize is 860px, so a bare `Label` silently crops it. The Canvas carries both scrollbars plus a `<MouseWheel>` binding (Canvas does not scroll on the wheel by default, unlike `Text`).
- **The image `Label` is created once and re-`configure`d, never rebuilt.** `chart_canvas.delete('all')` removes canvas *items* but does not destroy widgets parented to the canvas, so a fresh `ttk.Label(chart_canvas, image=...)` per redraw leaks one hidden widget every time. Call `root.update()` after `create_window` before reading `bbox('all')` for the scrollregion.
- **`tk.PhotoImage(data=...)` needs `bytes`, not a `BytesIO`.** The Pillow-less fallback path was passing `io.BytesIO(blob)` and would raise `TclError: couldn't recognize image data` at click time. Verified: `data=bytes` works, `data=BytesIO` always fails.
- **Scoring includes the 大運 pillar, and the per-year total is 86** = 本命 60 + 大運干支 13 + 流年干支 13. The 大運 contribution is computed once per 大運 (outside the 流年 loop) and copied, since every 流年 under it shares it.
- **Do not draw bazi.py's「中值29」as a reference line on these charts.** That string appears only in `bazi.py:308`'s print statement — there is no comparison against 29 anywhere, so it is descriptive text for the 本命 four-pillar scale, not a threshold. The charts plot 本命+大運+流年, where the same formula yields different numbers (e.g. 36/43 for the sample chart), so a line at 29 would be meaningless. The `strong` chart uses the chart's own 本命 value as the baseline instead.
- **`born_year` comes from `solar.getYear()`, never from `years[0]['year'] - 10`.** The `-10` was a guess at the 起運 offset and gave 1972 for a 1977 birth.
- **Radio buttons re-draw via `command=`, and `do_chart(force=True)` is the 畫圖 button.** `do_chart` keys the computed data on `chart_state['sig']` = (entries, flags), so switching chart kind redraws from cached data without re-running `bazi.py`; changing the birth date and pressing 畫圖 forces a recompute. The radio `command` is a no-op while `chart_state['data'] is None` so selecting a kind on a fresh tab 3 doesn't raise an error dialog.
- **Chart tab is date-mode only.** 大運 years come from `yun.getDaYun()[i].getStartYear()`, which needs a birth date. `-b` mode has no `yun`, so `collect()` raises `ChartError` with a message pointing back at tab 1. The check is on `options.b` specifically — a bare `KeyError('yun')` would print `'yun'` with quotes and look like a bug report.
- **`ten_deities[me][gan]` is a 十神 but `ten_deities[me][zhi]` is a 十二長生 state** (`建沐冠帝衰…`). The `dayun` chart plots them on two separate axes for that reason; don't "fix" the zhi line into a 十神 lookup.
- **`matplotlib.tests` fails to import during collection** (missing baseline test images) and prints a warning. Harmless — it only means test data isn't bundled.
- **`bazimaster.spec` excludes must stay conservative.** Excluding `numpy`, `unittest`, or `PIL` to save size breaks the chart at runtime inside the EXE (matplotlib imports all three) while `app.py`'s GUI `try` swallows it into a warning dialog that reads like a hang. `numpy` in particular was excluded in the first draft and cost a build cycle.
- **`--chart-selftest` exists because GUI failures are invisible in a headless test.** `BaziMaster.exe --chart-selftest [--out DIR]` runs `collect()` + `png_bytes()` for all three kinds and prints byte counts. Accepts the same args as `bazi.py`; `-b` is expected to be *rejected* (exit 0 with「已正確拒絕」). Use it after any spec change — a missing backend or font file only shows up there.
- `chart.available_cjk_font()` picks from `CJK_FONTS` by intersecting `font_manager.ttflist`; returns `None` if nothing matches, and the figure then gets a red suptitle saying the Chinese will be boxes. `Microsoft JhengHei` resolves on this machine.

## Blind school module (`mangpai.py`, the 盲派暗局做功 tab)

`mangpai.py` implements the seven steps of `盲派八字暗局做功體系.md` V2.0 (明局做功 → 尋藥 → 察飛神 → 定格局 → 類象 → 歲運 → 綜斷). Like `bazi.py` it is a **script** driven by `runpy`, and it reaches the shared model through `from common import *` only — do not re-derive 五行 / 藏干 / 十神 / 合沖刑會 tables inside it.

- It is listed in **both** `app.py`'s `SCRIPTS` and `bazimaster.spec`'s `SCRIPTS`, because the tab runs it with `run_script('mangpai.py', …)` and PyInstaller can only bundle it as `datas`. Adding a new top-level script means editing both lists.
- **`-b` cannot produce 流年.** Four pillars carry no birth date, hence no 起運年份, so `dayun_sequence()` leaves the year range empty and `render()` skips the 流年 block. This is also why the tab **blocks** 以四柱分析 when 只看某年 is filled in (it would silently do nothing), and why `--年` is ignored by the `--cli` 四柱 path. Don't "fix" this by inventing a 起運 year.
- **`-r` is only meaningful for 農曆.** `lunar_python` raises a bare `Exception("wrong lunar year … month -N")` when the year has no such leap month; `build_pillars_from_date()` catches it and prints 「該年沒有閏N月」 / 「農曆 … 不存在」 then returns `None`, and `main()` turns that into `sys.exit(1)`. The tab sends `-r` only when 公曆 is unchecked — checking both would send contradictory args.
- **解藥 tables come from the theory doc, not from 生克 reasoning.** 伏吟 is `KILL[病字]` for all ten stems; 合絆 is `KILL[克者]`, i.e. 甲己→庚, 丙辛→壬, 乙庚→丙, 丁壬→戊, 戊癸→甲 (the doc labels the table 失勢方 but the 解藥 is always the 克者's 殺). Don't "simplify" this back to `KILL[被合者]` — it gets 乙庚 wrong.
- **地支六合 has no 解藥 in the source doc (2.4 lists only the five 天干 combos).** `find_yao()` therefore *skips* branch 六合 and `render()` prints 「解藥待擴充（10.2），此處不臆造」. That note must print even when other 解神 exist, or the reader assumes the branch 絆 was handled.
- Branch 伏吟 藥 is derived as `KILL[zhi5_list[zhi][0]]` (主氣) and every such line is labelled 待研究. Same reason: don't present it as sourced.
- `decide_geju()` ranks 反噬解神 **before** 有效解神 — a strong 藥 that is itself 忌神 (分財破格) breaks the pattern worse than no 藥. Order matters.
- `liunian_effects()` compares the 流年 against each **伏神**'s 五行, not against the 日主; 「被制」 means the 伏神 制住 the 流年, i.e. the flow year is being attacked.

## Integrated launcher (`app.py`, `bazimaster.spec`, `build_exe.py`)

Added to package the scripts as one `BaziMaster.exe`. **The original scripts were not refactored** — `app.py` executes them with `runpy.run_path()` under a patched `sys.argv`, capturing stdout. That keeps `bazi.py`'s 2.5k lines and its verified output byte-identical; do not "improve" it by importing functions out of them.

Things to know before editing:

- `app.py` resolves its script directory as `sys._MEIPASS` when frozen, else the directory containing `app.py`, and inserts it into `sys.path`. Under PyInstaller the original `.py` files are bundled as **`datas`, not as modules** — PyInstaller cannot see imports made from a data file, so `lunar_python` / `bidict` / `colorama` are pulled in with `collect_all()`.
- Because `bazi.py` never calls `colorama.init()` (it only does `from colorama import init` at line 12), it emits raw ANSI escapes that no terminal interprets. `app.py` strips them with `ANSI_RE` before showing output in the Tk `Text` widget, and keeps them for `--cli`.
- **Encoding.** `app.py` calls `SetConsoleOutputCP(65001)` / `SetConsoleCP(65001)` then reconfigures the streams to UTF-8. `stdin` is only reconfigured when the console switch succeeded **or** stdin is a pipe — reconfiguring it unconditionally would break a user typing on a real cp950 console. `sys.stdin.isatty()` decides this.
- Argument routing: anything that is not `--cli` / `--show-console` / `--version` / `-h` / `--help` is forwarded verbatim to `bazi.py`, because `argparse` swallows `-n` / `-g` / `-b`.
- `sxtwl` is probed with `importlib.util.find_spec()` purely to label the status bar / About box as optional. `bazimaster.spec` bundles it only if it is importable at build time. **No feature is gated on it any more.**

## Admin panel (`Settings`, `apply_look`)

The 管理員設定 tab (last of 6) persists appearance to `%APPDATA%\BaziMaster\settings.json` — **not** next to the EXE, because `sys._MEIPASS` is a fresh read-only temp dir on every onefile launch. `app.py --reset-settings` restores defaults without opening Tk.

Non-obvious constraints, all of which cost a debugging round:

- **`Settings.load()`/`reset()` mutate `self.data` in place** (`clear()` + `update()`), never rebind. `build_gui()` holds `cfg = settings.data`; rebinding would make every UI edit write to a dict nobody saves. Anything else that caches a reference to the settings dict is subject to this.
- **Live preview uses `StringVar.trace_add('write')`, not `<KeyRelease>` bindings.** Key events on `ttk` widgets are unreliable (they don't fire under `event_generate` without a keysym) and miss spinbox arrows, paste, and programmatic sets. A variable trace catches every path.
- **`refresh_vars()` must hold the `busy` flag.** It sets the vars one at a time, and *each* write fires a trace → `collect()`, which reads the **not-yet-updated** vars and writes them back into `cfg`. The first `var.set()` therefore clobbers `cfg` before `refresh_vars` reads it, so 還原預設值 silently restores the old values instead. `live_apply()` returns early while `busy[0]` is set. Don't "simplify" the flag away.
- **`apply_look()` takes already-built widgets** so it can be re-run for live preview; `build_gui()` registers each output `Text` in `texts`. Anything new that should follow appearance settings must be added there too.
- **Never rebind `cfg` inside a helper**; the closure identity is what `settings.save()` and `collect()` agree on.
- Setting values are sanitized in `Settings.clean()` — ints are clamped to `INT_RANGES`, bad input falls back to the previous/default value, so a hand-edited or truncated JSON can't wedge the UI.

## Architecture

- Every `.py` is a **script**, not a library. `bazi.py` parses argv and computes the whole chart at module level, so it cannot be imported for testing. `convert.py` is the same shape (top-level `parse_args()` + prints).
- **Module-level globals are the API.** `gans`, `zhis`, `me` (= day gan), `shens`, `gan_shens`, `zhi_shens`, `scores`, `weak`, `yun`, `ge` are assigned in `bazi.py`'s top level and read by its own functions (`is_yang()`, `not_yang()`, `zhi_ku()`, `get_shens()`). Follow this pattern instead of threading new parameters.
- Import chain is `bazi.py` → `from datas import *`, `from common import *`; `common.py` re-exports `ganzhi` + `sizi`. Bare names like `ten_deities`, `zhi_atts`, `gan5`, `zhi5`, `nayins` resolve through that chain. New lookup tables belong in `ganzhi.py` (core model) or `datas.py` (interpretations), not in `bazi.py`.
- Chart columns are positional: index `0..3` = 年月日時; `zhis[2]` / `gans[2]` is the day pillar. `Gans`/`Zhis` are `collections.namedtuple`s.
- Data model highlights:
  - `ten_deities[me]` is a `bidict` (day-master → everything else): other gans/zhis → 十神 (`比劫食傷才財梟印`, `殺`, `官`), zhis → 12 長生 states (`建沐冠帝衰病死墓絕胎養長`), plus `本/克/被克/生我/生/合/沖/庫`. Lookups go both ways: `ten_deities[me][zhi]`, `ten_deities[me].inverse['建']` (祿), `['帝']`, `['胎']`, `['絕']`.
  - `zhi_atts[zhi]` = branch relations: `沖/刑/被刑/合/會/害/破/六/暗`. Values are a mix of `str`, 2-tuple, and `""` — iterate, never assume `str`.
  - `zhi5[zhi]` = hidden stems with weights (`{gan: weight}`), `zhi5_list[zhi]` = same data ordered 根/中/餘/尾 for strength analysis, `gan5[gan]` = element. 五行 scores and 身強弱 are computed from these.
  - `gan_hes` keys are **tuples** `(甲,己)`; `gong_he`/`gong_hui` keys are **2-char strings** (`"申辰"`).
- Text corpora are dicts keyed by *concatenated* Chinese strings, so a key mismatch fails silently:
  - `sizi.summarys[me + '日' + hour_pillar]` (《三命通會》)
  - `yue.months[me + zhis.month]` (《窮通寶鑑》), guarded by `if me+zhis.month in months`
  - `datas.days60[me+zhis.day]`, `tiaohous[me+zhis.month]`, `jinbuhuan[me+zhis.month]`
  Always `if key in table:` before printing.
- Output layout is hand-built with `chr(12288)` (ideographic space) and `"{1:{0}<15s}".format(...)`, sections separated by `print("-"*120)`. Keep the 15-char column convention or the chart stops lining up.
- `-b` mode has no `lunar_python` `yun` object, so every 大運 block is wrapped in `if not options.b:` / `else:`. New dayun-dependent code must go inside those guards.
- The 大運 table is printed **twice** in normal mode (early block ~line 483, again in the 《三命通會》 section ~line 1813). Legacy duplication — don't "fix" it casually.
- `get_shens()` shadows nothing but reads the module-level `me`; the module-level lists `shens` / `gan_shens` / `zhi_shens` are unrelated names used throughout. Don't rename either.

## Verification

There is no test suite or linter, so the only check is running the CLI and reading the output:

```bash
PYTHONIOENCODING=utf-8 PYTHONHASHSEED=0 python bazi.py 1977 8 11 19 -n
PYTHONIOENCODING=utf-8 python app.py --chart-selftest   # charts, no Tk needed
```

Useful invariants when touching the chart layer (asserted in the scratch tests, not committed):
- every 流年 has exactly **90** years and **9** 大運 (`yun.getDaYun()` returns 10 entries, index 0 is the pre-起運 slot)
- each 流年 五行 total is **constant** = 本命 60 + 大運干支 13 + 流年干支 13 = **86** (天干 is 5, and every `zhi5[zhi]` weights sum to 8)
- `strong` is always an int and takes more than 5 distinct values

- **`PYTHONHASHSEED` must be pinned when diffing output.** The 大運/流年 rows build branch relations in a `set` and `'  '.join(...)` it (`bazi.py:503`, `1829`, `1871`), so token order changes per process. Verified: seeds 0/1/2 produce different 大運 rows for the same chart.
- README lines 167-408 hold a full sample output for exactly that command, but it is **stale** (it predates the 命宮/胎元/身宮 fields in the header). Treat it as a rough reference only; check the pillars instead — header must read `丁 己 癸 壬` / `巳 酉 未 戌`.
- Exercise the branches that diverge: `-n` vs default (男), `-g` vs default (農曆), and `-b` (which works **without** `sxtwl`).
- `lunar_python` version differences shift 上運時間/節氣 output; pin nothing, just be aware diffs may come from the dependency.
- `bazi.py -g` echoes the date you passed as 公曆, so the 公曆 line only cross-checks your input; the 農曆 line is what proves `-g` took effect.
- After touching `app.py`, re-verify with a Tk smoke test that constructs the UI and `invoke()`s each button — a Tk `Text` widget is buildable without a visible display on Windows. Buttons must be located **within their own tab**, not by label, because 八字排盤 and 直接輸入八字 both have a 排　盤 button. Check that 排盤 on tab 1 contains `丁 己 癸 壬`, that tab 2 (直接輸入八字) also produces a full chart, that tab 3 (圖表) draws all three kinds, that tab 4 (盲派暗局做功) produces output from **both** 以四柱分析 and 以日期分析, and that 管理員設定 still saves. For `--cli`, drive it with `subprocess` and **UTF-8 encoded stdin**: piping Chinese through Windows PowerShell mangles it because `$OutputEncoding` defaults to ASCII, which is indistinguishable from a real `stdin` encoding bug in the app.

## Known traps (verified — the code is not self-evidently correct)

Silent-wrong-output bugs, all confirmed by reading plus (where possible) running:

- **Truthiness used where membership was meant.** `ten_deities[g]['庫']` is a sentinel string like `'未_'`, so `['庫'][-1]` is always `'_'` and `... in zhis` is always `False` — `bazi.py:2215` (財臨庫墓) and `bazi.py:2272` (官臨庫墓) are unreachable for every day-master; the rest of the file uses `['庫'][0]`. Same class: `bazi.py:2407` `if ten_deities[me].inverse['冠']:` is always true (a 1-char branch), making `勞累命！` unreachable — it needs `in zhis`.
- **Branch compared against a 十神 label.** `bazi.py:1076` `zhi_shen3[1] == ['梟']` (`zhi_shen3` holds *strings*, built at `bazi.py:199`), `bazi.py:1226` `zhis.count("印")`, `bazi.py:1555` `zhis[seq] == '食'` — all permanently false; the intended variables are `zhi_shen3[1] == '梟'`, `zhi_shens.count('印')`, `zhi_shens[seq] == '食'`.
- **Copy/paste index slip.** `bazi.py:2262` and `bazi.py:2266` are byte-identical guards; the second is labelled 時上正官 but reads index `0`, so it must be `3`. Likewise `bazi.py:1709` tests `zhi_shens[2] == '食' and zhi_shens[2] == '殺'` (impossible duplicate index; message text implies `[3]` for 殺), and `bazi.py:2014-2017` compares a branch char `ku` against the 2-tuple `zhus[1]`, so `continue` always fires and the 建祿格 body is dead.
- **`pass` where `continue` was meant.** `bazi.py:1254-1255`: the 偏財 block tests `gan_ != '才'` then `pass`es, so 偏財坐空亡 / 偏財坐陽刃劫財 print for *all four* pillars. Every analogous loop uses `continue`.
- **`bidict` compared to a string.** `bazi.py:2094` `ten_deities[me] != '建'` is always `True` (lhs is a bidict); likely meant `ten_deities[me].inverse['建'] not in zhis`.
- **Duplicate dict keys.** `yue.py` defines `'甲申'` twice (a 辰月 text at line 172 and a 戌月 text at line 191) and never defines `'甲戌'`. Python keeps the 戌月 text, so 申-month 甲 charts get the wrong month's 窮通寶鑑 text and `bazi.py:1797`'s `if me+zhis.month in months` guard silently drops the whole section for 甲戌.
- **`-b` validates pillar parity before charting.** `days60` / `nayins` / `empties` only hold the 60 same-parity 干支, so hand-typed mismatches used to raise a bare `KeyError: ('甲', '丑')`. `bazi.py` now checks length, membership in `Gan`/`Zhi`, and `Gan.index % 2 == Zhi.index % 2`, prints a Chinese message and `sys.exit(1)`. Keep that check ahead of the chart code.

Don't assume a printed section is missing because the chart lacks the condition — several are simply dead. Fixing them changes output for real charts, so treat it as a deliberate content decision, not a drive-by cleanup.

## Conventions

- Comments, identifiers for tables, and all printed output are Chinese. Do not translate or "clean up" output strings — users compare them against printed classics (三命通會, 窮通寶鑑, 子平真詮, 六十日用法口訣).
- Every file opens with `# -*- coding: utf-8 -*-`, an `# Author:` line and `# CreateDate:`. Preserve that header.
- **No promo / contact strings anywhere** — not in printed output, not in `# Author:` headers, not in `README.md`, not in `convert.py --version`. URLs and WeChat/DingTalk/QQ handles were stripped on request. Don't reintroduce them.
- **`bazi.py` output changed on 2026-10-05** when the promo lines were removed: the contact-method prefix ahead of the reading, the external reference link in the 羊刃 section, and the closing line about which of the five elements is missing are all gone. The byte-identical-to-old-versions guarantee no longer holds — compare against a current run, not `9ad41c1`.
- `README.md` is now usage docs and output samples only; the book list and image links were removed with the promo strings. Its dependency list is incomplete (see above).