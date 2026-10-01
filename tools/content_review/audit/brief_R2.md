# R2 — Исправитель (Sonnet)

Рабочая папка: `/Users/arslan/Desktop/ALGO/content-service/tools/content_review` (в docker монтируется как `/audit`).
Вход: строки находок `audit/find_NNN.jsonl` для указанных пачек + сами задачи из `audit/batch_NNN.json`.
Сначала ПЕРЕПРОВЕРЬ каждую находку вычислением (python3/sympy). Ложную — пропусти и запиши в `audit/rejected_W.jsonl` с причиной.

Выходы (W — номер волны, дан в задании):
1. `specs/fix_ctrl{W}.py` — исправления в принятом формате (образец: `specs/fix_ctrl140.py`):
   ```python
   S = "волна W, проход по базе"; P = {}
   def E(t, why, **kw): P[t] = dict(src=S, why=why, **kw)
   E('ID', 'причина', k=r'$новый ключ$', q=r'новое условие', qrep=('старое','новое'),
     dnew={i: (r'$значение$', r'Ученик …')}, dwhy={i: r'Ученик …'}, dval={i: r'$значение$'}, drop=[i])
   ```
   Правила: ключ менять ТОЛЬКО если верное значение подтверждено вычислением. Каждое объяснение начинается с «Ученик …» и, если выполнить описанную ошибку, ДАЁТ своё значение (проверь). Ни один дистрактор не равен ключу. Дистракторов ≥2 (да/нет — 1). LaTeX: числа с запятой `{,}`, дроби `\dfrac`, всё в `$…$`. В r-строках не использовать `%`-форматирование при наличии `\%`; не писать `f\'` (штрих: `f^{\prime}`).
2. Составные задачи (`multi`) — `specs/split_x{W}.py` (образец: `specs/split_n4.py`, хелперы `specs/_hlp.py`): 2–3 подзадачи на родителя с независимым ключом и ≥3 объяснёнными дистракторами.
3. Нерешаемые без данных — `deact_w{W}.json` `{id: "причина"}`.
4. `audit/changes_W.tsv` — по строке на КАЖДОЕ изменение ключа или условия: `id<TAB>старое<TAB>новое<TAB>вычисление`.

Прогон (без применения!):
```
cp specs/fix_ctrl{W}.py fix_ctrl{W}.py && ./sim.sh ctrl{W} && ./runv.sh val_spec.py ctrl{W} && python3 kx.py ctrl{W} && node katex_check.js ./kx_ctrl{W}.json
bash split_run.sh x{W} check
```
Всё должно быть `bad 0` / `problems 0` / `errors 0`; иначе исправь спецификацию.
В чат вернуть ОДНУ строку: `wave W: fixes F, splits S(→C), deact D, rejected R, key/cond changes K, checks OK|FAIL`.
НИЧЕГО не применять к базе.
