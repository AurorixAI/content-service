import psycopg2
import json
import re

def clean_str(s):
    if not isinstance(s, str):
        return s
    # 1. Strip inner dollars from \dfrac or exponents like \frac{$x^{2}$+4}{5} -> \frac{x^{2}+4}{5}
    s = re.sub(r'\\dfrac\{([^}]+)\}\{\$([^$]+)\$\}', r'\\dfrac{\1}{\2}', s)
    s = re.sub(r'\\dfrac\{\$([^$]+)\$\}\{([^}]+)\}', r'\\dfrac{\1}{\2}', s)
    s = re.sub(r'\\frac\{([^}]+)\}\{\$([^$]+)\$\}', r'\\frac{\1}{\2}', s)
    s = re.sub(r'\\frac\{\$([^$]+)\$\}\{([^}]+)\}', r'\\frac{\1}{\2}', s)
    s = re.sub(r'\\frac\{\$([^$]+)\$\}\{\$([^$]+)\$\}', r'\\frac{\1}{\2}', s)
    
    # 2. Fix inner dollars inside $...$ like $\frac{$x^{2}$+4}{5}$ -> $\frac{x^{2}+4}{5}$
    s = re.sub(r'\$x\^\{(\d+)\}\$', r'x^{\1}', s)
    s = re.sub(r'\$x\^(\d+)\$', r'x^{\1}', s)
    
    # 3. Fix unclosed $(-\infty at end of sentence -> $(-\infty; 0)$
    s = re.sub(r'\$\(-\\infty$', r'$(-\\infty; 0)$', s)
    
    # 4. Fix bare powers inside error analysis like 6x^2 -> 6x^{2} or $6x^{2}$
    s = re.sub(r'\b(\d+x\^\d+)\b', r'$\1$', s)
    s = re.sub(r'\b(-\d+x\^\d+)\b', r'$\1$', s)
    s = re.sub(r'\$+(\d+x\^\d+)\$+', r'$\1$', s)
    
    # 5. Fix \Deltax -> \Delta x, \quady -> \quad y
    s = re.sub(r'\\Deltax\b', r'\\Delta x', s)
    s = re.sub(r'\\quad([a-zA-Z])', r'\\quad \1', s)
    return s

def clean_json_obj(obj):
    if isinstance(obj, str):
        return clean_str(obj)
    elif isinstance(obj, list):
        return [clean_json_obj(x) for x in obj]
    elif isinstance(obj, dict):
        return {k: clean_json_obj(v) for k, v in obj.items()}
    return obj

conn_d = psycopg2.connect(dbname='algo_diagnostic', user='algo', password='algo_password', host='127.0.0.1', port=5433)
cur_d = conn_d.cursor()

cur_d.execute("SELECT id, report_json FROM diag_reports;")
reports = cur_d.fetchall()

updated = 0
for rid, rjson in reports:
    if isinstance(rjson, str):
        rjson = json.loads(rjson)
    cleaned = clean_json_obj(rjson)
    cur_d.execute("UPDATE diag_reports SET report_json = %s::jsonb WHERE id = %s", (json.dumps(cleaned, ensure_ascii=False), rid))
    updated += 1

conn_d.commit()
print(f"Sanitized all {updated} diagnostic reports in algo_diagnostic DB.")
