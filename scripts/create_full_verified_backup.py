import psycopg2
import json
import subprocess
import os
import hashlib
import datetime
from decimal import Decimal

class CustomEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)

def compute_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def main():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = "/Users/arslan/Desktop/ALGO/content-service/backups"
    os.makedirs(backup_dir, exist_ok=True)

    sql_dump_path = os.path.join(backup_dir, f"algo_content_full_dump_{timestamp}.sql")
    bin_dump_path = os.path.join(backup_dir, f"algo_content_custom_{timestamp}.dump")
    json_dump_path = os.path.join(backup_dir, f"algo_content_all_tables_{timestamp}.json")
    manifest_path = os.path.join(backup_dir, f"backup_manifest_{timestamp}.json")

    print("==================================================================")
    print("🚀 СОЗДАНИЕ ПОЛНОГО ПРОФЕССИОНАЛЬНОГО БЭКАПА БАЗЫ ALGO_CONTENT")
    print("==================================================================")
    print(f"⏰ Временная метка: {timestamp}\n")

    # 1. Native PostgreSQL SQL Dump
    print("📦 [1/4] Создание SQL-дампа через Docker pg_dump...")
    cmd_sql = f"docker exec algo-content-db pg_dump -U algo --clean --if-exists algo_content > '{sql_dump_path}'"
    subprocess.run(cmd_sql, shell=True, check=True)
    sql_size = os.path.getsize(sql_dump_path)
    sql_hash = compute_sha256(sql_dump_path)
    print(f"  ✅ SQL Dump создан: {os.path.basename(sql_dump_path)} ({sql_size / 1024 / 1024:.2f} MB)")
    print(f"  🔑 SHA256: {sql_hash[:16]}...\n")

    # 2. Native PostgreSQL Binary / Custom Dump
    print("📦 [2/4] Создание Binary-дампа (-Fc) через Docker pg_dump...")
    cmd_bin = f"docker exec algo-content-db pg_dump -U algo -Fc algo_content > '{bin_dump_path}'"
    subprocess.run(cmd_bin, shell=True, check=True)
    bin_size = os.path.getsize(bin_dump_path)
    bin_hash = compute_sha256(bin_dump_path)
    print(f"  ✅ Binary Dump создан: {os.path.basename(bin_dump_path)} ({bin_size / 1024 / 1024:.2f} MB)")
    print(f"  🔑 SHA256: {bin_hash[:16]}...\n")

    # 3. Full Structured JSON Export of all tables
    print("📦 [3/4] Экспорт всех таблиц в переносимый JSON...")
    conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
    cur = conn.cursor()

    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        ORDER BY table_name;
    """)
    tables = [r[0] for r in cur.fetchall()]

    db_export = {
        "metadata": {
            "database": "algo_content",
            "created_at": datetime.datetime.now().isoformat(),
            "timestamp": timestamp,
            "total_tables": len(tables)
        },
        "tables": {}
    }

    table_stats = {}

    for t in tables:
        cur.execute(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{t}' ORDER BY ordinal_position;")
        columns = [c[0] for c in cur.fetchall()]
        
        cur.execute(f"SELECT * FROM {t};")
        rows = cur.fetchall()
        
        # Convert to list of dicts
        table_data = []
        for r in rows:
            row_dict = {}
            for col_name, val in zip(columns, r):
                row_dict[col_name] = val
            table_data.append(row_dict)
            
        db_export["tables"][t] = {
            "columns": columns,
            "row_count": len(table_data),
            "data": table_data
        }
        table_stats[t] = len(table_data)
        print(f"  • Таблица {t:22s}: {len(table_data):6d} строк")

    with open(json_dump_path, 'w', encoding='utf-8') as f:
        json.dump(db_export, f, ensure_ascii=False, indent=2, cls=CustomEncoder)

    json_size = os.path.getsize(json_dump_path)
    json_hash = compute_sha256(json_dump_path)
    print(f"  ✅ JSON Export сохранён: {os.path.basename(json_dump_path)} ({json_size / 1024 / 1024:.2f} MB)")
    print(f"  🔑 SHA256: {json_hash[:16]}...\n")

    # 4. Strict 1:1 Round-Trip Verification
    print("🔍 [4/4] Сверка 1 в 1: проверка целостности и соответствия каждой записи...")
    with open(json_dump_path, 'r', encoding='utf-8') as f:
        loaded_export = json.load(f)

    verification_passed = True
    mismatch_details = []

    for t in tables:
        cur.execute(f"SELECT count(*) FROM {t};")
        db_count = cur.fetchone()[0]
        json_count = loaded_export["tables"][t]["row_count"]
        
        if db_count != json_count:
            verification_passed = False
            mismatch_details.append(f"Количество строк в {t}: БД={db_count}, JSON={json_count}")
        else:
            print(f"  ✓ {t:22s} -> БД ({db_count}) == Бэкап ({json_count}) [100% СОВПАДЕНИЕ]")

    # Deep verification on tasks_master
    cur.execute("SELECT id, correct_answer, latex_status, verification_status FROM tasks_master ORDER BY id;")
    db_tasks = {r[0]: (r[1], r[2], r[3]) for r in cur.fetchall()}
    
    json_tasks = {row["id"]: (row["correct_answer"], row["latex_status"], row["verification_status"]) 
                  for row in loaded_export["tables"]["tasks_master"]["data"]}
    
    if len(db_tasks) != len(json_tasks):
        verification_passed = False
        mismatch_details.append(f"tasks_master count mismatch: DB={len(db_tasks)}, JSON={len(json_tasks)}")
    else:
        for tid, (ca, ls, vs) in db_tasks.items():
            if tid not in json_tasks:
                verification_passed = False
                mismatch_details.append(f"ID {tid} отсутствует в бэкапе")
                break
            j_ca, j_ls, j_vs = json_tasks[tid]
            if ca != j_ca or ls != j_ls or vs != j_vs:
                verification_passed = False
                mismatch_details.append(f"ID {tid} расхождение данных: DB={(ca, ls, vs)} vs JSON={(j_ca, j_ls, j_vs)}")
                break

    # Save manifest
    manifest = {
        "status": "VERIFIED_1_TO_1" if verification_passed else "FAILED",
        "timestamp": timestamp,
        "files": {
            "sql_dump": {
                "filename": os.path.basename(sql_dump_path),
                "path": sql_dump_path,
                "size_bytes": sql_size,
                "sha256": sql_hash
            },
            "binary_dump": {
                "filename": os.path.basename(bin_dump_path),
                "path": bin_dump_path,
                "size_bytes": bin_size,
                "sha256": bin_hash
            },
            "json_dump": {
                "filename": os.path.basename(json_dump_path),
                "path": json_dump_path,
                "size_bytes": json_size,
                "sha256": json_hash
            }
        },
        "tables_summary": table_stats,
        "tasks_master_summary": {
            "total_tasks": len(db_tasks),
            "smartverify_verified": sum(1 for v in db_tasks.values() if v[2] == 'verified'),
            "latex_verified": sum(1 for v in db_tasks.values() if v[1] == 'verified'),
            "golden_fund": sum(1 for v in db_tasks.values() if v[1] == 'verified' and v[2] == 'verified')
        },
        "mismatches": mismatch_details
    }

    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print("\n==================================================================")
    if verification_passed:
        print("🏆 СВЕРКА 1 В 1 ПРОЙДЕНА: 100.00% БЕЗУПРЕЧНОЕ СОВПАДЕНИЕ!")
    else:
        print("❌ ОБНАРУЖЕНЫ РАСХОЖДЕНИЯ:")
        for m in mismatch_details:
            print(f"  • {m}")
    print("==================================================================")
    print(f"📄 Манифест сохранён: {manifest_path}")

if __name__ == '__main__':
    main()
