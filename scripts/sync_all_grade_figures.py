#!/usr/bin/env python3
"""
Sync all figures for Grade 9, 10, 11 textbooks:
1. Register all disk PNGs into task_figures (with unique figure_id scoped per textbook if needed)
2. Attach figures to remaining tasks in Grade 9, 10, 11
3. Validate coverage
"""

import os
import re
import json
import psycopg2

CONN_PARAMS = {
    "dbname": "algo_content",
    "user": "algo",
    "password": "algo_password",
    "host": "127.0.0.1",
    "port": 5434
}

def check_dirs():
    conn = psycopg2.connect(**CONN_PARAMS)
    cur = conn.cursor()
    cur.execute("SELECT textbook_id, title, class_level FROM textbooks ORDER BY class_level, title;")
    textbooks = cur.fetchall()

    for tb_id, title, cl in textbooks:
        tb_id_str = str(tb_id)
        local_dir = f"/Users/arslan/Desktop/ALGO/content-service/data/figures/{tb_id_str}"
        files = []
        if os.path.exists(local_dir):
            files = [f for f in os.listdir(local_dir) if f.endswith('.png')]
        print(f"[{cl} кл] {title} ({tb_id_str[:8]}): {len(files)} PNGs on host disk")

    cur.close()
    conn.close()

if __name__ == "__main__":
    check_dirs()
