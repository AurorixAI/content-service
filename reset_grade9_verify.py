import psycopg2
from src.core.config import get_settings

def main():
    updates = [
        # Original 17
        ("G9_TB_25_511", "первая труба: 12 ч; вторая труба: 8 ч", "первая труба: 12 ч; вторая труба: 8 ч"),
        ("G9_TB_31_732_1", "x = -3; x = 0", "$x = -3$; $x = 0$"),
        ("G9_TB_31_732_5", "x = 13/8; x = 3", "$x = \\frac{13}{8}$; $x = 3$"),
        ("G9_TB_31_732_6", "x = -26/35; x = 2", "$x = -\\frac{26}{35}$; $x = 2$"),
        ("G9_TB_31_737_2", "x = 1/3; x = -2", "$x = \\frac{1}{3}$; $x = -2$"),
        ("G9_TB_31_737_3", "x = -1; x = 3", "$x = -1$; $x = 3$"),
        ("G9_TB_31_737_9", "x = -8; x = 7", "$x = -8$; $x = 7$"),
        ("G9_TB_31_755_a", "x = 1; y = 2", "$(1; 2)$"),
        ("G9_TB_31_765", "рожь 48 ц/га; пшеница 65 ц/га", "рожь 48 ц/га; пшеница 65 ц/га"),
        ("G9_TB_31_777", "3/5", "$\\frac{3}{5}$"),
        ("G9_TB_31_784", "-2", "$-2$"),
        ("G9_TB_31_787", "-25", "$-25$"),
        ("G9_TB_31_788", "80", "$80$"),
        ("G9_TB_31_716_е", "4*sqrt(10)/5", "$\\frac{4\\sqrt{10}}{5}$"),
        ("G9_TB_31_681_2", "5/6", "$\\frac{5}{6}$"),
        ("G9_TB_31_681_3", "-34", "$-34$"),
        ("G9_TB_31_714_б", "4*x**16/(9*y**18)", "$\\frac{4 x^{16}}{9 y^{18}}$"),

        # Newly identified errors from Section 1
        ("G9_TB_25_514", "v1 = 6 км/ч; v2 = 4 км/ч", "$v_1 = 6\\text{ км/ч}; v_2 = 4\\text{ км/ч}$"),
        ("G9_TB_31_679", "400/11", "$\\frac{400}{11}$"),
        ("G9_TB_31_730_2", "m ∈ (-∞; +∞)", "$m \\in (-\\infty; +\\infty)$"),
        ("G9_TB_31_731_3", "k ∈ (-2√5; 2√5)", "$k \\in (-2\\sqrt{5}; 2\\sqrt{5})$"),
        ("G9_TB_31_732_4", "x = -127/7; x = -1", "$x = -\\frac{127}{7}$; $x = -1$"),
        ("G9_TB_31_737_4", "x = -14; x = 1", "$x = -14$; $x = 1$"),
        ("G9_TB_31_737_8", "x = -1; x = 1/5", "$x = -1$; $x = \\frac{1}{5}$"),
        ("G9_TB_31_790", "2/27", "$\\frac{2}{27}$"),
        ("G9_TB_31_798_7", "y <= 10", "$y \\le 10$"),
        ("G9_TB_31_827_2", "возрастает на (-1/4; +∞); убывает на (-∞; -1/4)", "возрастает на $(-\\frac{1}{4}; +\\infty)$; убывает на $(-\\infty; -\\frac{1}{4})$"),
        ("G9_TB_31_827_4", "возрастает на (-∞; 3/10]; убывает на [3/10; +∞)", "возрастает на $(-\\infty; 0.3]$; убывает на $[0.3; +\\infty)$"),
        ("G9_TB_31_847", "x = -(3 + sqrt(5))/4; x = -(3 - sqrt(5))/4; x = (3 - sqrt(5))/4; x = (3 + sqrt(5))/4", "$x = -\\frac{3 + \\sqrt{5}}{4}$; $x = -\\frac{3 - \\sqrt{5}}{4}$; $x = \\frac{3 - \\sqrt{5}}{4}$; $x = \\frac{3 + \\sqrt{5}}{4}$"),
        ("G9_TB_31_859", "3/8; 4/15; 5/24", "$\\frac{3}{8}$; $\\frac{4}{15}$; $\\frac{5}{24}$"),
        ("G9_TB_31_874", "1; 4; 7", "$1$; $4$; $7$"),
        ("G9_TB_31_799_3", "y >= 0.16", "$y \\ge 0.16$"),
        ("G9_TB_31_733", "110", "$110$"),
        ("G9_TB_31_736", "240", "$240$"),
        ("G9_TB_31_740", "15", "$15$"),
        ("G9_TB_31_741", "2", "$2$"),
        ("G9_TB_31_742", "20", "$20$"),
        ("G9_TB_31_699_7", "x**2 + 30*y**2", "$x^2 + 30y^2$"),
        ("G9_TB_31_699_8", "24*x**2 + 18*x + 27", "$24x^2 + 18x + 27$"),
        ("G9_TB_31_700_1", "2", "$2$"),
        ("G9_TB_31_711_е", "3/(9*x**2 + 3*x + 1)", "$\\frac{3}{9x^2 + 3x + 1}$")
    ]
    
    conn = psycopg2.connect(get_settings().database_url)
    cur = conn.cursor()
    
    # 1. Update correct answers
    updated_count = 0
    for tid, ans, latex in updates:
        cur.execute("""
            UPDATE tasks_master 
            SET correct_answer = %s,
                correct_answer_latex = %s
            WHERE id = %s
        """, (ans, latex, tid))
        updated_count += cur.rowcount
    
    print(f"Successfully updated database correct answers for {updated_count} tasks.")

    # 2. Globally reset retry counters and status for failed/exhausted Grade 9 tasks
    cur.execute("""
        UPDATE tasks_master tm
        SET tags = (tm.tags - 'smart_verify_retry_exhausted' - 'smart_verify_retry_count' - 'smart_verify_error' - 'choices_complete') 
          || '{"choices_complete": false, "smart_verify_status": "pending"}'::jsonb
        FROM textbook_toc toc
        JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
        WHERE toc.id = tm.toc_id 
          AND tb.class_level = 9 
          AND (
            tm.tags->>'smart_verify_status' IN ('failed_at_sympy', 'failed_at_llm', 'pending') 
            OR tm.tags->>'smart_verify_retry_exhausted' = 'true'
          );
    """)
    reset_count = cur.rowcount
    print(f"Successfully reset tags and set status to pending for {reset_count} Grade 9 tasks.")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    main()
