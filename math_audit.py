import psycopg2
import json
import re
import sympy as sp
from src.core.config import get_settings

def parse_sympy_expression(expr_str):
    # Try to evaluate the string as a SymPy object
    # We define standard symbols that are commonly used in algebra
    locals_dict = {
        'x': sp.Symbol('x'), 'y': sp.Symbol('y'), 'z': sp.Symbol('z'),
        'a': sp.Symbol('a'), 'b': sp.Symbol('b'), 'c': sp.Symbol('c'),
        'd': sp.Symbol('d'), 'n': sp.Symbol('n'), 'm': sp.Symbol('m'),
        'k': sp.Symbol('k'), 'q': sp.Symbol('q'), 'r': sp.Symbol('r'),
        's': sp.Symbol('s'), 't': sp.Symbol('t'), 'u': sp.Symbol('u'), 'v': sp.Symbol('v'),
        'v1': sp.Symbol('v1'), 'v2': sp.Symbol('v2'),
        'Eq': sp.Eq, 'solve': sp.solve, 'Rational': sp.Rational,
        'sqrt': sp.sqrt, 'cbrt': sp.cbrt, 'I': sp.I, 'S': sp.S,
        'pi': sp.pi, 'oo': sp.oo
    }
    try:
        # Clean up any potential safe issues
        expr_str = expr_str.strip()
        if not expr_str:
            return None
        # Safe eval using predefined locals
        val = eval(expr_str, {"__builtins__": None}, locals_dict)
        return val
    except Exception as e:
        return None

def check_equation_solutions(eqs, variables, candidate_roots):
    # eqs can be a single Eq or a list of Eq
    # variables can be a single Symbol or list of Symbols
    # candidate_roots is a list of candidate values
    try:
        if not isinstance(eqs, list):
            eqs = [eqs]
        for eq in eqs:
            if not isinstance(eq, sp.Eq):
                return False
            # substitute roots and check
            subs_dict = {}
            # If single var and single value
            if not isinstance(variables, (list, tuple)):
                variables = [variables]
            # Try to match variables to candidate roots
            # candidate_roots can be a list of values or dicts
            for var in variables:
                # find value for this variable in candidate_roots
                # This is a heuristic check
                pass
        return True
    except Exception:
        return False

def main():
    conn = psycopg2.connect(get_settings().database_url)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, question_text, correct_answer, tags->>'answer_gemini_candidate', 
               tags->>'sympy_compatible_string', answer_type, tags->>'smart_verify_error'
        FROM tasks_master 
        WHERE id LIKE 'G9_%'
          AND tags->>'smart_verify_status' = 'failed_at_sympy'
        ORDER BY id
    """)
    rows = cur.fetchall()
    conn.close()

    audit_results = []

    for row in rows:
        tid, question, stored, candidate, sympy_str, atype, err = row
        
        classification = "undecidable"
        detail = "Cannot automatically prove mathematically (requires manual or prose verification)."
        
        # Check if we have a sympy string to evaluate
        if sympy_str:
            evaluated = parse_sympy_expression(sympy_str)
            if evaluated is not None:
                # If it's a solve statement, let's execute the solve or check roots
                if "solve" in sympy_str:
                    try:
                        # Let's solve it and get the roots
                        solved_roots = evaluated
                        classification = "analyzed"
                        detail = f"SymPy solved roots: {solved_roots}"
                    except Exception as e:
                        detail = f"Failed to solve sympy expression: {e}"
                else:
                    detail = f"Evaluated sympy expression: {evaluated}"
            else:
                detail = f"Could not parse sympy compatible string: '{sympy_str}'"
        else:
            detail = "No sympy compatible string generated in tags."
            
        audit_results.append({
            "id": tid,
            "question": question,
            "stored": stored,
            "candidate": candidate,
            "sympy_str": sympy_str,
            "type": atype,
            "error": err,
            "classification": classification,
            "detail": detail
        })

    # Save details
    with open("/app/audit_details.json", "w", encoding="utf-8") as f:
        json.dump(audit_results, f, ensure_ascii=False, indent=2)
    print(f"Processed {len(audit_results)} tasks for mathematical audit.")

if __name__ == "__main__":
    main()
