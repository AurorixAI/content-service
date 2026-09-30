# -*- coding: utf-8 -*-
# Класс «сравнение / знак действия» (найден самопроверкой выборки Виленкин 5, 26.09): спецификация собрана gen_v5b.py → v5b_P.json
import json
P = json.load(open("/audit/v5b_P.json"))
for e in P.values():
    if "dnew" in e: e["dnew"] = {int(i): tuple(v) for i, v in e["dnew"].items()}
    if "dadd" in e: e["dadd"] = [tuple(x) for x in e["dadd"]]
    if "qrep" in e: e["qrep"] = tuple(e["qrep"])
