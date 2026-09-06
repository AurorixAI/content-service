import psycopg2
from src.core.config import get_settings

def main():
    updates = [
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
        ("G9_TB_31_714_б", "4*x**16/(9*y**18)", "$\\frac{4 x^{16}}{9 y^{18}}$")
    ]
    
    conn = psycopg2.connect(get_settings().database_url)
    cur = conn.cursor()
    
    updated_count = 0
    for tid, ans, latex in updates:
        cur.execute("""
            UPDATE tasks_master 
            SET correct_answer = %s,
                correct_answer_latex = %s,
                tags = (tags - 'smart_verify_retry_exhausted' - 'smart_verify_retry_count' - 'smart_verify_error' - 'choices_complete') || '{"smart_verify_status": "pending", "choices_complete": false}'::jsonb
            WHERE id = %s
        """, (ans, latex, tid))
        updated_count += cur.rowcount
        
    conn.commit()
    conn.close()
    print(f"Successfully updated database values and reset tags for {updated_count} tasks.")

if __name__ == "__main__":
    main()
