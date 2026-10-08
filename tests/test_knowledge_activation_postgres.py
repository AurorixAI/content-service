"""Activation of existing nodes, active inserts and prerequisite edges share the task-repair transaction.

Runs on the same disposable `content_repair_test` database as the other guarded-repair tests, with
either the clean alembic schema or a clone of the live local schema.
"""
import copy
import json
import pytest
from sqlalchemy import text
from test_guarded_content_repair_postgres import pg  # noqa: F401  (fixture)
from tools.content_review import knowledge_repair
from tools.content_review.build_n01_manifest import choices, d
from tools.content_review.guarded_repair import apply, rollback, candidate, fingerprint, _load
from tools.content_review.n01_review_knowledge import node

IDS = ('REVIEW_LEAF', 'REVIEW_DORM', 'REVIEW_OLD', 'REVIEW_PARENT', 'REVIEW_PREREQ', 'REVIEW_LATER', 'REVIEW_MID', 'REVIEW_L2')


def _cleanup(pg):
    with pg.begin() as conn:
        conn.execute(text("DELETE FROM tasks_master WHERE id='REVIEW_TASK'"))
        conn.execute(text("DELETE FROM skill_prerequisites WHERE skill_id LIKE 'REVIEW_%' OR prerequisite_id LIKE 'REVIEW_%'"))
        for node_id in IDS:
            conn.execute(text("DELETE FROM knowledge_hierarchy WHERE id=:id"), {"id": node_id})


def _node_row(conn, node_id):
    cols = knowledge_repair.table_columns(conn)
    row = dict(conn.execute(text("SELECT * FROM knowledge_hierarchy WHERE id=:id"), {"id": node_id}).mappings().one())
    return {k: v for k, v in row.items() if k in cols and k != 'updated_at'}


def _fields(conn, node_id):
    row = _node_row(conn, node_id)
    row = {k: v for k, v in row.items() if k in knowledge_repair.FIELDS}
    return row


def _edge(skill='REVIEW_PARENT', prereq='REVIEW_PREREQ'):
    return {'skill_id': skill, 'prerequisite_id': prereq, 'dependency_type': 'hard', 'weight': 0.9,
            'criticality': 4, 'relationship_description': 'Without the prerequisite the skill cannot be solved.',
            'discovery_source': 'expert'}


@pytest.fixture
def world(pg):
    _cleanup(pg)
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO knowledge_hierarchy(id,level,name_ru,class_level_start,class_level_end) VALUES ('REVIEW_PARENT','L3','Parent',11,11)"))
        conn.execute(text("INSERT INTO knowledge_hierarchy(id,level,name_ru,class_level_start,class_level_end) VALUES ('REVIEW_PREREQ','L3','Prereq',10,10)"))
        conn.execute(text("INSERT INTO knowledge_hierarchy(id,level,name_ru,class_level_start,class_level_end) VALUES ('REVIEW_L2','L2','Section',11,11)"))
        conn.execute(text("INSERT INTO knowledge_hierarchy(id,level,parent_id,name_ru,class_level_start,class_level_end,is_active,description) VALUES ('REVIEW_LATER','L3','REVIEW_L2','Sleeping L3',11,11,false,'Sleeping definition')"))
        conn.execute(text("INSERT INTO knowledge_hierarchy(id,level,parent_id,name_ru) VALUES ('REVIEW_OLD','L4','REVIEW_PARENT','Old skill')"))
        conn.execute(text("""INSERT INTO knowledge_hierarchy(id,level,parent_id,name_ru,description,assessed_ability,class_level_start,
                              class_level_end,importance,sequence_order,cognitive_type,is_active)
                             VALUES ('REVIEW_DORM','L4','REVIEW_PARENT','Dormant','Dormant definition','Dormant ability',11,11,3,2,'analyze',false)"""))
        conn.execute(text("""INSERT INTO tasks_master(id,skill_id,question_text,correct_answer,answer_type,difficulty,cognitive_load,is_active,tags)
                             VALUES ('REVIEW_TASK','REVIEW_OLD','Old','0','exact_number','B','apply',true,'{}')"""))
        row = _load(conn, ['REVIEW_TASK'], False)[0]
        dorm = _fields(conn, 'REVIEW_DORM')
        snapshot = {i: _node_row(conn, i) for i in ('REVIEW_PARENT', 'REVIEW_PREREQ', 'REVIEW_OLD', 'REVIEW_DORM')}
    changes = choices('New', '$1$', [d('$2$', 'Incorrect', 'wrong'), d('$3$', 'Incorrect', 'wrong'), d('$4$', 'Incorrect', 'wrong')],
                      skill_id='REVIEW_LEAF')
    entry = {'id': 'REVIEW_TASK', 'before_sha256': fingerprint(row), 'changes': changes, 'reason': 'Reviewed', 'evidence': 'Independent math'}
    entry['after_sha256'] = fingerprint(candidate(row, entry, 'activate-test'))
    leaf = node('REVIEW_LEAF', 'L4', 'REVIEW_PARENT', 'Reviewed skill', 'Atomic ability', 11, 1)
    leaf['is_active'] = True
    manifest = {'batch': 'activate-test', 'repairs': [entry], 'knowledge_allow_active': True,
                'knowledge_nodes': [leaf], 'knowledge_activate': [{'id': 'REVIEW_DORM', 'before': dorm}],
                'prerequisites': [_edge()]}
    yield pg, manifest, row, snapshot
    _cleanup(pg)


def _state(conn):
    return {'leaf': conn.scalar(text("SELECT count(*) FROM knowledge_hierarchy WHERE id='REVIEW_LEAF'")),
            'dorm': conn.scalar(text("SELECT is_active FROM knowledge_hierarchy WHERE id='REVIEW_DORM'")),
            'edges': conn.scalar(text("SELECT count(*) FROM skill_prerequisites WHERE skill_id LIKE 'REVIEW_%'")),
            'skill': conn.scalar(text("SELECT skill_id FROM tasks_master WHERE id='REVIEW_TASK'"))}


UNTOUCHED = {'leaf': 0, 'dorm': False, 'edges': 0, 'skill': 'REVIEW_OLD'}


def test_dry_run_changes_nothing_and_reports_everything(world, tmp_path):
    engine, manifest, _, _ = world
    report = apply(engine, manifest)
    assert report['knowledge_added'] == ['REVIEW_LEAF'] and report['knowledge_activated'] == ['REVIEW_DORM']
    assert report['prerequisites_added'] == [['REVIEW_PARENT', 'REVIEW_PREREQ']]
    with engine.connect() as conn:
        assert _state(conn) == UNTOUCHED


def test_apply_active_insert_activate_edges_then_exact_rollback(world, tmp_path):
    engine, manifest, before, snapshot = world
    backup = tmp_path / 'backup.json'
    assert len(apply(engine, manifest, execute=True, backup=backup)['updated']) == 1
    with engine.connect() as conn:
        assert _state(conn) == {'leaf': 1, 'dorm': True, 'edges': 1, 'skill': 'REVIEW_LEAF'}
        assert _node_row(conn, 'REVIEW_LEAF')['is_active'] is True
        edge = dict(conn.execute(text("SELECT * FROM skill_prerequisites WHERE skill_id='REVIEW_PARENT'")).mappings().one())
        assert float(edge['weight']) == 0.9 and edge['criticality'] == 4 and edge['dependency_type'] == 'hard'
        if 'is_cross_grade' in edge:
            assert edge['is_cross_grade'] is True  # grade 11 -> grade 10
    saved = json.loads(backup.read_text())
    assert [n['id'] for n in saved['knowledge_activated']] == ['REVIEW_DORM'] and len(saved['prerequisites_added']) == 1
    again = apply(engine, manifest, execute=True, backup=tmp_path / 'repeat.json')
    assert again['already_applied'] == ['REVIEW_TASK'] and again['knowledge_activated'] == [] and again['prerequisites_added'] == []
    assert not (tmp_path / 'repeat.json').exists()
    rollback(engine, saved, execute=True)
    with engine.connect() as conn:
        assert _state(conn) == UNTOUCHED
        assert fingerprint(_load(conn, ['REVIEW_TASK'], False)[0]) == fingerprint(before)
        for node_id, row in snapshot.items():
            assert _node_row(conn, node_id) == row
        assert rollback(engine, saved, execute=True)['already_restored'] == ['REVIEW_TASK']


def test_rollback_dry_run_writes_nothing(world, tmp_path):
    engine, manifest, _, _ = world
    backup = tmp_path / 'b.json'
    apply(engine, manifest, execute=True, backup=backup)
    assert rollback(engine, json.loads(backup.read_text()))['restored'] == ['REVIEW_TASK']
    with engine.connect() as conn:
        assert _state(conn) == {'leaf': 1, 'dorm': True, 'edges': 1, 'skill': 'REVIEW_LEAF'}


@pytest.mark.parametrize('drift', ['name_ru', 'description', 'importance', 'already_active_other', 'missing'])
def test_activation_refuses_drifted_row_and_writes_nothing(world, tmp_path, drift):
    engine, manifest, _, _ = world
    with engine.begin() as conn:
        if drift == 'name_ru':
            conn.execute(text("UPDATE knowledge_hierarchy SET name_ru='Changed' WHERE id='REVIEW_DORM'"))
        elif drift == 'description':
            conn.execute(text("UPDATE knowledge_hierarchy SET description='Changed' WHERE id='REVIEW_DORM'"))
        elif drift == 'importance':
            conn.execute(text("UPDATE knowledge_hierarchy SET importance=9 WHERE id='REVIEW_DORM'"))
        elif drift == 'already_active_other':  # active AND different from `before`
            conn.execute(text("UPDATE knowledge_hierarchy SET is_active=true, name_ru='Changed' WHERE id='REVIEW_DORM'"))
        else:
            conn.execute(text("UPDATE tasks_master SET skill_id='REVIEW_OLD' WHERE id='REVIEW_TASK'"))
            conn.execute(text("DELETE FROM knowledge_hierarchy WHERE id='REVIEW_DORM'"))
    for execute in (False, True):
        with pytest.raises(ValueError, match='drift|missing'):
            apply(engine, manifest, execute=execute, backup=tmp_path / 'bad.json')
    assert not (tmp_path / 'bad.json').exists()
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM knowledge_hierarchy WHERE id='REVIEW_LEAF'")) == 0
        assert conn.scalar(text("SELECT count(*) FROM skill_prerequisites WHERE skill_id LIKE 'REVIEW_%'")) == 0
        assert conn.scalar(text("SELECT skill_id FROM tasks_master WHERE id='REVIEW_TASK'")) == 'REVIEW_OLD'


def _mutate(manifest, how):
    m = copy.deepcopy(manifest)
    if how == 'active_without_flag':
        del m['knowledge_allow_active']
    elif how == 'active_flag_not_bool':
        m['knowledge_allow_active'] = 'yes'
    elif how == 'activate_active_row':
        m['knowledge_activate'][0]['before']['is_active'] = True
    elif how == 'activate_partial_before':
        del m['knowledge_activate'][0]['before']['importance']
    elif how == 'set_level':
        m['knowledge_activate'][0]['set'] = {'level': 'L3'}
    elif how == 'set_is_active':
        m['knowledge_activate'][0]['set'] = {'is_active': False}
    elif how == 'set_bad_importance':
        m['knowledge_activate'][0]['set'] = {'importance': 11}
    elif how == 'set_bool_order':
        m['knowledge_activate'][0]['set'] = {'sequence_order': True}
    elif how == 'set_parent_wrong_level':
        m['knowledge_activate'][0]['set'] = {'parent_id': 'REVIEW_OLD'}
    elif how == 'set_parent_inactive':
        m['knowledge_activate'][0]['set'] = {'parent_id': 'REVIEW_LATER'}
    elif how == 'unknown_entry_key':
        m['knowledge_activate'][0]['after'] = {}
    elif how == 'activate_and_insert_same':
        m['knowledge_activate'][0]['id'] = 'REVIEW_LEAF'
        m['knowledge_activate'][0]['before']['id'] = 'REVIEW_LEAF'
    elif how == 'active_child_of_inactive_parent':
        m['knowledge_nodes'][0]['parent_id'] = 'REVIEW_LATER'
        m['knowledge_activate'] = []
    elif how == 'edge_extra_key':
        m['prerequisites'][0]['is_cross_grade'] = True
    elif how == 'edge_duplicate_in_manifest':
        m['prerequisites'].append(copy.deepcopy(m['prerequisites'][0]))
    elif how == 'edge_self':
        m['prerequisites'][0]['prerequisite_id'] = 'REVIEW_PARENT'
    elif how == 'edge_unknown_node':
        m['prerequisites'][0]['prerequisite_id'] = 'REVIEW_NOPE'
    elif how == 'edge_bad_type':
        m['prerequisites'][0]['dependency_type'] = 'required'
    elif how == 'edge_bad_weight':
        m['prerequisites'][0]['weight'] = 1.5
    elif how == 'edge_weight_3_decimals':
        m['prerequisites'][0]['weight'] = 0.905
    elif how == 'edge_bad_criticality':
        m['prerequisites'][0]['criticality'] = 0
    elif how == 'edge_empty_description':
        m['prerequisites'][0]['relationship_description'] = ' '
    elif how == 'edge_to_inactive':
        m['knowledge_activate'] = []
        m['prerequisites'][0]['prerequisite_id'] = 'REVIEW_DORM'
    return m


@pytest.mark.parametrize('how', ['active_without_flag', 'active_flag_not_bool', 'activate_active_row', 'activate_partial_before',
                                 'activate_and_insert_same', 'set_level', 'set_is_active', 'set_bad_importance',
                                 'set_bool_order', 'set_parent_wrong_level', 'set_parent_inactive', 'unknown_entry_key',
                                 'edge_extra_key', 'edge_duplicate_in_manifest', 'edge_self',
                                 'edge_unknown_node', 'edge_bad_type', 'edge_bad_weight', 'edge_weight_3_decimals',
                                 'edge_bad_criticality', 'edge_empty_description', 'edge_to_inactive'])
def test_invalid_manifest_refuses_every_write(world, tmp_path, how):
    engine, manifest, _, _ = world
    bad = _mutate(manifest, how)
    for execute in (False, True):
        with pytest.raises(ValueError):
            apply(engine, bad, execute=execute, backup=tmp_path / 'bad.json')
    assert not (tmp_path / 'bad.json').exists()
    with engine.connect() as conn:
        assert _state(conn) == UNTOUCHED


def test_active_node_may_hang_under_a_node_activated_in_the_same_manifest(world, tmp_path):
    engine, manifest, _, _ = world
    m = copy.deepcopy(manifest)
    m['knowledge_nodes'][0]['parent_id'] = 'REVIEW_LATER'  # inactive L3, activated by the same manifest
    with engine.connect() as conn:
        later = _fields(conn, 'REVIEW_LATER')
    m['knowledge_activate'].append({'id': 'REVIEW_LATER', 'before': later})
    apply(engine, m, execute=True, backup=tmp_path / 'ok.json')
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT is_active FROM knowledge_hierarchy WHERE id='REVIEW_LEAF'")) is True
        assert conn.scalar(text("SELECT is_active FROM knowledge_hierarchy WHERE id='REVIEW_LATER'")) is True


def test_active_node_under_inactive_parent_is_refused(world, tmp_path):
    engine, manifest, _, _ = world
    m = copy.deepcopy(manifest)
    m['knowledge_nodes'][0]['parent_id'] = 'REVIEW_LATER'
    m['knowledge_activate'] = []
    with pytest.raises(ValueError, match='active parent'):
        apply(engine, m, execute=True, backup=tmp_path / 'x.json')
    with engine.connect() as conn:
        assert _state(conn) == UNTOUCHED


def test_existing_edge_is_a_duplicate_while_tasks_are_pending(world, tmp_path):
    engine, manifest, _, _ = world
    with engine.begin() as conn:  # identical edge already present, other attributes irrelevant
        conn.execute(text("""INSERT INTO skill_prerequisites(skill_id,prerequisite_id,dependency_type,weight,criticality,
                              relationship_description,discovery_source)
                             VALUES ('REVIEW_PARENT','REVIEW_PREREQ','hard',0.9,4,'Without the prerequisite the skill cannot be solved.','expert')"""))
    with pytest.raises(ValueError, match='already present'):
        apply(engine, manifest, execute=True, backup=tmp_path / 'dup.json')
    assert not (tmp_path / 'dup.json').exists()
    with engine.begin() as conn:
        conn.execute(text("UPDATE skill_prerequisites SET weight=0.8 WHERE skill_id='REVIEW_PARENT'"))
    with pytest.raises(ValueError, match='different values'):
        apply(engine, manifest, execute=True, backup=tmp_path / 'dup.json')
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT skill_id FROM tasks_master WHERE id='REVIEW_TASK'")) == 'REVIEW_OLD'
        assert conn.scalar(text("SELECT count(*) FROM knowledge_hierarchy WHERE id='REVIEW_LEAF'")) == 0


def test_reverse_edge_and_cycle_are_refused(world, tmp_path):
    engine, manifest, _, _ = world
    with engine.begin() as conn:
        conn.execute(text("""INSERT INTO skill_prerequisites(skill_id,prerequisite_id,dependency_type,weight,criticality,
                              relationship_description,discovery_source)
                             VALUES ('REVIEW_PREREQ','REVIEW_PARENT','hard',0.9,4,'Reverse direction.','expert')"""))
    with pytest.raises(ValueError, match='reverse'):
        apply(engine, manifest, execute=True, backup=tmp_path / 'cyc.json')
    # indirect cycle: PARENT -> PREREQ already requested; add PREREQ -> LATER -> PARENT
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM skill_prerequisites WHERE skill_id LIKE 'REVIEW_%'"))
        conn.execute(text("INSERT INTO knowledge_hierarchy(id,level,name_ru,class_level_start,class_level_end) VALUES ('REVIEW_MID','L3','Mid',11,11)"))
        for s, p in (('REVIEW_PREREQ', 'REVIEW_MID'), ('REVIEW_MID', 'REVIEW_PARENT')):
            conn.execute(text("""INSERT INTO skill_prerequisites(skill_id,prerequisite_id,dependency_type,weight,criticality,
                                  relationship_description,discovery_source) VALUES (:s,:p,'hard',0.9,4,'x','expert')"""), {'s': s, 'p': p})
    with pytest.raises(ValueError, match='cycle'):
        apply(engine, manifest, execute=True, backup=tmp_path / 'cyc.json')
    assert not (tmp_path / 'cyc.json').exists()
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM knowledge_hierarchy WHERE id='REVIEW_LEAF'")) == 0


def test_failure_after_node_and_activation_writes_rolls_everything_back(world, tmp_path, monkeypatch):
    engine, manifest, _, _ = world

    def boom(conn, edges):
        raise RuntimeError('edge insert failed')
    monkeypatch.setattr(knowledge_repair, 'insert_edges', boom)
    with pytest.raises(RuntimeError):
        apply(engine, manifest, execute=True, backup=tmp_path / 'atomic.json')
    with engine.connect() as conn:
        assert _state(conn) == UNTOUCHED


@pytest.mark.parametrize('what', ['node', 'activation', 'edge'])
def test_rollback_refuses_newer_changes_and_changes_nothing(world, tmp_path, what):
    engine, manifest, _, _ = world
    backup = tmp_path / 'backup.json'
    apply(engine, manifest, execute=True, backup=backup)
    with engine.begin() as conn:
        if what == 'node':
            conn.execute(text("UPDATE knowledge_hierarchy SET name_ru='Newer' WHERE id='REVIEW_LEAF'"))
        elif what == 'activation':
            conn.execute(text("UPDATE knowledge_hierarchy SET importance=9 WHERE id='REVIEW_DORM'"))
        else:
            conn.execute(text("UPDATE skill_prerequisites SET weight=0.5 WHERE skill_id='REVIEW_PARENT'"))
    with pytest.raises(ValueError, match='drift'):
        rollback(engine, json.loads(backup.read_text()), execute=True)
    with engine.connect() as conn:
        assert _state(conn) == {'leaf': 1, 'dorm': True, 'edges': 1, 'skill': 'REVIEW_LEAF'}


def test_rollback_removes_activation_only_manifest_parts_when_tasks_already_restored(world, tmp_path):
    engine, manifest, before, _ = world
    backup = tmp_path / 'backup.json'
    apply(engine, manifest, execute=True, backup=backup)
    saved = json.loads(backup.read_text())
    with engine.begin() as conn:  # operator restored the task by hand first
        conn.execute(text("UPDATE tasks_master SET skill_id='REVIEW_OLD' WHERE id='REVIEW_TASK'"))
        manual = _load(conn, ['REVIEW_TASK'], False)[0]
    saved['before'][0] = manual
    assert 'restored' in rollback(engine, saved, execute=True)
    with engine.connect() as conn:
        assert _state(conn) == UNTOUCHED


def test_old_backup_without_new_keys_still_rolls_back(world, tmp_path):
    engine, manifest, before, _ = world
    plain = copy.deepcopy(manifest)
    for key in ('knowledge_allow_active', 'knowledge_activate', 'prerequisites'):
        plain.pop(key)
    plain['knowledge_nodes'][0]['is_active'] = False
    backup = tmp_path / 'old.json'
    apply(engine, plain, execute=True, backup=backup)
    saved = json.loads(backup.read_text())
    for key in ('knowledge_activated', 'prerequisites_added'):
        saved.pop(key)
    rollback(engine, saved, execute=True)
    with engine.connect() as conn:
        assert _state(conn) == UNTOUCHED


def test_activation_set_adjusts_fields_and_rollback_restores_the_exact_row(world, tmp_path):
    engine, manifest, before, snapshot = world
    m = copy.deepcopy(manifest)
    m['knowledge_activate'][0]['set'] = {'importance': 8, 'sequence_order': 5, 'cognitive_type': 'apply',
                                         'name_ru': 'Renamed dormant', 'description': 'New definition',
                                         'assessed_ability': 'New ability'}
    backup = tmp_path / 'set.json'
    assert apply(engine, m, execute=True, backup=backup)['knowledge_activated'] == ['REVIEW_DORM']
    with engine.connect() as conn:
        row = _node_row(conn, 'REVIEW_DORM')
        assert (row['is_active'], row['importance'], row['sequence_order'], row['cognitive_type'], row['name_ru']) == \
            (True, 8, 5, 'apply', 'Renamed dormant')
        assert row['description'] == 'New definition' and row['assessed_ability'] == 'New ability'
    assert apply(engine, m, execute=True, backup=tmp_path / 'again.json')['knowledge_activated'] == []
    with engine.begin() as conn:
        conn.execute(text("UPDATE knowledge_hierarchy SET importance=3 WHERE id='REVIEW_DORM'"))
    with pytest.raises(ValueError, match='drift'):
        rollback(engine, json.loads(backup.read_text()), execute=True)
    with engine.begin() as conn:
        conn.execute(text("UPDATE knowledge_hierarchy SET importance=8 WHERE id='REVIEW_DORM'"))
    rollback(engine, json.loads(backup.read_text()), execute=True)
    with engine.connect() as conn:
        for node_id, expect in snapshot.items():
            assert _node_row(conn, node_id) == expect


def test_activation_set_may_reparent_to_an_active_node_of_the_right_level(world, tmp_path):
    engine, manifest, _, snapshot = world
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO knowledge_hierarchy(id,level,name_ru,class_level_start,class_level_end) VALUES ('REVIEW_MID','L3','Mid',11,11)"))
    m = copy.deepcopy(manifest)
    m['knowledge_activate'][0]['set'] = {'parent_id': 'REVIEW_MID'}
    backup = tmp_path / 'reparent.json'
    apply(engine, m, execute=True, backup=backup)
    with engine.connect() as conn:
        assert _node_row(conn, 'REVIEW_DORM')['parent_id'] == 'REVIEW_MID'
    rollback(engine, json.loads(backup.read_text()), execute=True)
    with engine.connect() as conn:
        assert _node_row(conn, 'REVIEW_DORM') == snapshot['REVIEW_DORM']
