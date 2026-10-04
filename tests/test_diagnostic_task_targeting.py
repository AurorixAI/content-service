"""Exercise the real SQL ranking and LIMIT with a task beyond the first page."""
import sqlite3
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.content_router import router, get_db, require_internal_service_token


class SQLiteConnection:
    def __init__(self):
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.executescript("""
            CREATE TABLE tasks_master (id TEXT, skill_id TEXT, irt_difficulty REAL, is_active BOOLEAN);
            CREATE TABLE knowledge_hierarchy (id TEXT);
            INSERT INTO knowledge_hierarchy VALUES ('skill');
        """)
        self.db.executemany("INSERT INTO tasks_master VALUES (?, 'skill', ?, 1)",
                            [(f'easy-{i}', -1.0) for i in range(25)] + [('matched', 1.5)])
        self.db.execute("INSERT INTO tasks_master VALUES ('inactive', 'skill', 1.5, 0)")
    def execute(self, statement, params):
        return self.db.execute(str(statement), params)


@pytest.fixture
def client():
    conn = SQLiteConnection()
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[get_db] = lambda: conn
    app.dependency_overrides[require_internal_service_token] = lambda: None
    # Only presentation columns are reduced; WHERE, ORDER BY and LIMIT are real.
    with patch("src.api.content_router._TASK_COLS", "tm.id, tm.irt_difficulty"), \
         patch("src.api.content_router._task_row_full", lambda r: {"id": r[0], "b": r[1]}):
        with TestClient(app) as http:
            yield http
    conn.db.close()


def test_nearest_task_is_selected_before_limit_and_inactive_stays_excluded(client):
    response = client.get('/api/v1/content/tasks', params={'skill_id': 'skill', 'target_b': 1.5, 'limit': 20})
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 20 and rows[0]['id'] == 'matched'
    assert all(row['id'] != 'inactive' for row in rows)


def test_no_target_preserves_old_order(client):
    rows = client.get('/api/v1/content/tasks', params={'skill_id': 'skill', 'limit': 20}).json()
    assert len(rows) == 20 and all(row['b'] == -1 for row in rows)


@pytest.mark.parametrize('target', ['nan', 'inf', '-inf', '4.1', '-4.1'])
def test_invalid_target_rejected_at_api_boundary(client, target):
    assert client.get('/api/v1/content/tasks', params={'skill_id': 'skill', 'target_b': target}).status_code == 422
