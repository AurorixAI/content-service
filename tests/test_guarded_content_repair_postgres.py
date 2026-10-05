"""Transaction, concurrency and rollback tests on a disposable real PostgreSQL.

CI always provisions this database. Refuse to run cleanup against any database
whose name is not content_repair_test; never use the application's DATABASE_URL.
"""
from concurrent.futures import ThreadPoolExecutor
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import uuid

import pytest
from sqlalchemy import create_engine, text
from alembic.migration import MigrationContext
from alembic.operations import Operations

from tools.content_review.build_n01_manifest import BATCH, REPAIRS
from tools.content_review.guarded_repair import (
    FIELDS, _load, apply, candidate, fingerprint, rollback,
)

ROOT = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def pg():
    url = os.environ.get("CONTENT_REPAIR_TEST_DATABASE_URL")
    if not url:
        pytest.fail("CONTENT_REPAIR_TEST_DATABASE_URL is required; provision isolated PostgreSQL")
    engine = create_engine(url)
    with engine.connect() as conn:
        if conn.scalar(text("SELECT current_database()")) != "content_repair_test":
            pytest.fail("refusing to run cleanup on a non-test database")
    env = {**os.environ, "DATABASE_URL": url}
    result = subprocess.run(["alembic", "upgrade", "head"], cwd=ROOT, env=env,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr[-5000:]
    yield engine
    engine.dispose()


@pytest.fixture()
def bank(pg):
    with pg.begin() as conn:
        conn.execute(text("TRUNCATE task_latex_display_attestations, tasks_master, latex_backfill_runs CASCADE"))
        for index, (task_id, spec) in enumerate(list(REPAIRS.items())[:2]):
            skill_id = spec["changes"].get("skill_id", "G10_S28_04")
            conn.execute(text("""INSERT INTO knowledge_hierarchy(id, level, name_ru)
                VALUES (:id, 'L4', 'Test skill') ON CONFLICT DO NOTHING"""), {"id": skill_id})
            conn.execute(text("""INSERT INTO tasks_master
                (id,skill_id,question_text,question_latex,correct_answer,correct_answer_latex,
                 tags,is_active,answer_options,answer_options_latex,distractor_meta,
                 answer_type,difficulty,cognitive_load)
                VALUES (:id,:skill,'Legacy statement','Legacy statement','old','old',
                 '{"latex_attested_fields":["question","answer","option[0]","dmeta[0].value"],
                   "content_quality":{"latex_attested_fields":["question","answer"]}}',true,'[]','[]','[]',
                 'multiple_choice','B','apply')"""),
                {"id": task_id, "skill": skill_id})
    return pg


def manifest(engine):
    ids = list(REPAIRS)[:2]
    with engine.connect() as conn:
        rows = _load(conn, ids, False)
    entries = []
    for row in rows:
        spec = REPAIRS[row["id"]]
        e = {"id": row["id"], "before_sha256": fingerprint(row), **copy.deepcopy(spec)}
        e["after_sha256"] = fingerprint(candidate(row, e, BATCH))
        entries.append(e)
    return {"batch": BATCH, "repairs": entries}


def sources(engine):
    with engine.connect() as conn:
        return {r["id"]: fingerprint(r) for r in _load(conn, list(REPAIRS)[:2], False)}


def attest(engine, task_id, field="question"):
    run, attestation = str(uuid.uuid4()), str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(text("""INSERT INTO latex_backfill_runs
            (run_id,label,actor,status,model,prompt_version,policy_version,config)
            VALUES (:id,'test','test','completed','none','test','test','{}')"""), {"id": run})
        conn.execute(text("""INSERT INTO task_latex_display_attestations
            (attestation_id,task_id,field_key,source_value,display_value,source_sha256,display_sha256,run_id)
            VALUES (:id,:task,:field,'Legacy statement','Legacy statement',:sha,:sha,:run)"""),
            {"id": attestation, "task": task_id, "field": field, "sha": "a" * 64, "run": run})
    return attestation


def test_dry_run_does_not_write_or_create_backup(bank, tmp_path):
    before = sources(bank)
    backup = tmp_path / "private.json"
    apply(bank, manifest(bank), backup=backup)
    assert sources(bank) == before and not backup.exists()


def test_complete_apply_repeat_and_guarded_rollback(bank, tmp_path):
    before, m = sources(bank), manifest(bank)
    attestation = attest(bank, m["repairs"][0]["id"])
    backup = tmp_path / "private.json"
    result = apply(bank, m, execute=True, backup=backup)
    assert len(result["updated"]) == 2 and backup.stat().st_mode & 0o777 == 0o600
    assert sources(bank) == {e["id"]: e["after_sha256"] for e in m["repairs"]}
    repeat_path = tmp_path / "repeat.json"
    assert apply(bank, m, execute=True, backup=repeat_path)["already_applied"]
    assert not repeat_path.exists()
    with bank.connect() as conn:
        assert conn.scalar(text("SELECT status FROM task_latex_display_attestations WHERE attestation_id=:id"), {"id": attestation}) == "revoked"
        assert conn.scalar(text("SELECT count(*) FROM tasks_master")) == 2
    saved = json.loads(backup.read_text())
    assert saved["student_data_included"] is False
    assert rollback(bank, saved)["restored"] and sources(bank) != before
    rollback(bank, saved, execute=True)
    assert sources(bank) == before
    with bank.connect() as conn:
        assert conn.scalar(text("SELECT status FROM task_latex_display_attestations WHERE attestation_id=:id"), {"id": attestation}) == "active"


def test_source_drift_in_second_task_aborts_whole_batch(bank, tmp_path):
    m = manifest(bank)
    with bank.begin() as conn:
        conn.execute(text("UPDATE tasks_master SET question_latex='A later edit' WHERE id=:id"), {"id": m["repairs"][1]["id"]})
    before = sources(bank)
    with pytest.raises(ValueError, match="source drift"):
        apply(bank, m, execute=True, backup=tmp_path / "never.json")
    assert sources(bank) == before and not (tmp_path / "never.json").exists()


def test_missing_task_aborts_and_execution_requires_backup(bank, tmp_path):
    m = manifest(bank)
    before = sources(bank)
    with pytest.raises(ValueError, match="backup"):
        apply(bank, m, execute=True)
    with bank.begin() as conn:
        conn.execute(text("DELETE FROM tasks_master WHERE id=:id"), {"id": m["repairs"][1]["id"]})
    with pytest.raises(ValueError, match="missing"):
        apply(bank, m, execute=True, backup=tmp_path / "never.json")
    assert not (tmp_path / "never.json").exists()


def test_database_failure_rolls_back_already_updated_first_row(bank, tmp_path):
    m, before = manifest(bank), sources(bank)
    with bank.begin() as conn:
        conn.execute(text("ALTER TABLE tasks_master ADD CONSTRAINT repair_test_failure CHECK (question_text <> 'trigger_failure')"))
    try:
        e = m["repairs"][1]
        e["changes"].update(question_text="trigger_failure", question_latex="trigger_failure")
        with bank.connect() as conn:
            row = _load(conn, [e["id"]], False)[0]
        e["after_sha256"] = fingerprint(candidate(row, e, BATCH))
        with pytest.raises(Exception, match="repair_test_failure"):
            apply(bank, m, execute=True, backup=tmp_path / "rollback.json")
        assert sources(bank) == before
    finally:
        with bank.begin() as conn:
            conn.execute(text("ALTER TABLE tasks_master DROP CONSTRAINT repair_test_failure"))


def test_concurrent_application_updates_once_without_duplicate_tasks(bank, tmp_path):
    m = manifest(bank)
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(apply, bank, m, execute=True, backup=tmp_path / f"copy{i}.json") for i in range(2)]
        results = [job.result(timeout=10) for job in jobs]
    assert sorted(len(r["updated"]) for r in results) == [0, 2]
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_backup_is_never_overwritten(bank, tmp_path):
    m, before = manifest(bank), sources(bank)
    path = tmp_path / "only-backup.json"
    path.write_text("previous backup")
    with pytest.raises(FileExistsError):
        apply(bank, m, execute=True, backup=path)
    assert path.read_text() == "previous backup" and sources(bank) == before


def test_rollback_refuses_later_content_edit_without_partial_restore(bank, tmp_path):
    path, m = tmp_path / "backup.json", manifest(bank)
    apply(bank, m, execute=True, backup=path)
    with bank.begin() as conn:
        conn.execute(text("UPDATE tasks_master SET question_text='Later review' WHERE id=:id"), {"id": m["repairs"][1]["id"]})
    before = sources(bank)
    with pytest.raises(ValueError, match="rollback source drift"):
        rollback(bank, json.loads(path.read_text()), execute=True)
    assert sources(bank) == before


def test_rollback_refuses_new_attestation(bank, tmp_path):
    path, m = tmp_path / "backup.json", manifest(bank)
    apply(bank, m, execute=True, backup=path)
    attest(bank, m["repairs"][0]["id"])
    before = sources(bank)
    with pytest.raises(ValueError, match="attestation drift"):
        rollback(bank, json.loads(path.read_text()), execute=True)
    assert sources(bank) == before


def migration(prefix):
    path = next((ROOT / "alembic/versions").glob(prefix + "*.py"))
    spec = importlib.util.spec_from_file_location(prefix, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_legacy_figure_repairs_handle_partial_import_without_reactivating_tasks(bank):
    first, second = migration("i0c1"), migration("j1d2")
    with bank.connect() as conn:
        transaction = conn.begin()
        try:
            conn.execute(text("INSERT INTO textbooks(textbook_id,title,class_level) VALUES (:id,'Test book',11)"),
                         {"id": first.TEXTBOOK_ID})
            conn.execute(text("""INSERT INTO tasks_master
                (id,skill_id,question_text,correct_answer,answer_type,difficulty,cognitive_load,is_active)
                VALUES (:id,:skill,'Figure question','old','text','B','apply',false)"""),
                {"id": first.TASKS_FIG_212[0], "skill": REPAIRS["G10_TB_3_9_9"]["changes"]["skill_id"]})
            # j1 already ran in upgrade head. Replay it in this rolled-back
            # transaction to exercise the populated / partly imported path.
            conn.execute(text("DROP TABLE task_figure_ref_quarantine"))
            with Operations.context(MigrationContext.configure(conn)):
                first.upgrade()
                second.upgrade()
                assert conn.scalar(text("SELECT count(*) FROM task_figures")) == 3
                assert conn.scalar(text("SELECT count(*) FROM task_figure_refs")) == 1
                assert conn.scalar(text("SELECT is_active FROM tasks_master WHERE id=:id"),
                                   {"id": first.TASKS_FIG_212[0]}) is False
                second.downgrade()
                first.downgrade()  # no legacy global figure: must not invent it
                assert conn.scalar(text("SELECT count(*) FROM task_figure_refs")) == 0
        finally:
            transaction.rollback()


def test_coverage_repair_requires_existing_skill_and_remains_idempotent(bank):
    module = migration("m4a5")
    with bank.connect() as conn:
        transaction = conn.begin()
        try:
            with Operations.context(MigrationContext.configure(conn)):
                module.upgrade()
                assert conn.scalar(text("SELECT count(*) FROM tasks_master WHERE id=:id"), {"id": module.TASK_ID}) == 0
                conn.execute(text("INSERT INTO knowledge_hierarchy(id,level,name_ru) VALUES ('G8_S28_04','L4','Test trend')"))
                module.upgrade()
                module.upgrade()
                assert conn.scalar(text("SELECT count(*) FROM tasks_master WHERE id=:id"), {"id": module.TASK_ID}) == 1
        finally:
            transaction.rollback()
