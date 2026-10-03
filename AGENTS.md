# bazi (八字排盤) — agent notes

Pure-Python Chinese fortune-telling CLI scripts. **No package metadata, no tests, no CI, no lint/format config, no requirements.txt.** Flat directory; modules import each other by bare name, so everything must be run from this directory.

## Commands

```bash
pip install bidict lunar_python colorama   # what README lists
pip install sxtwl                          # REQUIRED but absent from README

python bazi.py 1977 8 11 19 -n             # 農曆 input (default), 女命
python bazi.py -g 1977 9 23 19 -n          # 公曆 input
python bazi.py -b "丁巳 己酉 癸未 壬戌"    # four-pillar reverse lookup (needs sxtwl)
python shengxiao.py 虎
python luohou.py -d "2019 6 16" -n 32      # needs sxtwl
python convert.py 丁巳己酉 癸未壬戌         # shells out to `python bazi.py -b`
```

Non-obvious flags:
- `bazi.py` takes **農曆** year/month/day unless `-g`. `bazi.py 1977 8 11 19` = lunar 1977-8-11 19:00 → solar 1977-9-23.
- `-b` switches to "already have the pillars" mode; pillars are 4 two-char strings, not 4 args.
- `-n` means 女命 in `bazi.py` but "number of days to print" in `luohou.py`.
- `-r` (閏月) only applies to 農曆 input; the month is negated internally.

## Environment gotchas (verified on this machine)

- Default `sys.stdout.encoding` here is **cp950**, so `python bazi.py ...` dies with `UnicodeEncodeError` on the first CJK print. Export `PYTHONIOENCODING=utf-8` (or use `python -X utf8`) first.
- `sxtwl` is **not installed** in this environment → `luohou.py` and `bazi.py -b` fail at import. `bazi.py` imports it lazily inside the `-b` branch (via `ganzhi.getGZ`), so normal runs work without it.
- `convert.py` hardcodes `.decode('gbk')` on the child's stdout. That only works on a GBK console — under `PYTHONIOENCODING=utf-8` it raises `UnicodeDecodeError`. It's Windows-only by construction (`python bazi.py`, `shell=True`).
- The enclosing git repo root is `C:\Users\Nothing User` (the user's home), **not** this project; the project is untracked there. Never run bare `git add -A` / `git commit -a` from this directory.

## Architecture

- Every `.py` is a **script**, not a library. `bazi.py` parses argv and computes the whole chart at module level, so it cannot be imported for testing. `luohou.py`/`shengxiao.py`/`convert.py` are the same shape (top-level `parse_args()` + prints).
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
```

- **`PYTHONHASHSEED` must be pinned when diffing output.** The 大運/流年 rows build branch relations in a `set` and `'  '.join(...)` it (`bazi.py:503`, `1829`, `1871`), so token order changes per process. Verified: seeds 0/1/2 produce different 大運 rows for the same chart.
- README lines 127-338 hold a full sample output for exactly that command, but it is **stale** (it predates the 命宮/胎元/身宮 fields in the header). Treat it as a rough reference only; check the pillars instead — header must read `丁 己 癸 壬` / `巳 酉 未 戌`.
- Exercise the branches that diverge: `-n` vs default (男), `-g` vs default (農曆), and if touching `-b`, install `sxtwl` first.
- `luohou.py` without `-d` uses today's date → output is not reproducible; always pass `-d "Y M D"`.
- `lunar_python` version differences shift 上運時間/節氣 output; pin nothing, just be aware diffs may come from the dependency.

## Known traps (verified — the code is not self-evidently correct)

Silent-wrong-output bugs, all confirmed by reading plus (where possible) running:

- **Truthiness used where membership was meant.** `ten_deities[g]['庫']` is a sentinel string like `'未_'`, so `['庫'][-1]` is always `'_'` and `... in zhis` is always `False` — `bazi.py:2215` (財臨庫墓) and `bazi.py:2272` (官臨庫墓) are unreachable for every day-master; the rest of the file uses `['庫'][0]`. Same class: `bazi.py:2407` `if ten_deities[me].inverse['冠']:` is always true (a 1-char branch), making `勞累命！` unreachable — it needs `in zhis`.
- **Branch compared against a 十神 label.** `bazi.py:1076` `zhi_shen3[1] == ['梟']` (`zhi_shen3` holds *strings*, built at `bazi.py:199`), `bazi.py:1226` `zhis.count("印")`, `bazi.py:1555` `zhis[seq] == '食'` — all permanently false; the intended variables are `zhi_shen3[1] == '梟'`, `zhi_shens.count('印')`, `zhi_shens[seq] == '食'`.
- **Copy/paste index slip.** `bazi.py:2262` and `bazi.py:2266` are byte-identical guards; the second is labelled 時上正官 but reads index `0`, so it must be `3`. Likewise `bazi.py:1709` tests `zhi_shens[2] == '食' and zhi_shens[2] == '殺'` (impossible duplicate index; message text implies `[3]` for 殺), and `bazi.py:2014-2017` compares a branch char `ku` against the 2-tuple `zhus[1]`, so `continue` always fires and the 建祿格 body is dead.
- **`pass` where `continue` was meant.** `bazi.py:1254-1255`: the 偏財 block tests `gan_ != '才'` then `pass`es, so 偏財坐空亡 / 偏財坐陽刃劫財 print for *all four* pillars. Every analogous loop uses `continue`.
- **`bidict` compared to a string.** `bazi.py:2094` `ten_deities[me] != '建'` is always `True` (lhs is a bidict); likely meant `ten_deities[me].inverse['建'] not in zhis`.
- **Duplicate dict keys.** `yue.py` defines `'甲申'` twice (a 辰月 text at line 172 and a 戌月 text at line 191) and never defines `'甲戌'`. Python keeps the 戌月 text, so 申-month 甲 charts get the wrong month's 窮通寶鑑 text and `bazi.py:1797`'s `if me+zhis.month in months` guard silently drops the whole section for 甲戌.
- **`Lunar.fromYmd` fed solar components.** `luohou.py:243` calls `Lunar.fromYmd(d.year, d.month, d.day)` where `d` is a *solar* date; the same file does it correctly at `luohou.py:21` via `getLunarYear()/getLunarMonth()/getLunarDay()`. Can't be exercised here (needs `sxtwl`); expect `Exception` on dates whose solar day exceeds the interpreted lunar month's length.
- **`-b` does not validate pillar parity.** `days60` / `nayins` / `empties` only hold the 60 same-parity 干支, so hand-typed mismatched pillars raise a bare `KeyError` (e.g. `bazi.py -b "甲丑 乙丑 丙子 丁卯"`). Date-input mode can't hit this because `lunar_python` always returns matching parity.

Don't assume a printed section is missing because the chart lacks the condition — several are simply dead. Fixing them changes output for real charts, so treat it as a deliberate content decision, not a drive-by cleanup.

## Conventions

- Comments, identifiers for tables, and all printed output are Chinese. Do not translate or "clean up" output strings — users compare them against printed classics (三命通會, 窮通寶鑑, 子平真詮, 六十日用法口訣).
- Every file opens with `# -*- coding: utf-8 -*-`, an `# Author:` line and `# CreateDate:`. Preserve that header.
- `README.md` is mostly a book-download list plus usage docs; its dependency list is incomplete (see above).