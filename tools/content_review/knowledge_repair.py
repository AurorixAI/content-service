"""Bounded taxonomy changes inside a task-repair transaction.

Supported, all optional and all rolled back exactly from the private backup:
  * insert reviewed nodes (inactive by default; ACTIVE only when the manifest
    sets ``knowledge_allow_active`` true),
  * ``knowledge_activate``: [{"id", "before": <full node row>, "set": {optional fields}}]
    flips an existing inactive node to active (and applies the optional ``set`` of
    importance / sequence_order / cognitive_type / name_ru / description /
    assessed_ability / parent_id); refused if the row differs from ``before``,
  * ``prerequisites``: new rows for skill_prerequisites; duplicates refused.
"""
from decimal import Decimal, InvalidOperation
from sqlalchemy import text

FIELDS = {'id', 'level', 'parent_id', 'name', 'name_ru', 'description', 'assessed_ability',
          'class_level_start', 'class_level_end', 'importance', 'sequence_order',
          'cognitive_type', 'is_active'}
LEVELS = {'L1': None, 'L2': 'L1', 'L3': 'L2', 'L4': 'L3'}
# Columns every schema variant must have; others (e.g. the live-only `name`) are optional.
REQUIRED_COLUMNS = {'id', 'level', 'parent_id', 'name_ru', 'description', 'assessed_ability',
                    'class_level_start', 'class_level_end', 'importance', 'sequence_order',
                    'cognitive_type', 'is_active'}


def table_columns(conn):
    """Columns of knowledge_hierarchy in the connected database.

    The live local schema and `alembic upgrade head` differ (live has `name`,
    alembic has `origin`/`is_advanced`), so writes and drift checks are limited
    to columns that really exist.
    """
    cols = {r[0] for r in conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='knowledge_hierarchy' AND table_schema=current_schema()"))}
    if not REQUIRED_COLUMNS <= cols:
        raise ValueError('knowledge_hierarchy lacks columns: ' + ', '.join(sorted(REQUIRED_COLUMNS - cols)))
    return cols


def prepare(conn, nodes, allow_active=False):
    if not nodes:
        return []
    cols = table_columns(conn)
    ids = [n.get('id') for n in nodes]
    if not all(ids) or len(set(ids)) != len(ids):
        raise ValueError('knowledge IDs must be unique')
    known = {r['id']: dict(r) for r in conn.execute(text(
        'SELECT * FROM knowledge_hierarchy WHERE id = ANY(:ids) FOR UPDATE'),
        {'ids': ids + [n.get('parent_id') for n in nodes if n.get('parent_id')]}).mappings()}
    missing, todo = [], list(nodes)
    while todo:
        ready = [n for n in todo if not n.get('parent_id') or n['parent_id'] in known]
        if not ready:
            raise ValueError('knowledge parent is missing or cyclic')
        for n in ready:
            if set(n) != FIELDS or n['level'] not in LEVELS or not isinstance(n['is_active'], bool) \
                    or (n['is_active'] and not allow_active):
                raise ValueError('only complete inactive reviewed knowledge nodes may be inserted')
            parent = known.get(n['parent_id'])
            if (parent['level'] if parent else None) != LEVELS[n['level']]:
                raise ValueError('knowledge parent level mismatch')
            if not n['name_ru'] or not n['description'] or (n['level'] == 'L4' and not n['assessed_ability']):
                raise ValueError('knowledge nodes need a subject definition')
            if n['id'] in known:
                if any(known[n['id']].get(k) != v for k, v in n.items() if k in cols):
                    raise ValueError('existing knowledge node drift; refusing to repurpose it')
            else:
                missing.append(n)
                known[n['id']] = n
            todo.remove(n)
    return missing


def insert(conn, nodes):
    cols = table_columns(conn)
    for node in nodes:
        keys = sorted(k for k in node if k in cols)
        conn.execute(text('INSERT INTO knowledge_hierarchy (' + ','.join(keys) + ') VALUES ('
                          + ','.join(':'+k for k in keys) + ')'), {k: node[k] for k in keys})


def check_rollback(conn, nodes):
    if not nodes:
        return
    cols = table_columns(conn)
    rows = {r['id']: r for r in conn.execute(text(
        'SELECT * FROM knowledge_hierarchy WHERE id = ANY(:ids) FOR UPDATE'),
        {'ids': [n['id'] for n in nodes]}).mappings()}
    for n in nodes:
        r = rows.get(n['id'])
        if r is None or any(r.get(k) != v for k, v in n.items() if k in cols):
            raise ValueError('rollback knowledge drift; nothing deleted')
        if any(r.get(k) is not None for k in ('example_task', 'difficulty_level', 'formula')):
            raise ValueError('rollback would discard newer knowledge review')


def remove(conn, nodes):
    # Foreign keys protect any new references not belonging to this repair.
    for n in reversed(nodes):
        conn.execute(text('DELETE FROM knowledge_hierarchy WHERE id=:id'), {'id': n['id']})


# --------------------------------------------------------------------------
# Activation of existing nodes and prerequisite edges
# --------------------------------------------------------------------------
SETTABLE = {'importance', 'sequence_order', 'cognitive_type', 'name_ru', 'name', 'description',
            'assessed_ability', 'parent_id'}
EDGE_FIELDS = {'skill_id', 'prerequisite_id', 'dependency_type', 'weight', 'criticality',
               'relationship_description', 'discovery_source'}
EDGE_TYPES = {'hard', 'soft'}


def _dec(value):
    if isinstance(value, bool):
        raise ValueError('weight must be numeric')
    try:
        return Decimal(str(value))
    except InvalidOperation:
        raise ValueError('weight must be numeric') from None


def _same(row, want, cols):
    return all(row.get(k) == v for k, v in want.items() if k in cols)


def prepare_activation(conn, entries, inserted=()):
    """Return (to_activate, already_active) as {'id','before','after'} dicts; refuse any drift."""
    if not entries:
        return [], []
    cols = table_columns(conn)
    ids = [e.get('id') for e in entries]
    if not all(ids) or len(set(ids)) != len(ids):
        raise ValueError('activation IDs must be unique')
    todo, done = [], []
    rows = {r['id']: dict(r) for r in conn.execute(text(
        'SELECT * FROM knowledge_hierarchy WHERE id = ANY(:ids) FOR UPDATE'), {'ids': ids}).mappings()}
    for e in entries:
        before, change = e.get('before'), e.get('set', {})
        if not set(e) <= {'id', 'before', 'set'} or not {'id', 'before'} <= set(e) \
                or not isinstance(before, dict) or set(before) not in (FIELDS, FIELDS - {'name'}) \
                or before['id'] != e['id'] or before['is_active'] is not False:
            raise ValueError('activation needs the complete inactive before-row')
        if not isinstance(change, dict) or not set(change) <= SETTABLE or not set(change) <= set(before):
            raise ValueError('activation may only set: ' + ', '.join(sorted(SETTABLE)))
        for key, value in change.items():
            if key in ('importance', 'sequence_order') and (isinstance(value, bool) or not isinstance(value, int)):
                raise ValueError(key + ' must be an integer')
            if key == 'importance' and not 1 <= value <= 10:
                raise ValueError('importance must be 1..10')
            if key in ('name_ru', 'name', 'parent_id') and not value:
                raise ValueError(key + ' must not be empty')
        after = {**before, **change, 'is_active': True}
        if not after['name_ru'] or not after['description'] or (after['level'] == 'L4' and not after['assessed_ability']):
            raise ValueError('knowledge nodes need a subject definition')
        row = rows.get(e['id'])
        if row is None:
            raise ValueError('activation target is missing: ' + e['id'])
        entry = {'id': e['id'], 'before': before, 'after': after}
        if _same(row, before, cols):
            todo.append(entry)
        elif _same(row, after, cols):
            done.append(entry)
        else:
            raise ValueError('knowledge node drift; refusing to activate ' + e['id'])
    return todo, done


def prepare_edges(conn, edges, active_after, extra=None):
    """Validate edges; return (to_insert, already_present). active_after: ids active in the final state."""
    if not edges:
        return [], []
    cols = {r[0] for r in conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='skill_prerequisites' AND table_schema=current_schema()"))}
    if not {'skill_id', 'prerequisite_id', 'weight', 'dependency_type', 'criticality',
            'relationship_description', 'discovery_source'} <= cols:
        raise ValueError('skill_prerequisites lacks required columns')
    seen = set()
    for e in edges:
        if set(e) != EDGE_FIELDS:
            raise ValueError('prerequisite edge needs exactly: ' + ', '.join(sorted(EDGE_FIELDS)))
        key = (e['skill_id'], e['prerequisite_id'])
        if key in seen:
            raise ValueError('duplicate prerequisite edge in manifest: %s -> %s' % key)
        seen.add(key)
        if e['skill_id'] == e['prerequisite_id']:
            raise ValueError('prerequisite edge to itself')
        if e['dependency_type'] not in EDGE_TYPES:
            raise ValueError('dependency_type must be hard or soft')
        w = _dec(e['weight'])
        if not (0 < w <= 1) or w != w.quantize(Decimal('0.01')):
            raise ValueError('weight must be in (0,1] with at most 2 decimals')
        if isinstance(e['criticality'], bool) or not isinstance(e['criticality'], int) or not 1 <= e['criticality'] <= 10:
            raise ValueError('criticality must be an integer 1..10')
        if not (e['relationship_description'] or '').strip() or not (e['discovery_source'] or '').strip():
            raise ValueError('prerequisite edge needs description and discovery_source')
    ids = sorted({i for k in seen for i in k})
    nodes = {r['id']: dict(r) for r in conn.execute(text(
        'SELECT id, level, class_level_start FROM knowledge_hierarchy WHERE id = ANY(:ids)'), {'ids': ids}).mappings()}
    nodes.update({n['id']: n for n in (extra or [])})
    for i in ids:
        if i not in nodes:
            raise ValueError('prerequisite endpoint is not a knowledge node: ' + i)
        if i not in active_after:
            raise ValueError('prerequisite endpoint is not active: ' + i)
    existing = {(r['skill_id'], r['prerequisite_id']): dict(r) for r in conn.execute(text(
        'SELECT * FROM skill_prerequisites'
        ' WHERE skill_id = ANY(:ids) AND prerequisite_id = ANY(:ids) FOR UPDATE'), {'ids': ids}).mappings()}
    todo, done = [], []
    for e in edges:
        key = (e['skill_id'], e['prerequisite_id'])
        row = existing.get(key)
        if row is None:
            if (e['prerequisite_id'], e['skill_id']) in existing:
                raise ValueError('reverse prerequisite edge already exists: %s -> %s' % key)
            todo.append(e)
        elif _edge_same(row, e):
            done.append(e)
        else:
            raise ValueError('prerequisite edge already exists with different values: %s -> %s' % key)
    # No cycles: after adding the new edges, a skill must not be reachable from its own prerequisite.
    graph = {}
    for r in conn.execute(text('SELECT skill_id, prerequisite_id FROM skill_prerequisites')):
        graph.setdefault(r[0], set()).add(r[1])
    for e in todo:
        graph.setdefault(e['skill_id'], set()).add(e['prerequisite_id'])
    for e in todo:
        stack, seen_nodes = [e['prerequisite_id']], set()
        while stack:
            cur = stack.pop()
            if cur == e['skill_id']:
                raise ValueError('prerequisite edge creates a cycle: %s -> %s' % (e['skill_id'], e['prerequisite_id']))
            if cur not in seen_nodes:
                seen_nodes.add(cur)
                stack.extend(graph.get(cur, ()))
    # is_cross_grade is derived, never supplied by the manifest (copies keep the manifest untouched)
    todo = [dict(e, _cross=nodes[e['skill_id']]['class_level_start'] != nodes[e['prerequisite_id']]['class_level_start'])
            for e in todo]
    return todo, done


def _edge_same(row, e):
    return all((_dec(row[k]) == _dec(e[k])) if k == 'weight' else row[k] == e[k] for k in EDGE_FIELDS)


def _edge_cols(conn):
    return {r[0] for r in conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='skill_prerequisites' AND table_schema=current_schema()"))}


def _settable_cols(conn):
    return SETTABLE & table_columns(conn)


def activate(conn, entries):
    cols = table_columns(conn)
    extra = ', updated_at = NOW()' if 'updated_at' in cols else ''
    for e in entries:
        keys = sorted(k for k in _settable_cols(conn) if k in e['after'] and e['after'][k] != e['before'][k])
        conn.execute(text('UPDATE knowledge_hierarchy SET is_active = TRUE' + extra
                          + ''.join(', %s = :%s' % (k, k) for k in keys) + ' WHERE id = :id'),
                     {'id': e['id'], **{k: e['after'][k] for k in keys}})


def deactivate(conn, entries):
    """Restore the exact before-row (inactive, original importance/order/parent/text)."""
    cols = table_columns(conn)
    extra = ', updated_at = NOW()' if 'updated_at' in cols else ''
    for e in entries:
        keys = sorted(k for k in _settable_cols(conn) if k in e['before'])
        conn.execute(text('UPDATE knowledge_hierarchy SET is_active = FALSE' + extra
                          + ''.join(', %s = :%s' % (k, k) for k in keys) + ' WHERE id = :id'),
                     {'id': e['id'], **{k: e['before'][k] for k in keys}})


def edge_records(edges):
    """Edge identity as stored in the backup (no derived columns)."""
    return [dict({k: e[k] for k in EDGE_FIELDS}, weight=str(_dec(e['weight']))) for e in edges]


def insert_edges(conn, edges):
    cols = _edge_cols(conn)
    for e in edges:
        values = {k: e[k] for k in EDGE_FIELDS}
        if 'is_cross_grade' in cols:
            values['is_cross_grade'] = bool(e['_cross'])
        keys = sorted(values)
        conn.execute(text('INSERT INTO skill_prerequisites (' + ','.join(keys) + ') VALUES ('
                          + ','.join(':' + k for k in keys) + ')'), values)


def check_rollback_edges(conn, edges):
    if not edges:
        return
    for e in edges:
        row = conn.execute(text('SELECT * FROM skill_prerequisites WHERE skill_id=:s AND prerequisite_id=:p FOR UPDATE'),
                           {'s': e['skill_id'], 'p': e['prerequisite_id']}).mappings().first()
        if row is None or not _edge_same(row, e):
            raise ValueError('rollback prerequisite drift; nothing deleted')


def remove_edges(conn, edges):
    for e in edges:
        conn.execute(text('DELETE FROM skill_prerequisites WHERE skill_id=:s AND prerequisite_id=:p'),
                     {'s': e['skill_id'], 'p': e['prerequisite_id']})


def check_rollback_activation(conn, entries):
    if not entries:
        return
    cols = table_columns(conn)
    current = {r['id']: r for r in conn.execute(text(
        'SELECT * FROM knowledge_hierarchy WHERE id = ANY(:ids) FOR UPDATE'),
        {'ids': [e['id'] for e in entries]}).mappings()}
    for e in entries:
        r = current.get(e['id'])
        if r is None or not _same(r, e['after'], cols):
            raise ValueError('rollback knowledge activation drift; nothing changed')


def state_restored(conn, saved):
    """True when every taxonomy change of the backup is already undone."""
    cols = table_columns(conn)
    for n in saved.get('knowledge_added', []):
        if conn.scalar(text('SELECT count(*) FROM knowledge_hierarchy WHERE id=:id'), {'id': n['id']}):
            return False
    for e in saved.get('knowledge_activated', []):
        r = conn.execute(text('SELECT * FROM knowledge_hierarchy WHERE id=:id'), {'id': e['id']}).mappings().first()
        if r is not None and _same(r, e['after'], cols):
            return False
    for e in saved.get('prerequisites_added', []):
        if conn.scalar(text('SELECT count(*) FROM skill_prerequisites WHERE skill_id=:s AND prerequisite_id=:p'),
                       {'s': e['skill_id'], 'p': e['prerequisite_id']}):
            return False
    return True


def plan(conn, manifest):
    """Validate every taxonomy part of a manifest against the locked database state.

    Returns a dict: added (new nodes), activate / already_active (node before-rows),
    edges / edges_present. Nothing is written.
    """
    nodes = manifest.get('knowledge_nodes', [])
    entries = manifest.get('knowledge_activate', [])
    edges = manifest.get('prerequisites', [])
    allow_active = manifest.get('knowledge_allow_active')
    if allow_active not in (None, True, False):
        raise ValueError('knowledge_allow_active must be boolean')
    added = prepare(conn, nodes, allow_active is True)
    to_act, act_done = prepare_activation(conn, entries)
    if {n['id'] for n in nodes} & {e['id'] for e in entries}:
        raise ValueError('a node cannot be both inserted and activated')
    state = {}
    want = {n.get('parent_id') for n in nodes if n.get('is_active')} | {e['after']['parent_id'] for e in to_act + act_done}
    want |= {i for e in edges for i in (e.get('skill_id'), e.get('prerequisite_id'))}
    for r in conn.execute(text('SELECT id, is_active FROM knowledge_hierarchy WHERE id = ANY(:ids)'),
                          {'ids': sorted(i for i in want if i)}):
        state[r[0]] = bool(r[1])
    for n in nodes:
        state[n['id']] = n['is_active']
    for e in to_act + act_done:
        state[e['id']] = True
    for n in nodes:
        if n['is_active'] and n.get('parent_id') and not state.get(n['parent_id']):
            raise ValueError('active knowledge node needs an active parent: ' + n['id'])
    levels = {r[0]: r[1] for r in conn.execute(text(
        'SELECT id, level FROM knowledge_hierarchy WHERE id = ANY(:ids)'),
        {'ids': sorted({e['after']['parent_id'] for e in to_act + act_done if e['after']['parent_id']})})}
    levels.update({n['id']: n['level'] for n in nodes})
    for e in to_act + act_done:
        parent = e['after'].get('parent_id')
        if parent and not state.get(parent):
            raise ValueError('activated knowledge node needs an active parent: ' + e['id'])
        if (levels.get(parent) if parent else None) != LEVELS[e['after']['level']]:
            raise ValueError('activated knowledge node parent level mismatch: ' + e['id'])
    todo_edges, edges_present = prepare_edges(conn, edges, {i for i, v in state.items() if v}, nodes)
    return {'added': added, 'activate': to_act, 'already_active': act_done,
            'edges': todo_edges, 'edges_present': edges_present}
