"""guarded_insert on disposable PostgreSQL: a clean `alembic upgrade head` schema and (optionally) a
clone of the live schema. Cleanup is refused on any database not named content_repair_test.

  CONTENT_REPAIR_TEST_DATABASE_URL        clean alembic schema (required)
  CONTENT_REPAIR_TEST_CLONE_DATABASE_URL  clone of the live schema + data (optional, skipped if unset)
"""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import create_engine, text

from tools.content_review.build_w15_new_tasks import OUT, build
from tools.content_review.guarded_insert import apply, rollback
from tools.content_review.guarded_repair import fingerprint

ROOT = Path(__file__).parents[1]
MANIFEST = build()
IDS = [r["id"] for r in MANIFEST["new_tasks"]]
SKILLS = sorted({r["skill_id"] for r in MANIFEST["new_tasks"]})


def _engine(var, migrate):
    url = os.environ.get(var)
    if not url:
        if var.endswith("CLONE_DATABASE_URL"):
            pytest.skip(f"{var} not set")
        pytest.fail(f"{var} is required; provision isolated PostgreSQL")
    engine = create_engine(url)
    with engine.connect() as conn:
        if conn.scalar(text("SELECT current_database()")) != "content_repair_test":
            pytest.fail("refusing to run cleanup on a non-test database")
    if migrate:
        result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env={**os.environ, "DATABASE_URL": url},
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr[-5000:]
    return engine


@pytest.fixture(scope="module", params=["clean", "clone"])
def pg(request):
    engine = (_engine("CONTENT_REPAIR_TEST_DATABASE_URL", True) if request.param == "clean"
              else _engine("CONTENT_REPAIR_TEST_CLONE_DATABASE_URL", False))
    yield engine
    engine.dispose()


@pytest.fixture()
def bank(pg):
    with pg.begin() as conn:
        conn.execute(text("DELETE FROM tasks_master WHERE id = ANY(:ids) OR id LIKE 'INS_TEST_%'"), {"ids": IDS})
        for skill in SKILLS:
            conn.execute(text("""INSERT INTO knowledge_hierarchy(id, level, name_ru) VALUES (:id, 'L4', 'Test skill')
                ON CONFLICT (id) DO UPDATE SET is_active = true"""), {"id": skill})
    yield pg
    with pg.begin() as conn:
        conn.execute(text("DELETE FROM task_latex_display_attestations WHERE task_id = ANY(:ids)"), {"ids": IDS})
        conn.execute(text("DELETE FROM tasks_master WHERE id = ANY(:ids) OR id LIKE 'INS_TEST_%'"), {"ids": IDS})


def count(engine, ids=IDS):
    with engine.connect() as conn:
        return conn.scalar(text("SELECT count(*) FROM tasks_master WHERE id = ANY(:ids)"), {"ids": ids})


def stored(engine):
    from tools.content_review.guarded_repair import _plain
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT * FROM tasks_master WHERE id = ANY(:ids)"), {"ids": IDS}).mappings().all()
    return {r["id"]: fingerprint(_plain(dict(r))) for r in rows}


def manifest():
    return copy.deepcopy(MANIFEST)


def reseal(row):
    row["after_sha256"] = fingerprint(row)


def test_manifest_file_is_current():
    assert json.loads(OUT.read_text()) == MANIFEST


def test_dry_run_is_read_only_and_creates_no_backup(bank, tmp_path):
    report = apply(bank, manifest(), backup=tmp_path / "b.json")
    assert report["inserted"] == IDS and report["execute"] is False
    assert len(report["per_skill"]) == 14 and set(report["per_skill"].values()) == {7}
    assert count(bank) == 0 and not (tmp_path / "b.json").exists()


def test_execute_inserts_exact_rows_then_repeat_is_noop_and_rollback_is_exact(bank, tmp_path):
    with bank.begin() as conn:
        conn.execute(text("""INSERT INTO tasks_master (id,skill_id,question_text,correct_answer,answer_type,difficulty,cognitive_load)
            VALUES ('INS_TEST_KEEP',:s,'Keep me','1','exact_number','A','apply')"""), {"s": SKILLS[0]})
    m, backup = manifest(), tmp_path / "backup.json"
    result = apply(bank, m, execute=True, backup=backup)
    assert result["inserted"] == IDS and count(bank) == 98
    assert backup.stat().st_mode & 0o777 == 0o600
    assert stored(bank) == {r["id"]: r["after_sha256"] for r in m["new_tasks"]}
    repeat = tmp_path / "repeat.json"
    assert apply(bank, m, execute=True, backup=repeat)["already_applied"] == IDS and not repeat.exists()
    saved = json.loads(backup.read_text())
    assert saved["student_data_included"] is False and saved["mode"] == "insert_new_tasks"
    assert rollback(bank, saved)["deleted"] == sorted(IDS) and count(bank) == 98      # dry-run deletes nothing
    assert len(rollback(bank, saved, execute=True)["deleted"]) == 98
    assert count(bank) == 0
    with bank.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM tasks_master WHERE id='INS_TEST_KEEP'")) == 1
    assert rollback(bank, saved, execute=True)["already_rolled_back"] == sorted(IDS)


def test_existing_id_aborts_whole_batch_even_if_different(bank, tmp_path):
    victim = IDS[40]
    with bank.begin() as conn:
        conn.execute(text("""INSERT INTO tasks_master (id,skill_id,question_text,correct_answer,answer_type,difficulty,cognitive_load)
            VALUES (:id,:s,'Something else entirely','1','exact_number','A','apply')"""), {"id": victim, "s": SKILLS[0]})
    with pytest.raises(ValueError, match="already exist"):
        apply(bank, manifest(), execute=True, backup=tmp_path / "never.json")
    assert count(bank) == 1 and not (tmp_path / "never.json").exists()


def test_partial_replay_is_refused(bank, tmp_path):
    m = manifest()
    apply(bank, {**m, "new_tasks": m["new_tasks"][:3]}, execute=True, backup=tmp_path / "part.json")
    with pytest.raises(ValueError, match="already exist"):
        apply(bank, m, execute=True, backup=tmp_path / "full.json")
    assert count(bank) == 3 and not (tmp_path / "full.json").exists()


def test_edited_row_without_new_fingerprint_is_refused(bank, tmp_path):
    m = manifest()
    m["new_tasks"][5]["question_text"] = "Edited"
    m["new_tasks"][5]["question_latex"] = "Edited"
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        apply(bank, m, backup=tmp_path / "x.json")


@pytest.mark.parametrize("mutate,message", [
    (lambda r: r.update(difficulty="D"), "difficulty"),
    (lambda r: r.update(answer_type="exact_number"), "multiple_choice"),
    (lambda r: r.update(is_active=False), "active"),
    (lambda r: r["tags"].pop("content_review"), "batch"),
    (lambda r: r["distractor_meta"][0].update(error_logic="Плохо", explanation="Плохо", error_logic_latex="Плохо", explanation_latex="Плохо"), "Ученик"),
    (lambda r: (r["answer_options"].pop(), r["answer_options_latex"].pop()), "distractor|exactly one|choice"),
])
def test_invalid_rows_are_refused(bank, tmp_path, mutate, message):
    m = manifest()
    mutate(m["new_tasks"][0])
    reseal(m["new_tasks"][0])
    with pytest.raises(ValueError, match=message):
        apply(bank, m, execute=True, backup=tmp_path / "x.json")
    assert count(bank) == 0


def test_unknown_or_inactive_skill_and_duplicate_statement_are_refused(bank, tmp_path):
    m = manifest()
    m["new_tasks"][0]["skill_id"] = "G11_S99_99"
    reseal(m["new_tasks"][0])
    with pytest.raises(ValueError, match="skill"):
        apply(bank, m)
    with bank.begin() as conn:
        conn.execute(text("UPDATE knowledge_hierarchy SET is_active=false WHERE id=:s"), {"s": SKILLS[1]})
    with pytest.raises(ValueError, match="skill"):
        apply(bank, manifest())
    with bank.begin() as conn:
        conn.execute(text("UPDATE knowledge_hierarchy SET is_active=true WHERE id=:s"), {"s": SKILLS[1]})
        conn.execute(text("""INSERT INTO tasks_master (id,skill_id,question_text,correct_answer,answer_type,difficulty,cognitive_load,is_active)
            VALUES ('INS_TEST_DUP',:s,:q,'1','exact_number','A','apply',true)"""),
            {"s": SKILLS[0], "q": MANIFEST["new_tasks"][7]["question_text"]})
    with pytest.raises(ValueError, match="same statement"):
        apply(bank, manifest())
    d = manifest()
    d["new_tasks"][1]["question_text"] = d["new_tasks"][2]["question_text"] = "Одинаковое условие $x$"
    for i in (1, 2):
        d["new_tasks"][i]["question_latex"] = d["new_tasks"][i]["question_text"]
        reseal(d["new_tasks"][i])
    with bank.begin() as conn:
        conn.execute(text("DELETE FROM tasks_master WHERE id='INS_TEST_DUP'"))
    with pytest.raises(ValueError, match="duplicate statement"):
        apply(bank, d)


def test_database_failure_rolls_back_every_insert(bank, tmp_path):
    m = manifest()
    bad = m["new_tasks"][60]
    bad["question_text"] = bad["question_latex"] = "trigger_failure"
    reseal(bad)
    with bank.begin() as conn:
        conn.execute(text("ALTER TABLE tasks_master ADD CONSTRAINT insert_test_failure CHECK (question_text <> 'trigger_failure')"))
    try:
        with pytest.raises(Exception, match="insert_test_failure"):
            apply(bank, m, execute=True, backup=tmp_path / "b.json")
        assert count(bank) == 0
    finally:
        with bank.begin() as conn:
            conn.execute(text("ALTER TABLE tasks_master DROP CONSTRAINT insert_test_failure"))


def test_concurrent_execution_inserts_once(bank, tmp_path):
    m = manifest()
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(apply, bank, m, execute=True, backup=tmp_path / f"c{i}.json") for i in range(2)]
        results = [j.result(timeout=30) for j in jobs]
    assert sorted(len(r["inserted"]) for r in results) == [0, 98] and count(bank) == 98
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_backup_is_never_overwritten(bank, tmp_path):
    path = tmp_path / "only.json"
    path.write_text("previous backup")
    with pytest.raises(FileExistsError):
        apply(bank, manifest(), execute=True, backup=path)
    assert path.read_text() == "previous backup" and count(bank) == 0


def test_execution_requires_backup_path(bank):
    with pytest.raises(ValueError, match="backup"):
        apply(bank, manifest(), execute=True)
    assert count(bank) == 0


def test_rollback_refuses_changed_row_and_deletes_nothing(bank, tmp_path):
    backup = tmp_path / "b.json"
    apply(bank, manifest(), execute=True, backup=backup)
    with bank.begin() as conn:
        conn.execute(text("UPDATE tasks_master SET question_text = question_text || ' (later edit)' WHERE id=:id"), {"id": IDS[10]})
    with pytest.raises(ValueError, match="rollback source drift"):
        rollback(bank, json.loads(backup.read_text()), execute=True)
    assert count(bank) == 98


def test_rollback_refuses_referenced_task(bank, tmp_path):
    backup = tmp_path / "b.json"
    apply(bank, manifest(), execute=True, backup=backup)
    run, att = str(uuid.uuid4()), str(uuid.uuid4())
    with bank.begin() as conn:
        conn.execute(text("""INSERT INTO latex_backfill_runs (run_id,label,actor,status,model,prompt_version,policy_version,config)
            VALUES (:id,'test','test','completed','none','test','test','{}')"""), {"id": run})
        conn.execute(text("""INSERT INTO task_latex_display_attestations
            (attestation_id,task_id,field_key,source_value,display_value,source_sha256,display_sha256,run_id)
            VALUES (:id,:task,'question','a','a',:sha,:sha,:run)"""), {"id": att, "task": IDS[3], "sha": "a" * 64, "run": run})
    with pytest.raises(ValueError, match="referenced"):
        rollback(bank, json.loads(backup.read_text()), execute=True)
    assert count(bank) == 98
    with bank.begin() as conn:
        conn.execute(text("DELETE FROM task_latex_display_attestations WHERE attestation_id=:id"), {"id": att})
        conn.execute(text("DELETE FROM latex_backfill_runs WHERE run_id=:id"), {"id": run})
    assert len(rollback(bank, json.loads(backup.read_text()), execute=True)["deleted"]) == 98
