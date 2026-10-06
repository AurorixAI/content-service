"""Build manifest n01-2026-10-06-w7 (two owner decisions). Reads the local DB only; never writes to it.

Usage (from content-service):
  CONTENT_REPAIR_DATABASE_URL=... python3 -m tools.content_review.build_w7_owner_decisions
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from sqlalchemy import create_engine

from tools.content_review import guarded_repair as gr

BATCH = "n01-source-repair-2026-10-06-w7"
OUT = Path(__file__).resolve().parents[2] / "data/content_repairs/n01-2026-10-06-w7.json"
DEACT_ID, TB_ID = "GEN_G6_S38_01_C_01", "G5_TB_69_1692"


def dm(value: str, error_type: str, logic: str) -> dict:
    return {"value": value, "value_latex": value, "error_type": error_type,
            "error_logic": logic, "explanation": logic,
            "error_logic_latex": logic, "explanation_latex": logic}


QUESTION = (
    "Предприниматель Алиев собрал $40$ млн сумов. Он построил курятник за $20$ млн, "
    "купил корм на $6$ месяцев за $5$ млн и цыплят за $5$ млн; оставшиеся деньги выделил "
    "на зарплату за $6$ месяцев. Цыплята вырастают за $2$ месяца (это один цикл); после "
    "продажи мяса выручка составляет $17$ млн, и на $5$ млн покупают новых цыплят. "
    "Все циклы одинаковы. В этой модели курятник, корм и зарплата оплачены заранее из "
    "стартового капитала и в прибыль цикла не входят: прибыль цикла равна выручке минус "
    "стоимость цыплят. Налог на прибыль — $25\\%$ от прибыли. Найдите прибыль за один цикл "
    "до налога, прибыль за один цикл после налога и прибыль за $6$ месяцев ($3$ цикла) "
    "после налога (млн сумов)."
)
KEY = "$12;\\ 9;\\ 27$"
WRONG = [
    ("$12;\\ 12;\\ 36$", "tax_not_deducted",
     "Налог не вычтен: прибыль после налога принята равной прибыли до налога $12$ млн, а за три цикла $12\\cdot3=36$ млн. Нужно $12\\cdot0{,}75=9$ млн."),
    ("$7;\\ 5{,}25;\\ 15{,}75$", "prepaid_costs_deducted_again",
     "Корм и зарплата ($5+10=15$ млн за $6$ месяцев) уже оплачены из стартового капитала и в прибыль цикла не входят; вычтено ещё $15:3=5$ млн за цикл, получилось $17-5-5=7$ вместо $17-5=12$."),
    ("$12;\\ 7{,}75;\\ 23{,}25$", "tax_taken_from_revenue",
     "Налог $25\\%$ взят от выручки $17$ млн ($4{,}25$ млн), а не от прибыли $12$ млн: $12-4{,}25=7{,}75$. Правильно $12\\cdot0{,}75=9$."),
]

DEACT_REASON = ("исходная постановка неоднозначна: (2019,1,…) и (1009,1,2,…) дают 2024, после обмена "
                "2024 и 1015; переписанная Codex версия тривиальна (a+b=b+a)")
DEACT_EVIDENCE = ("Исходный набор данных допускает разные результаты после обмена (2024 и 1015), поэтому "
                  "однозначного ключа нет; редакторская замена сводится к a+b=b+a и не проверяет навык. "
                  "Обратимая деактивация по решению владельца; id, текст и ключ не удаляются.")
TB_REASON = ("Решение владельца: вернуть простую учебную модель источника. Корм, зарплата и курятник "
             "оплачены заранее и в прибыль цикла не входят, поэтому прибыль цикла равна 17−5=12 млн.")
TB_EVIDENCE = ("Исходник: капитал 40, курятник 20, корм 5, цыплята 5, зарплата 40−20−5−5=10, цикл 2 месяца, "
               "выручка 17, новые цыплята 5, налог 25% от прибыли. Модель задана явно: прибыль цикла 17−5=12; "
               "после налога 12·0,75=9; за 3 цикла 9·3=27. Дистракторы: 12·3=36 (налог не вычтен); "
               "17−5−(5+10)/3=7, 7·0,75=5,25, 5,25·3=15,75 (повторный вычет оплаченных расходов); "
               "налог 17·0,25=4,25, 12−4,25=7,75, 7,75·3=23,25 (налог от выручки).")


def entry(row: dict, changes: dict, reason: str, evidence: str) -> dict:
    e = {"id": row["id"], "before_sha256": gr.fingerprint(row), "reason": reason,
         "evidence": evidence, "changes": changes}
    gr.validate_entry(e)
    after = gr.candidate(row, e, BATCH)
    if "answer_options" in changes:
        gr.validate_choices(after)
    e["after_sha256"] = gr.fingerprint(after)
    return e


def main() -> None:
    engine = create_engine(os.environ["CONTENT_REPAIR_DATABASE_URL"])
    with engine.connect() as conn:
        rows = {r["id"]: r for r in gr._load(conn, [DEACT_ID, TB_ID], False)}
    options = [KEY] + [w[0] for w in WRONG]
    tb_changes = {
        "question_text": QUESTION, "question_latex": QUESTION,
        "correct_answer": KEY, "correct_answer_latex": KEY,
        "answer_options": options, "answer_options_latex": list(options),
        "distractor_meta": [dm(*w) for w in WRONG],
    }
    manifest = {
        "batch": BATCH, "mode": "in_place_owner_requested",
        "source_checked_at": "2026-10-06T00:00:00Z", "student_data_included": False,
        "repairs": [
            entry(rows[DEACT_ID], {"is_active": False}, DEACT_REASON, DEACT_EVIDENCE),
            entry(rows[TB_ID], tb_changes, TB_REASON, TB_EVIDENCE),
        ],
    }
    OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(OUT)


if __name__ == "__main__":
    main()
