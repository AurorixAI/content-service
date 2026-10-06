"""Bounded insertion of inactive reviewed nodes in a task-repair transaction."""
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


def prepare(conn, nodes):
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
            if set(n) != FIELDS or n['is_active'] is not False or n['level'] not in LEVELS:
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
