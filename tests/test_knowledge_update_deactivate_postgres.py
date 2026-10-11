"""knowledge_update / knowledge_deactivate share the task-repair transaction and roll back exactly.

Same disposable `content_repair_test` database as the other guarded-repair tests (clean alembic schema
or a clone of the live local schema). Apply order: insert -> activate -> update -> tasks -> deactivate -> edges.
"""
import copy
import json
import pytest
from sqlalchemy import text
from test_guarded_content_repair_postgres import pg  # noqa: F401  (fixture)
from tools.content_review import knowledge_repair
from tools.content_review.build_n01_manifest import choices, d
from tools.content_review.guarded_repair import apply, rollback, candidate, fingerprint, _load

# children first, so cleanup respects the parent foreign key
IDS = ('RKU_OLD', 'RKU_SPARE', 'RKU_OTHER', 'RKU_PARENT', 'RKU_EMPTY', 'RKU_MID', 'RKU_L2C', 'RKU_L2', 'RKU_L2B', 'RKU_L1')
LEAVES = ('RKU_OLD', 'RKU_SPARE', 'RKU_OTHER')


def _cleanup(pg):
    with pg.begin() as conn:
        conn.execute(text("DELETE FROM tasks_master WHERE id='RKU_TASK'"))
        conn.execute(text("DELETE FROM skill_prerequisites WHERE skill_id LIKE 'RKU_%' OR prerequisite_id LIKE 'RKU_%'"))
        conn.execute(text("UPDATE knowledge_hierarchy SET parent_id=NULL WHERE id LIKE 'RKU_%'"))
        for node_id in IDS:
            conn.execute(text("DELETE FROM knowledge_hierarchy WHERE id=:id"), {"id": node_id})


def _row(conn, node_id):
    cols = knowledge_repair.table_columns(conn)
    row = dict(conn.execute(text("SELECT * FROM knowledge_hierarchy WHERE id=:id"), {"id": node_id}).mappings().one())
    return {k: v for k, v in row.items() if k in cols and k != 'updated_at'}


def _before(conn, node_id):
    return {k: v for k, v in _row(conn, node_id).items() if k in knowledge_repair.FIELDS}


def _node(conn, node_id, level, parent, start, end, active=True):
    conn.execute(text("""INSERT INTO knowledge_hierarchy(id,level,parent_id,name_ru,description,assessed_ability,
                         class_level_start,class_level_end,importance,sequence_order,cognitive_type,is_active)
                         VALUES (:id,:level,:parent,:name,:descr,:ab,:s,:e,4,3,'apply',:a)"""),
                 {'id': node_id, 'level': level, 'parent': parent, 'name': 'Name ' + node_id, 'descr': 'Definition ' + node_id,
                  'ab': 'Ability ' + node_id if level == 'L4' else None, 's': start, 'e': end, 'a': active})


@pytest.fixture
def world(pg):
    _cleanup(pg)
    with pg.begin() as conn:
        _node(conn, 'RKU_L1', 'L1', None, 5, 11)
        _node(conn, 'RKU_L2', 'L2', 'RKU_L1', 5, 11)
        _node(conn, 'RKU_L2B', 'L2', 'RKU_L1', 9, 11)
        _node(conn, 'RKU_PARENT', 'L3', 'RKU_L2', 10, 11)
        _node(conn, 'RKU_MID', 'L3', 'RKU_L2B', 10, 11)
        _node(conn, 'RKU_EMPTY', 'L3', 'RKU_L2', 10, 11)
        _node(conn, 'RKU_OLD', 'L4', 'RKU_PARENT', 10, 11)
        _node(conn, 'RKU_SPARE', 'L4', 'RKU_PARENT', 10, 11)
        _node(conn, 'RKU_OTHER', 'L4', 'RKU_MID', 10, 11)
        conn.execute(text("""INSERT INTO tasks_master(id,skill_id,question_text,correct_answer,answer_type,difficulty,cognitive_load,is_active,tags)
                             VALUES ('RKU_TASK','RKU_OLD','Old','0','exact_number','B','apply',true,'{}')"""))
        task = _load(conn, ['RKU_TASK'], False)[0]
        snapshot = {i: _row(conn, i) for i in IDS if i != 'RKU_L2C'}
    yield pg, task, snapshot
    _cleanup(pg)


def _manifest(engine, task, move_to='RKU_SPARE', **keys):
    """A manifest whose only task repair moves RKU_TASK to `move_to`; knowledge keys come from `keys`."""
    changes = choices('New', '$1$', [d('$2$', 'Incorrect', 'wrong'), d('$3$', 'Incorrect', 'wrong'), d('$4$', 'Incorrect', 'wrong')],
                      skill_id=move_to)
    entry = {'id': 'RKU_TASK', 'before_sha256': fingerprint(task), 'changes': changes, 'reason': 'Reviewed', 'evidence': 'Independent math'}
    entry['after_sha256'] = fingerprint(candidate(task, entry, 'upd-test'))
    return {'batch': 'upd-test', 'repairs': [entry], **keys}


def upd(engine, node_id, **change):
    with engine.connect() as conn:
        return {'id': node_id, 'before': _before(conn, node_id), 'set': change}


def deact(engine, node_id):
    with engine.connect() as conn:
        return {'id': node_id, 'before': _before(conn, node_id)}


def _snap(engine, ids=None):
    with engine.connect() as conn:
        return {i: _row(conn, i) for i in (ids or [i for i in IDS if i != 'RKU_L2C'])}


def _skill(engine):
    with engine.connect() as conn:
        return conn.scalar(text("SELECT skill_id FROM tasks_master WHERE id='RKU_TASK'"))


def _refused(engine, manifest, tmp_path, match):
    before = _snap(engine)
    for execute in (False, True):
        with pytest.raises(ValueError, match=match):
            apply(engine, manifest, execute=execute, backup=tmp_path / 'bad.json')
    assert not (tmp_path / 'bad.json').exists()
    assert _snap(engine) == before and _skill(engine) == 'RKU_OLD'


# ---------------------------------------------------------------- rename
def test_rename_dry_run_apply_idempotent_and_exact_rollback(world, tmp_path):
    engine, task, snapshot = world
    m = _manifest(engine, task, knowledge_update=[upd(engine, 'RKU_PARENT', name_ru='Renamed', description='New def',
                                                      importance=9, sequence_order=7)])
    assert apply(engine, m)['knowledge_updated'] == ['RKU_PARENT']
    assert _snap(engine) == snapshot and _skill(engine) == 'RKU_OLD'  # dry run writes nothing
    backup = tmp_path / 'b.json'
    assert apply(engine, m, execute=True, backup=backup)['knowledge_updated'] == ['RKU_PARENT']
    with engine.connect() as conn:
        row = _row(conn, 'RKU_PARENT')
    assert (row['name_ru'], row['description'], row['importance'], row['sequence_order']) == ('Renamed', 'New def', 9, 7)
    assert row['parent_id'] == 'RKU_L2' and row['is_active'] is True and _skill(engine) == 'RKU_SPARE'
    saved = json.loads(backup.read_text())
    assert [e['id'] for e in saved['knowledge_updated']] == ['RKU_PARENT'] and saved['knowledge_deactivated'] == []
    again = apply(engine, m, execute=True, backup=tmp_path / 'again.json')
    assert again['knowledge_updated'] == [] and again['already_applied'] == ['RKU_TASK'] and not (tmp_path / 'again.json').exists()
    rollback(engine, saved, execute=True)
    assert _snap(engine) == snapshot and _skill(engine) == 'RKU_OLD'
    assert rollback(engine, saved, execute=True)['already_restored'] == ['RKU_TASK']


def test_rename_of_live_only_name_column(world, tmp_path):
    engine, task, snapshot = world
    with engine.connect() as conn:
        has_name = 'name' in knowledge_repair.table_columns(conn)
    if not has_name:
        pytest.skip('schema has no knowledge_hierarchy.name')
    backup = tmp_path / 'n.json'
    apply(engine, _manifest(engine, task, knowledge_update=[upd(engine, 'RKU_PARENT', name='Technical name')]), execute=True, backup=backup)
    with engine.connect() as conn:
        assert _row(conn, 'RKU_PARENT')['name'] == 'Technical name'
    rollback(engine, json.loads(backup.read_text()), execute=True)
    assert _snap(engine) == snapshot


# ---------------------------------------------------------------- reparent
def test_valid_reparents_apply_and_roll_back_exactly(world, tmp_path):
    engine, task, snapshot = world
    m = _manifest(engine, task, knowledge_update=[upd(engine, 'RKU_PARENT', parent_id='RKU_L2B'),   # L3 -> other L2
                                                  upd(engine, 'RKU_OTHER', parent_id='RKU_EMPTY'),  # L4 -> other L3
                                                  upd(engine, 'RKU_L2B', parent_id='RKU_L1', class_level_start=8)])
    backup = tmp_path / 'r.json'
    apply(engine, m, execute=True, backup=backup)
    with engine.connect() as conn:
        assert (_row(conn, 'RKU_PARENT')['parent_id'], _row(conn, 'RKU_OTHER')['parent_id'], _row(conn, 'RKU_L2B')['class_level_start']) \
            == ('RKU_L2B', 'RKU_EMPTY', 8)
    rollback(engine, json.loads(backup.read_text()), execute=True)
    assert _snap(engine) == snapshot


def test_reparent_under_a_parent_that_is_updated_in_the_same_manifest(world, tmp_path):
    engine, task, snapshot = world
    # L2B widens to 5-11 and the L3 (class 4-? no, 10-11) moves under it: range is judged against the FINAL parent
    m = _manifest(engine, task, knowledge_update=[upd(engine, 'RKU_PARENT', parent_id='RKU_L2B', class_level_start=6),
                                                  upd(engine, 'RKU_L2B', class_level_start=5)])
    backup = tmp_path / 'f.json'
    apply(engine, m, execute=True, backup=backup)
    rollback(engine, json.loads(backup.read_text()), execute=True)
    assert _snap(engine) == snapshot


@pytest.mark.parametrize('node,change,match', [
    ('RKU_OLD', {'parent_id': 'RKU_L2'}, 'level mismatch'),            # L4 under L2
    ('RKU_PARENT', {'parent_id': 'RKU_MID'}, 'level mismatch'),        # L3 under L3
    ('RKU_PARENT', {'parent_id': 'RKU_L1'}, 'level mismatch'),         # L3 under L1
    ('RKU_L2', {'parent_id': 'RKU_PARENT'}, 'level mismatch'),         # L2 under L3
    ('RKU_L1', {'parent_id': 'RKU_L2'}, 'L1 node cannot have a parent'),
    ('RKU_PARENT', {'parent_id': 'RKU_MISSING'}, 'does not exist'),
    ('RKU_PARENT', {'parent_id': ''}, 'must not be empty'),
    ('RKU_PARENT', {'parent_id': 'RKU_L2B', 'class_level_start': 8}, 'outside parent'),   # L2B starts at 9
    ('RKU_PARENT', {'class_level_end': 12}, 'must be 1..11'),
    ('RKU_PARENT', {'class_level_start': 11, 'class_level_end': 10}, 'exceed'),
    ('RKU_PARENT', {'class_level_start': 4, 'class_level_end': 11}, 'outside parent'),  # parent RKU_L2 starts at 5
])
def test_invalid_updates_are_refused_and_write_nothing(world, tmp_path, node, change, match):
    engine, task, _ = world
    _refused(engine, _manifest(engine, task, knowledge_update=[upd(engine, node, **change)]), tmp_path, match)


def test_reparent_to_inactive_parent_is_refused(world, tmp_path):
    engine, task, _ = world
    with engine.begin() as conn:
        conn.execute(text("UPDATE knowledge_hierarchy SET is_active=false WHERE id='RKU_L2B'"))
    _refused(engine, _manifest(engine, task, knowledge_update=[upd(engine, 'RKU_PARENT', parent_id='RKU_L2B')]), tmp_path, 'not active')
    with engine.begin() as conn:
        conn.execute(text("UPDATE knowledge_hierarchy SET is_active=true WHERE id='RKU_L2B'"))


def test_reparent_creating_a_cycle_is_refused(world, tmp_path):
    engine, task, _ = world
    with engine.begin() as conn:  # level-inconsistent legacy row: an L2 hanging under RKU_PARENT
        _node(conn, 'RKU_L2C', 'L2', 'RKU_PARENT', 10, 11)
    _refused_cycle = _manifest(engine, task, knowledge_update=[upd(engine, 'RKU_PARENT', parent_id='RKU_L2C')])
    for execute in (False, True):
        with pytest.raises(ValueError, match='cycle'):
            apply(engine, _refused_cycle, execute=execute, backup=tmp_path / 'c.json')
    assert not (tmp_path / 'c.json').exists() and _skill(engine) == 'RKU_OLD'
    with engine.connect() as conn:
        assert _row(conn, 'RKU_PARENT')['parent_id'] == 'RKU_L2'


def test_children_may_not_escape_a_narrowed_class_range(world, tmp_path):
    engine, task, _ = world
    _refused(engine, _manifest(engine, task, knowledge_update=[upd(engine, 'RKU_PARENT', class_level_start=11)]), tmp_path, 'active child')


def test_class_start_change_of_node_with_edges_is_refused(world, tmp_path):
    engine, task, _ = world
    with engine.begin() as conn:
        conn.execute(text("""INSERT INTO skill_prerequisites(skill_id,prerequisite_id,dependency_type,weight,criticality,relationship_description,discovery_source)
                             VALUES ('RKU_MID','RKU_EMPTY','hard',0.9,3,'Needed','expert')"""))
    _refused(engine, _manifest(engine, task, knowledge_update=[upd(engine, 'RKU_MID', class_level_start=11)]), tmp_path, 'prerequisite edges')


# ---------------------------------------------------------------- deactivate
def test_deactivate_ok_when_the_same_manifest_empties_the_node_then_exact_rollback(world, tmp_path):
    engine, task, snapshot = world
    m = _manifest(engine, task, move_to='RKU_OTHER',
                  knowledge_deactivate=[deact(engine, 'RKU_OLD'), deact(engine, 'RKU_SPARE'), deact(engine, 'RKU_PARENT'), deact(engine, 'RKU_EMPTY')])
    assert apply(engine, m)['knowledge_deactivated'] == ['RKU_OLD', 'RKU_SPARE', 'RKU_PARENT', 'RKU_EMPTY']
    assert _snap(engine) == snapshot
    backup = tmp_path / 'd.json'
    apply(engine, m, execute=True, backup=backup)
    with engine.connect() as conn:
        assert [conn.scalar(text("SELECT is_active FROM knowledge_hierarchy WHERE id=:i"), {'i': i})
                for i in ('RKU_OLD', 'RKU_SPARE', 'RKU_PARENT', 'RKU_EMPTY', 'RKU_MID')] == [False] * 4 + [True]
    assert _skill(engine) == 'RKU_OTHER'
    again = apply(engine, m, execute=True, backup=tmp_path / 'again.json')
    assert again['knowledge_deactivated'] == [] and not (tmp_path / 'again.json').exists()
    rollback(engine, json.loads(backup.read_text()), execute=True)
    assert _snap(engine) == snapshot and _skill(engine) == 'RKU_OLD'
    assert rollback(engine, json.loads(backup.read_text()), execute=True)['already_restored'] == ['RKU_TASK']


def test_deactivate_refused_while_tasks_remain(world, tmp_path):
    engine, task, _ = world
    # the repair moves the task INTO RKU_SPARE, and RKU_OLD keeps no task only if the move happens
    _refused(engine, _manifest(engine, task, move_to='RKU_SPARE', knowledge_deactivate=[deact(engine, 'RKU_SPARE')]), tmp_path, 'still have active tasks')
    # task repaired but another active task stays on RKU_OTHER
    with engine.begin() as conn:
        conn.execute(text("""INSERT INTO tasks_master(id,skill_id,question_text,correct_answer,answer_type,difficulty,cognitive_load,is_active,tags)
                             VALUES ('RKU_TASK2','RKU_OTHER','Other','0','exact_number','B','apply',true,'{}')"""))
    try:
        _refused(engine, _manifest(engine, task, move_to='RKU_SPARE', knowledge_deactivate=[deact(engine, 'RKU_OTHER')]), tmp_path, 'RKU_OTHER \\(1\\)')
        with engine.begin() as conn:  # an INACTIVE leftover task does not block
            conn.execute(text("UPDATE tasks_master SET is_active=false WHERE id='RKU_TASK2'"))
        apply(engine, _manifest(engine, task, knowledge_deactivate=[deact(engine, 'RKU_OTHER')]), execute=True, backup=tmp_path / 'ok.json')
        rollback(engine, json.loads((tmp_path / 'ok.json').read_text()), execute=True)
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM tasks_master WHERE id='RKU_TASK2'"))


def test_deactivate_refused_without_the_repair_that_empties_it(world, tmp_path):
    engine, task, _ = world
    # repair moves the task to RKU_OTHER; deactivating RKU_OLD is fine, but deactivating RKU_OTHER (task lands there) is not
    _refused(engine, _manifest(engine, task, move_to='RKU_OTHER', knowledge_deactivate=[deact(engine, 'RKU_OTHER')]), tmp_path, 'still have active tasks')


def test_l3_with_active_children_is_refused(world, tmp_path):
    engine, task, _ = world
    _refused(engine, _manifest(engine, task, move_to='RKU_OTHER', knowledge_deactivate=[deact(engine, 'RKU_PARENT')]), tmp_path, 'active children remain')


def test_l3_children_moved_away_in_the_same_manifest_do_not_block(world, tmp_path):
    engine, task, snapshot = world
    m = _manifest(engine, task, move_to='RKU_OTHER',
                  knowledge_update=[upd(engine, 'RKU_OLD', parent_id='RKU_MID'), upd(engine, 'RKU_SPARE', parent_id='RKU_MID')],
                  knowledge_deactivate=[deact(engine, 'RKU_PARENT')])
    backup = tmp_path / 'm.json'
    apply(engine, m, execute=True, backup=backup)
    with engine.connect() as conn:
        assert _row(conn, 'RKU_PARENT')['is_active'] is False and _row(conn, 'RKU_OLD')['parent_id'] == 'RKU_MID'
    rollback(engine, json.loads(backup.read_text()), execute=True)
    assert _snap(engine) == snapshot


def test_node_named_by_a_prerequisite_edge_is_refused(world, tmp_path):
    engine, task, _ = world
    with engine.begin() as conn:
        conn.execute(text("""INSERT INTO skill_prerequisites(skill_id,prerequisite_id,dependency_type,weight,criticality,relationship_description,discovery_source)
                             VALUES ('RKU_MID','RKU_EMPTY','hard',0.9,3,'Needed','expert')"""))
    _refused(engine, _manifest(engine, task, knowledge_deactivate=[deact(engine, 'RKU_EMPTY')]), tmp_path, 'skill_prerequisites')
    _refused(engine, _manifest(engine, task, knowledge_deactivate=[deact(engine, 'RKU_MID')]), tmp_path, 'skill_prerequisites')


def test_only_l3_l4_may_be_deactivated(world, tmp_path):
    engine, task, _ = world
    _refused(engine, _manifest(engine, task, knowledge_deactivate=[deact(engine, 'RKU_L2B')]), tmp_path, 'only L3/L4')


def test_same_node_updated_and_deactivated_is_refused(world, tmp_path):
    engine, task, _ = world
    _refused(engine, _manifest(engine, task, knowledge_update=[upd(engine, 'RKU_EMPTY', name_ru='X')],
                               knowledge_deactivate=[deact(engine, 'RKU_EMPTY')]), tmp_path, 'both')


def test_edge_to_a_node_deactivated_in_the_same_manifest_is_refused(world, tmp_path):
    engine, task, _ = world
    edge = {'skill_id': 'RKU_MID', 'prerequisite_id': 'RKU_EMPTY', 'dependency_type': 'hard', 'weight': 0.9, 'criticality': 3,
            'relationship_description': 'Needed', 'discovery_source': 'expert'}
    _refused(engine, _manifest(engine, task, knowledge_deactivate=[deact(engine, 'RKU_EMPTY')], prerequisites=[edge]), tmp_path, 'not active')


# ---------------------------------------------------------------- drift
@pytest.mark.parametrize('key', ['knowledge_update', 'knowledge_deactivate'])
@pytest.mark.parametrize('drift', ['name_ru', 'importance', 'inactive_other', 'missing', 'parent_id'])
def test_drift_is_refused_and_writes_nothing(world, tmp_path, key, drift):
    engine, task, _ = world
    node = 'RKU_EMPTY'
    entry = upd(engine, node, name_ru='Renamed') if key == 'knowledge_update' else deact(engine, node)
    m = _manifest(engine, task, **{key: [entry]})
    with engine.begin() as conn:
        if drift == 'name_ru':
            conn.execute(text("UPDATE knowledge_hierarchy SET name_ru='Changed' WHERE id=:i"), {'i': node})
        elif drift == 'importance':
            conn.execute(text("UPDATE knowledge_hierarchy SET importance=9 WHERE id=:i"), {'i': node})
        elif drift == 'parent_id':
            conn.execute(text("UPDATE knowledge_hierarchy SET parent_id='RKU_L2B' WHERE id=:i"), {'i': node})
        elif drift == 'inactive_other':  # inactive AND different from `before` and from the after-image
            conn.execute(text("UPDATE knowledge_hierarchy SET is_active=false, name_ru='Changed' WHERE id=:i"), {'i': node})
        else:
            conn.execute(text("DELETE FROM knowledge_hierarchy WHERE id=:i"), {'i': node})
    for execute in (False, True):
        with pytest.raises(ValueError, match='drift|missing'):
            apply(engine, m, execute=execute, backup=tmp_path / 'bad.json')
    assert not (tmp_path / 'bad.json').exists() and _skill(engine) == 'RKU_OLD'


@pytest.mark.parametrize('how', ['inactive_before', 'partial_before', 'empty_set', 'unknown_field', 'noop', 'bad_importance', 'bool_int', 'extra_key'])
def test_malformed_entries_are_refused(world, tmp_path, how):
    engine, task, _ = world
    e = upd(engine, 'RKU_EMPTY', name_ru='Renamed')
    if how == 'inactive_before':
        e['before']['is_active'] = False
    elif how == 'partial_before':
        del e['before']['description']
    elif how == 'empty_set':
        e['set'] = {}
    elif how == 'unknown_field':
        e['set'] = {'level': 'L2'}
    elif how == 'noop':
        e['set'] = {'name_ru': e['before']['name_ru']}
    elif how == 'bad_importance':
        e['set'] = {'importance': 11}
    elif how == 'bool_int':
        e['set'] = {'sequence_order': True}
    else:
        e['x'] = 1
    _refused(engine, _manifest(engine, task, knowledge_update=[e]), tmp_path, '.')


# ---------------------------------------------------------------- rollback exactness
def test_failure_after_writes_rolls_everything_back(world, tmp_path, monkeypatch):
    engine, task, snapshot = world
    m = _manifest(engine, task, move_to='RKU_OTHER', knowledge_update=[upd(engine, 'RKU_MID', name_ru='Renamed')],
                  knowledge_deactivate=[deact(engine, 'RKU_EMPTY')])

    def boom(*a, **k):
        raise ValueError('post-write boom')
    monkeypatch.setattr(knowledge_repair, 'verify_written', boom)
    with pytest.raises(ValueError, match='boom'):
        apply(engine, m, execute=True, backup=tmp_path / 'f.json')
    assert _snap(engine) == snapshot and _skill(engine) == 'RKU_OLD'


@pytest.mark.parametrize('what', ['update', 'deactivate'])
def test_rollback_refuses_newer_changes_and_changes_nothing(world, tmp_path, what):
    engine, task, snapshot = world
    m = _manifest(engine, task, knowledge_update=[upd(engine, 'RKU_MID', name_ru='Renamed')],
                  knowledge_deactivate=[deact(engine, 'RKU_EMPTY')])
    backup = tmp_path / 'b.json'
    apply(engine, m, execute=True, backup=backup)
    after = _snap(engine)
    with engine.begin() as conn:
        if what == 'update':
            conn.execute(text("UPDATE knowledge_hierarchy SET name_ru='Newer edit' WHERE id='RKU_MID'"))
        else:
            conn.execute(text("UPDATE knowledge_hierarchy SET is_active=true WHERE id='RKU_EMPTY'"))
    drifted = _snap(engine)
    with pytest.raises(ValueError, match='drift'):
        rollback(engine, json.loads(backup.read_text()), execute=True)
    assert _snap(engine) == drifted
    assert _skill(engine) == 'RKU_SPARE'
    with engine.begin() as conn:  # undo the newer edit; rollback then works and is exact
        if what == 'update':
            conn.execute(text("UPDATE knowledge_hierarchy SET name_ru='Renamed' WHERE id='RKU_MID'"))
        else:
            conn.execute(text("UPDATE knowledge_hierarchy SET is_active=false WHERE id='RKU_EMPTY'"))
    assert {k: v for k, v in _snap(engine).items()} == after
    rollback(engine, json.loads(backup.read_text()), execute=True)
    assert _snap(engine) == snapshot


def test_rollback_dry_run_writes_nothing(world, tmp_path):
    engine, task, _ = world
    backup = tmp_path / 'b.json'
    apply(engine, _manifest(engine, task, knowledge_update=[upd(engine, 'RKU_MID', name_ru='Renamed')],
                            knowledge_deactivate=[deact(engine, 'RKU_EMPTY')]), execute=True, backup=backup)
    after = _snap(engine)
    assert rollback(engine, json.loads(backup.read_text()))['restored'] == ['RKU_TASK']
    assert _snap(engine) == after
