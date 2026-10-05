#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author: opencode
# CreateDate: 2026-10-05
"""盲派八字「暗局做功體系」可程式化判讀。

依《盲派八字暗局做功體系》V2.0 的七步流程逐條落成可執行的判斷：

    第一步 理法——明局做功：體用、五類做功、明局四大病
    第二步 理法——尋藥：七殺解神、解神鏈、解神效力三級
    第三步 理法——察飛神：干合飛／支合飛／支沖飛／拱飛，隔位拱夾
    第四步 理法——定格局：有病有藥、有病無藥、有暗藥
    第五步 象法——落人事：十神類象、干支類象、宮位類象、做功類象與力度
    第六步 歲運——定應期：大運六影響、流年引動與填實
    第七步 綜斷：串聯上述信息成完整斷語

**這個模組不重算八字，也不推翻 bazi.py。**
四柱排盤、起運、流年仍然由 lunar_python 提供（與 bazi.py 同一套），
核心關係表也全部沿用 ganzhi.py（ten_deities / zhi5 / gan_hes / zhi_atts /
chongs / zhi_6hes / gong_he / gong_hui），所以這裡只多一層「做功」的解讀，
不會另外發明一套生克。

只有本體系專屬的三張表寫在下面，不放進 ganzhi.py（那裡是共用核心模型）：

    解神規則 KILL / 合絆解藥合主 / 七殺解神鏈
    五類做功、四大病型
    類象表（四張）

盲派口訣與本程式的對應（原文 -> 本程式）：

    「有病方為貴，無傷不是奇」        -> 第四步：病是前提，無病不論層次
    「見不見之形，無時不有」          -> 第三步：飛神四法
    「虛則有勢，實則有變」            -> 第六步：引動為吉、填實為凶
    「刑沖最烈，飛伏最深，克合最緩」  -> 第五步：做功力度
    「吉凶在原局，應期在歲運」        -> 第六步

命令列：

    python mangpai.py 1977 8 11 19 -n              # 農曆（預設），女命
    python mangpai.py -g 1977 9 23 19 -n           # 公曆
    python mangpai.py -b 丁巳 己酉 癸未 壬戌       # 直接輸入四柱
    python mangpai.py 1977 8 11 19 -n --年 2024    # 只看某一年的應期
    python mangpai.py 1977 8 11 19 -n --不印類象   # 精簡輸出（省略第五步）
"""

import argparse
import collections
import sys

from common import *

# ==========================================================================
# 一、本體系專屬的三張表
# ==========================================================================

# --------------------------------------------------------------------------
# 體用：體是我擁有的資源，用是我想獲取的東西
# --------------------------------------------------------------------------
TI_SHENS = ('比', '劫', '印', '梟')          # 體：日主、比劫、祿、印
YONG_SHENS = ('食', '傷', '財', '才', '官', '殺')  # 用：財、官、殺、食傷
JI_SHENS = ('印', '梟')                        # 印：化殺有功，但過重會破做功
BIJIE_SHENS = ('比', '劫')                     # 比劫：分財、破格

# 十神全名，只給類象與斷語用
SHEN_FULL = {
    '比': '比肩', '劫': '劫財', '食': '食神', '傷': '傷官',
    '財': '正財', '才': '偏財', '官': '正官', '殺': '七殺',
    '印': '正印', '梟': '偏印',
}

# --------------------------------------------------------------------------
# 七殺解神
#
# 伏吟與合絆必須「破」而後「立」，七殺為解神。解藥一律等於「所克之神」的
# 七殺，所以整張表不必逐條硬寫，用 ten_deities 反查即可自洽：
#
#     伏吟　甲甲　解庚（七殺劈木，成棟樑材）
#     合絆　甲己　甲克己而絆之，取甲之七殺庚砍甲，己重獲自由
#     解神鏈 甲→庚→丙→壬→甲…（五行相克之鏈同時是解神之鏈）
# --------------------------------------------------------------------------
KILL = {g: ten_deities[g].inverse['殺'] for g in Gan}

# 天干順生：黏連的判斷依據（陰陽同類相生）
GAN_SHENG = {}
for _g in Gan:
    _same = [x for x in Gan
             if gan5[x] == ten_deities[_g]['生']
             and Gan.index(x) % 2 == Gan.index(_g) % 2]
    GAN_SHENG[_g] = _same[0]

# 墓庫：水土同庫於辰
ZHI_MU = {'木': '未', '火': '戌', '土': '辰', '金': '丑', '水': '辰'}

# 六合：zhi_6hes 的鍵是兩字串，這裡翻成「一對一支」的單向表
ZHI_6HE = {}
for _pair in zhi_6hes:
    ZHI_6HE[_pair[0]] = _pair[1]
    ZHI_6HE[_pair[1]] = _pair[0]

# 三合拱中神與三會拱中神的「兩支 -> 中神」。gong_he / gong_hui 的鍵正反各存
# 一次（「申辰」與「辰申」同義），這裡正規化成排序後的兩字串。
GONG_HE = {}
for _k, _v in gong_he.items():
    GONG_HE[''.join(sorted((_k[0], _k[1])))] = _v
GONG_HUI = {}
for _k, _v in gong_hui.items():
    GONG_HUI[''.join(sorted((_k[0], _k[1])))] = _v

# --------------------------------------------------------------------------
# 五類做功
# --------------------------------------------------------------------------
GONG_WAYS = [
    ('食傷制殺', ('食', '傷'), ('殺',),
     '食傷克七殺。以技藝謀略奪權，層次最高'),
    ('食傷生財', ('食', '傷'), ('財', '才'),
     '食傷生財星。以才華技術求財'),
    ('官印相生', ('官', '殺'), ('印', '梟'),
     '官殺生印，印生身。靠權力名聲，穩定上升'),
    ('比劫克財', ('比', '劫'), ('財', '才'),
     '比劫制財星。合作求財，亦易破財'),
    ('印化殺', ('印', '梟'), ('殺',),
     '印星化七殺。以德服人，壓力轉為權柄'),
]

# --------------------------------------------------------------------------
# 四大病型：只放識別規則，實際判定在 _find_bing()
# --------------------------------------------------------------------------
BING_RULES = [
    ('伏吟', '同干／同支並見，氣聚一處淤堵。例：甲甲、丙丙、申申'),
    ('合絆', '天干相合或地支六合而不化，雙方被束縛。例：甲己合、巳申合絆'),
    ('黏連', '天干順生緊貼，氣化單一偏枯。例：乙丙、庚辛、癸甲'),
    ('刑沖', '刑沖破壞做功結構，能量內耗。例：子午沖、丑未沖、寅巳申三刑'),
]

# --------------------------------------------------------------------------
# 類象（第五步）
# --------------------------------------------------------------------------
SHEN_XIANG = {
    '比': ('兄弟、同輩、合夥人、競爭者', '合作、分財、爭奪、破財', '四肢、骨骼', '剛健、固執、行動力'),
    '劫': ('朋友、異性同輩、盜賊', '投機、破耗、合作不穩', '手足、肌肉', '衝動、慷慨、佔有'),
    '食': ('晚輩、學生、下屬', '飲食、藝術、口福、悠閒', '腸胃、乳房', '溫和、樂觀、享受'),
    '傷': ('晚輩、下屬、情人、訟師', '技藝、口才、是非、創新', '膽、神經、生殖', '叛逆、聰明、尖銳'),
    '財': ('妻子、父親、員工', '薪水、不動產、穩定財', '肌肉、血液', '勤儉、踏實、吝嗇'),
    '才': ('父親、情人、傭人', '橫財、流動財、生意財', '皮膚、毛髮', '慷慨、圓滑、善交際'),
    '官': ('上司、丈夫、法官', '名聲、權位、法律、約束', '膀胱、膽', '正直、守規、壓力'),
    '殺': ('敵人、小人、上司、武職', '權力、暴力、災禍、開創', '肺、骨、外傷', '果斷、狠辣、壓力大'),
    '印': ('母親、長輩、老師', '文書、學歷、房產、庇護', '脾胃、皮膚', '仁慈、保守、依賴'),
    '梟': ('繼母、養母、宗教人士', '偏門學問、孤獨、玄學', '肝、神經衰弱', '敏感、多思、孤僻'),
}

GAN_XIANG = {
    '甲': ('陽木', '首領、家長、老闆', '大樹、高樓、棟樑', '頭、膽、毛髮', '東方'),
    '乙': ('陰木', '妻、醫生、文人', '花草、藤蔓、紙張', '肝、頸、神經', '東方'),
    '丙': ('陽火', '名人、領導、法官', '太陽、電力、媒體', '心臟、小腸、眼', '南方'),
    '丁': ('陰火', '文人、學生、信徒', '燈火、星光、香火', '心、血壓、視力', '南方'),
    '戊': ('陽土', '長輩、地主、胖子', '高山、堤壩、城牆', '胃、肋、皮膚', '中央'),
    '己': ('陰土', '主婦、農民、員工', '田園、濕土、灰塵', '脾、腹部', '中央'),
    '庚': ('陽金', '軍警、武將、屠夫', '刀劍、鋼鐵、大路', '大腸、骨骼、喉', '西方'),
    '辛': ('陰金', '珠寶商、牙醫、刺客', '珠玉、手術刀、鎖', '肺、牙齒、小骨', '西方'),
    '壬': ('陽水', '經理、盜賊、司機', '江河、大海、運輸', '膀胱、腎、耳', '北方'),
    '癸': ('陰水', '智者、護士、間諜', '雨露、眼淚、沼澤', '腎、足、腦髓', '北方'),
}

ZHI_XIANG = {
    '子': ('陽水', '盜賊、學者', '井、河流、暗處', '耳、膀胱、腎', '鼠'),
    '丑': ('陰土', '農夫、廚師', '倉庫、墳墓、田', '脾、肚、腳', '牛'),
    '寅': ('陽木', '官員、丈夫', '山林、公門、電器', '膽、手、筋', '虎'),
    '卯': ('陰木', '手工藝人、司機', '門窗、草木、車', '肝、指、毛髮', '兔'),
    '辰': ('陽土', '軍人、獄吏', '水庫、監獄、寺廟', '胃、肩、胸', '龍'),
    '巳': ('陰火', '婦人、爐工', '爐灶、煙囪、蛇穴', '心、面、齒', '蛇'),
    '午': ('陽火', '軍人、騎手', '戰場、馬房、旗', '眼、頭、心', '馬'),
    '未': ('陰土', '牧人、酒鬼', '田野、木庫、糧倉', '脾、腹、脊', '羊'),
    '申': ('陽金', '商人、僧道', '道路、驛站、刀劍', '大腸、肺、骨', '猴'),
    '酉': ('陰金', '銀行家、妓女', '金銀、酒器、珠寶', '肺、小腸、精血', '雞'),
    '戌': ('陽土', '軍人、屠夫', '火庫、寺廟、戰場', '腿、足、命門', '狗'),
    '亥': ('陰水', '漁夫、司機', '江河、浴池、豬欄', '腎、頭、陰囊', '豬'),
}

GONG_WAY_XIANG = {
    '食傷制殺': '以暴制暴，武職、外科、整頓者',
    '食傷生財': '靠技藝、口才、生意',
    '官印相生': '靠權力、名聲、文書',
    '比劫克財': '靠體力、合作、爭奪',
    '印化殺': '以德服人，壓力轉權柄',
}

# 做功力度：刑沖最烈、飛伏最深、克合最緩
LI_DI = [
    ('刑沖', '劇烈、突發、徹底', '最強'),
    ('飛伏', '暗中、持續、深遠', '次強'),
    ('克合', '溫和、漸進、有商量', '較弱'),
]

PILLARS = ('年柱', '月柱', '日柱', '時柱')
PILLAR_AGE = ('1-16歲', '17-32歲', '33-48歲', '49歲後')
PILLAR_PEOPLE = ('祖上、父母、領導', '父母、兄弟、上司', '自己、配偶', '子女、下屬、晚輩')
PILLAR_BODY = ('頭面', '胸肩', '腹股', '腿足')
PILLAR_PLACE = ('遠方、故鄉', '家門、單位', '自身、夫妻宮', '遠方、歸宿')

# 飛神層級：拱飛 > 沖飛 > 合飛 > 天干合飛
FEI_RANK = {'拱飛': 0, '沖飛': 1, '合飛': 2, '天干合飛': 3}


# ==========================================================================
# 二、小工具
# ==========================================================================

def dwidth(text):
    """螢幕寬度：CJK／全形標點佔 2 欄，ASCII 佔 1 欄。"""
    return sum(2 if ord(char) > 0x2000 else 1 for char in text)


def pad(text, width=30):
    """以全形空格補滿到指定的螢幕欄寬。

    bazi.py 用的是 15 **字元**寬（'{1:{0}<15s}'），因為它的欄位內容多半是
    兩字元以內所以看不出差別。這裡的欄位長短差很多（斷語可以長到三十幾字），
    照字元數補會整片歪掉，所以改用螢幕欄寬計算。
    """
    fill = max(0, width - dwidth(text)) // 2
    return text + chr(12288) * fill


def adjacent_pairs(items):
    """相鄰兩位；貼得越緊，能量越難轉化。"""
    return [(i, i + 1) for i in range(len(items) - 1)]


def is_gan(item):
    return item in Gan


# 五行相生鏈：木→火→土→金→水→木
GAN_SHENG_VALUES = {'木': '火', '火': '土', '土': '金', '金': '水', '水': '木'}


def wuxing_action(a, b):
    """五行 a 對五行 b 的作用：生／剋／同。"""
    if a == b:
        return '同'
    if GAN_SHENG_VALUES[a] == b:
        return '生'
    return '剋'


# ==========================================================================
# 三、十神分布：透干、通根、餘藏
#
# 盲派論做功不論旺衰，但要知道一個十神「算不算數」：
# 透干最實、本氣通根次之、只剩餘氣尾氣最虛。三種來源分開統計，
# 判定做功是否成立時用「透干或通根」，只用餘氣的標成虛。
# ==========================================================================

def shen_power(me, gans, zhis):
    """回傳 {十神: {'透': [天干...], '根': [地支...], '藏': [(地支,天干)...]}}。

    日主自己是比肩／日主之位，屬於「體」而不是「用」，所以第一項直接標為
    日主——否則一個八字會印出「比肩無」，那不是真話。
    """
    power = {'比': {'日主': True}}
    for seq, item in enumerate(gans):
        if seq == 2:          # 日主自己不算「透」，它是太極
            continue
        power.setdefault(ten_deities[me][item], {}).setdefault('透', []).append(item)

    for zhi in zhis:
        ben = zhi5_list[zhi][0]
        if ten_deities[ben]['本'] == ten_deities[me]['本']:
            power.setdefault(ten_deities[me][ben], {}).setdefault('根', []).append(zhi)
        for gan in zhi5_list[zhi]:
            power.setdefault(ten_deities[me][gan], {}).setdefault('藏', []).append(
                (zhi, gan))
    return power


def shen_strength(shen, power):
    """日主 > 透 > 根 > 虛（只剩餘氣尾氣）。"""
    info = power.get(shen)
    if not info:
        return '無'
    if info.get('日主'):
        return '主'
    if info.get('透'):
        return '透'
    if info.get('根'):
        return '根'
    return '虛'


COUNTABLE = ('主', '透', '根')


def shen_source_text(shen, power):
    info = power.get(shen)
    if not info:
        return '—'
    parts = []
    if info.get('日主'):
        parts.append('日主本氣')
    if info.get('透'):
        parts.append('透' + ''.join(info['透']))
    if info.get('根'):
        parts.append('根' + ''.join(info['根']))
    if info.get('藏'):
        parts.append('藏' + ''.join('{}{}'.format(z, g) for z, g in info['藏']))
    return '　'.join(parts)


# ==========================================================================
# 四、第一步：明局做功
# ==========================================================================

def find_gong_ways(me, power):
    """五類做功逐類判定是否成立。"""
    result = []
    for name, src, dst, comment in GONG_WAYS:
        src_state = [(s, shen_strength(s, power)) for s in src]
        dst_state = [(s, shen_strength(s, power)) for s in dst]
        src_ok = [s for s, v in src_state if v in COUNTABLE]
        dst_ok = [s for s, v in dst_state if v in COUNTABLE]
        if src_ok and dst_ok:
            state = '成立'
        elif any(v != '無' for _, v in src_state) and \
                any(v != '無' for _, v in dst_state):
            state = '虛'
        else:
            state = '不成'
        result.append({
            'name': name, 'state': state,
            'src': [SHEN_FULL[s] for s in src_ok],
            'dst': [SHEN_FULL[s] for s in dst_ok],
            'src_all': [SHEN_FULL[s] for s in src if shen_strength(s, power) != '無'],
            'dst_all': [SHEN_FULL[s] for s in dst if shen_strength(s, power) != '無'],
            'comment': comment,
        })
    return result


def find_fuyin(gans, zhis):
    """伏吟：同干／同支並見，氣聚一處淤堵。不論相鄰，全部位置都算。"""
    out = []
    for kind, items in (('天干', gans), ('地支', zhis)):
        for item, count in sorted(collections.Counter(items).items()):
            if count >= 2:
                pos = [i for i, x in enumerate(items) if x == item]
                out.append({
                    'kind': kind, 'char': item, 'count': count, 'pos': pos,
                    'text': '{}　{}出現{}次（{}{}）'.format(
                        kind, item, count,
                        '、'.join(PILLARS[i] for i in pos),
                        '貼' if len(pos) == 2 and pos[1] - pos[0] == 1 else '隔位'),
                })
    return out


def find_heban(gans, zhis):
    """合絆：天干五合或地支六合而不化，雙方被束縛。"""
    out = []
    for i, j in adjacent_pairs(gans):
        a, b = gans[i], gans[j]
        pair = (a, b) if (a, b) in gan_hes else None
        if pair is None and (b, a) in gan_hes:
            pair = (b, a)
        if pair:
            out.append({
                'kind': '天干', 'pair': pair, 'pos': (i, j),
                'text': '{}與{}相合（{}{}）　{}'.format(
                    a, b, PILLARS[i], PILLARS[j], gan_hes[pair].split()[0]),
            })
    for i, j in adjacent_pairs(zhis):
        a, b = zhis[i], zhis[j]
        if ZHI_6HE.get(a) == b:
            # zhi_6hes 的鍵只收一種書寫順序（子丑，不是丑子），
            # 而 ZHI_6HE 是對稱的，所以要挑對方向再查。
            key = a + b if a + b in zhi_6hes else b + a
            out.append({
                'kind': '地支', 'pair': (a, b), 'pos': (i, j),
                'text': '{}與{}六合（{}{}）　化{}'.format(
                    a, b, PILLARS[i], PILLARS[j], zhi_6hes[key]),
            })
    return out


def find_nianlian(me, gans):
    """黏連：天干順生緊貼，氣化單一偏枯。"""
    out = []
    for i, j in adjacent_pairs(gans):
        a, b = gans[i], gans[j]
        if GAN_SHENG[a] == b:
            out.append({
                'pair': (a, b), 'pos': (i, j),
                'src': ten_deities[me][a], 'dst': ten_deities[me][b],
                'text': '{}生{}（{}{}）　{}生{}'.format(
                    a, b, PILLARS[i], PILLARS[j],
                    SHEN_FULL[ten_deities[me][a]], SHEN_FULL[ten_deities[me][b]]),
            })
    return out


def find_xingchong(zhis):
    """刑沖過度：相鄰刑沖，能量內耗。"""
    out = []
    for i, j in adjacent_pairs(zhis):
        a, b = zhis[i], zhis[j]
        if zhi_atts[a]['沖'] == b:
            out.append({'type': '沖', 'pair': (a, b), 'pos': (i, j),
                        'text': '{}沖{}（{}{}）'.format(a, b, PILLARS[i], PILLARS[j])})
        elif zhi_atts[a]['刑'] == b:
            out.append({'type': '刑', 'pair': (a, b), 'pos': (i, j),
                        'text': '{}刑{}（{}{}）'.format(a, b, PILLARS[i], PILLARS[j])})
        elif zhi_atts[b]['刑'] == a:
            # 刑是單向的：戌刑未而非未刑戌，所以這裡要反過來寫，
            # 否則會印成「未刑戌」而與 zhi_atts 的方向相反。
            out.append({'type': '刑', 'pair': (b, a), 'pos': (i, j),
                        'text': '{}刑{}（{}{}）'.format(b, a, PILLARS[j], PILLARS[i])})
    return out


def find_bing(me, gans, zhis):
    return {
        '伏吟': find_fuyin(gans, zhis),
        '合絆': find_heban(gans, zhis),
        '黏連': find_nianlian(me, gans),
        '刑沖': find_xingchong(zhis),
    }


# ==========================================================================
# 五、第二步：尋藥（解神鏈）
# ==========================================================================

def kill_chain(start, limit=6):
    """解神鏈：病 → 殺 → 殺之殺 … 五行相克之鏈同時是解神之鏈。"""
    chain = [start]
    cur = start
    for _ in range(limit):
        cur = KILL[cur]
        if cur in chain:
            break
        chain.append(cur)
    return chain


def find_yao(me, gans, zhis, power, bing):
    """明藥、暗藥、外藥，以及解神效力三級。

    明藥　原局自帶的解神（病字的七殺在原局透或通根）
    暗藥　飛出的伏神恰為所需之藥（伏神由第三步飛出，這裡只留待補的欄位）
    外藥　原局沒有，要等大運流年送來

    2.4 的解藥表只列到天干。地支伏吟（申申、酉酉）與地支合絆（巳申、寅亥）
    在原文 10.2 列為「待擴充」，所以這裡採保守作法：取該支主氣干的七殺當
    參考藥，並在斷語裡標明是推的，不假裝那是定論。
    """
    need = []
    for item in bing['伏吟']:
        need.append(('伏吟', item['char']))
    for item in bing['合絆']:
        a, b = item['pair']
        if not (is_gan(a) and is_gan(b)):
            # 地支六合（巳申、寅亥…）的解藥表在原文 10.2 列為待擴充，
            # 這裡不硬套天干那條規則，直接跳過並在第二步說明。
            continue
        # 2.4.2：合絆要「找到被合住而失勢的一方，用**它所被制的那一方**的七殺
        # 來撕毀合約」。以甲己為例，己土被甲木剋而失勢，解藥取甲之七殺庚，
        # 庚砍甲，己才重獲自由。五組天干五合全都可以這樣推出來：
        #   甲己→庚、丙辛→壬、乙庚→丙、丁壬→戊、戊癸→甲
        if gan5[b] == ten_deities[a]['克']:
            need.append(('合絆', a))      # a 克 b，b 失勢
        elif gan5[a] == ten_deities[b]['克']:
            need.append(('合絆', b))      # b 克 a，a 失勢

    yaos = []
    seen = set()
    for kind, char in need:
        if (kind, char) in seen:
            continue
        seen.add((kind, char))
        if is_gan(char):
            gan_for_kill = char
            note = ''
        else:
            gan_for_kill = zhi5_list[char][0]
            note = '（{}為地支，原文只列天干解藥表，此藥取主氣{}之殺推得，待研究）'.format(
                char, gan_for_kill)
        yao = KILL[gan_for_kill]
        chain = kill_chain(gan_for_kill)
        shen = ten_deities[me][yao]
        state = shen_strength(shen, power)

        if yao in gans:
            place = '原局自帶（{}透干）'.format(yao)
        elif state in COUNTABLE:
            place = '原局自帶（{}通根）'.format(yao)
        elif state == '虛':
            place = '原局藏而不透，力弱'
        else:
            place = '原局沒有，待大運流年送來'

        # 反噬的判斷要排在「有效」之前：藥再有力，若藥本身就是忌神，
        # 解開病的同時會招來更大的災。
        if shen in BIJIE_SHENS:
            level = '反噬解神'
            reason = '解神{}為{}，分財破格，解開反而招禍'.format(yao, SHEN_FULL[shen])
        elif shen in JI_SHENS and _ji_du(power):
            level = '反噬解神'
            reason = '解神{}為{}，原局印重奪殺，破壞做功'.format(yao, SHEN_FULL[shen])
        elif state in COUNTABLE:
            level = '有效解神'
            reason = '解神{}透干通根，真能破局，格局層次高'.format(yao)
        elif state == '虛':
            level = '弱解神'
            reason = '解神{}虛浮無根，只能暫時解困，不能根本翻盤'.format(yao)
        else:
            level = '外藥'
            reason = '解神{}不在原局，須行到歲運方能破局'.format(yao)

        yaos.append({
            'kind': kind, 'bing': char, 'yao': yao, 'shen': SHEN_FULL[shen],
            'place': place + note, 'level': level, 'reason': reason,
            'chain': chain,
            # 地支病（申申）是以主氣庚起鏈，但病名要寫原來的「申」，
            # 否則讀者會以為病字是庚。
            'chain_text': '　'.join(
                ((('病' + char) if i == 0 else ('解' + x))
                 for i, x in enumerate(chain))),
        })
    return yaos


def _ji_du(power):
    """印是否過重（透或通根的印梟達三個以上）。"""
    count = sum(1 for s in JI_SHENS if shen_strength(s, power) in COUNTABLE)
    return count >= 3


# ==========================================================================
# 六、第三步：飛神
# ==========================================================================

def find_fushen(gans, zhis, ming=None, shen=None, tai=None):
    """飛神四法：干合飛、支合飛、支沖飛、拱飛（含隔位拱夾）。

    每個伏神都標明飛法、層級、宮位出處，以及與三宮的關係。
    """
    gans = list(gans)
    zhis = list(zhis)
    gset, zset = set(gans), set(zhis)
    out = []

    def push(char, method, reason, pos=None):
        out.append({
            'char': char, 'method': method, 'reason': reason,
            'shen': None, 'pos': pos,
            'in_ming': bool(ming and char in ming),
            'in_shen': bool(shen and char in shen),
            'in_tai': bool(tai and char in tai),
        })

    # 3.2.1 天干合飛：二干並見，飛出所缺之合干
    for item, count in sorted(collections.Counter(gans).items()):
        if count >= 2:
            he = ten_deities[item]['合']
            if he and he not in gset:
                push(he, '天干合飛',
                     '{}二見而{}無，飛{}為伏神'.format(item, he, he),
                     [i for i, x in enumerate(gans) if x == item])

    # 3.2.2 地支合飛：二支並見，飛出所缺之六合
    for item, count in sorted(collections.Counter(zhis).items()):
        if count >= 2:
            he = ZHI_6HE.get(item)
            if he and he not in zset:
                push(he, '合飛', '{}二見而{}無，飛{}為伏神'.format(item, he, he),
                     [i for i, x in enumerate(zhis) if x == item])

    # 3.2.3 地支沖飛：二支並見，飛出所缺之對沖支
    for item, count in sorted(collections.Counter(zhis).items()):
        if count >= 2:
            chong = chongs.get(item)
            if chong and chong not in zset:
                push(chong, '沖飛', '{}二見而{}無，飛{}為暗沖伏神'.format(
                    item, chong, chong),
                    [i for i, x in enumerate(zhis) if x == item])

    # 3.2.4 地支拱飛：三合拱中神
    for pair, mid in sorted(GONG_HE.items()):
        a, b = pair[0], pair[1]
        if a in zset and b in zset and mid not in zset:
            pos = [i for i, x in enumerate(zhis) if x in (a, b)]
            push(mid, '拱飛', '{}{}拱{}，{}無，飛{}為伏神'.format(a, b, mid, mid, mid),
                 pos)

    # 3.2.4 隔位拱夾：三會拱中神
    for pair, mid in sorted(GONG_HUI.items()):
        a, b = pair[0], pair[1]
        if a in zset and b in zset and mid not in zset:
            pos = [i for i, x in enumerate(zhis) if x in (a, b)]
            push(mid, '拱飛', '{}{}隔位拱夾{}，{}無，飛{}為伏神'.format(a, b, mid, mid, mid),
                 pos)

    for item in out:
        item['level'] = FEI_RANK[item['method']]
        item['level_text'] = ('拱飛（三合中神）力度最強、最穩，持續做功',
                              '沖飛（暗沖）爆發力強，應驗迅速、變化劇烈',
                              '合飛（暗合）較穩，漸進顯現、暗中牽引',
                              '天干合飛需地支支持，須歲運配合')[item['level']]
    out.sort(key=lambda x: (x['level'], x['char']))
    return out


def decorate_fushen(me, fushen):
    """給伏神標上十神（以原局日主為唯一太極）與三宮出處。"""
    for item in fushen:
        char = item['char']
        if is_gan(char):
            item['shen'] = SHEN_FULL[ten_deities[me][char]]
            item['wuhang'] = gan5[char]
        else:
            item['shen'] = SHEN_FULL[ten_deities[me][zhi5_list[char][0]]]
            item['wuhang'] = zhi_wuhangs[char]
        tags = []
        if item['in_ming']:
            tags.append('落命宮')
        if item['in_shen']:
            tags.append('落身宮')
        if item['in_tai']:
            tags.append('落胎元')
        item['gong_tag'] = '、'.join(tags) if tags else '不入三宮'


def fushen_output(me, fushen_item):
    """伏神對日主的「輸出」是吉是凶——暗局只判這一項。

    暗局不另立日主，也不重排十神格局：以原局日主為唯一太極，看這個伏神
    落在體（生我、同我）還是用（我生、我剋、剋我）那一側。
    """
    me5 = gan5[me]
    wu = fushen_item['wuhang']
    if wu == me5:
        return '同我為比劫，分財破格'
    if GAN_SHENG_VALUES[wu] == me5:
        return '生我為印，印生身，暗中得力'
    if wuxing_action(me5, wu) == '生':
        return '我生者為食傷，洩秀為功'
    if wuxing_action(me5, wu) == '剋':
        return '我剋者為財，輸出資源求利'
    return '剋我者為官殺，壓力轉權柄'


# ==========================================================================
# 七、第四步：定格局
# ==========================================================================

def decide_geju(bing, yaos, fushen, gong_ways):
    has_bing = bool(bing['伏吟'] or bing['合絆'])
    you_yao = [y for y in yaos if y['level'] == '有效解神']
    an_yao = [y for y in yaos if y['level'] == '弱解神']
    fan_yao = [y for y in yaos if y['level'] == '反噬解神']
    an_fu = [f for f in fushen if f['char'] in {y['yao'] for y in yaos}]

    # 一病可能同時被天干合絆與地支伏吟各記一筆，解藥又可能相同。
    # 直接把「病」和「藥」各自 join 會印出「甲的病由庚、庚解」這種病藥對不上的句子，
    # 所以改成列「病→藥」的配對，並依原文順序去重。
    def _pairs(group):
        seen = []
        for y in group:
            p = '{}→{}'.format(y['bing'], y['yao'])
            if p not in seen:
                seen.append(p)
        return '、'.join(seen)

    if has_bing and you_yao:
        level = '格局層次高'
        summary = '有病有藥。{}，破局有力'.format(_pairs(you_yao))
    elif has_bing and an_yao:
        level = '格局層次中'
        summary = '有病有弱藥。{}，但藥力不足，只能暫時解困、不能根本翻盤'.format(
            _pairs(an_yao))
    elif has_bing and fan_yao:
        level = '有藥而藥反噬'
        summary = '有病，唯一的解神{}為命局所忌（分財破格），解開反而引發更大災禍'.format(
            fan_yao[0]['yao'])
    elif has_bing:
        level = '有志難伸'
        summary = '有病無藥。原局的矛盾沒有出口，只能靠歲運送藥'
    else:
        level = '無病不作'
        summary = '原局無伏吟合絆之病，依「無傷不是奇」不論層次，只看做功純度'

    if an_fu:
        summary += '。暗局飛出的{}恰為所需之藥，屬待時而發之命'.format(
            '、'.join(sorted({f['char'] for f in an_fu})))

    strong_ways = [w['name'] for w in gong_ways if w['state'] == '成立']
    return {
        'level': level, 'summary': summary,
        'has_bing': has_bing, 'you_yao': you_yao, 'an_yao': an_yao,
        'fan_yao': fan_yao, 'an_fu': an_fu, 'gong_ways': strong_ways,
    }


# ==========================================================================
# 八、第五步：類象
# ==========================================================================

def build_xiang(me, gans, zhis, gong_ways, geju):
    xiang = {'gong': [], 'gan': [], 'zhi': [], 'gong_li': []}
    for name in geju['gong_ways']:
        xiang['gong'].append((name, GONG_WAY_XIANG[name]))

    # `src` / `dst` 存的是全名（`find_gong_ways()` 內部已過 `SHEN_FULL`），
    # 而 `ten_deities[me][me]` 是簡碼，兩邊要先統一成全名再比。
    me_shen = SHEN_FULL[ten_deities[me][me]]
    used = set()
    for item in gong_ways:
        if item['state'] != '成立':
            continue
        for shen in item['src'] + item['dst']:
            # 日主自己不算「做功用神」——它是太極，兩邊都不當作用方。
            if shen != me_shen:
                used.add(shen)
    for seq, item in enumerate(gans):
        shen = ten_deities[me][item]
        tag = []
        if seq == 2:
            tag.append('日主')
        if shen in used:
            tag.append('做功用神')
        xiang['gan'].append({
            'pos': PILLARS[seq], 'gan': item, 'shen': SHEN_FULL[shen],
            'wuhang': GAN_XIANG[item][0],
            'people': GAN_XIANG[item][1], 'thing': GAN_XIANG[item][2],
            'body': GAN_XIANG[item][3], 'fangwei': GAN_XIANG[item][4],
            'tag': '、'.join(tag),
        })
    for seq, item in enumerate(zhis):
        wu, people, thing, body, sheng = ZHI_XIANG[item]
        xiang['zhi'].append({
            'pos': PILLARS[seq], 'zhi': item, 'shen': SHEN_FULL[
                ten_deities[me][zhi5_list[item][0]]],
            'wuhang': wu, 'people': people, 'thing': thing, 'body': body,
            'sheng': sheng, 'changsheng': ten_deities[me][item],
        })
    for name, feature, level in LI_DI:
        xiang['gong_li'].append((name, feature, level))
    return xiang


def sangong_view(fushen, yaos, ming, shen, tai):
    """三維協同：命宮最高、身宮次之、胎元輔助。"""
    rows = []
    for tag, gz, weight, duty in (
            ('命宮', ming, '最高', '後半生、思想、事業歸宿；暗局的主要載體'),
            ('身宮', shen, '次高', '安身立命、中年運勢；自解潛能所在'),
            ('胎元', tai, '輔助', '先天根基、福澤伏筆')):
        if not gz:
            rows.append({'tag': tag, 'gz': '—', 'weight': weight, 'duty': duty,
                         'text': '（此模式沒有出生日期，無法排三宮）'})
            continue
        hit = [f['char'] for f in fushen if f['char'] in gz]
        yao_hit = [y['yao'] for y in yaos if y['yao'] in gz]
        notes = []
        if hit:
            notes.append('伏神{}落{}，半明半暗，貫穿始終'.format(
                '、'.join(hit), tag))
        if yao_hit:
            notes.append('解藥{}藏於{}，{}'.format(
                '、'.join(yao_hit), tag,
                '晚年發力' if tag == '命宮' else '中年發力'))
        if not notes:
            notes.append('與暗局無直接關聯')
        rows.append({'tag': tag, 'gz': gz, 'weight': weight, 'duty': duty,
                     'text': '；'.join(notes)})
    return rows


# ==========================================================================
# 九、第六步：歲運應期
# ==========================================================================

def _touched_by(ch, gan_, zhi_):
    """大運的某一字，與 ch 有沒有發生引動（合／沖／刑／拱）。回傳關係字或 None。

    這是 7.2「引動暗局」與 7.4「引動」的共用判斷：只看大運／流年主動碰到
    伏神，而不是原局自己去碰——原局本來就有的關係已經算在明局了。
    """
    if is_gan(ch):
        if ch == gan_:
            return '填'
        if ten_deities[ch]['合'] == gan_:
            return '合'
        if chongs.get(ch) == gan_:
            return '沖'
        return None
    if ch == zhi_:
        return '填'
    if ZHI_6HE.get(ch) == zhi_:
        return '六合'
    if chongs.get(ch) == zhi_:
        return '沖'
    if zhi_atts[ch]['刑'] == zhi_ or zhi_atts[zhi_]['刑'] == ch:
        return '刑'
    for pair, mid in GONG_HE.items():
        if mid == ch and zhi_ in pair:
            return '拱' + pair
    for pair, mid in GONG_HUI.items():
        if mid == ch and zhi_ in pair:
            return '夾' + pair
    return None


def dayun_effects(dayun_gz, me, gans, zhis, bing, yaos, fushen, sangan):
    """大運對原局的六種影響（7.2）。"""
    gan_, zhi_ = dayun_gz[0], dayun_gz[1]
    dayun_set = set(dayun_gz)
    out = []
    seen = set()

    def add(kind, luck, text):
        key = (kind, text)
        if key in seen:
            return
        seen.add(key)
        out.append((kind, luck, text))

    # 補缺解病：送來所缺的解神／用神
    for y in yaos:
        if y['yao'] in dayun_set:
            add('補缺解病', '吉', '大運{}送來{}的解神{}（{}），病得其藥'.format(
                dayun_gz, y['bing'], y['yao'], y['shen']))
    # 引動暗局 / 填實伏神
    for f in fushen:
        touch = _touched_by(f['char'], gan_, zhi_)
        if touch == '填':
            add('填實伏神', '凶多吉少', '大運{}直接填實伏神{}，虛變實，得而復失'.format(
                dayun_gz, f['char']))
        elif touch:
            add('引動暗局', '吉', '大運{}以{}引動伏神{}，暗能量釋放'.format(
                dayun_gz, touch, f['char']))
    # 加重病情：與原局病神同氣
    for item in bing['伏吟']:
        if item['char'] in dayun_set:
            add('加重病情', '凶', '大運{}再見病神{}，氣更聚而淤'.format(
                dayun_gz, item['char']))
    for item in bing['合絆']:
        for char in item['pair']:
            if char in dayun_set:
                add('加重病情', '凶', '大運{}再見合神{}，纏得更緊'.format(dayun_gz, char))
    # 解神激活：送來解神之解神
    for y in yaos:
        for step in y['chain'][2:]:
            if step in dayun_set:
                add('解神激活', '吉', '大運{}送來解神之解神{}，化凶為吉'.format(
                    dayun_gz, step))
                break
    # 改變格局：與命身胎成新三合三會
    for tag, gz in sangan:
        if not gz:
            continue
        combined = set(zhis) | {zhi_} | set(gz)
        for group, element in zhi_hes.items():
            if set(group) <= combined:
                add('改變格局', '視情況', '大運{}與{}{}及原局成{}局（化{}）'.format(
                    dayun_gz, tag, gz, group, element))
    return out


def liunian_effects(ln_gz, me, fushen, gans, zhis):
    """流年是觸發器（7.3／7.4）：引動為吉、填實為凶多吉少。"""
    gan_, zhi_ = ln_gz[0], ln_gz[1]
    out = []
    for f in fushen:
        ch = f['char']
        touch = _touched_by(ch, gan_, zhi_)
        if touch == '填':
            out.append(('填實', '凶多吉少',
                        '伏神{}被流年直接填實，虛變實，突發變故'.format(ch)))
            continue
        if touch:
            out.append(('引動', '吉', '流年以{}引動伏神{}，暗能量釋放，主動出擊'.format(
                touch, ch)))
            continue
        mu = ZHI_MU[gan5[ch]] if is_gan(ch) else None
        if mu and zhi_ == mu:
            out.append(('入墓', '平', '流年{}入伏神{}之墓，能量收藏，蓄勢待發'.format(
                zhi_, ch)))
            continue
        # 7.3 的「被制」是流年與**伏神**之間的關係（伏神受剋而暫時受抑），
        # 不是流年被日主剋——後者與伏神無關，不該混進應期判斷。
        fu5 = gan5[ch] if is_gan(ch) else gan5[zhi5_list[ch][0]]
        for src, label in ((gan_, '天干'), (zhi_, '地支')):
            src5 = gan5[src] if is_gan(src) else gan5[zhi5_list[src][0]]
            if wuxing_action(src5, fu5) == '剋':
                out.append(('被制', '平', '流年{}{}剋伏神{}，伏神暫時受抑，待時而動'.format(
                    label, src, ch)))
                break

    if not out:
        out.append(('無事', '平', '流年{}與伏神無引動亦無填實，無特殊應驗'.format(ln_gz)))
    return out


# ==========================================================================
# 十、組版
# ==========================================================================

def sep():
    print('-' * 120)


def render(d, show_xiang=True):
    me = d['me']
    gans, zhis = d['gans'], d['zhis']

    print()
    print('=' * 120)
    print('　盲派八字暗局做功體系　V2.0　可程式化判讀')
    print('=' * 120)
    print('　四柱　　{}　{}　{}　{}'.format(
        *['{}{}'.format(g, z) for g, z in zip(gans, zhis)]))
    print('　日主　　{}　{}（{}）'.format(
        me, gan5[me], '陽' if Gan.index(me) % 2 == 0 else '陰'))
    if d['date_text']:
        print('　出生　　{}　上運：{}'.format(d['date_text'], d['start_text']))
    else:
        print('　出生　　（直接輸入四柱：無起運年份，故第六步只列大運干支，無流年）')
    print('　三宮　　命宮{}　身宮{}　胎元{}'.format(
        d['ming'] or '—', d['shen'] or '—', d['tai'] or '—'))
    print('　建祿　　{}'.format(ten_deities[me].inverse['建']))
    print()

    # ---------------- 第一步 ----------------
    sep()
    print('【第一步】理法——明局做功')
    sep()
    power = d['power']
    print('　體（日主、比劫、祿、印）與用（財、官、殺、食傷）——')
    print('　　十神　　 力　來源（透＝天干、根＝本氣通根、藏＝只留餘氣尾氣）')
    for shen in TI_SHENS + YONG_SHENS:
        tag = '體' if shen in TI_SHENS else '用'
        tail = '　← 日主本氣即體，一切做功的太極' if shen == '比' else ''
        print('　　{} {} {}{}'.format(
            pad(tag, 6), pad(SHEN_FULL[shen], 10),
            pad(shen_strength(shen, power), 6),
            shen_source_text(shen, power) + tail))
    print()
    print('　五類做功：')
    for item in d['gong_ways']:
        if item['state'] == '成立':
            detail = '{}　→　{}'.format('、'.join(item['src']), '、'.join(item['dst']))
        elif item['state'] == '虛':
            detail = '（透根不齊：{}　／　{}）'.format(
                '、'.join(item['src_all']) or '無', '、'.join(item['dst_all']) or '無')
        else:
            detail = item['comment']
        print('　　{} {} {}'.format(pad(item['name'], 14), pad(item['state'], 6),
                                   detail))
    print()
    print('　明局之病（四病皆為「有病方為貴」的前提）：')
    for name, rule in BING_RULES:
        hits = d['bing'][name]
        if not hits:
            print('　　{} 無　　（{}）'.format(pad(name, 8), rule))
            continue
        for idx, hit in enumerate(hits):
            head = pad(name, 8) if idx == 0 else pad('', 8)
            print('　　{} {}'.format(head, hit['text']))
    print()
    print('　病藥總說：「有病方為貴，無傷不是奇」。原局無病者不論層次，')
    print('　　　　　　有病而無藥者有志難伸，有病有藥方為富貴之基。')
    print()

    # ---------------- 第二步 ----------------
    sep()
    print('【第二步】理法——尋藥（七殺解神、解神鏈）')
    sep()
    zhi_heban = [h for h in d['bing']['合絆'] if h['kind'] == '地支']
    if not d['yaos']:
        if zhi_heban:
            print('　原局無天干伏吟、無天干合絆，故無解神鏈可走。')
            print('　但有地支六合之絆：{}——原文 2.4 的解藥表只列天干五合，'
                  '地支六合的解藥待擴充（10.2），此處不臆造。'.format(
                      '；'.join(h['text'] for h in zhi_heban)))
        else:
            print('　原局無伏吟、無合絆，故無病可施藥，也沒有解神鏈可走。')
        print()
    else:
        for item in d['yaos']:
            print('　病 {}（{}）'.format(item['bing'], item['kind']))
            print('　解 {} {} {}'.format(
                pad(item['yao'], 4), pad(item['shen'], 6), item['place']))
            print('　層 {} {}'.format(pad(item['level'], 12), item['reason']))
            print('　鏈 {}'.format(item['chain_text']))
            print()
        print('　解神鏈原理：木病→金解→金病→火解→火病→水解→水病→土解→土病→木解……')
        print('　　　　　　　五行相克之鏈，同時也是解神之鏈。')
        print()

    # 地支六合的解藥表原文未列，不論有沒有天干解藥都要把這個缺口講清楚，
    # 否則讀者會以為地支合絆已被上面的解藥鏈處理掉了。
    if zhi_heban and d['yaos']:
        print('　另：地支六合之絆 {}——原文 2.4 的解藥表只列天干五合，'
              '地支六合的解藥待擴充（10.2），此處不臆造。'.format(
                  '；'.join(h['text'] for h in zhi_heban)))
        print()

    # ---------------- 第三步 ----------------
    sep()
    print('【第三步】理法——察飛神（「見不見之形，無時不有」）')
    sep()
    if not d['fushen']:
        print('　原局無重複干支、無拱局，飛不出伏神。此命為明局單純之局。')
        print()
    else:
        for item in d['fushen']:
            print('　　{} 伏神 {} {}'.format(
                pad(item['method'], 10), item['char'],
                pad('（{}）'.format(item['shen']), 10)))
            print('　　{} {}'.format(pad('', 10), item['reason']))
            print('　　{} {}'.format(pad('', 10), item['level_text']))
            print('　　{} 以日主{}為太極　{}　{}'.format(
                pad('', 10), d['me'], fushen_output(d['me'], item),
                item['gong_tag']))
            print()
        print('　飛神三原則：')
        print('　　一、直接做功——飛出的字直接參與生克，不再與原局合沖刑穿拱夾。')
        print('　　二、宜藏不宜現——最喜歲運合沖引動，最忌直接填實。')
        print('　　三、暗局不另立日主——伏神之間可以互生互克，只判其對日主的輸出吉凶。')
        print()
        print('　飛神層級：拱飛（三合中神）＞ 沖飛（暗沖）＞ 合飛（暗合）＞ 天干合飛')
        print()

    # ---------------- 第四步 ----------------
    sep()
    print('【第四步】理法——定格局')
    sep()
    geju = d['geju']
    print('　格局 {}'.format(pad(geju['level'], 16)))
    print('　斷語 {}'.format(geju['summary']))
    print('　做功 {}'.format('、'.join(geju['gong_ways']) or '五類做功皆未成立'))
    print()

    # ---------------- 第五步 ----------------
    if show_xiang:
        sep()
        print('【第五步】象法——落人事（「理法定吉凶，象法落人事」）')
        sep()
        xiang = d['xiang']
        print('　做功類象（行為模式）：')
        for name, behavior in xiang['gong']:
            print('　　{} {}'.format(pad(name, 14), behavior))
        if not xiang['gong']:
            print('　　（做功未成立，無行為類象可取）')
        print()
        print('　做功力度（刑沖最烈、飛伏最深、克合最緩）：')
        for name, feature, level in xiang['gong_li']:
            print('　　{} {} {}'.format(pad(name, 10), pad(level, 8), feature))
        print()
        print('　十神與天干類象：')
        for item in xiang['gan']:
            print('　　{} {} {} {} {}'.format(
                pad(item['pos'] + ' ' + item['gan'], 12),
                pad(item['shen'], 8), pad(item['wuhang'], 8),
                item['thing'], item['tag']))
            print('　　{} 人物：{}　身體：{}　{}方'.format(
                pad('', 12), item['people'], item['body'], item['fangwei']))
        print()
        print('　干支與宮位類象：')
        for idx, item in enumerate(xiang['zhi']):
            print('　　{} {} {} {} 生肖{}'.format(
                pad(item['pos'] + ' ' + item['zhi'], 12),
                pad(item['shen'], 8), pad(item['wuhang'], 8),
                item['thing'], item['sheng']))
            print('　　{} 人物：{}　身體：{}'.format(
                pad('', 12), item['people'], item['body']))
            print('　　{} 宮位：{}　{}　{}'.format(
                pad('', 12), PILLAR_AGE[idx], PILLAR_PEOPLE[idx],
                PILLAR_PLACE[idx]))
        print()
        print('　三維協同（命宮最高、身宮次之、胎元輔助）：')
        for row in d['sangong']:
            print('　　{} {} {}'.format(
                pad(row['tag'] + ' ' + row['gz'], 14), pad(row['weight'], 8),
                row['text']))
            print('　　{} {}'.format(pad('', 14), row['duty']))
        print()

    # ---------------- 第六步 ----------------
    sep()
    print('【第六步】歲運——定應期（「吉凶在原局，應期在歲運」）')
    sep()
    if not d['dayuns']:
        print('　（沒有起運年份，也未排得大運序列）')
        print()
    else:
        for item in d['dayuns']:
            gz = item['ganzhi']
            age = item['age']
            year = item['year']
            head = '　大運{}'.format(gz)
            if age[0] is not None:
                head += '　{}歲-{}歲　（{}年-{}年）'.format(
                    age[0], age[1], year[0], year[1])
            else:
                head += '　（無起運年份，只有干支）'
            print(head)
            gan_, zhi_ = gz[0], gz[1]
            print('　　前五年　天干{}　{}　外部環境、事業方向、人際變動'.format(
                gan_, SHEN_FULL[ten_deities[me][gan_]]))
            # 注意：`ten_deities[me][zhi]` 取到的是十二長生狀態（建沐冠帝…），
            # 不是十神。要判十神得先取本氣藏干。
            print('　　後五年　地支{}　{}（{}）　內部根基、家庭健康、實際得失'.format(
                zhi_, SHEN_FULL[ten_deities[me][zhi5_list[zhi_][0]]],
                zhi5_list[zhi_][0]))
            if item['effects']:
                for eff in item['effects']:
                    print('　　{} {} {}'.format(pad(eff[0], 14), pad(eff[1], 10),
                                                eff[2]))
            else:
                print('　　{} {} 與原局無六種作用，安穩過運'.format(
                    pad('無事', 14), pad('平', 10)))
            print()
        if any(item['liunian'] for item in d['dayuns']):
            print('　流年（觸發器）：')
            for item in d['dayuns']:
                for ln in item['liunian']:
                    body = '　'.join('{}／{}／{}'.format(e[0], e[1], e[2])
                                     for e in ln['effects'])
                    print('　　{} {}'.format(
                        pad('{}年 {} {}歲'.format(ln['year'], ln['ganzhi'],
                                               ln['age']), 22), body))
            print()
            print('　引動與填實的差別：')
            print('　　引動＝流年合沖刑伏神　→ 吉，暗能量釋放，主動出擊')
            print('　　填實＝流年直接出現伏神之字　→ 凶多吉少，虛變實，得而復失')
            print()

    # ---------------- 第七步 ----------------
    sep()
    print('【第七步】綜斷')
    sep()
    for line in d['zongduan']:
        print('　' + line)
    print()
    print('=' * 120)
    print('　理法看流通，象法看呈現，歲運看時機。三者合一，方為完整。')
    print('=' * 120)
    print()


# ==========================================================================
# 十一、主流程
# ==========================================================================

def dayun_sequence(gans, zhis, female):
    """順排／逆排十二步大運干支。

    與 bazi.py:256-275 同一套規則：年干陽男陰女順排、陰男陽女逆排，
    月干與月支各加減一步。直接輸入四柱時沒有起運時間，但干支序列算得出來，
    所以 -b 模式仍然列得出大運（只是沒有年份與流年）。
    """
    seq = Gan.index(gans[0])
    forward = (seq % 2 == 0) if not female else (seq % 2 == 1)
    direction = 1 if forward else -1
    gan_seq = Gan.index(gans[1])
    zhi_seq = Zhi.index(zhis[1])
    out = []
    for _ in range(12):
        gan_seq += direction
        zhi_seq += direction
        out.append(Gan[gan_seq % 10] + Zhi[zhi_seq % 12])
    return out


def analyze(gans, zhis, ming=None, shen=None, tai=None, yun=None,
            start_text='', year_only=None, female=False):
    me = gans[2]
    power = shen_power(me, gans, zhis)
    gong_ways = find_gong_ways(me, power)
    bing = find_bing(me, gans, zhis)
    yaos = find_yao(me, gans, zhis, power, bing)
    fushen = find_fushen(gans, zhis, ming, shen, tai)
    decorate_fushen(me, fushen)
    geju = decide_geju(bing, yaos, fushen, gong_ways)
    xiang = build_xiang(me, gans, zhis, gong_ways, geju)
    sangong = sangong_view(fushen, yaos, ming, shen, tai)

    # 暗藥：飛出的伏神恰為所需之藥
    need_yao = {y['yao'] for y in yaos}
    an_yao = sorted({f['char'] for f in fushen if f['char'] in need_yao})

    sangan = [('命宮', ming), ('身宮', shen), ('胎元', tai)]
    dayuns = []
    if yun is not None:
        for dayun in yun.getDaYun()[1:]:
            gz = dayun.getGanZhi()
            start_year, end_year = dayun.getStartYear(), dayun.getEndYear()
            if year_only is not None and not (start_year <= year_only <= end_year):
                continue
            entry = {
                'ganzhi': gz,
                'age': (dayun.getStartAge(), dayun.getEndAge()),
                'year': (start_year, end_year),
                'effects': dayun_effects(gz, me, gans, zhis, bing, yaos,
                                         fushen, sangan),
                'liunian': [],
            }
            for ln in dayun.getLiuNian():
                year = ln.getYear()
                if year_only is not None and year != year_only:
                    continue
                lz = ln.getGanZhi()
                entry['liunian'].append({
                    'year': year, 'ganzhi': lz, 'age': ln.getAge(),
                    'effects': liunian_effects(lz, me, fushen, gans, zhis),
                })
            dayuns.append(entry)
    elif year_only is None:
        # 沒有起運時間（例如 -b 模式）：只列干支序列，效應照算。
        for gz in dayun_sequence(gans, zhis, female):
            dayuns.append({
                'ganzhi': gz, 'age': (None, None), 'year': (None, None),
                'effects': dayun_effects(gz, me, gans, zhis, bing, yaos,
                                         fushen, sangan),
                'liunian': [],
            })

    data = {
        'gans': list(gans), 'zhis': list(zhis), 'me': me, 'power': power,
        'gong_ways': gong_ways, 'bing': bing, 'yaos': yaos, 'fushen': fushen,
        'geju': geju, 'xiang': xiang, 'sangong': sangong,
        'ming': ming, 'shen': shen, 'tai': tai,
        'date_text': '', 'start_text': start_text,
        'dayuns': dayuns, 'an_yao': an_yao,
    }
    data['zongduan'] = build_zongduan(data)
    return data


def build_zongduan(d):
    me = d['me']
    geju = d['geju']
    lines = []

    lines.append('【格局層次】{}'.format(geju['level']))
    lines.append('　　{}'.format(geju['summary']))

    gong_text = '、'.join(geju['gong_ways']) or '五類做功皆未成立'
    lines.append('')
    lines.append('【做功方向】{}'.format(gong_text))
    for item in d['gong_ways']:
        if item['state'] != '成立':
            continue
        behavior = GONG_WAY_XIANG[item['name']]
        lines.append('　　{}（{}　→　{}）：{}'.format(
            item['name'],
            '、'.join(item['src']), '、'.join(item['dst']),
            behavior))

    lines.append('')
    lines.append('【體用配置】')
    ti_on = [SHEN_FULL[s] for s in TI_SHENS if shen_strength(s, d['power']) != '無']
    yong_on = [SHEN_FULL[s] for s in YONG_SHENS
               if shen_strength(s, d['power']) != '無']
    lines.append('　　體：{}'.format('、'.join(ti_on) or '全無，無資源可運用'))
    lines.append('　　用：{}'.format('、'.join(yong_on) or '全無，無目標可獲取'))

    lines.append('')
    lines.append('【暗局】')
    if not d['fushen']:
        lines.append('　　原局飛不出伏神，格局全在明處。')
    else:
        for item in d['fushen']:
            lines.append('　　{}{}（{}）　{}'.format(
                pad(item['method'], 10), item['char'], item['shen'],
                item['gong_tag']))
        if d['an_yao']:
            lines.append('　　暗藥：{}——伏神即解藥，待時而發之命。'.format(
                '、'.join(d['an_yao'])))
        else:
            lines.append('　　暗局飛出的伏神都不是所需之藥，暫只能作「暗能量」看。')

    lines.append('')
    lines.append('【應期抓法】')
    if d['dayuns']:
        hot = [(dy['ganzhi'], eff) for dy in d['dayuns'] for eff in dy['effects']
               if eff[1].startswith('吉') or eff[1] == '凶多吉少']
        if hot:
            for gz, eff in hot[:8]:
                lines.append('　　大運{}：{}／{}／{}'.format(
                    gz, eff[0], eff[1], eff[2]))
            if len(hot) > 8:
                lines.append('　　（其餘見第六步）')
        else:
            lines.append('　　各步大運與原局無明顯作用，應期主要看流年引動。')
    else:
        lines.append('　　無起運年份，應期需另以四柱與流年自行推算。')

    lines.append('')
    lines.append('【一句話總斷】')
    lines.append('　　日主{}，{}。{}'.format(me, gong_text, geju['summary']))
    return lines


# ==========================================================================
# 十二、命令列
# ==========================================================================

def build_pillars_from_date(options):
    from lunar_python import Lunar, Solar
    if options.g:
        solar = Solar.fromYmdHms(int(options.year), int(options.month),
                                 int(options.day), int(options.time), 0, 0)
    else:
        month = int(options.month) * -1 if options.r else int(options.month)
        # lunar_python 對「該年沒有這個閏月」直接丟 Exception，
        # 在這裡換成中文提示，免得使用者看到一整串 traceback。
        try:
            solar = Lunar.fromYmdHms(int(options.year), month, int(options.day),
                                     int(options.time), 0, 0).getSolar()
        except Exception:
            if options.r:
                print('{}年沒有閏{}月，請取消 -r（閏月）後再試。'.format(
                    options.year, options.month))
            else:
                print('農曆 {}年{}月{}日 不存在，請檢查日期。'.format(
                    options.year, options.month, options.day))
            return None
    lunar = solar.getLunar()
    ba = lunar.getEightChar()
    gans = [ba.getYearGan(), ba.getMonthGan(), ba.getDayGan(), ba.getTimeGan()]
    zhis = [ba.getYearZhi(), ba.getMonthZhi(), ba.getDayZhi(), ba.getTimeZhi()]
    yun = ba.getYun(not options.n)
    return (gans, zhis, ba.getMingGong(), ba.getShenGong(), ba.getTaiYuan(), yun,
            '{}年{}月{}日'.format(solar.getYear(), solar.getMonth(), solar.getDay()),
            yun.getStartSolar().toYmdHms())


def check_pillars(options):
    """四柱格式與陰陽檢查（與 bazi.py -b 同一套規則）。"""
    for name, gz in (('年', options.year), ('月', options.month),
                     ('日', options.day), ('時', options.time)):
        if len(gz) != 2 or gz[0] not in Gan or gz[1] not in Zhi:
            print('{}柱「{}」格式有誤，請輸入兩字干支，例如 丁巳。'.format(name, gz))
            return False
        if Gan.index(gz[0]) % 2 != Zhi.index(gz[1]) % 2:
            print('{}柱「{}」的天干與地支陰陽不配（例如 甲丑、乙卯），請重新確認。'.format(
                name, gz))
            return False
    return True


def main():
    parser = argparse.ArgumentParser(
        description='盲派八字暗局做功體系 V2.0 可程式化判讀',
        formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('year', action='store', help='year')
    parser.add_argument('month', action='store', help='month')
    parser.add_argument('day', action='store', help='day')
    parser.add_argument('time', action='store', help='time')
    parser.add_argument('-b', action='store_true', default=False,
                        help='直接輸入四柱（year month day time 為四組兩字干支）')
    parser.add_argument('-g', action='store_true', default=False, help='是否採用公曆')
    parser.add_argument('-r', action='store_true', default=False,
                        help='是否為閏月，僅僅使用於農曆')
    parser.add_argument('-n', action='store_true', default=False,
                        help='是否為女，默認為男')
    parser.add_argument('--年', type=int, default=None, dest='nian',
                        help='只看這一年的應期（需有出生日期）')
    parser.add_argument('--不印類象', action='store_true', default=False,
                        dest='no_xiang', help='省略第五步類象，輸出較精簡')
    options = parser.parse_args()

    if options.b:
        if not check_pillars(options):
            sys.exit(1)
        gans = [options.year[0], options.month[0], options.day[0], options.time[0]]
        zhis = [options.year[1], options.month[1], options.day[1], options.time[1]]
        ming = shen = tai = yun = None
        date_text, start_text = '', ''
    else:
        try:
            built = build_pillars_from_date(options)
        except ValueError:
            print('日期格式有誤，請確認年、月、日、時都是整數。')
            sys.exit(1)
        if built is None:
            # build_pillars_from_date 已經印好中文原因了。
            sys.exit(1)
        (gans, zhis, ming, shen, tai, yun, date_text,
         start_text) = built

    data = analyze(gans, zhis, ming=ming, shen=shen, tai=tai, yun=yun,
                   start_text=start_text, year_only=options.nian,
                   female=options.n)
    data['date_text'] = date_text
    data['start_text'] = start_text
    render(data, show_xiang=not options.no_xiang)


if __name__ == '__main__':
    main()