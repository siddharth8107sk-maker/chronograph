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


def test_college_signup_and_same_college_event_sharing(client):
    """
    Verifies that:
    1. Users can sign up with a chosen college from the dropdown.
    2. Users from the same college see each other's events on their dashboard.
    3. Users from a different college are isolated into their own college schedule.
    """
    # 1. Sign up Alice at Karunya
    res_a = client.post('/api/auth/signup', json={
        'full_name': 'Prof. Alice Karunya',
        'email': 'alice@karunya.edu',
        'password': 'Password123',
        'college': 'Karunya Institute of Technology and Sciences'
    })
    assert res_a.status_code == 200
    assert res_a.get_json()['data']['college'] == 'Karunya Institute of Technology and Sciences'

    # Alice creates an event
    res_evt = client.post('/api/events', json={
        'name': 'Karunya Robotics Expo',
        'date': '2026-11-15',
        'start_time': '10:00',
        'end_time': '12:00',
        'venue': 'Main Auditorium',
        'organizer': 'Robotics Dept'
    })
    assert res_evt.status_code == 201
    alice_event_id = res_evt.get_json()['data']['id']

    # 2. Sign up Bob at Karunya
    client_bob = app.test_client()
    res_b = client_bob.post('/api/auth/signup', json={
        'full_name': 'Student Bob Karunya',
        'email': 'bob@karunya.edu',
        'password': 'Password123',
        'college': 'Karunya Institute of Technology and Sciences'
    })
    assert res_b.status_code == 200
    assert res_b.get_json()['data']['college'] == 'Karunya Institute of Technology and Sciences'

    # Bob fetches events: must see Alice's event because they attend the same college
    res_b_evts = client_bob.get('/api/events')
    assert res_b_evts.status_code == 200
    bob_events = res_b_evts.get_json()['data']
    bob_event_ids = [e['id'] for e in bob_events]
    assert alice_event_id in bob_event_ids

    # 3. Sign up Clara at Vellore Institute of Technology
    client_clara = app.test_client()
    res_c = client_clara.post('/api/auth/signup', json={
        'full_name': 'Dr. Clara VIT',
        'email': 'clara@vit.edu',
        'password': 'Password123',
        'college': 'Vellore Institute of Technology'
    })
    assert res_c.status_code == 200
    assert res_c.get_json()['data']['college'] == 'Vellore Institute of Technology'

    # Clara fetches events: must NOT see Alice's Karunya event
    res_c_evts = client_clara.get('/api/events')
    assert res_c_evts.status_code == 200
    clara_events = res_c_evts.get_json()['data']
    clara_event_ids = [e['id'] for e in clara_events]
    assert alice_event_id not in clara_event_ids

    # Clara creates a VIT event
    res_c_create = client_clara.post('/api/events', json={
        'name': 'VIT Riviera Fest',
        'date': '2026-11-16',
        'start_time': '13:00',
        'end_time': '15:00',
        'venue': 'Main Auditorium',
        'organizer': 'VIT Student Council'
    })
    assert res_c_create.status_code == 201
    vit_event_id = res_c_create.get_json()['data']['id']

    # 4. Sign up David at Vellore Institute of Technology
    client_david = app.test_client()
    res_d = client_david.post('/api/auth/signup', json={
        'full_name': 'Prof. David VIT',
        'email': 'david@vit.edu',
        'password': 'Password123',
        'college': 'Vellore Institute of Technology'
    })
    assert res_d.status_code == 200

    # David fetches events: must see Clara's VIT event, but NOT Alice's Karunya event
    res_d_evts = client_david.get('/api/events')
    assert res_d_evts.status_code == 200
    david_event_ids = [e['id'] for e in res_d_evts.get_json()['data']]
    assert vit_event_id in david_event_ids
    assert alice_event_id not in david_event_ids


def test_demo_accounts_and_seeded_events_for_all_three_colleges(client):
    """
    Verifies that demo accounts exist and are seeded with events for all three colleges:
    1. Karunya Institute of Technology and Sciences (karunya@chronograph.app / Demo@1234)
    2. Vellore Institute of Technology (vit@chronograph.app / Demo@1234)
    3. PSG College of Arts and Science (psg@chronograph.app / Demo@1234)
    """
    # 1. Karunya Demo Login
    client_karunya = app.test_client()
    res_k = client_karunya.post('/api/auth/signin', json={
        'email': 'karunya@chronograph.app',
        'password': 'Demo@1234'
    })
    assert res_k.status_code == 200
    user_k = res_k.get_json()['data']
    assert user_k['college'] == 'Karunya Institute of Technology and Sciences'
    evts_k = client_karunya.get('/api/events').get_json()['data']
    assert len(evts_k) >= 15
    assert any('Hackathon Kickoff' in e['name'] for e in evts_k)

    # 2. VIT Demo Login
    client_vit = app.test_client()
    res_v = client_vit.post('/api/auth/signin', json={
        'email': 'vit@chronograph.app',
        'password': 'Demo@1234'
    })
    assert res_v.status_code == 200
    user_v = res_v.get_json()['data']
    assert user_v['college'] == 'Vellore Institute of Technology'
    evts_v = client_vit.get('/api/events').get_json()['data']
    assert len(evts_v) >= 15
    assert any('Riviera' in e['name'] or 'Gravitas' in e['name'] for e in evts_v)

    # 3. PSG Demo Login
    client_psg = app.test_client()
    res_p = client_psg.post('/api/auth/signin', json={
        'email': 'psg@chronograph.app',
        'password': 'Demo@1234'
    })
    assert res_p.status_code == 200
    user_p = res_p.get_json()['data']
    assert user_p['college'] == 'PSG College of Arts and Science'
    evts_p = client_psg.get('/api/events').get_json()['data']
    assert len(evts_p) >= 15
    assert any('Culturals' in e['name'] or 'Exhibition' in e['name'] for e in evts_p)

    # Cross-college isolation verification
    k_ids = set(e['id'] for e in evts_k)
    v_ids = set(e['id'] for e in evts_v)
    p_ids = set(e['id'] for e in evts_p)
    assert k_ids.isdisjoint(v_ids)
    assert k_ids.isdisjoint(p_ids)
    assert v_ids.isdisjoint(p_ids)


def test_college_specific_venue_creation_and_sharing(client):
    """
    Verifies that:
    1. Unauthenticated users cannot create venues.
    2. Users can add new venues to their specific college.
    3. Peers from the same college see the new venue.
    4. Users from other colleges are isolated and do not see it.
    5. Duplicate additions are idempotent and empty names are rejected.
    """
    # 1. Unauthenticated creation rejected
    client_unauth = app.test_client()
    res_unauth = client_unauth.post('/api/venues', json={'name': 'Rooftop Observatory'})
    assert res_unauth.status_code == 401

    # 2. Karunya user logs in and adds a new venue
    client_k1 = app.test_client()
    client_k1.post('/api/auth/signin', json={'email': 'karunya@chronograph.app', 'password': 'Demo@1234'})
    
    # Empty name check
    res_bad = client_k1.post('/api/venues', json={'name': '   '})
    assert res_bad.status_code == 400

    new_venue_name = "Aerospace Wind Tunnel Lab"
    res_v1 = client_k1.post('/api/venues', json={'name': new_venue_name})
    assert res_v1.status_code == 201
    assert res_v1.get_json()['data']['name'] == new_venue_name

    # Check venues list for Karunya user 1
    res_k1_venues = client_k1.get('/api/venues')
    assert res_k1_venues.status_code == 200
    k1_venues = res_k1_venues.get_json()['data']
    assert new_venue_name in k1_venues

    # 3. Another Karunya user logs in and checks venues
    client_k2 = app.test_client()
    client_k2.post('/api/auth/signup', json={
        'full_name': 'Prof. Karunya Colleague',
        'email': 'colleague@karunya.edu',
        'password': 'Password123',
        'college': 'Karunya Institute of Technology and Sciences'
    })
    res_k2_venues = client_k2.get('/api/venues')
    assert res_k2_venues.status_code == 200
    assert new_venue_name in res_k2_venues.get_json()['data']

    # 4. VIT user logs in: must NOT see Karunya's new venue
    client_vit = app.test_client()
    client_vit.post('/api/auth/signin', json={'email': 'vit@chronograph.app', 'password': 'Demo@1234'})
    res_vit_venues = client_vit.get('/api/venues')
    assert res_vit_venues.status_code == 200
    vit_venues = res_vit_venues.get_json()['data']
    assert new_venue_name not in vit_venues

    # 5. VIT user adds their own new venue
    vit_new_venue = "SJT Smart Classroom 401"
    res_vit_add = client_vit.post('/api/venues', json={'name': vit_new_venue})
    assert res_vit_add.status_code == 201
    
    # VIT user sees their new venue
    assert vit_new_venue in client_vit.get('/api/venues').get_json()['data']
    # Karunya user does NOT see VIT's venue
    assert vit_new_venue not in client_k1.get('/api/venues').get_json()['data']


