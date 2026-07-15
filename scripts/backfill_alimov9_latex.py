#!/usr/bin/env python3
import sys
import os
import json

sys.path.insert(0, "/app")
os.environ.setdefault('APP_ENV', 'production')

from sqlalchemy import create_engine, text
from src.core.config import get_settings
from src.pipeline.answer_sympy_gate import to_answer_latex

def main():
    print("=== Запуск локального накала LaTeX для Алимова 9 класс ===")
    settings = get_settings()
    engine = create_engine(settings.database_url)
    
    textbook_id = "2aa7af81-af13-42f9-a26b-e7e6bebaa4e6"
    
    with engine.connect() as conn:
        # Получаем все задачи Алимова
        rows = conn.execute(text("""
            SELECT tm.id, tm.correct_answer, tm.answer_type, tm.distractor_meta
            FROM tasks_master tm
            JOIN textbook_toc toc ON toc.id = tm.toc_id
            WHERE toc.textbook_id = :textbook_id
        """), {"textbook_id": textbook_id}).fetchall()
        
    print(f"Найдено задач для обработки: {len(rows)}")
    
    updated_count = 0
    with engine.begin() as conn:
        for tid, correct_answer, answer_type, dmeta in rows:
            # 1. Генерируем LaTeX для правильного ответа
            correct_latex = to_answer_latex(correct_answer, answer_type)
            
            # 2. Генерируем LaTeX для дистракторов
            new_dmeta = []
            if dmeta:
                try:
                    for d in dmeta:
                        if isinstance(d, dict) and d.get("value"):
                            val = str(d["value"]).strip()
                            d["value_latex"] = to_answer_latex(val, answer_type)
                        new_dmeta.append(d)
                except Exception as e:
                    print(f"Ошибка парсинга дистракторов для {tid}: {e}")
                    new_dmeta = dmeta
            
            # 3. Записываем в базу
            conn.execute(text("""
                UPDATE tasks_master
                SET correct_answer_latex = :cal,
                    distractor_meta = :dmeta,
                    updated_at = NOW()
                WHERE id = :id
            """), {
                "cal": correct_latex,
                "dmeta": json.dumps(new_dmeta, ensure_ascii=False) if isinstance(new_dmeta, list) else dmeta,
                "id": tid
            })
            updated_count += 1

    print(f"Успешно обработано и обновлено задач в БД: {updated_count}")

if __name__ == "__main__":
    main()
