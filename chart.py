# -*- coding: utf-8 -*-
# Author: opencode
# CreateDate: 2026-10-05
"""大運／流年走勢圖表。

這個模組**不修改 bazi.py 的任何輸出**，只是讀取 bazi.py 跑完之後留下的
module globals（由 app.py 用 runpy 取得），取出計算圖表需要的部分：

* 五行分數走勢  —— 把大運與每個流年干支都加回命盤，沿年份畫金木水火土
* 身強弱走勢    —— 沿年份畫「比劫梟印」四個干的分數總和（子平真詮算法）
* 大運干支      —— 每步大運的天干十神、地支長生畫成分類折線

計分方式完全沿用 bazi.py 自己的表與權重（gan5 / zhi5 / ten_deities），
所以圖上的數字與文字排盤是同一套算法，不會各自發明一套。

每個年份的分數 = 本命四柱 + 該年所屬大運的干支 + 該流年的干支。
天干固定 5 分，地支用 zhi5 的隱藏干權重，所以總分恆為 60 + 13 + 13 = 86。

注意尺度：bazi.py:308 印的「中值29」是本命尺度的說明文字，不是門檻值
（bazi.py 裡沒有任何比較式用到 29）。加了流年與大運後同一演算法算出來
會是別的數字，所以本模組不用 29 畫參考線，改畫同尺度的本命值當基準線。

不依賴 Tk，也不碰 matplotlib 的 Tk backend：只輸出 PNG 位元組，
由 app.py 貼到 Label 上。這樣在 onefile EXE 裡也不需要互動式 backend。
"""

import io

# 十神分類軸：天干十神依固定順序編成 1..10
SHEN10 = ['比', '劫', '食', '傷', '才', '財', '官', '殺', '梟', '印']
# 地支長生分類軸：十二長生依循環順序編成 1..12
CHANGSHENG12 = ['長', '沐', '冠', '帝', '衰', '病',
                '死', '墓', '絕', '胎', '養', '建']

# 五行固定畫線順序與顏色（順序固定，圖例位置才不會每次跳動）
WUXING = ['金', '木', '水', '火', '土']
WUXING_COLOR = {'金': '#8a8a8a', '木': '#2e8b57',
                '水': '#1f6fb4', '火': '#c0392b', '土': '#b8860b'}

# 與 bazi.py:279 相同：這四個干合起來算「強」
STRONG_SHENS = ('比', '劫', '梟', '印')

# 單一干支的固定分數：天干 5 分，地支藏干合計 8 分，合計 13 分
GAN_POINTS = 5
ZHI_POINTS = 8

KINDS = [
    ('wuxing', '五行分數走勢'),
    ('strong', '身強弱數值走勢'),
    ('dayun', '大運干支走勢'),
]

# Windows 上穩定存在的中文字型，依優先順序嘗試
CJK_FONTS = ['Microsoft JhengHei', 'Microsoft JhengHei UI', 'Microsoft YaHei',
             'SimHei', 'KaiTi', 'SimSun', 'NSimSun', 'Arial Unicode MS']


class ChartError(Exception):
    """圖表無法產生時丟出，訊息直接顯示給使用者看。"""


def available_cjk_font():
    """回傳第一個 matplotlib 找得到的中文字型，找不到就回傳 None。"""
    from matplotlib import font_manager
    installed = {f.name for f in font_manager.fontManager.ttflist}
    for name in CJK_FONTS:
        if name in installed:
            return name
    return None


def _apply_font():
    """設定中文字型與負號顯示，缺字型時不報錯（退成 DejaVu Sans）。"""
    from matplotlib import pyplot as plt
    name = available_cjk_font()
    plt.rcParams['font.sans-serif'] = ([name] if name else []) + ['DejaVu Sans']
    plt.rcParams['font.family'] = 'sans-serif'
    # 沒中文字型時 minus 號會變成方框，這裡關掉 Unicode minus 即可
    plt.rcParams['axes.unicode_minus'] = False
    return name


def _add(gan, zhi, gan5, zhi5, gan_scores=None, scores=None):
    """把一個干支（天干 +5、地支藏干依權重）加進分數。

    與 bazi.py:231-239 同一套權重：天干固定 5 分，地支用 zhi5 的隱藏干權重。
    gan_scores / scores 傳 None 就不算該份，用來分別算「干分」與「五行分」。
    """
    if gan_scores is not None:
        gan_scores[gan] = gan_scores.get(gan, 0) + GAN_POINTS
        for hidden, weight in zhi5[zhi].items():
            gan_scores[hidden] = gan_scores.get(hidden, 0) + weight
    if scores is not None:
        scores[gan5[gan]] = scores.get(gan5[gan], 0) + GAN_POINTS
        for hidden, weight in zhi5[zhi].items():
            scores[gan5[hidden]] = scores.get(gan5[hidden], 0) + weight


def collect(g):
    """從 bazi.py 的 globals 組出畫圖需要的資料。

    必須是日期模式（有 yun 物件）才會有真實年份與流年；`-b` 模式沒有 yun，
    這時回傳 None，由呼叫端決定要不要改用相對序號。
    """
    # -b 模式沒有 yun / solar 物件，起運年份算不出來。
    # 先講清楚原因，不要丟一串 KeyError 名稱給使用者。
    options = g.get('options')
    if options is not None and getattr(options, 'b', False):
        raise ChartError(
            '直接輸入八字模式沒有起運年份，算不出大運對應的西元年份。\n'
            '請改用「八字排盤」分頁填出生日期後再畫圖。')

    needed = ('yun', 'gan5', 'zhi5', 'ten_deities', 'gans', 'zhis', 'me',
              'scores', 'gan_scores', 'solar')
    missing = [name for name in needed if name not in g]
    if missing:
        raise ChartError('bazi.py 沒有提供「{}」，無法畫圖。'.format(
            '、'.join(missing)))
    yun = g['yun']
    gan5 = g['gan5']
    zhi5 = g['zhi5']
    ten = g['ten_deities']
    gans = g['gans']
    zhis = g['zhis']
    me = g['me']
    base_scores = g['scores']
    base_gan_scores = g['gan_scores']
    solar = g['solar']

    if yun is None:
        raise ChartError('這個命盤沒有起運年份，無法畫大運圖表。')

    # 「強」的四個干：bazi.py:278-280 用 ten_deities[me].inverse 反查
    inverse = ten[me].inverse
    try:
        strong_gans = [inverse[k] for k in STRONG_SHENS]
    except KeyError as exc:
        raise ChartError('查不到「{}」對應的天干。'.format(exc))

    dayun_list = list(yun.getDaYun()[1:])
    if not dayun_list:
        raise ChartError('這個命盤沒有大運資料。')

    # 大運清單第一筆是「童限」段：ganZhi 是空字串，lunar_python 給的是
    # 出生年到起運年前的那幾年，沒有干支可算。所以用 [1:] 略過它。
    # 這不是「空白的占位資料」，是真的有年份但無干支。
    years = []
    dayuns = []
    for dayun in dayun_list:
        ganzhi = dayun.getGanZhi()
        gan_, zhi_ = ganzhi[0], ganzhi[1]
        dayuns.append({
            'age': dayun.getStartAge(),
            'start': dayun.getStartYear(),
            'end': dayun.getEndYear(),
            'ganzhi': ganzhi,
            # 天干是十神，地支在 ten_deities 裡存的是十二長生
            'gan_shen': ten[me][gan_],
            'zhi_sheng': ten[me][zhi_],
        })

        # 先把大運干支加在命盤上，這一步對該大運底下每個流年都一樣，
        # 所以只算一次，迴圈內直接複製，不再重複加。
        dayun_scores = dict(base_scores)
        _add(gan_, zhi_, gan5, zhi5, scores=dayun_scores)
        dayun_gan_scores = dict(base_gan_scores)
        _add(gan_, zhi_, gan5, zhi5, gan_scores=dayun_gan_scores)

        for liunian in dayun.getLiuNian():
            gz2 = liunian.getGanZhi()
            gan2, zhi2 = gz2[0], gz2[1]

            scores = dict(dayun_scores)
            _add(gan2, zhi2, gan5, zhi5, scores=scores)

            gan_scores = dict(dayun_gan_scores)
            _add(gan2, zhi2, gan5, zhi5, gan_scores=gan_scores)
            strong_value = sum(gan_scores[x] for x in strong_gans)

            years.append({
                'year': liunian.getYear(),
                'dayun': ganzhi,
                'liunian': gz2,
                'age': dayun.getStartAge() + (liunian.getYear()
                                              - dayun.getStartYear()),
                'wuxing': scores,
                'strong': strong_value,
            })

    if not years:
        raise ChartError('這個命盤沒有流年資料。')

    return {
        'gans': ' '.join(gans),
        'zhis': ' '.join(zhis),
        'me': me,
        'date': '{}年{}月{}日'.format(solar.getYear(), solar.getMonth(),
                                    solar.getDay()),
        'strong_base': g.get('strong', 0),
        'weak_base': g.get('weak', True),
        'years': years,
        'dayuns': dayuns,
        'born_year': solar.getYear(),
        'font': available_cjk_font(),
        # 每個流年分數的理論總分：本命 60 + 大運 13 + 流年 13
        'year_total': sum(base_scores.values()) + 2 * (GAN_POINTS
                                                       + ZHI_POINTS),
    }


def _mark_dayun_borders(ax, data):
    """在每步大運的起點畫淡色虛線，方便對照三張圖。"""
    for item in data['dayuns']:
        if item['start'] == data['years'][0]['year']:
            continue
        ax.axvline(item['start'], color='#bbbbbb', linestyle=':',
                   linewidth=0.8, zorder=0)


def _figure_wuxing(data):
    xs = [item['year'] for item in data['years']]
    fig, ax = _new_figure(len(xs))
    for element in WUXING:
        ax.plot(xs, [item['wuxing'][element] for item in data['years']],
                color=WUXING_COLOR[element], linewidth=1.4,
                marker='.', markersize=3, label=element)
    _mark_dayun_borders(ax, data)
    # 每年總分固定，所以畫一條總分線當量尺：五行線的起伏才有絕對分數的意義
    total = data['year_total']
    ax.axhline(total / len(WUXING), color='#999999', linestyle='-.',
               linewidth=0.9,
               label='平均 {:.1f}（總分 {}）'.format(total / len(WUXING),
                                                  total))
    ax.set_title('五行分數走勢　（{} {}　本命＋大運＋流年，總分 {}）'.format(
        data['gans'], data['zhis'], total), fontsize=12)
    ax.set_xlabel('年份')
    ax.set_ylabel('分數')
    ax.legend(loc='upper left', ncol=3, framealpha=0.9)
    ax.grid(alpha=0.3)
    return fig, ax


def _figure_strong(data):
    xs = [item['year'] for item in data['years']]
    fig, ax = _new_figure(len(xs))
    ax.plot(xs, [item['strong'] for item in data['years']],
            color='#1f6fb4', linewidth=1.4, marker='.', markersize=3,
            label='比劫梟印（含大運＋流年）')

    # 參考線用「同尺度的本命值」，不用 bazi.py 印的「中值29」。
    # 29 是本命四柱的說明文字；這條線是本命＋大運＋流年，尺度不同，
    # 照抄 29 會讓人誤以為整條曲線都遠高於「門檻」。
    base = data['strong_base']
    ax.axhline(base, color='#2e8b57', linestyle='--', linewidth=1.1,
               label='本命 {}'.format(base))
    _mark_dayun_borders(ax, data)
    ax.set_title('身強弱走勢　（強 = 比劫梟印；本命 {}，強根 {}）'.format(
        base, '無' if data['weak_base'] else '有'), fontsize=13)
    ax.set_xlabel('年份')
    ax.set_ylabel('分數')
    ax.legend(loc='upper left', framealpha=0.9)
    ax.grid(alpha=0.3)
    return fig, ax


def _figure_dayun(data):
    """兩條分類折線：大運天干十神、地支長生。

    分類軸要固定順序才能畫折線，所以 y 軸是人工編號，
    右側再把編號標回真正的十神／長生名稱。
    """
    items = data['dayuns']
    xs = list(range(1, len(items) + 1))
    gan_y = [SHEN10.index(d['gan_shen']) + 1 if d['gan_shen'] in SHEN10 else 0
             for d in items]
    zhi_y = [CHANGSHENG12.index(d['zhi_sheng']) + 1
             if d['zhi_sheng'] in CHANGSHENG12 else 0
             for d in items]

    fig, ax = _new_figure(len(xs) * 2, base=6.0)
    ax.plot(xs, gan_y, color='#c0392b', linewidth=1.6, marker='o',
            markersize=5, label='天干十神')
    ax.plot(xs, zhi_y, color='#1f6fb4', linewidth=1.6, marker='s',
            markersize=5, label='地支長生')
    ax.set_xticks(xs)
    ax.set_xticklabels(['{}\n{}歲'.format(d['ganzhi'], d['age'])
                        for d in items], fontsize=9)
    ax.set_yticks(range(1, 11))
    ax.set_yticklabels(SHEN10[:10], fontsize=9)
    ax.set_ylim(0.4, 10.8)
    ax.set_title('大運干支走勢　（{}）'.format(
        ' / '.join(d['ganzhi'] for d in items)), fontsize=11)
    ax.set_xlabel('大運　（{}）'.format(
        '{} 起運，{} - {}'.format(data['dayuns'][0]['age'],
                                data['years'][0]['year'],
                                data['years'][-1]['year'])))
    ax.set_ylabel('天干十神')
    ax2 = ax.twinx()
    ax2.set_ylim(0.4, 10.8)
    ax2.set_yticks(range(1, 13))
    ax2.set_yticklabels(CHANGSHENG12, fontsize=9)
    ax2.set_ylabel('地支長生')
    ax.grid(alpha=0.3, axis='x')
    ax.legend(loc='upper left', framealpha=0.9)
    fig.subplots_adjust(bottom=0.28, right=0.92)
    return fig, ax


_BUILDERS = {'wuxing': _figure_wuxing,
             'strong': _figure_strong,
             'dayun': _figure_dayun}


def _new_figure(points, base=9.0):
    """依資料點數決定寬度，太寬就限住，免得 90 年拉成兩百吋。"""
    from matplotlib import pyplot as plt
    width = max(7.0, min(22.0, points / 9.0))
    return plt.subplots(figsize=(width, base))


def figure(kind, data):
    """產生指定種類的 Figure。"""
    if kind not in _BUILDERS:
        raise ChartError('不认识的圖表種類：{}'.format(kind))
    _apply_font()
    fig, _ax = _BUILDERS[kind](data)
    if not data['font']:
        fig.suptitle('（找不到中文字型，圖上的中文會變成方框）', fontsize=9,
                     color='#c0392b', y=0.005)
    return fig


def png_bytes(kind, data, dpi=100):
    """把圖轉成 PNG 位元組。"""
    fig = figure(kind, data)
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight',
                facecolor='white')
    import matplotlib.pyplot as plt
    plt.close(fig)
    return buf.getvalue()


def save(kind, data, path, dpi=100):
    """存成 PNG 檔，回傳實際寫入的位元組數。"""
    blob = png_bytes(kind, data, dpi=dpi)
    with open(path, 'wb') as handle:
        handle.write(blob)
    return len(blob)