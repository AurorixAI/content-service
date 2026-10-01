# -*- coding: utf-8 -*-
# Shared helpers for batch-drill split specs (exec'd by specs/split_d*.py). Every distractor names the concrete mistake.
from fractions import Fraction as Fr
from decimal import Decimal as D, getcontext
getcontext().prec = 40
SPLIT = {}
def P(q, k, d, yn=False): return {"q": q, "k": k, "d": d, "yesno": yn}
def T(parent, why, parts): SPLIT[parent] = {"why": why, "parts": parts}
B = "пачка из нескольких однотипных вычислений в одной задаче с выбором ответа (ответ угадывался сравнением вариантов, время ученика — на все пункты сразу); оставлены характерные пункты, каждый — отдельная задача"
EXPR = "составление выражения и несколько его значений в одной задаче с выбором ответа; разделены на вопрос о выражении и вопрос о значении"

def num(x):
    x = D(str(x))
    if x == x.to_integral_value():
        n = int(x); s = "{:,}".format(abs(n)).replace(",", "\\,") if abs(n) >= 10000 else str(abs(n))
        return ("-" if n < 0 else "") + s
    s = format(x.normalize(), "f"); i, f = s.split(".")
    return i + "{,}" + f
def src(s): return s.replace(".", "{,}")
def _nv(v):
    t = v.replace("$", "").replace("{,}", ".").replace("\\,", "").replace("\\%", "").replace("%", "").strip()
    for u in (" кг", " г", " т", " мин", " ч", " км", " м", " р.", " л", " мл", "^{\\circ}"):
        t = t.replace(u, "")
    try: return D(t)
    except Exception: return v
def uniq(key, cands, n=3):
    d, seen = [], {_nv(key)}
    for v, w in cands:
        if not w: continue
        if _nv(v) not in seen: seen.add(_nv(v)); d.append((v, w))
    assert len(d) >= n, (key, d)
    return d[:n]

PLN = {0: "единиц", 1: "десятых", 2: "сотых", 3: "тысячных", 4: "десятитысячных", 5: "стотысячных", -1: "десятков", -2: "сотен", -3: "тысяч"}
def rnd(x, place, word):
    x = D(x)
    def r(v, pl):
        q = D(1).scaleb(-pl); return (v / q).quantize(D(1), rounding="ROUND_HALF_UP") * q
    def show(v, pl):
        v = v.normalize() if v != v.to_integral_value() else D(int(v)); s = num(v)
        if pl > 0 and "{,}" not in s: s += "{,}" + "0" * pl
        elif pl > 0:
            have = len(s.split("{,}")[1])
            if have < pl: s += "0" * (pl - have)
        return "$%s$" % s
    kv = r(x, place); key = show(kv, place); q = D(1).scaleb(-place)
    trunc = (x / q).quantize(D(1), rounding="ROUND_DOWN") * q
    up = (x / q).quantize(D(1), rounding="ROUND_UP") * q
    casc = r(r(x, place + 1), place)
    c = []
    if trunc != kv: c.append((show(trunc, place), r"Ученик отбросил цифры после разряда %s без округления; следующая цифра $5$ или больше, поэтому последняя сохраняемая цифра увеличивается." % PLN[place]))
    if up != kv: c.append((show(up, place), r"Ученик увеличил последнюю сохраняемую цифру, хотя следующая за ней цифра меньше $5$."))
    if casc != kv: c.append((show(casc, place), r"Ученик округлял по шагам (сначала до %s, потом до %s); округлять нужно сразу, глядя только на следующую цифру." % (PLN[place + 1], PLN[place])))
    for pl in (place + 1, place - 1, place + 2, place - 2):
        if pl in PLN: c.append((show(r(x, pl), pl), r"Ученик округлил до %s, а не до %s." % (PLN[pl], PLN[place])))
    ts = show(trunc, place).strip("$")
    if up != trunc and ts.endswith("9"):
        c.append(("$" + ts[:-1] + "10$", r"Ученик при округлении записал $10$ в разряд %s вместо переноса единицы в старший разряд." % PLN[place]))
    q1 = D(1).scaleb(-(place + 1))
    c.append((show((x / q1).quantize(D(1), rounding="ROUND_DOWN") * q1, place + 1), r"Ученик отбросил цифры, оставив лишний разряд (%s); нужно округлить до %s." % (PLN[place + 1], PLN[place])))
    return P(r"Округлите число $%s$ до %s." % (src(str(x)) if "." in str(x) else num(x), word), key, uniq(key, c))

def mulk(x, k, stem="Найдите значение произведения"):
    """x * k where k is a power of ten (10, 100, 0.1, 0.01 ...)."""
    X, K = D(x), D(k); key = "$%s$" % num(X * K)
    c = [("$%s$" % num(X * K * 10), r"Ученик сдвинул запятую на один разряд меньше, чем нужно."),
         ("$%s$" % num(X * K / 10), r"Ученик сдвинул запятую на лишний разряд."),
         ("$%s$" % num(X / K), r"Ученик сдвинул запятую не в ту сторону: умножение на $%s$ %s." % (num(K), "уменьшает число" if K < 1 else "увеличивает число"))]
    return P(r"%s $%s\cdot%s$." % (stem, src(x), num(K)), key, uniq(key, c))
def divk(x, k, stem="Выполните деление"):
    X, K = D(x), D(k); key = "$%s$" % num(X / K)
    c = [("$%s$" % num(X * K), r"Ученик умножил на $%s$ вместо деления: деление на $%s$ %s." % (num(K), num(K), "увеличивает число" if K < 1 else "уменьшает число")),
         ("$%s$" % num(X / K * 10), r"Ученик сдвинул запятую на лишний разряд."),
         ("$%s$" % num(X / K / 10), r"Ученик сдвинул запятую на один разряд меньше, чем нужно.")]
    return P(r"%s $%s:%s$." % (stem, src(x), num(K)), key, uniq(key, c))
def pct2dec(p):
    Pn = D(p); key = "$%s$" % num(Pn / 100)
    c = [("$%s$" % num(Pn / 10), r"Ученик разделил на $10$ вместо $100$: процент — сотая часть."),
         ("$%s$" % num(Pn / 1000), r"Ученик разделил на $1000$ вместо $100$."),
         ("$%s$" % num(Pn), r"Ученик просто убрал знак процента, не разделив на $100$.")]
    return P(r"Запишите в виде десятичной дроби $%s\%%$." % src(p), key, uniq(key, c))
def dec2pct(x):
    X = D(x); key = r"$%s\%%$" % num(X * 100)
    c = [(r"$%s\%%$" % num(X * 10), r"Ученик умножил на $10$ вместо $100$."),
         (r"$%s\%%$" % num(X), r"Ученик просто приписал знак процента, не умножив на $100$."),
         (r"$%s\%%$" % num(X * 1000), r"Ученик умножил на $1000$ вместо $100$.")]
    return P(r"Запишите в процентах десятичную дробь $%s$." % src(x), key, uniq(key, c))
def numpct(p, v):
    Pn, V = D(p), D(v); key = "$%s$" % num(V * 100 / Pn)
    c = [("$%s$" % num(V * Pn / 100), r"Ученик нашёл $%s\%%$ от данного числа, а нужно найти число по его части: $%s:%s\cdot100$." % (src(p), src(v), src(p))),
         ("$%s$" % num(V * 100), r"Ученик разделил на $1\%%$ вместо $%s\%%$." % src(p)),
         ("$%s$" % num(V * Pn), r"Ученик умножил на число процентов вместо деления."),
         ("$%s$" % num(V * 100 / Pn / 10), r"Ученик разделил на $10$ лишний раз: число, $%s\%%$ которого равны $%s$, равно $%s\cdot\dfrac{100}{%s}$." % (src(p), src(v), src(v), src(p))),
         ("$%s$" % num(V * 100 / Pn * 10), r"Ученик ошибся в разряде: умножил на $1000$ вместо $100$.")]
    return P(r"Найдите число, если $%s\%%$ этого числа %s $%s$." % (src(p), "равен" if D(p) == 1 else "равны", src(v)), key, uniq(key, c))
def fracof(f, base):
    F, Bv = D(f), D(base); key = "$%s$" % num(F * Bv)
    c = [("$%s$" % num(Bv / F), r"Ученик разделил на $%s$ вместо умножения." % src(f)),
         ("$%s$" % num(F * Bv * 10), r"Ученик ошибся в разряде при умножении десятичной дроби."),
         ("$%s$" % num(F * Bv / 10), r"Ученик ошибся в разряде при умножении десятичной дроби.")]
    return P(r"Найдите $%s$ числа $%s$." % (src(f), src(base)), key, uniq(key, c))
def power(b, e, stem="Найдите значение"):
    key = "$%s$" % num(b ** e)
    c = [("$%s$" % num(b * e), r"Ученик умножил основание на показатель: $%d\cdot%d$; степень — произведение $%d$ одинаковых множителей $%d$." % (b, e, e, b)),
         ("$%s$" % num(e ** b), r"Ученик перепутал основание и показатель: $%d^{%d}$ вместо $%d^{%d}$." % (e, b, b, e)) if e ** b < 10 ** 5 else ("", ""),
         ("$%s$" % num(b ** (e - 1)), r"Ученик взял на один множитель меньше: $%d^{%d}$ вместо $%d^{%d}$." % (b, e - 1, b, e)),
         ("$%s$" % num(b + e), r"Ученик сложил основание и показатель."),
         ("$%s$" % num(b ** (e + 1)), r"Ученик взял на один множитель больше: $%d^{%d}$ вместо $%d^{%d}$." % (b, e + 1, b, e))]
    return P(r"%s $%d^{%d}$." % (stem, b, e), key, uniq(key, c))
def mixed2dec(w, n, den, stem="Представьте в виде десятичной дроби число"):
    val = D(w) + D(n) / D(den); key = "$%s$" % num(val)
    c = [("$%s$" % num(D(w) + D(n) / D(10 ** len(str(n)))), r"Ученик записал числитель сразу после запятой, не учтя знаменатель $%d$." % den),
         ("$%s$" % num(D(w) + D(n) / D(den * 10)), r"Ученик поставил лишний ноль после запятой: знаменатель $%d$ определяет число знаков после запятой." % den),
         ("$%s$" % num(D(w) * D(10) ** len(str(n)) + D(n)) if w else "", r"Ученик приписал числитель к целой части без запятой."),
         ("$%s$" % num(D(w) + D(n) / D(den * 100)), r"Ученик поставил два лишних нуля после запятой."),
         ("$%s$" % num(D(n)), r"Ученик записал числитель как целое число, потеряв знаменатель.")]
    frac = r"%d\dfrac{%d}{%d}" % (w, n, den) if w else r"\dfrac{%d}{%d}" % (n, den)
    return P(r"%s $%s$." % (stem, frac), key, uniq(key, c))
def frac2dec(n, den, w=0, stem="Представьте в виде десятичной дроби число"):
    """Non-decimal denominator (4, 8, 25, ...)."""
    val = D(w) + D(n) / D(den); key = "$%s$" % num(val)
    c = [("$%s{,}%d%d$" % (num(w), n, den), r"Ученик записал числитель и знаменатель подряд после запятой; дробь нужно привести к знаменателю $10$, $100$ или $1000$ либо разделить числитель на знаменатель."),
         ("$%s{,}%d$" % (num(w), n), r"Ученик записал числитель после запятой, не разделив его на знаменатель $%d$." % den),
         ("$%s$" % num(D(w) + D(n) / D(den) / 10), r"Ученик ошибся в разряде при делении: $\dfrac{%d}{%d}=%s$." % (n, den, num(D(n) / D(den)))),
         ("$%s$" % num(D(w) + D(n) / D(den) * 10), r"Ученик ошибся в разряде при делении: $\dfrac{%d}{%d}=%s$." % (n, den, num(D(n) / D(den))))]
    frac = r"%d\dfrac{%d}{%d}" % (w, n, den) if w else r"\dfrac{%d}{%d}" % (n, den)
    return P(r"%s $%s$." % (stem, frac), key, uniq(key, c))
def cmpd(a, b, key_sign):
    A, Bv = src(a), src(b)
    signs = {">": r"$%s>%s$" % (A, Bv), "<": r"$%s<%s$" % (A, Bv), "=": r"$%s=%s$" % (A, Bv)}
    why = {">": r"Ученик сравнил числа неверно: сравнивать нужно поразрядно, начиная с целой части.",
           "<": r"Ученик сравнил количество цифр после запятой, а не значения разрядов.",
           "=": r"Ученик решил, что числа равны; сравнение по разрядам показывает разницу."}
    if key_sign == "=": why[">"] = why["<"] = r"Ученик не учёл, что нули в конце десятичной дроби не меняют её значения."
    return P(r"Сравните числа $%s$ и $%s$." % (A, Bv), signs[key_sign], [(signs[s], why[s]) for s in (">", "<", "=") if s != key_sign], yn=True)
def calc(expr, key_v, op):
    """Calculator arithmetic; distractors model decimal-point slips."""
    K = D(key_v); key = "$%s$" % num(K)
    c = [("$%s$" % num(K * 10), r"Ученик ошибся в положении запятой в ответе."),
         ("$%s$" % num(K / 10), r"Ученик ошибся в положении запятой в ответе."),
         ("$%s$" % num(K * 100), r"Ученик потерял запятую в одном из чисел.")]
    return P(r"Выполните %s $%s$." % (op, expr), key, uniq(key, c))
