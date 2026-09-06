import psycopg2
import json
import re

def fix_str(s: str) -> str:
    if not s or not isinstance(s, str):
        return s
    
    # 1. Unescape \\sin -> \sin, \\cos -> \cos
    s = re.sub(r'\\{2,}([a-zA-Z]+)', r'\\\1', s)
    
    # 2. Add space to trig/func commands: \sinx -> \sin x, \cosx -> \cos x, \cos2x -> \cos 2x
    s = re.sub(r'\\(sin|cos|tan|cot|tg|ctg|arcsin|arccos|arctan|arcctg|lim|ln|log|lg)([a-zA-Z0-9])', r'\\\1 \2', s)

    # 3. Fix \lim\limits or \lim\lim -> \lim
    s = re.sub(r'\\lim(\\limits|\s+its|\s+\\limits|\s*\\limits|\\lim)', r'\\lim', s)

    # 4. Fix \dfrac -> \frac in inline mode
    s = s.replace(r'\dfrac', r'\frac')

    # 5. Fix double dollars $$...$$ -> $...$
    s = re.sub(r'\$\$\s*([^$]+?)\s*\$\$', r'$\1$', s)

    return s

def clean_obj(obj):
    if isinstance(obj, dict):
        return {k: clean_obj(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_obj(v) for v in obj]
    elif isinstance(obj, str):
        return fix_str(obj)
    return obj

def main():
    conn = psycopg2.connect(dbname='algo_diagnostic', user='algo', password='algo_password', host='127.0.0.1', port=5433)
    cur = conn.cursor()

    cur.execute("SELECT id, report_json FROM diag_reports")
    rows = cur.fetchall()

    cleaned_count = 0
    for rid, rjson in rows:
        if isinstance(rjson, str):
            rjson = json.loads(rjson)
        
        cleaned = clean_obj(rjson)
        if json.dumps(cleaned, ensure_ascii=False) != json.dumps(rjson, ensure_ascii=False):
            cur.execute("UPDATE diag_reports SET report_json = %s::jsonb WHERE id = %s", (json.dumps(cleaned, ensure_ascii=False), rid))
            cleaned_count += 1

    conn.commit()
    print(f"Cleaned {cleaned_count} report_json records in algo_diagnostic database!")

if __name__ == '__main__':
    main()
