import psycopg2
import json

conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
cur = conn.cursor()

# ─── ПРОГРЕСС ───────────────────────────────────────────────────────────────
print("=" * 70)
print("📊 ПРОГРЕСС")
print("=" * 70)

cur.execute("SELECT count(*) FROM tasks_master WHERE latex_status = 'verified';")
l_done = cur.fetchone()[0]
cur.execute("SELECT count(*) FROM tasks_master WHERE latex_status = 'partial';")
l_partial = cur.fetchone()[0]
cur.execute("SELECT count(*) FROM tasks_master WHERE latex_status IS NULL;")
l_left = cur.fetchone()[0]
total = 35251

cur.execute("SELECT count(*) FROM tasks_master WHERE verification_status = 'verified';")
sv_done = cur.fetchone()[0]
cur.execute("SELECT count(*) FROM tasks_master WHERE verification_status = 'pending';")
sv_left = cur.fetchone()[0]

print(f"\n📐 LaTeX Backfill:")
print(f"   Верифицировано : {l_done:>6} / {total}  ({l_done*100//total}%)")
print(f"   Partial        : {l_partial:>6}")
print(f"   Осталось (NULL): {l_left:>6} ({l_left*100//total}%)")

print(f"\n🧠 Smart Verify:")
print(f"   Верифицировано : {sv_done:>6} / {total}  ({sv_done*100//total}%)")
print(f"   Осталось       : {sv_left:>6} ({sv_left*100//total}%)")

# ─── АУДИТ LATEX ─────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("📐 АУДИТ КАЧЕСТВА LATEX (свежие 5 задач)")
print("=" * 70)

cur.execute("""
    SELECT id, question_latex, correct_answer_latex, distractor_meta
    FROM tasks_master
    WHERE latex_status = 'verified'
    ORDER BY id DESC LIMIT 5;
""")

ok_count = 0
bad_count = 0
for r in cur.fetchall():
    tid, ql, cal, dm_raw = r
    dm = dm_raw if isinstance(dm_raw, list) else json.loads(dm_raw or '[]')
    bad = (
        (ql and 'sqrt{$' in ql) or
        (ql and '$($' in ql) or
        (ql and '\\begin{cases}' in ql and '$$' not in ql)
    )
    mark = "✅" if not bad else "❌"
    if bad: bad_count += 1
    else: ok_count += 1
    print(f"\n{mark} {tid}")
    print(f"   question_latex : {repr(ql[:100]) if ql else 'EMPTY'}")
    print(f"   answer_latex   : {repr(cal[:70]) if cal else 'EMPTY'}")
    for i, d in enumerate(dm):
        if isinstance(d, dict):
            vl = d.get('value_latex') or d.get('value')
            print(f"   dist[{i}]: {repr(str(vl)[:65])}")

print(f"\n  → Проверено: {ok_count+bad_count} | ✅ OK: {ok_count} | ❌ Брак: {bad_count}")

# ─── АУДИТ SMART VERIFY ──────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("🧠 АУДИТ КАЧЕСТВА SMART VERIFY (свежие 5 задач)")
print("=" * 70)

cur.execute("""
    SELECT id, question_text, correct_answer, answer_type, distractor_meta
    FROM tasks_master
    WHERE verification_status = 'verified'
      AND tags->>'smart_verify_at' IS NOT NULL
    ORDER BY tags->>'smart_verify_at' DESC LIMIT 5;
""")

for r in cur.fetchall():
    tid, qt, ca, atype, dm_raw = r
    dm = dm_raw if isinstance(dm_raw, list) else json.loads(dm_raw or '[]')
    print(f"\n✅ {tid} | type={atype}")
    print(f"   Вопрос: {repr(qt[:100])}")
    print(f"   Ответ : {repr(ca)}")
    for i, d in enumerate(dm):
        if isinstance(d, dict):
            val = d.get('value') or d.get('value_latex')
            logic = d.get('error_logic') or d.get('explanation') or ''
            print(f"   dist[{i+1}]: {repr(str(val)[:45])} | {repr(str(logic)[:90])}")
