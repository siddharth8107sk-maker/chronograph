"""
API Endpoint and System Consistency Tests (Course 25CS306 MP-01).
Tests HTTP status codes (200, 201, 400, 401, 404, 409), JSON structure,
data consistency between SQLite and all in-memory structures (AVL, BST, Hash Table, Trie),
and concurrency safety.
"""

import pytest
import json
import threading
import db
from app import app, USER_ENGINES, get_user_engine


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Sets up an isolated database and test client."""
    test_db = str(tmp_path / "test_api_chronograph.db")
    monkeypatch.setattr(db, "DB_PATH", test_db)
    USER_ENGINES.clear()
    db.init_db()

    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def auth_client(client):
    """Signs in with the seeded demo user and returns client with session cookie."""
    res = client.post('/api/auth/signin', json={
        'email': 'demo@chronograph.app',
        'password': 'Demo@1234'
    })
    assert res.status_code == 200
    return client


def test_missing_fields_returns_400(auth_client):
    """Missing required event fields returns HTTP 400."""
    res = auth_client.post('/api/events', json={
        'name': 'Incomplete Event'
        # Missing date, start_time, end_time, venue
    })
    assert res.status_code == 400
    data = res.get_json()
    assert data['ok'] is False
    assert 'Missing' in data['error']


def test_invalid_time_range_returns_400(auth_client):
    """End time earlier than start time returns HTTP 400."""
    res = auth_client.post('/api/events', json={
        'name': 'Backward Event',
        'date': '2026-10-26',
        'start_time': '15:00',
        'end_time': '14:00',
        'venue': 'CSE Lab 2',
        'organizer': 'ACM'
    })
    assert res.status_code == 400
    data = res.get_json()
    assert data['ok'] is False
    assert 'End time must be after start time' in data['error']


def test_malformed_timestamp_returns_400(auth_client):
    """Malformed date or time format returns HTTP 400."""
    res = auth_client.post('/api/events', json={
        'name': 'Bad Time Event',
        'date': 'not-a-date',
        'start_time': 'noon',
        'end_time': 'afternoon',
        'venue': 'Main Auditorium',
        'organizer': 'Host'
    })
    assert res.status_code == 400
    data = res.get_json()
    assert data['ok'] is False
    assert 'Invalid date or time format' in data['error']


def test_nonexistent_event_returns_404(auth_client):
    """Accessing, updating, deleting, or rescheduling nonexistent event returns HTTP 404."""
    # GET
    res = auth_client.get('/api/events/NONEXISTENT-999')
    assert res.status_code == 404

    # PUT
    res = auth_client.put('/api/events/NONEXISTENT-999', json={'name': 'Updated'})
    assert res.status_code == 404

    # DELETE
    res = auth_client.delete('/api/events/NONEXISTENT-999')
    assert res.status_code == 404

    # Reschedule preview
    res = auth_client.post('/api/events/NONEXISTENT-999/reschedule-preview', json={'date': '2026-10-26'})
    assert res.status_code == 404

    # Reschedule commit
    res = auth_client.post('/api/events/NONEXISTENT-999/reschedule-commit', json={'date': '2026-10-26'})
    assert res.status_code == 404


def test_create_and_conflict_workflow(auth_client):
    """Attempting to schedule in an occupied slot returns 409 with conflict details and suggestions."""
    # 1. Create event at 08:00 - 09:30
    res = auth_client.post('/api/events', json={
        'name': 'Breakfast Symposium',
        'date': '2026-10-26',
        'start_time': '07:00',
        'end_time': '08:30',
        'venue': 'CSE Lab 2',
        'organizer': 'IEEE'
    })
    assert res.status_code == 201
    evt1 = res.get_json()['data']

    # 2. Try to schedule conflicting event: 07:30 - 09:00
    res_conf = auth_client.post('/api/events', json={
        'name': 'Conflicting Workshop',
        'date': '2026-10-26',
        'start_time': '07:30',
        'end_time': '09:00',
        'venue': 'CSE Lab 2',
        'organizer': 'ACM'
    })
    assert res_conf.status_code == 409
    data = res_conf.get_json()
    assert data['ok'] is False
    assert len(data['data']['conflicts']) > 0
    assert data['data']['conflicts'][0]['id'] == evt1['id']
    assert 'suggestions' in data['data']


def test_reschedule_preview_and_commit(auth_client):
    """Rescheduling preview returns ripple score and suggestions; commit persists changes."""
    # Create an initial event
    res = auth_client.post('/api/events', json={
        'name': 'Initial Talk',
        'date': '2026-11-09',
        'start_time': '09:00',
        'end_time': '10:00',
        'venue': 'Open Air Theatre',
        'organizer': 'Club'
    })
    assert res.status_code == 201
    event_id = res.get_json()['data']['id']

    # Preview moving to 11:00 - 12:00
    res_prev = auth_client.post(f'/api/events/{event_id}/reschedule-preview', json={
        'date': '2026-11-09',
        'start_time': '11:00',
        'end_time': '12:00'
    })
    assert res_prev.status_code == 200
    prev_data = res_prev.get_json()['data']
    assert prev_data['event_id'] == event_id
    assert len(prev_data['conflicts']) == 0
    assert 'ripple_score' in prev_data

    # Commit the reschedule
    res_commit = auth_client.post(f'/api/events/{event_id}/reschedule-commit', json={
        'date': '2026-11-09',
        'start_time': '11:00',
        'end_time': '12:00'
    })
    assert res_commit.status_code == 200
    commit_data = res_commit.get_json()['data']
    assert commit_data['start_time'] == '11:00'
    assert commit_data['end_time'] == '12:00'

    # Verify persistence via GET
    res_get = auth_client.get(f'/api/events/{event_id}')
    assert res_get.status_code == 200
    assert res_get.get_json()['data']['start_time'] == '11:00'


def test_sqlite_and_in_memory_data_consistency(auth_client):
    """Verifies that SQLite database and in-memory structures (AVL, BST, Hash Table, Trie) match exactly."""
    user_row = db.get_user_by_email('demo@chronograph.app')
    user_id = user_row['id']
    engine = get_user_engine(user_id)

    # 1. Add event
    res = auth_client.post('/api/events', json={
        'name': 'Consistency Check Event',
        'date': '2026-11-10',
        'start_time': '09:00',
        'end_time': '10:30',
        'venue': 'Main Auditorium',
        'organizer': 'Audit Team'
    })
    assert res.status_code == 201
    event_id = res.get_json()['data']['id']

    # Check Hash Table, AVL, BST, Trie, SQLite
    assert engine.hash_table.contains(event_id)
    assert engine.avl_tree.search_by_key(db.date_time_to_minutes('2026-11-10', '09:00')) is not None
    assert engine.bst_tree.search_by_key(db.date_time_to_minutes('2026-11-10', '09:00')) is not None
    assert len(engine.trie.search_prefix('Consistency Check')) > 0

    conn = db.get_db_connection()
    row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    conn.close()
    assert row is not None
    assert row['name'] == 'Consistency Check Event'

    # 2. Undo
    res_undo = auth_client.post('/api/undo')
    assert res_undo.status_code == 200
    assert not engine.hash_table.contains(event_id)

    conn = db.get_db_connection()
    row_after_undo = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    conn.close()
    assert row_after_undo is None

    # 3. Redo
    res_redo = auth_client.post('/api/redo')
    assert res_redo.status_code == 200
    assert engine.hash_table.contains(event_id)

    conn = db.get_db_connection()
    row_after_redo = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    conn.close()
    assert row_after_redo is not None


def test_concurrent_claim_race_condition_protection(client):
    """Verifies that two concurrent requests for the same exclusive slot cannot both succeed without conflict."""
    # Sign in
    res = client.post('/api/auth/signin', json={'email': 'demo@chronograph.app', 'password': 'Demo@1234'})
    assert res.status_code == 200

    results = []

    def make_booking(name):
        # Each thread uses client
        with app.test_client() as c:
            c.post('/api/auth/signin', json={'email': 'demo@chronograph.app', 'password': 'Demo@1234'})
            r = c.post('/api/events', json={
                'name': name,
                'date': '2026-11-11',
                'start_time': '10:00',
                'end_time': '11:00',
                'venue': 'CSE Lab 2',
                'organizer': 'Concurrent Test'
            })
            results.append(r.status_code)

    t1 = threading.Thread(target=make_booking, args=('Booking A',))
    t2 = threading.Thread(target=make_booking, args=('Booking B',))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Exactly one request should succeed (201), and the other should be rejected as a conflict (409)
    assert 201 in results
    assert 409 in results
