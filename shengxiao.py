#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author: bazimaster
# CreateDate: 2019-2-21

import argparse
from datas import shengxiaos, zhi_atts

def output(des, key):
    print()
    print(des, end='')
    for item in zhi_atts[zhi][key]:
        print(shengxiaos[item], end='')       

description = '''
'''
parser = argparse.ArgumentParser(description=description,
                                 formatter_class=argparse.RawTextHelpFormatter)
parser.add_argument('shengxiao', action="store", help=u'生肖')
parser.add_argument('--version', action='version',
                    version='%(prog)s 0.1 Rongzhong xu 2019 03 06 ')
options = parser.parse_args()

if options.shengxiao not in shengxiaos.inverse:
    print("請輸入正確的生肖：")
    print(shengxiaos.inverse.keys())
else:
    print("你的生肖是：", options.shengxiao)
    zhi = shengxiaos.inverse[options.shengxiao]
    print("你的年支是：", zhi)
    print("="*80) 
    print("合生肖是合八字的一小部分，有一定參考意義，但是不是全部。") 
    print("以下為相合的生肖：") 
    print("="*80) 
    output("與你三合的生肖：", '合')  
    output("與你六合的生肖：", '六')      
    output("與你三會的生肖：", '會')
    print()
    print("="*80) 
    print("以下為不合的生肖：") 
    print("="*80)     
    output("與你相沖的生肖：", '沖')  
    output("你刑的生肖：", '刑')
    output("被你刑的生肖：", '被刑') 
    output("與你相害的生肖：", '害')     
    output("與你相破的生肖：", '破') 
    print()
    print("="*80) 
    print("如果生肖同時在你的合與不合中，則做加減即可。") 
    print("比如豬對於虎，有一個相破，有一六合，抵消就為平性。") 