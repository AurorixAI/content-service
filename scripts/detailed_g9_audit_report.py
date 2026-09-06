import sys, os, json, re
sys.path.insert(0, '/app')
os.environ.setdefault('APP_ENV', 'production')

import psycopg2
import psycopg2.extras
from src.core.config import get_settings
from src.pipeline.compound_detect import detect_compound

def is_garbage_task(qt: str, ans: str) -> tuple[bool, str]:
    qt_clean = re.sub(r"\s+", " ", qt).strip()
    ans_clean = re.sub(r"\s+", " ", ans).strip()
    
    if not qt_clean:
        return True, "Empty question"
    
    if ans_clean and ans_clean.lower() in qt_clean.lower():
        if "докажите" not in qt_clean.lower() and "свойства функции" not in qt_clean.lower() and "тождество" not in qt_clean.lower():
            if ":" in qt_clean:
                tail = qt_clean.split(":", 1)[-1].strip()
                tail_clean = re.sub(r"\s*(м|см|дм|мм|кг|г|л|°)\.?$", "", tail, flags=re.I).strip()
                ans_no_units = re.sub(r"\s*(м|см|дм|мм|кг|г|л|°)\.?$", "", ans_clean, flags=re.I).strip()
                if tail_clean == ans_no_units or tail_clean in (f"a) {ans_no_units}", f"б) {ans_no_units}", f"в) {ans_no_units}", f"г) {ans_no_units}"):
                    return True, f"Answer is in question tail after colon: '{tail}'"
            if len(qt_clean) < 35:
                if not any(word in qt_clean.lower() for word in ["найдите", "решите", "вычислите", "упростите"]):
                    return True, "Short question containing answer"
                    
    if "неравенство" in qt_clean.lower() and ":" in qt_clean:
        tail = qt_clean.split(":", 1)[-1].strip()
        if re.match(r"^[a-zA-Z\s\)]*[\[\()]-?\d+.*[\]\)]$", tail):
            return True, "Nonsense inequality tail (contains interval instead of expression)"
            
    if any(p in qt_clean.lower() for p in ["не дано", "нет условия", "не указано", "без условия"]):
        return True, "Placeholder for missing condition"
        
    return False, ""

def run_audit():
    settings = get_settings()
    conn = psycopg2.connect(settings.database_url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    # 1. Load textbook metadata
    cur.execute("SELECT textbook_id, title FROM textbooks WHERE class_level = 9 LIMIT 1")
    tb = cur.fetchone()
    tb_id = tb[0]
    tb_title = tb[1]
    
    # 2. Fetch all Grade 9 tasks with TOC info
    cur.execute("""
        SELECT 
            tm.id, tm.question_text, tm.correct_answer, tm.answer_type,
            tm.tags, tm.distractor_meta, tm.is_active,
            toc.id as toc_id, toc.number as toc_number, toc.title as toc_title,
            tt.exercise_number
        FROM tasks_master tm
        JOIN textbook_toc toc ON toc.id = tm.toc_id
        JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
        LEFT JOIN textbook_tasks tt ON tt.task_id = tm.id AND tt.textbook_id = tb.textbook_id
        WHERE tb.class_level = 9
        ORDER BY toc.id, tt.exercise_number
    """)
    rows = [dict(r) for r in cur.fetchall()]
    
    # 3. Categorize tasks
    para_stats = {}
    garbage_tasks = []
    compound_tasks = []
    missing_distractors = []
    failed_verification = []
    
    for r in rows:
        tid = r['id']
        qt = r['question_text'] or ""
        ans = r['correct_answer'] or ""
        atype = r['answer_type'] or "exact_number"
        tags = r['tags'] or {}
        dist_meta = r['distractor_meta'] or []
        toc_id = r['toc_id']
        toc_num = r['toc_number']
        toc_title = r['toc_title']
        ex_num = r['exercise_number'] or ""
        
        # Init stats
        if toc_id not in para_stats:
            para_stats[toc_id] = {
                'number': toc_num,
                'title': toc_title,
                'total': 0,
                'active': 0,
                'has_distractors': 0,
                'no_distractors_gaps': 0,
                'verified': 0,
                'failed_verify': 0,
                'compound': 0,
                'garbage': 0
            }
            
        p = para_stats[toc_id]
        p['total'] += 1
        if r['is_active']:
            p['active'] += 1
            
        # A. Garbage check
        is_g, g_reason = is_garbage_task(qt, ans)
        if is_g:
            p['garbage'] += 1
            garbage_tasks.append({
                'id': tid, 'para': f'{toc_num} {toc_title[:30]}', 'qt': qt[:100], 'ans': ans, 'reason': g_reason, 'active': r['is_active']
            })
            
        # B. Distractor gaps
        # Distractors are useful for: expression, fraction, decimal, exact_number, equation_solution, inequality, set, multiple_choice
        supports_dist = atype in ('exact_number', 'decimal', 'fraction', 'expression', 'equation_solution', 'inequality', 'set', 'multiple_choice')
        has_dist = len(dist_meta) >= 3
        if has_dist:
            p['has_distractors'] += 1
        elif supports_dist and r['is_active']:
            p['no_distractors_gaps'] += 1
            missing_distractors.append({
                'id': tid, 'para': f'{toc_num} {toc_title[:30]}', 'qt': qt[:100], 'ans': ans, 'type': atype
            })
            
        # C. Verification status
        # smart_verify_status can be: confirmed, verified_match, verified_corrected, ai_consensus_override
        # Failed can be: failed_at_llm, failed_at_sympy, needs_human_review, or quarantine_v3_needs_review
        is_verified = (
            tags.get('quarantine_v3_verified') == True or
            tags.get('smart_verify_status') in ('confirmed', 'verified_match', 'verified_corrected', 'ai_consensus_override')
        )
        is_failed = (
            tags.get('quarantine_v3_needs_review') == True or
            tags.get('smart_verify_status') in ('failed_at_llm', 'failed_at_sympy', 'needs_human_review')
        )
        if is_verified:
            p['verified'] += 1
        if is_failed:
            p['failed_verify'] += 1
            failed_verification.append({
                'id': tid, 'para': f'{toc_num} {toc_title[:30]}', 'qt': qt[:100], 'ans': ans, 
                'verify_status': tags.get('smart_verify_status'), 'ai_ans': tags.get('quarantine_v3_ai_answer') or tags.get('verified_answer')
            })
            
        # D. Compound tasks
        cd = detect_compound(
            task_id=tid,
            question_text=qt,
            correct_answer=ans,
            answer_type=atype,
            tags=tags,
            exercise_number=str(ex_num)
        )
        if cd.should_split:
            p['compound'] += 1
            compound_tasks.append({
                'id': tid, 'para': f'{toc_num} {toc_title[:30]}', 'qt': qt[:100], 'ans': ans, 'pattern': cd.pattern, 'subitems': cd.n_subitems
            })

    # 4. Generate Markdown report
    report_path = '/app/data/detailed_g9_audit_report.md'
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"# Детальный аудит оцифровки и качества контента 9 класса\n\n")
        f.write(f"**Учебник:** {tb_title} ({tb_id})\n")
        f.write(f"**Всего задач в БД:** {len(rows)}\n\n")
        
        f.write("## 1. Сводная статистика по разделам\n\n")
        f.write("| Раздел | Всего | Активных | С дистракт. | Пропуски дистракт. | Верифицировано | Требует ревью / Сбой | Составные (сплит) | Мусор |\n")
        f.write("|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|\n")
        for tid, p in sorted(para_stats.items()):
            f.write(f"| **{p['number']}** {p['title'][:40]} | {p['total']} | {p['active']} | {p['has_distractors']} | {p['no_distractors_gaps']} | {p['verified']} | {p['failed_verify']} | {p['compound']} | {p['garbage']} |\n")
            
        f.write("\n## 2. Задачи, требующие сплита (составные задачи)\n")
        f.write(f"Найдено составных задач: **{len(compound_tasks)}**\n\n")
        if compound_tasks:
            f.write("| ID задачи | Раздел | Текст вопроса | Шаблон | Подзадач |\n")
            f.write("|---|---|---|---|:---:|\n")
            for ct in compound_tasks[:40]:  # Limit to first 40 examples
                f.write(f"| {ct['id']} | {ct['para']} | {ct['qt']}... | `{ct['pattern']}` | {ct['subitems']} |\n")
            if len(compound_tasks) > 40:
                f.write(f"| ... | ... | ... | ... | ... |\n")
                f.write(f"\n*(Показано 40 примеров из {len(compound_tasks)} задачи)*\n")
        else:
            f.write("Составных задач не обнаружено. Все задачи сплитованы корректно! ✅\n")
            
        f.write("\n## 3. Задачи, не прошедшие верификацию (сбои или расхождения)\n")
        f.write(f"Найдено проблемных задач: **{len(failed_verification)}**\n\n")
        if failed_verification:
            f.write("| ID задачи | Раздел | Текст вопроса | Ответ в книге | Ответ AI | Статус |\n")
            f.write("|---|---|---|---|---|---|\n")
            for fv in failed_verification[:40]:
                f.write(f"| {fv['id']} | {fv['para']} | {fv['qt']}... | `{fv['ans']}` | `{fv['ai_ans']}` | `{fv['verify_status']}` |\n")
            if len(failed_verification) > 40:
                f.write(f"| ... | ... | ... | ... | ... | ... |\n")
                f.write(f"\n*(Показано 40 примеров из {len(failed_verification)} задачи)*\n")
        else:
            f.write("Все оцифрованные задачи успешно верифицированы! ✅\n")
            
        f.write("\n## 4. OCR мусор и технические placeholders\n")
        f.write(f"Найдено мусорных задач: **{len(garbage_tasks)}**\n\n")
        if garbage_tasks:
            f.write("| ID задачи | Раздел | Текст вопроса | Ответ | Причина | Активна |\n")
            f.write("|---|---|---|---|---|:---:|\n")
            for gt in garbage_tasks:
                f.write(f"| {gt['id']} | {gt['para']} | {gt['qt']}... | `{gt['ans']}` | {gt['reason']} | {gt['active']} |\n")
        else:
            f.write("Мусорных задач с техническими ошибками не обнаружено! ✅\n")

        f.write("\n## 5. Пропуски дистракторов (по активным задачам)\n")
        f.write(f"Найдено активных задач без дистракторов: **{len(missing_distractors)}**\n\n")
        if missing_distractors:
            f.write("| ID задачи | Раздел | Текст вопроса | Ответ | Тип |\n")
            f.write("|---|---|---|---|---|\n")
            for md in missing_distractors[:40]:
                f.write(f"| {md['id']} | {md['para']} | {md['qt']}... | `{md['ans']}` | `{md['type']}` |\n")
            if len(missing_distractors) > 40:
                f.write(f"| ... | ... | ... | ... | ... |\n")
                f.write(f"\n*(Показано 40 примеров из {len(missing_distractors)})*\n")
        else:
            f.write("Пропусков дистракторов нет! ✅\n")

    print('Audit completed successfully. Report written to', report_path)

if __name__ == '__main__':
    run_audit()
