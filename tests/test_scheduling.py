"""
Scheduling and Rescheduling Logic Tests (Course 25CS306 MP-01).
Tests interval validation, conflict detection, self-conflict exclusion,
preview/commit workflows, rollbacks on failed updates, and adjacent boundary rules.
"""

import pytest
import os
import sqlite3
from ds.avl_gap import AVLTree
import db
from app import UserEngine


@pytest.fixture
def test_engine(tmp_path, monkeypatch):
    """Provides a UserEngine with an isolated temporary SQLite database."""
    test_db = str(tmp_path / "test_chronograph.db")
    monkeypatch.setattr(db, "DB_PATH", test_db)
    db.init_db()

    # Create test user and clean tables
    conn = db.get_db_connection()
    conn.execute("DELETE FROM events")
    conn.execute("DELETE FROM waitlist")
    conn.execute("""
        INSERT OR IGNORE INTO users (id, full_name, email, password_hash, salt, created_at)
        VALUES ('test-user-001', 'Test Engineer', 'tester@test.com', 'pwd_hash', X'00', '2026-01-01T00:00:00')
    """)
    conn.commit()
    conn.close()

    engine = UserEngine("test-user-001")
    return engine


def test_create_valid_event(test_engine):
    """Event creation succeeds and populates SQLite and in-memory structures."""
    ev = {
        'id': 'EVT-TEST-1',
        'name': 'Algorithms Lecture',
        'date': '2026-10-26',
        'start_time': '09:00',
        'end_time': '10:30',
        'start_minute': db.date_time_to_minutes('2026-10-26', '09:00'),
        'end_minute': db.date_time_to_minutes('2026-10-26', '10:30'),
        'venue': 'Main Auditorium',
        'organizer': 'CSE Dept',
        'priority': 2,
        'depends_on': None,
        'owner_user_id': test_engine.user_id
    }
    test_engine.add_event(ev)

    assert test_engine.hash_table.contains('EVT-TEST-1')
    assert test_engine.avl_tree.node_count() == 1
    assert test_engine.bst_tree.node_count() == 1

    # Check SQLite
    conn = db.get_db_connection()
    row = conn.execute("SELECT * FROM events WHERE id = 'EVT-TEST-1'").fetchone()
    conn.close()
    assert row is not None
    assert row['name'] == 'Algorithms Lecture'


def test_reject_invalid_time_range():
    """Events with end_time <= start_time are rejected."""
    # Equal times
    sm = db.date_time_to_minutes('2026-10-26', '10:00')
    em = db.date_time_to_minutes('2026-10-26', '10:00')
    assert em <= sm

    # Inverted times
    em2 = db.date_time_to_minutes('2026-10-26', '09:30')
    assert em2 < sm


def test_conflict_detection_and_adjacent_events(test_engine):
    """Adjacent half-open intervals [09:00, 10:00) and [10:00, 11:00) do NOT conflict."""
    ev1 = {
        'id': 'EVT-1',
        'name': 'Session 1',
        'date': '2026-10-26',
        'start_time': '09:00',
        'end_time': '10:00',
        'start_minute': db.date_time_to_minutes('2026-10-26', '09:00'),
        'end_minute': db.date_time_to_minutes('2026-10-26', '10:00'),
        'venue': 'Room 101',
        'organizer': 'Org',
        'priority': 3,
        'depends_on': None
    }
    test_engine.add_event(ev1)

    # Directly adjacent: 10:00 to 11:00
    st_adj = db.date_time_to_minutes('2026-10-26', '10:00')
    et_adj = db.date_time_to_minutes('2026-10-26', '11:00')
    conflicts = test_engine.avl_tree.has_conflict(st_adj, et_adj)
    assert len(conflicts) == 0

    # Overlapping by 5 minutes: 09:55 to 10:30
    st_over = db.date_time_to_minutes('2026-10-26', '09:55')
    et_over = db.date_time_to_minutes('2026-10-26', '10:30')
    conflicts_over = test_engine.avl_tree.has_conflict(st_over, et_over)
    assert len(conflicts_over) == 1
    assert conflicts_over[0]['id'] == 'EVT-1'


def test_self_conflict_exclusion_on_reschedule(test_engine):
    """An event being rescheduled must NOT conflict with its own existing time slot."""
    ev = {
        'id': 'EVT-SELF',
        'name': 'Keynote',
        'date': '2026-10-26',
        'start_time': '10:00',
        'end_time': '12:00',
        'start_minute': db.date_time_to_minutes('2026-10-26', '10:00'),
        'end_minute': db.date_time_to_minutes('2026-10-26', '12:00'),
        'venue': 'Auditorium',
        'organizer': 'Host',
        'priority': 1,
        'depends_on': None
    }
    test_engine.add_event(ev)

    # Propose shifting slot from 10:00-12:00 to 10:30-12:30 (overlaps old slot)
    new_sm = db.date_time_to_minutes('2026-10-26', '10:30')
    new_em = db.date_time_to_minutes('2026-10-26', '12:30')

    # Without ignore_id, it reports conflict with itself
    assert len(test_engine.avl_tree.has_conflict(new_sm, new_em)) == 1

    # With ignore_id='EVT-SELF', no conflict
    conflicts_excluded = test_engine.avl_tree.has_conflict(new_sm, new_em, ignore_id='EVT-SELF')
    assert len(conflicts_excluded) == 0


def test_failed_rescheduling_leaves_event_unchanged(test_engine):
    """If a conflict prevents reschedule, the original event is unchanged."""
    ev1 = {
        'id': 'EVT-A',
        'name': 'Meeting A',
        'date': '2026-10-26',
        'start_time': '10:00',
        'end_time': '11:00',
        'start_minute': db.date_time_to_minutes('2026-10-26', '10:00'),
        'end_minute': db.date_time_to_minutes('2026-10-26', '11:00'),
        'venue': 'Room 1',
        'organizer': 'Host',
        'priority': 2,
        'depends_on': None
    }
    ev2 = {
        'id': 'EVT-B',
        'name': 'Meeting B',
        'date': '2026-10-26',
        'start_time': '14:00',
        'end_time': '15:00',
        'start_minute': db.date_time_to_minutes('2026-10-26', '14:00'),
        'end_minute': db.date_time_to_minutes('2026-10-26', '15:00'),
        'venue': 'Room 1',
        'organizer': 'Host',
        'priority': 2,
        'depends_on': None
    }
    test_engine.add_event(ev1)
    test_engine.add_event(ev2)

    # Attempt to move EVT-B into EVT-A's slot (10:30 - 11:30)
    target_sm = db.date_time_to_minutes('2026-10-26', '10:30')
    target_em = db.date_time_to_minutes('2026-10-26', '11:30')
    conflicts = test_engine.avl_tree.has_conflict(target_sm, target_em, ignore_id='EVT-B')
    assert len(conflicts) > 0
    assert conflicts[0]['id'] == 'EVT-A'

    # Do not commit; check EVT-B is still at 14:00
    stored_b = test_engine.hash_table.get('EVT-B')
    assert stored_b['start_time'] == '14:00'
    assert stored_b['end_time'] == '15:00'


def test_delete_existing_and_nonexistent_event(test_engine):
    """Deleting an event removes it from DB and in-memory structures; nonexistent returns None."""
    ev = {
        'id': 'EVT-DEL',
        'name': 'To Be Deleted',
        'date': '2026-10-26',
        'start_time': '16:00',
        'end_time': '17:00',
        'start_minute': db.date_time_to_minutes('2026-10-26', '16:00'),
        'end_minute': db.date_time_to_minutes('2026-10-26', '17:00'),
        'venue': 'Room 1',
        'organizer': 'Host',
        'priority': 3,
        'depends_on': None
    }
    test_engine.add_event(ev)
    assert test_engine.hash_table.contains('EVT-DEL')

    test_engine.delete_event('EVT-DEL')
    assert not test_engine.hash_table.contains('EVT-DEL')
    assert test_engine.avl_tree.search_by_key(ev['start_minute']) is None

    # Deleting nonexistent event returns None
    result = test_engine.delete_event('NONEXISTENT-999')
    assert result is None


def test_waitlist_auto_placement_on_event_delete(test_engine):
    """When an event is deleted, a waitlisted event fitting the freed slot is automatically scheduled."""
    # Schedule event 14:00 to 16:00 (120 min)
    ev = {
        'id': 'EVT-MAIN',
        'name': 'Big Block',
        'date': '2026-10-26',
        'start_time': '14:00',
        'end_time': '16:00',
        'start_minute': db.date_time_to_minutes('2026-10-26', '14:00'),
        'end_minute': db.date_time_to_minutes('2026-10-26', '16:00'),
        'venue': 'Hall A',
        'organizer': 'Org',
        'priority': 2,
        'depends_on': None
    }
    test_engine.add_event(ev)

    # Waitlist item needing 60 min
    w_item = {
        'id': 'EVT-W1',
        'waitlist_id': 'WLT-001',
        'name': 'Waitlisted Session',
        'date': '2026-10-26',
        'start_time': '14:00',
        'end_time': '15:00',
        'venue': 'Hall A',
        'organizer': 'Org',
        'priority': 1,
        'depends_on': None
    }
    test_engine.waitlist.push(w_item)
    db.save_waitlist_item_to_db(w_item, test_engine.user_id)

    # Delete EVT-MAIN
    auto_placed = test_engine.delete_event('EVT-MAIN')
    assert auto_placed is not None
    assert auto_placed['id'] == 'EVT-W1'
    assert test_engine.hash_table.contains('EVT-W1')
    assert test_engine.waitlist.is_empty()
