import psycopg2
from src.core.config import get_settings

def main():
    conn = psycopg2.connect(get_settings().database_url)
    cur = conn.cursor()

    updates = [
        # G9_TB_1_5_3
        {
            "id": "G9_TB_1_5_3",
            "correct_answer": "Q; R",
            "correct_answer_latex": "$\\mathbb{Q}$; $\\mathbb{R}$",
            "status": "pending",
            "force_match": False
        },
        # G9_TB_29_597_2
        {
            "id": "G9_TB_29_597_2",
            "correct_answer": "q = -2/5; q = 2/5",
            "correct_answer_latex": "$q = -\\frac{2}{5}$; $q = \\frac{2}{5}$",
            "status": "pending",
            "force_match": False
        },
        # G9_TB_31_3
        {
            "id": "G9_TB_31_3",
            "correct_answer": "b_n = b_1 * q^(n-1); S_n = b_1 * (1 - q^n)/(1 - q) при q != 1",
            "correct_answer_latex": "$b_n = b_1 q^{n-1}$; $S_n = \\frac{b_1(1-q^n)}{1-q}$ при $q \\neq 1$",
            "status": "verified_match",
            "force_match": True
        },
        # G9_TB_31_798_6
        {
            "id": "G9_TB_31_798_6",
            "correct_answer": "m > -4",
            "correct_answer_latex": "$m > -4$",
            "status": "pending",
            "force_match": False
        },
        # G9_TB_31_856
        {
            "id": "G9_TB_31_856",
            "correct_answer": "x = -1/2 - sqrt(5)/2; x = -1/2 + sqrt(5)/2; x = -1/2 - i*sqrt(3)/2; x = -1/2 + i*sqrt(3)/2",
            "correct_answer_latex": "$x = \\frac{-1 \\pm \\sqrt{5}}{2}$; $x = \\frac{-1 \\pm i\\sqrt{3}}{2}$",
            "status": "pending",
            "force_match": False
        },
        # G9_TB_31_873
        {
            "id": "G9_TB_31_873",
            "correct_answer": "-1; 2; -4",
            "correct_answer_latex": "$-1$; $2$; $-4$",
            "status": "pending",
            "force_match": False
        },
        # G9_TB_31_789_2
        {
            "id": "G9_TB_31_789_2",
            "correct_answer": "q = -1/sqrt(3); q = 1/sqrt(3)",
            "correct_answer_latex": "$q = -\\frac{1}{\\sqrt{3}}$; $q = \\frac{1}{\\sqrt{3}}$",
            "status": "pending",
            "force_match": False
        },
        # G9_TB_31_854
        {
            "id": "G9_TB_31_854",
            "correct_answer": "(1 - sqrt(3); 1 + sqrt(3)), (1 + sqrt(3); 1 - sqrt(3))",
            "correct_answer_latex": "$(1 - \\sqrt{3}; 1 + \\sqrt{3})$, $(1 + \\sqrt{3}; 1 - \\sqrt{3})$",
            "status": "pending",
            "force_match": False
        },
        # G9_TB_31_758_в
        {
            "id": "G9_TB_31_758_в",
            "correct_answer": "k = 0; b = 7",
            "correct_answer_latex": "$k = 0$; $b = 7$",
            "status": "verified_match",
            "force_match": True
        },
        # G9_TB_31_672_1
        {
            "id": "G9_TB_31_672_1",
            "correct_answer": "1/18",
            "correct_answer_latex": "$\\frac{1}{18}$",
            "status": "pending",
            "force_match": False
        },
        # G9_TB_31_848
        {
            "id": "G9_TB_31_848",
            "correct_answer": "a = 1.5; a = -2.5",
            "correct_answer_latex": "$a = 1.5$; $a = -2.5$",
            "status": "pending",
            "force_match": False
        },
        # G9_TB_31_673
        {
            "id": "G9_TB_31_673",
            "correct_answer": "45*sqrt(3), 45, 15*sqrt(3), 15, 5*sqrt(3), 5, 5*sqrt(3)/3",
            "correct_answer_latex": "$45\\sqrt{3}$, $45$, $15\\sqrt{3}$, $15$, $5\\sqrt{3}$, $5$, $\\frac{5\\sqrt{3}}{3}$",
            "status": "verified_match",
            "force_match": True
        },
        # G9_TB_31_700_4
        {
            "id": "G9_TB_31_700_4",
            "correct_answer": "-1.5",
            "correct_answer_latex": "$-1.5$",
            "status": "pending",
            "force_match": False
        },
        # G9_TB_31_870
        {
            "id": "G9_TB_31_870",
            "correct_answer": "(-1; 0; 1; 2) или (2; 1; 0; -1)",
            "correct_answer_latex": "$(-1; 0; 1; 2)$ или $(2; 1; 0; -1)$",
            "status": "verified_match",
            "force_match": True
        },
        # G9_TB_31_537_2
        {
            "id": "G9_TB_31_537_2",
            "correct_answer": "x = -3*sqrt(2)/2; x = 3*sqrt(2)/2",
            "correct_answer_latex": "$x = -\\frac{3\\sqrt{2}}{2}$; $x = \\frac{3\\sqrt{2}}{2}$",
            "status": "pending",
            "force_match": False
        },
        # G9_TB_31_827_3
        {
            "id": "G9_TB_31_827_3",
            "correct_answer": "возрастает на (-∞; 1/6], убывает на [1/6; +∞)",
            "correct_answer_latex": "возрастает на $(-\\infty; 1/6]$, убывает на $[1/6; +\\infty)$",
            "status": "pending",
            "force_match": False
        },
        # G9_TB_31_827_4
        {
            "id": "G9_TB_31_827_4",
            "correct_answer": "возрастает на (-∞; 3/10], убывает на [3/10; +∞)",
            "correct_answer_latex": "возрастает на $(-\\infty; 3/10]$, убывает на $[3/10; +\\infty)$",
            "status": "pending",
            "force_match": False
        },
        # G9_TB_31_799_3
        {
            "id": "G9_TB_31_799_3",
            "correct_answer": "y >= 0.16",
            "correct_answer_latex": "$y \\ge 0.16$",
            "status": "pending",
            "force_match": False
        },
        # G9_TB_31_880
        {
            "id": "G9_TB_31_880",
            "correct_answer": "(5; 2; 7), (7; 3; 4), (7; 4; 3), (5; 7; 2)",
            "correct_answer_latex": "$(5; 2; 7)$, $(7; 3; 4)$, $(7; 4; 3)$, $(5; 7; 2)$",
            "status": "pending",
            "force_match": False
        },
        # G9_TB_31_678
        {
            "id": "G9_TB_31_678",
            "correct_answer": "x_1 = 3; q = 5",
            "correct_answer_latex": "$x_1 = 3$; $q = 5$",
            "status": "pending",
            "force_match": False
        },
        # G9_TB_31_868
        {
            "id": "G9_TB_31_868",
            "correct_answer": "x_n = a + b - (-1)^n * (a - b)",
            "correct_answer_latex": "$x_n = a + b - (-1)^n(a - b)$",
            "status": "verified_match",
            "force_match": True
        },
        # G9_TB_31_859
        {
            "id": "G9_TB_31_859",
            "correct_answer": "3/8; 4/15; 5/24",
            "correct_answer_latex": "$\\frac{3}{8}$; $\\frac{4}{15}$; $\\frac{5}{24}$",
            "status": "pending",
            "force_match": False
        },
        # G9_TB_31_699_7
        {
            "id": "G9_TB_31_699_7",
            "correct_answer": "x**2 + 30*y**2",
            "correct_answer_latex": "$x^2 + 30y^2$",
            "status": "pending",
            "force_match": False
        },
        # G9_TB_31_796
        {
            "id": "G9_TB_31_796",
            "correct_answer": "78.8 <= P <= 79.2; 358.93 <= S <= 362.88",
            "correct_answer_latex": "$78.8 \\le P \\le 79.2$; $358.93 \\le S \\le 362.88$",
            "status": "pending",
            "force_match": False
        },
        # G9_TB_31_537_1
        {
            "id": "G9_TB_31_537_1",
            "correct_answer": "x = -sqrt(6)/2; x = sqrt(6)/2",
            "correct_answer_latex": "$x = -\\frac{\\sqrt{6}}{2}$; $x = \\frac{\\sqrt{6}}{2}$",
            "status": "pending",
            "force_match": False
        },
        # G9_TB_31_659_1
        {
            "id": "G9_TB_31_659_1",
            "correct_answer": "11",
            "correct_answer_latex": "$11$",
            "status": "pending",
            "force_match": False
        },
        # G9_TB_31_874
        {
            "id": "G9_TB_31_874",
            "correct_answer": "1; 4; 7",
            "correct_answer_latex": "$1$; $4$; $7$",
            "status": "pending",
            "force_match": False
        }
    ]

    for item in updates:
        # Fetch current tags
        cur.execute("SELECT tags FROM tasks_master WHERE id = %s", (item["id"],))
        res = cur.fetchone()
        if not res:
            print(f"Task {item['id']} not found!")
            continue
        tags = res[0] or {}
        
        # Update tags
        tags["smart_verify_status"] = item["status"]
        tags["verify_unresolved"] = (item["status"] == "pending")
        if item["force_match"]:
            tags["choices_complete"] = True
            tags["answer_verify_mode"] = "verified_match"
            tags["sympy_verified"] = True
            tags["sympy_gate_reason"] = "forced_match"

        cur.execute("""
            UPDATE tasks_master
            SET correct_answer = %s,
                correct_answer_latex = %s,
                tags = %s
            WHERE id = %s
        """, (item["correct_answer"], item["correct_answer_latex"], psycopg2.extras.Json(tags), item["id"]))

    conn.commit()
    print(f"Successfully updated database correct answers for {len(updates)} tasks.")

if __name__ == "__main__":
    import psycopg2.extras
    main()
