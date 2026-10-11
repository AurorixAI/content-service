"""Bounded taxonomy changes inside a task-repair transaction.

Supported, all optional and all rolled back exactly from the private backup:
  * insert reviewed nodes (inactive by default; ACTIVE only when the manifest
    sets ``knowledge_allow_active`` true),
  * ``knowledge_activate``: [{"id", "before": <full node row>, "set": {optional fields}}]
    flips an existing inactive node to active (and applies the optional ``set`` of
    importance / sequence_order / cognitive_type / name_ru / description /
    assessed_ability / parent_id); refused if the row differs from ``before``,
  * ``knowledge_update``: [{"id", "before": <full ACTIVE node row>, "set": {name, name_ru,
    description, parent_id, importance, sequence_order, class_level_start, class_level_end}}]
    edits an active node in place; refused on drift, on a parent that is missing / inactive /
    of the wrong level (L4->L3, L3->L2, L2->L1), on class levels outside the parent range
    (or children escaping the node's new range), on a cycle, and on a class_level_start change of
    a node that has prerequisite edges (their derived is_cross_grade would go stale),
  * ``knowledge_deactivate``: [{"id", "before": <full ACTIVE node row>}] switches an L4/L3 node off.
    Allowed only when, AFTER this manifest's task repairs, it has 0 active tasks (L3: also 0 active
    children) and no skill_prerequisites row names it (edges have no active flag, so a remaining
    edge would dangle: remove the edge by another route first; refused with a clear message),
  * ``prerequisites``: new rows for skill_prerequisites; duplicates refused.

Apply order (guarded_repair.apply): nodes insert -> activate -> update -> task repairs ->
deactivate -> prerequisites -> post-write check. Rollback runs in the reverse order.
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


# --------------------------------------------------------------------------
# In-place update and deactivation of ACTIVE nodes
# --------------------------------------------------------------------------
UPDATE_SETTABLE = {'name', 'name_ru', 'description', 'parent_id', 'importance', 'sequence_order',
                   'class_level_start', 'class_level_end'}
INT_FIELDS = ('importance', 'sequence_order', 'class_level_start', 'class_level_end')
RETIRABLE = {'L3', 'L4'}


def _active_before(e, allowed_keys):
    before = e.get('before')
    if not set(e) <= allowed_keys or not {'id', 'before'} <= set(e) \
            or not isinstance(before, dict) or set(before) not in (FIELDS, FIELDS - {'name'}) \
            or before['id'] != e['id'] or before['is_active'] is not True:
        raise ValueError('needs the complete ACTIVE before-row')
    return before


def _unique_ids(entries, what):
    ids = [e.get('id') for e in entries]
    if not all(ids) or len(set(ids)) != len(ids):
        raise ValueError(what + ' IDs must be unique')
    return ids


def _locked_rows(conn, ids):
    return {r['id']: dict(r) for r in conn.execute(text(
        'SELECT * FROM knowledge_hierarchy WHERE id = ANY(:ids) FOR UPDATE'), {'ids': ids}).mappings()}


def prepare_updates(conn, entries):
    """Return (to_update, already_updated) as {'id','before','after'}; refuse any drift."""
    if not entries:
        return [], []
    cols = table_columns(conn)
    rows = _locked_rows(conn, _unique_ids(entries, 'update'))
    todo, done = [], []
    for e in entries:
        try:
            before = _active_before(e, {'id', 'before', 'set'})
        except ValueError as exc:
            raise ValueError('knowledge_update ' + str(exc)) from None
        change = e.get('set')
        if not isinstance(change, dict) or not change or not set(change) <= UPDATE_SETTABLE \
                or not set(change) <= set(before):
            raise ValueError('knowledge_update may only set: ' + ', '.join(sorted(UPDATE_SETTABLE)))
        for key, value in change.items():
            if key in INT_FIELDS and (isinstance(value, bool) or not isinstance(value, int)):
                raise ValueError(key + ' must be an integer')
            if key in ('name_ru', 'name', 'description', 'parent_id') and (not isinstance(value, str) or not value.strip()):
                raise ValueError(key + ' must not be empty')
        if 'importance' in change and not 1 <= change['importance'] <= 10:
            raise ValueError('importance must be 1..10')
        after = {**before, **change}
        for k in ('class_level_start', 'class_level_end'):
            if k in change and not 1 <= change[k] <= 11:
                raise ValueError(k + ' must be 1..11')
        if after['class_level_start'] is not None and after['class_level_end'] is not None \
                and after['class_level_start'] > after['class_level_end']:
            raise ValueError('class_level_start must not exceed class_level_end')
        if not after['name_ru'] or not after['description']:
            raise ValueError('knowledge nodes need a subject definition')
        if _same(after, before, cols):
            raise ValueError('knowledge_update changes nothing for ' + e['id'])
        row = rows.get(e['id'])
        if row is None:
            raise ValueError('update target is missing: ' + e['id'])
        entry = {'id': e['id'], 'before': before, 'after': after}
        if _same(row, before, cols):
            todo.append(entry)
        elif _same(row, after, cols):
            done.append(entry)
        else:
            raise ValueError('knowledge node drift; refusing to update ' + e['id'])
    return todo, done


def prepare_deactivations(conn, entries):
    """Return (to_deactivate, already_inactive) as {'id','before','after'}; refuse drift / bad levels."""
    if not entries:
        return [], []
    cols = table_columns(conn)
    rows = _locked_rows(conn, _unique_ids(entries, 'deactivation'))
    todo, done = [], []
    for e in entries:
        try:
            before = _active_before(e, {'id', 'before'})
        except ValueError as exc:
            raise ValueError('knowledge_deactivate ' + str(exc)) from None
        if before['level'] not in RETIRABLE:
            raise ValueError('only L3/L4 nodes may be deactivated: ' + e['id'])
        row = rows.get(e['id'])
        if row is None:
            raise ValueError('deactivation target is missing: ' + e['id'])
        entry = {'id': e['id'], 'before': before, 'after': {**before, 'is_active': False}}
        if _same(row, before, cols):
            todo.append(entry)
        elif _same(row, entry['after'], cols):
            done.append(entry)
        else:
            raise ValueError('knowledge node drift; refusing to deactivate ' + e['id'])
    return todo, done


class _Tree:
    """Final-state view of the taxonomy: database rows overlaid with this manifest's changes."""

    def __init__(self, conn, over):
        self.conn, self.over, self.cache = conn, over, {}

    def get(self, node_id):
        if node_id in self.over:
            return self.over[node_id]
        if node_id not in self.cache:
            r = self.conn.execute(text('SELECT * FROM knowledge_hierarchy WHERE id=:id'),
                                  {'id': node_id}).mappings().first()
            self.cache[node_id] = dict(r) if r else None
        return self.cache[node_id]

    def children(self, node_id):
        found = {}
        for r in self.conn.execute(text('SELECT * FROM knowledge_hierarchy WHERE parent_id=:id'),
                                   {'id': node_id}).mappings():
            found[r['id']] = self.over.get(r['id'], dict(r))
        for k, v in self.over.items():
            found.setdefault(k, v)
        return [v for v in found.values() if v.get('parent_id') == node_id]


def _edge_nodes(conn, ids):
    return {r[0] for r in conn.execute(text(
        'SELECT skill_id FROM skill_prerequisites WHERE skill_id = ANY(:i) OR prerequisite_id = ANY(:i) '
        'UNION SELECT prerequisite_id FROM skill_prerequisites WHERE skill_id = ANY(:i) OR prerequisite_id = ANY(:i)'),
        {'i': sorted(ids)}) if r[0] in ids}


def active_task_counts(conn, node_ids, repairs=()):
    """{node_id: n active tasks} AFTER the manifest's task repairs (their skill_id / is_active changes)."""
    if not node_ids:
        return {}
    repair_ids = [r['id'] for r in repairs]
    counts = {i: 0 for i in node_ids}
    for r in conn.execute(text(
            'SELECT skill_id, count(*) FROM tasks_master WHERE is_active AND skill_id = ANY(:n) '
            'AND NOT (id = ANY(:r)) GROUP BY skill_id'), {'n': sorted(node_ids), 'r': repair_ids}):
        counts[r[0]] = r[1]
    if repairs:
        cur = {r['id']: dict(r) for r in conn.execute(text(
            'SELECT id, skill_id, is_active FROM tasks_master WHERE id = ANY(:r)'), {'r': repair_ids}).mappings()}
        for rep in repairs:
            row = cur.get(rep['id'])
            if row is None:
                continue
            final = {**row, **{k: v for k, v in (rep.get('changes') or {}).items() if k in ('skill_id', 'is_active')}}
            if final['is_active'] and final['skill_id'] in counts:
                counts[final['skill_id']] += 1
    return counts


def validate_taxonomy_changes(conn, nodes, to_act, act_done, to_upd, upd_done, to_deact, deact_done, repairs):
    """Cross-check updates and deactivations against the FINAL taxonomy (database + whole manifest)."""
    ids = {}
    for label, group in (('inserted', [n['id'] for n in nodes]), ('activated', [e['id'] for e in to_act + act_done]),
                         ('updated', [e['id'] for e in to_upd + upd_done]),
                         ('deactivated', [e['id'] for e in to_deact + deact_done])):
        for i in group:
            if i in ids:
                raise ValueError('a node cannot be both %s and %s: %s' % (ids[i], label, i))
            ids[i] = label
    over = {n['id']: dict(n) for n in nodes}
    over.update({e['id']: dict(e['after']) for e in to_act + act_done + to_upd + upd_done + to_deact + deact_done})
    tree = _Tree(conn, over)
    changed_edges = _edge_nodes(conn, {e['id'] for e in to_upd + to_deact})

    for e in to_upd + upd_done:
        a, b = e['after'], e['before']
        parent = tree.get(a['parent_id']) if a['parent_id'] else None
        moved = a['parent_id'] != b['parent_id']
        ranged = (a['class_level_start'], a['class_level_end']) != (b['class_level_start'], b['class_level_end'])
        if a['level'] == 'L1' and a['parent_id']:
            raise ValueError('L1 node cannot have a parent: ' + a['id'])
        if (moved or ranged) and a['level'] != 'L1':
            if not a['parent_id']:
                raise ValueError('updated node needs a parent: ' + a['id'])
            if parent is None:
                raise ValueError('update parent does not exist: ' + a['parent_id'])
            if not parent['is_active']:
                raise ValueError('update parent is not active: ' + a['parent_id'])
            if parent['level'] != LEVELS[a['level']]:
                raise ValueError('update parent level mismatch: %s (%s) under %s (%s)'
                                 % (a['id'], a['level'], parent['id'], parent['level']))
            pr = (parent['class_level_start'], parent['class_level_end'])
            if None not in pr and None not in (a['class_level_start'], a['class_level_end']) \
                    and not (pr[0] <= a['class_level_start'] and a['class_level_end'] <= pr[1]):
                raise ValueError('class levels %s-%s of %s are outside parent %s range %s-%s'
                                 % (a['class_level_start'], a['class_level_end'], a['id'], parent['id'], pr[0], pr[1]))
        if moved:
            seen, cur = set(), a['parent_id']
            while cur:
                if cur == a['id']:
                    raise ValueError('update creates a cycle: ' + a['id'])
                if cur in seen:
                    break
                seen.add(cur)
                node = tree.get(cur)
                cur = node['parent_id'] if node else None
        if ranged:
            if a['id'] in changed_edges and a['class_level_start'] != b['class_level_start']:
                raise ValueError('class_level_start of %s cannot change: it has prerequisite edges '
                                 '(is_cross_grade would go stale)' % a['id'])
            if None not in (a['class_level_start'], a['class_level_end']):
                for child in tree.children(a['id']):
                    if child['is_active'] and None not in (child['class_level_start'], child['class_level_end']) \
                            and not (a['class_level_start'] <= child['class_level_start']
                                     and child['class_level_end'] <= a['class_level_end']):
                        raise ValueError('active child %s would leave the class range of %s'
                                         % (child['id'], a['id']))

    if to_deact:
        todo_ids = {e['id'] for e in to_deact}
        edges = _edge_nodes(conn, todo_ids)
        if edges:
            raise ValueError('cannot deactivate nodes named by skill_prerequisites edges (no active flag on edges, '
                             'they would dangle; remove the edges separately first): ' + ', '.join(sorted(edges)))
        counts = active_task_counts(conn, todo_ids, repairs)
        left = {i: n for i, n in counts.items() if n}
        if left:
            raise ValueError('cannot deactivate nodes that still have active tasks after the repairs: '
                             + ', '.join('%s (%d)' % kv for kv in sorted(left.items())))
        for e in to_deact:
            if e['before']['level'] == 'L3':
                kids = [c['id'] for c in tree.children(e['id']) if c['is_active']]
                if kids:
                    raise ValueError('cannot deactivate L3 %s: active children remain: %s'
                                     % (e['id'], ', '.join(sorted(kids)[:5])))
    return over


def verify_written(conn, plan_result, repairs=()):
    """Post-write check: every updated / deactivated row equals its after-image; deactivation preconditions still hold."""
    cols = table_columns(conn)
    for key in ('update', 'deactivate'):
        entries = plan_result.get(key, [])
        if not entries:
            continue
        rows = _locked_rows(conn, [e['id'] for e in entries])
        for e in entries:
            if not _same(rows[e['id']], e['after'], cols):
                raise ValueError('post-write knowledge mismatch: %s; transaction rolled back' % e['id'])
    if plan_result.get('deactivate'):
        ids = {e['id'] for e in plan_result['deactivate']}
        counts = active_task_counts(conn, ids, repairs)
        if any(counts.values()) or _edge_nodes(conn, ids):
            raise ValueError('post-write deactivation precondition violated; transaction rolled back')


def update(conn, entries):
    cols = table_columns(conn)
    extra = ', updated_at = NOW()' if 'updated_at' in cols else ''
    for e in entries:
        keys = sorted(k for k in UPDATE_SETTABLE & cols if k in e['after'] and e['after'][k] != e['before'][k])
        conn.execute(text('UPDATE knowledge_hierarchy SET ' + ', '.join('%s = :%s' % (k, k) for k in keys)
                          + extra + ' WHERE id = :id'), {'id': e['id'], **{k: e['after'][k] for k in keys}})


def restore_updated(conn, entries):
    """Exact before-image of every settable column."""
    cols = table_columns(conn)
    extra = ', updated_at = NOW()' if 'updated_at' in cols else ''
    for e in entries:
        keys = sorted(k for k in UPDATE_SETTABLE & cols if k in e['before'])
        conn.execute(text('UPDATE knowledge_hierarchy SET ' + ', '.join('%s = :%s' % (k, k) for k in keys)
                          + extra + ' WHERE id = :id'), {'id': e['id'], **{k: e['before'][k] for k in keys}})


def retire(conn, entries):
    cols = table_columns(conn)
    extra = ', updated_at = NOW()' if 'updated_at' in cols else ''
    for e in entries:
        conn.execute(text('UPDATE knowledge_hierarchy SET is_active = FALSE' + extra + ' WHERE id = :id'), {'id': e['id']})


def unretire(conn, entries):
    cols = table_columns(conn)
    extra = ', updated_at = NOW()' if 'updated_at' in cols else ''
    for e in entries:
        conn.execute(text('UPDATE knowledge_hierarchy SET is_active = TRUE' + extra + ' WHERE id = :id'), {'id': e['id']})


def check_rollback_after_images(conn, entries, what):
    """Rollback of update / deactivate: the row must still equal the after-image written by this repair."""
    if not entries:
        return
    cols = table_columns(conn)
    current = _locked_rows(conn, [e['id'] for e in entries])
    for e in entries:
        r = current.get(e['id'])
        if r is None or not _same(r, e['after'], cols):
            raise ValueError('rollback knowledge %s drift; nothing changed' % what)


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
    for key in ('knowledge_updated', 'knowledge_deactivated'):
        for e in saved.get(key, []):
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
    upd_entries = manifest.get('knowledge_update', [])
    deact_entries = manifest.get('knowledge_deactivate', [])
    allow_active = manifest.get('knowledge_allow_active')
    if allow_active not in (None, True, False):
        raise ValueError('knowledge_allow_active must be boolean')
    added = prepare(conn, nodes, allow_active is True)
    to_act, act_done = prepare_activation(conn, entries)
    if {n['id'] for n in nodes} & {e['id'] for e in entries}:
        raise ValueError('a node cannot be both inserted and activated')
    to_upd, upd_done = prepare_updates(conn, upd_entries)
    to_deact, deact_done = prepare_deactivations(conn, deact_entries)
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
    for e in to_deact + deact_done:
        state[e['id']] = False
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
    validate_taxonomy_changes(conn, nodes, to_act, act_done, to_upd, upd_done, to_deact, deact_done,
                              manifest.get('repairs', []))
    active_after = {i for i, v in state.items() if v}
    extra = list(nodes) + [e['after'] for e in to_upd + upd_done]
    for e in to_upd + upd_done:
        active_after.add(e['id'])
    todo_edges, edges_present = prepare_edges(conn, edges, active_after, extra)
    return {'added': added, 'activate': to_act, 'already_active': act_done,
            'update': to_upd, 'already_updated': upd_done,
            'deactivate': to_deact, 'already_deactivated': deact_done,
            'edges': todo_edges, 'edges_present': edges_present}
