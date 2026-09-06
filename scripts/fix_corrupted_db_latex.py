import psycopg2
import json
import re

def fix_latex_string(s: str) -> str:
    if not s or not isinstance(s, str):
        return s

    # 1. Unescape double backslashes before LaTeX commands: \\sin -> \sin, \\cos -> \cos
    s = re.sub(r'\\{2,}([a-zA-Z]+)', r'\\\1', s)

    # 2. Fix \lim\limits or \lim\lim its -> \lim
    s = re.sub(r'\\lim(\\limits|\s+its|\s+\\limits|\s*\\limits)', r'\\lim', s)

    # 3. Add space between trig/func command and variable/arg: \sinx -> \sin x, \cosx -> \cos x, \cos2x -> \cos 2x
    s = re.sub(r'\\(sin|cos|tan|cot|tg|ctg|arcsin|arccos|arctan|arcctg|lim|ln|log|lg)([a-zA-Z0-9])', r'\\\1 \2', s)

    # 4. Fix \dfrac in inline math -> \frac (prevents huge line height breaks)
    s = s.replace(r'\dfrac', r'\frac')

    # 5. Fix double dollar signs $$...$$ -> $...$ where single inline is intended
    s = re.sub(r'\$\$\s*([^$]+?)\s*\$\$', r'$\1$', s)

    return s

def fix_dmeta(dmeta):
    if not dmeta:
        return dmeta
    if isinstance(dmeta, str):
        try:
            dmeta = json.loads(dmeta)
        except Exception:
            return dmeta
    if isinstance(dmeta, list):
        new_list = []
        for item in dmeta:
            if isinstance(item, dict):
                new_item = dict(item)
                for k in ['value', 'value_latex', 'explanation', 'error_logic']:
                    if k in new_item and isinstance(new_item[k], str):
                        new_item[k] = fix_latex_string(new_item[k])
                new_list.append(new_item)
            else:
                new_list.append(item)
        return new_list
    return dmeta

def main():
    conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
    cur = conn.cursor()

    cur.execute("""
        SELECT id, question_text, question_latex, correct_answer_latex, distractor_meta
        FROM tasks_master
    """)
    rows = cur.fetchall()

    fixed_count = 0
    for r in rows:
        tid, qt, ql, cal, dm = r[0], r[1], r[2], r[3], r[4]

        new_qt = fix_latex_string(qt)
        new_ql = fix_latex_string(ql)
        new_cal = fix_latex_string(cal)
        new_dm = fix_dmeta(dm)

        if new_qt != qt or new_ql != ql or new_cal != cal or new_dm != dm:
            cur.execute("""
                UPDATE tasks_master
                SET question_text = %s,
                    question_latex = %s,
                    correct_answer_latex = %s,
                    distractor_meta = %s::jsonb
                WHERE id = %s
            """, (new_qt, new_ql, new_cal, json.dumps(new_dm, ensure_ascii=False) if new_dm else None, tid))
            fixed_count += 1

    conn.commit()
    print(f"Successfully cleaned {fixed_count} task records in algo_content database!")

if __name__ == '__main__':
    main()
