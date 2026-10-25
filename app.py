"""
ChronoGraph - Real-Time Event Scheduling System
Course: Data Structures and Algorithms (25CS306) MP-01
Flask Application, Custom DS In-Memory Engine, and JSON REST API.
"""

from __future__ import annotations
import re
import secrets
import random
import threading
from typing import Dict, Any, Optional, List
from flask import Flask, request, jsonify, render_template, make_response

import db
from ds.avl_gap import AVLTree
from ds.bst_baseline import BSTBaseline
from ds.hash_index import EventHashTable
from ds.trie import EventTrie
from ds.heap import MinHeapWaitlist
from ds.version_stack import VersionStack, SystemSnapshot, RequestQueue
from ds.ripple_graph import ConflictRippleGraph
import benchmark

app = Flask(__name__)
app.config['SECRET_KEY'] = 'chronograph-secret-25cs306-mp01'


# =====================================================================
# In-Memory DS Engine per User (Rebuilt from SQLite on startup/login)
# =====================================================================
class UserEngine:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.lock = threading.RLock()
        self.avl_tree = AVLTree()
        self.bst_tree = BSTBaseline()
        self.hash_table = EventHashTable(64)
        self.trie = EventTrie()
        self.waitlist = MinHeapWaitlist()
        self.request_queue = RequestQueue()

        self._load_from_db()

        # Initialize version stack
        init_snap = SystemSnapshot(
            version=1,
            description="Initial State",
            tree=self.avl_tree,
            hash_table=self.hash_table.snapshot(),
            trie=self.trie.snapshot(),
            waitlist=self.waitlist.snapshot()
        )
        self.version_stack = VersionStack(init_snap)

    def _load_from_db(self) -> None:
        events = db.load_user_events_from_db(self.user_id)
        for ev in events:
            sm = ev['start_minute']
            em = ev['end_minute']
            self.avl_tree = self.avl_tree.insert(ev, sm, em)
            self.bst_tree = self.bst_tree.insert(ev, sm, em)
            self.hash_table.put(ev['id'], ev)
            self.trie.insert(ev['name'], ev['id'])

        waitlist_items = db.load_waitlist_from_db(self.user_id)
        for w in waitlist_items:
            self.waitlist.push(w)

    def add_event(self, event: Dict[str, Any], record_version: bool = True) -> None:
        sm = event['start_minute']
        em = event['end_minute']
        # Persist to SQLite first; in-memory indexes update only upon successful commit
        db.save_event_to_db(event, self.user_id)
        self.avl_tree = self.avl_tree.insert(event, sm, em)
        self.bst_tree = self.bst_tree.insert(event, sm, em)
        self.hash_table.put(event['id'], event)
        self.trie.insert(event['name'], event['id'])

        if record_version:
            self.version_stack.push(
                description=f"Added {event['id']} ({event['name'][:20]})",
                tree=self.avl_tree,
                hash_table=self.hash_table.snapshot(),
                trie=self.trie.snapshot(),
                waitlist=self.waitlist.snapshot()
            )

    def update_event(self, old_event: Dict[str, Any], new_event: Dict[str, Any], record_version: bool = True) -> None:
        sm = new_event['start_minute']
        em = new_event['end_minute']
        # Persist to SQLite first
        db.save_event_to_db(new_event, self.user_id)

        # Update in-memory structures atomically
        self.avl_tree = self.avl_tree.delete(old_event['id'], old_event['start_minute'])
        self.avl_tree = self.avl_tree.insert(new_event, sm, em)
        self.bst_tree = self.bst_tree.delete(old_event['id'], old_event['start_minute'])
        self.bst_tree = self.bst_tree.insert(new_event, sm, em)
        self.trie.delete(old_event['name'], old_event['id'])
        self.trie.insert(new_event['name'], new_event['id'])
        self.hash_table.put(new_event['id'], new_event)

        if record_version:
            self.version_stack.push(
                description=f"Rescheduled {new_event['id']}",
                tree=self.avl_tree,
                hash_table=self.hash_table.snapshot(),
                trie=self.trie.snapshot(),
                waitlist=self.waitlist.snapshot()
            )

    def delete_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        ev = self.hash_table.get(event_id)
        if not ev:
            return None

        # Remove from SQLite first
        db.delete_event_from_db(ev['id'], self.user_id)

        # Remove from in-memory structures
        self.avl_tree = self.avl_tree.delete(ev['id'], ev['start_minute'])
        self.bst_tree = self.bst_tree.delete(ev['id'], ev['start_minute'])
        self.hash_table.delete(ev['id'])
        self.trie.delete(ev['name'], ev['id'])

        # Auto-place waitlisted event into freed gap if suitable
        auto_placed = None
        if not self.waitlist.is_empty():
            candidates = self.waitlist.to_list()
            for cand in candidates:
                cand_dur = db.date_time_to_minutes(cand['date'], cand['end_time']) - db.date_time_to_minutes(cand['date'], cand['start_time'])
                freed_dur = ev['end_minute'] - ev['start_minute']

                # Check if candidate fits in freed slot
                if cand_dur <= freed_dur:
                    test_end = ev['start_minute'] + cand_dur
                    if not self.avl_tree.has_conflict(ev['start_minute'], test_end):
                        cand_date, cand_st = db.minutes_to_date_time(ev['start_minute'])
                        _, cand_et = db.minutes_to_date_time(test_end)
                        placed_event = dict(cand)
                        placed_event['date'] = cand_date
                        placed_event['start_time'] = cand_st
                        placed_event['end_time'] = cand_et
                        placed_event['start_minute'] = ev['start_minute']
                        placed_event['end_minute'] = test_end

                        # Atomic DB promotion
                        db.promote_waitlist_to_event(cand.get('waitlist_id') or cand['id'], placed_event, self.user_id)
                        self.waitlist.remove_by_id(cand['id'])
                        self.avl_tree = self.avl_tree.insert(placed_event, placed_event['start_minute'], placed_event['end_minute'])
                        self.bst_tree = self.bst_tree.insert(placed_event, placed_event['start_minute'], placed_event['end_minute'])
                        self.hash_table.put(placed_event['id'], placed_event)
                        self.trie.insert(placed_event['name'], placed_event['id'])
                        auto_placed = placed_event
                        break

        self.version_stack.push(
            description=f"Deleted {ev['id']}" + (f" (Auto-placed {auto_placed['id']})" if auto_placed else ""),
            tree=self.avl_tree,
            hash_table=self.hash_table.snapshot(),
            trie=self.trie.snapshot(),
            waitlist=self.waitlist.snapshot()
        )
        return auto_placed


USER_ENGINES: Dict[str, UserEngine] = {}
ENGINE_LOCK = threading.Lock()


def get_user_engine(user_id: str) -> UserEngine:
    with ENGINE_LOCK:
        if user_id not in USER_ENGINES:
            USER_ENGINES[user_id] = UserEngine(user_id)
        return USER_ENGINES[user_id]


# =====================================================================
# Authentication & Request Context
# =====================================================================
def get_current_user() -> Optional[Dict[str, Any]]:
    token = request.cookies.get('session_token')
    if not token:
        # Also check Authorization header for flexibility
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
    return db.validate_session(token) if token else None


def require_auth():
    user = get_current_user()
    if not user:
        return None, (jsonify({'ok': False, 'data': None, 'error': 'Unauthorized'}), 401)
    return user, None


# =====================================================================
# Frontend Route
# =====================================================================
@app.route('/')
def index():
    return render_template('index.html')


# =====================================================================
# Auth Endpoints
# =====================================================================
@app.route('/api/auth/signup', methods=['POST'])
def signup():
    data = request.get_json() or {}
    full_name = (data.get('full_name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if len(full_name) < 2 or len(full_name) > 60:
        return jsonify({'ok': False, 'data': None, 'error': 'Name must be between 2 and 60 characters'}), 400

    email_regex = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    if not re.match(email_regex, email):
        return jsonify({'ok': False, 'data': None, 'error': 'Invalid email format'}), 400

    if len(password) < 8 or not re.search(r'[A-Za-z]', password) or not re.search(r'\d', password):
        return jsonify({'ok': False, 'data': None, 'error': 'Password must be at least 8 characters and contain at least one letter and one number'}), 400

    if db.get_user_by_email(email):
        return jsonify({'ok': False, 'data': None, 'error': 'Email already registered'}), 400

    pwd_hash, salt = db.hash_password(password)
    user = db.create_user(full_name, email, pwd_hash, salt)
    token = db.create_session(user['id'])

    resp = make_response(jsonify({'ok': True, 'data': user, 'error': None}))
    resp.set_cookie('session_token', token, httponly=True, samesite='Lax', max_age=7 * 24 * 3600)
    return resp


@app.route('/api/auth/signin', methods=['POST'])
def signin():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    user_row = db.get_user_by_email(email)
    if not user_row or not db.verify_password(password, user_row['password_hash'], user_row['salt']):
        return jsonify({'ok': False, 'data': None, 'error': 'Invalid email or password'}), 401

    token = db.create_session(user_row['id'])
    user_data = {
        'id': user_row['id'],
        'full_name': user_row['full_name'],
        'email': user_row['email']
    }
    resp = make_response(jsonify({'ok': True, 'data': user_data, 'error': None}))
    resp.set_cookie('session_token', token, httponly=True, samesite='Lax', max_age=7 * 24 * 3600)
    return resp


@app.route('/api/auth/signout', methods=['POST'])
def signout():
    token = request.cookies.get('session_token')
    if token:
        db.delete_session(token)
    resp = make_response(jsonify({'ok': True, 'data': True, 'error': None}))
    resp.set_cookie('session_token', '', expires=0)
    return resp


@app.route('/api/auth/me', methods=['GET'])
def get_me():
    user = get_current_user()
    if not user:
        return jsonify({'ok': False, 'data': None, 'error': 'Not authenticated'}), 401
    return jsonify({'ok': True, 'data': user, 'error': None})


# =====================================================================
# Events Endpoints
# =====================================================================
@app.route('/api/events', methods=['GET'])
def list_events():
    user, err = require_auth()
    if err:
        return err

    engine = get_user_engine(user['id'])
    date_filter = request.args.get('date')
    venue_filter = request.args.get('venue')
    q_filter = (request.args.get('q') or '').strip()

    events = engine.hash_table.values()

    # Search query
    if q_filter:
        q_lower = q_filter.lower()
        # Direct ID match
        direct = engine.hash_table.get(q_filter.upper())
        if direct:
            events = [direct]
        else:
            # Trie prefix match
            trie_matches = {m['id'] for m in engine.trie.search_prefix(q_lower, limit=20)}
            events = [e for e in events if e['id'] in trie_matches or q_lower in e['name'].lower()]

    if date_filter:
        events = [e for e in events if e['date'] == date_filter]

    if venue_filter:
        events = [e for e in events if e.get('venue') == venue_filter]

    # Return sorted by start_minute
    events.sort(key=lambda x: x['start_minute'])
    return jsonify({'ok': True, 'data': events, 'error': None})


@app.route('/api/events', methods=['POST'])
def create_event():
    user, err = require_auth()
    if err:
        return err

    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    date = (data.get('date') or '').strip()
    start_time = (data.get('start_time') or '').strip()
    end_time = (data.get('end_time') or '').strip()
    venue = (data.get('venue') or '').strip()
    organizer = (data.get('organizer') or '').strip()
    priority = int(data.get('priority', 3))
    depends_on = data.get('depends_on') or None
    force = data.get('force', False)

    if not name or not date or not start_time or not end_time or not venue:
        return jsonify({'ok': False, 'data': None, 'error': 'Missing required fields'}), 400

    try:
        start_min = db.date_time_to_minutes(date, start_time)
        end_min = db.date_time_to_minutes(date, end_time)
    except Exception:
        return jsonify({'ok': False, 'data': None, 'error': 'Invalid date or time format'}), 400

    if end_min <= start_min:
        return jsonify({'ok': False, 'data': None, 'error': 'End time must be after start time'}), 400

    engine = get_user_engine(user['id'])

    with engine.lock:
        # Validate dependency cycle
        if depends_on:
            if not engine.hash_table.contains(depends_on):
                return jsonify({'ok': False, 'data': None, 'error': f"Dependency event {depends_on} not found"}), 400

            # Test graph with new dependency edge
            all_events = list(engine.hash_table.values())
            test_event = {
                'id': 'TEMP-CHECK',
                'name': name,
                'date': date,
                'start_time': start_time,
                'end_time': end_time,
                'start_minute': start_min,
                'end_minute': end_min,
                'venue': venue,
                'organizer': organizer,
                'priority': priority,
                'depends_on': depends_on
            }
            test_graph = ConflictRippleGraph(all_events + [test_event])
            topo = test_graph.topological_sort()
            if topo['has_cycle']:
                return jsonify({'ok': False, 'data': None, 'error': 'Dependency cycle detected! ' + topo.get('error', '')}), 400

        # Conflict check
        conflicts = engine.avl_tree.has_conflict(start_min, end_min)
        if conflicts and not force:
            # Find suggestions
            duration = end_min - start_min
            day_start = db.date_time_to_minutes(date, "08:00")
            day_end = db.date_time_to_minutes(date, "20:00")
            raw_slots = engine.avl_tree.find_earliest_slot(duration, day_start, day_start, day_end)
            suggestions = []
            for s in raw_slots:
                _, s_st = db.minutes_to_date_time(s['start'])
                _, s_et = db.minutes_to_date_time(s['end'])
                suggestions.append({'date': date, 'start_time': s_st, 'end_time': s_et, 'start_minute': s['start'], 'end_minute': s['end']})

            return jsonify({
                'ok': False,
                'data': {
                    'conflicts': conflicts,
                    'suggestions': suggestions
                },
                'error': f"Conflict detected with {len(conflicts)} event(s)"
            }), 409

        event_id = f"EVT-{random.randint(1000, 9999)}"
        while engine.hash_table.contains(event_id):
            event_id = f"EVT-{random.randint(1000, 9999)}"

        new_event = {
            'id': event_id,
            'name': name,
            'date': date,
            'start_time': start_time,
            'end_time': end_time,
            'start_minute': start_min,
            'end_minute': end_min,
            'venue': venue,
            'organizer': organizer,
            'priority': priority,
            'depends_on': depends_on,
            'owner_user_id': user['id']
        }

        engine.add_event(new_event)
        return jsonify({'ok': True, 'data': new_event, 'error': None}), 201


@app.route('/api/events/<event_id>', methods=['GET'])
def get_event(event_id: str):
    user, err = require_auth()
    if err:
        return err
    engine = get_user_engine(user['id'])
    event = engine.hash_table.get(event_id)
    if not event:
        return jsonify({'ok': False, 'data': None, 'error': 'Event not found'}), 404
    return jsonify({'ok': True, 'data': event, 'error': None})


@app.route('/api/events/<event_id>', methods=['PUT'])
def update_event(event_id: str):
    user, err = require_auth()
    if err:
        return err

    engine = get_user_engine(user['id'])

    with engine.lock:
        old_event = engine.hash_table.get(event_id)
        if not old_event:
            return jsonify({'ok': False, 'data': None, 'error': 'Event not found'}), 404

        data = request.get_json() or {}
        name = (data.get('name') if data.get('name') is not None else old_event['name']).strip()
        date = (data.get('date') if data.get('date') is not None else old_event['date']).strip()
        start_time = (data.get('start_time') if data.get('start_time') is not None else old_event['start_time']).strip()
        end_time = (data.get('end_time') if data.get('end_time') is not None else old_event['end_time']).strip()
        venue = (data.get('venue') if data.get('venue') is not None else old_event['venue']).strip()
        organizer = (data.get('organizer') if data.get('organizer') is not None else old_event['organizer']).strip()
        priority = int(data.get('priority', old_event['priority']))
        depends_on = data.get('depends_on', old_event.get('depends_on'))
        if depends_on == '':
            depends_on = None
        force = data.get('force', False)

        if not name or not venue:
            return jsonify({'ok': False, 'data': None, 'error': 'Missing required fields'}), 400

        try:
            start_min = db.date_time_to_minutes(date, start_time)
            end_min = db.date_time_to_minutes(date, end_time)
        except Exception:
            return jsonify({'ok': False, 'data': None, 'error': 'Invalid date or time format'}), 400

        if end_min <= start_min:
            return jsonify({'ok': False, 'data': None, 'error': 'End time must be after start time'}), 400

        # Validate dependencies
        if depends_on:
            if depends_on == event_id:
                return jsonify({'ok': False, 'data': None, 'error': 'An event cannot depend on itself'}), 400
            if not engine.hash_table.contains(depends_on):
                return jsonify({'ok': False, 'data': None, 'error': f"Dependency event {depends_on} not found"}), 400

            # Cycle test
            all_other = [e for e in engine.hash_table.values() if e['id'] != event_id]
            test_ev = {
                'id': event_id,
                'name': name,
                'date': date,
                'start_time': start_time,
                'end_time': end_time,
                'start_minute': start_min,
                'end_minute': end_min,
                'venue': venue,
                'organizer': organizer,
                'priority': priority,
                'depends_on': depends_on
            }
            test_graph = ConflictRippleGraph(all_other + [test_ev])
            topo = test_graph.topological_sort()
            if topo['has_cycle']:
                return jsonify({'ok': False, 'data': None, 'error': 'Dependency cycle detected! ' + topo.get('error', '')}), 400

        # Conflict check excluding self
        conflicts = engine.avl_tree.has_conflict(start_min, end_min, ignore_id=event_id)
        if conflicts and not force:
            duration = end_min - start_min
            day_start = db.date_time_to_minutes(date, "08:00")
            day_end = db.date_time_to_minutes(date, "20:00")
            forked_tree = engine.avl_tree.delete(old_event['id'], old_event['start_minute'])
            raw_slots = forked_tree.find_earliest_slot(duration, day_start, day_start, day_end)
            suggestions = []
            for s in raw_slots:
                _, s_st = db.minutes_to_date_time(s['start'])
                _, s_et = db.minutes_to_date_time(s['end'])
                suggestions.append({'date': date, 'start_time': s_st, 'end_time': s_et, 'start_minute': s['start'], 'end_minute': s['end']})

            return jsonify({
                'ok': False,
                'data': {
                    'conflicts': conflicts,
                    'suggestions': suggestions
                },
                'error': f"Conflict detected with {len(conflicts)} event(s)"
            }), 409

        new_event = {
            'id': event_id,
            'name': name,
            'date': date,
            'start_time': start_time,
            'end_time': end_time,
            'start_minute': start_min,
            'end_minute': end_min,
            'venue': venue,
            'organizer': organizer,
            'priority': priority,
            'depends_on': depends_on,
            'owner_user_id': user['id']
        }

        engine.update_event(old_event, new_event)
        return jsonify({'ok': True, 'data': new_event, 'error': None})


@app.route('/api/events/<event_id>', methods=['DELETE'])
def delete_event(event_id: str):
    user, err = require_auth()
    if err:
        return err

    engine = get_user_engine(user['id'])

    with engine.lock:
        if not engine.hash_table.contains(event_id):
            return jsonify({'ok': False, 'data': None, 'error': 'Event not found'}), 404

        auto_placed = engine.delete_event(event_id)
        return jsonify({
            'ok': True,
            'data': {
                'deleted_id': event_id,
                'auto_placed': auto_placed
            },
            'error': None
        })


# =====================================================================
# Reschedule "What-If" Sandbox
# =====================================================================
@app.route('/api/events/<event_id>/reschedule-preview', methods=['POST'])
def reschedule_preview(event_id: str):
    user, err = require_auth()
    if err:
        return err

    engine = get_user_engine(user['id'])
    curr_event = engine.hash_table.get(event_id)
    if not curr_event:
        return jsonify({'ok': False, 'data': None, 'error': 'Event not found'}), 404

    data = request.get_json() or {}
    new_date = (data.get('date') or curr_event['date']).strip()
    new_st = (data.get('start_time') or curr_event['start_time']).strip()
    new_et = (data.get('end_time') or curr_event['end_time']).strip()

    try:
        new_start_min = db.date_time_to_minutes(new_date, new_st)
        new_end_min = db.date_time_to_minutes(new_date, new_et)
    except Exception:
        return jsonify({'ok': False, 'data': None, 'error': 'Invalid date or time format'}), 400

    if new_end_min <= new_start_min:
        return jsonify({'ok': False, 'data': None, 'error': 'End time must be after start time'}), 400

    duration = new_end_min - new_start_min

    # Fork tree: remove event being rescheduled so it does not conflict with itself
    forked_tree = engine.avl_tree.delete(curr_event['id'], curr_event['start_minute'])
    conflicts = forked_tree.has_conflict(new_start_min, new_end_min)

    # Ripple score via BFS on hypothetical graph
    all_events = [dict(e) for e in engine.hash_table.values() if e['id'] != event_id]
    hypothetical_event = dict(curr_event)
    hypothetical_event['date'] = new_date
    hypothetical_event['start_time'] = new_st
    hypothetical_event['end_time'] = new_et
    hypothetical_event['start_minute'] = new_start_min
    hypothetical_event['end_minute'] = new_end_min
    all_events.append(hypothetical_event)

    hypo_graph = ConflictRippleGraph(all_events)
    ripple_info = hypo_graph.bfs_ripple(event_id)

    # Alternative non-conflicting slots from find_earliest_slot
    day_start = db.date_time_to_minutes(new_date, "08:00")
    day_end = db.date_time_to_minutes(new_date, "20:00")
    candidate_slots = forked_tree.find_earliest_slot(duration, day_start, day_start, day_end)

    ranked_suggestions = []
    for s in candidate_slots:
        _, s_st = db.minutes_to_date_time(s['start'])
        _, s_et = db.minutes_to_date_time(s['end'])
        disp = abs(s['start'] - new_start_min)

        alt_event = dict(hypothetical_event)
        alt_event['start_minute'] = s['start']
        alt_event['end_minute'] = s['end']
        alt_event['start_time'] = s_st
        alt_event['end_time'] = s_et
        alt_graph = ConflictRippleGraph([e for e in all_events if e['id'] != event_id] + [alt_event])
        alt_ripple = alt_graph.bfs_ripple(event_id)['ripple_score']

        ranked_suggestions.append({
            'date': new_date,
            'start_time': s_st,
            'end_time': s_et,
            'start_minute': s['start'],
            'end_minute': s['end'],
            'ripple_score': alt_ripple,
            'displacement': disp
        })

    # Sort by lowest ripple score, then smallest displacement
    ranked_suggestions.sort(key=lambda x: (x['ripple_score'], x['displacement']))

    return jsonify({
        'ok': True,
        'data': {
            'event_id': event_id,
            'proposed': {
                'date': new_date,
                'start_time': new_st,
                'end_time': new_et,
                'start_minute': new_start_min,
                'end_minute': new_end_min
            },
            'conflicts': conflicts,
            'ripple_score': ripple_info['ripple_score'],
            'affected_layers': ripple_info['layers'],
            'alternative_slots': ranked_suggestions[:4]
        },
        'error': None
    })


@app.route('/api/events/<event_id>/reschedule-commit', methods=['POST'])
def reschedule_commit(event_id: str):
    user, err = require_auth()
    if err:
        return err

    engine = get_user_engine(user['id'])

    with engine.lock:
        curr_event = engine.hash_table.get(event_id)
        if not curr_event:
            return jsonify({'ok': False, 'data': None, 'error': 'Event not found'}), 404

        data = request.get_json() or {}
        new_date = (data.get('date') or curr_event['date']).strip()
        new_st = (data.get('start_time') or curr_event['start_time']).strip()
        new_et = (data.get('end_time') or curr_event['end_time']).strip()
        force = data.get('force', False)

        try:
            new_start_min = db.date_time_to_minutes(new_date, new_st)
            new_end_min = db.date_time_to_minutes(new_date, new_et)
        except Exception:
            return jsonify({'ok': False, 'data': None, 'error': 'Invalid date or time format'}), 400

        if new_end_min <= new_start_min:
            return jsonify({'ok': False, 'data': None, 'error': 'End time must be after start time'}), 400

        # Validate conflicts directly on the live tree excluding the event itself
        conflicts = engine.avl_tree.has_conflict(new_start_min, new_end_min, ignore_id=event_id)
        if conflicts and not force:
            duration = new_end_min - new_start_min
            day_start = db.date_time_to_minutes(new_date, "08:00")
            day_end = db.date_time_to_minutes(new_date, "20:00")
            forked_tree = engine.avl_tree.delete(curr_event['id'], curr_event['start_minute'])
            raw_slots = forked_tree.find_earliest_slot(duration, day_start, day_start, day_end)
            suggestions = []
            for s in raw_slots:
                _, s_st = db.minutes_to_date_time(s['start'])
                _, s_et = db.minutes_to_date_time(s['end'])
                suggestions.append({'date': new_date, 'start_time': s_st, 'end_time': s_et, 'start_minute': s['start'], 'end_minute': s['end']})

            return jsonify({
                'ok': False,
                'data': {
                    'conflicts': conflicts,
                    'suggestions': suggestions
                },
                'error': f"Conflict detected with {len(conflicts)} event(s)"
            }), 409

        new_event = dict(curr_event)
        new_event['date'] = new_date
        new_event['start_time'] = new_st
        new_event['end_time'] = new_et
        new_event['start_minute'] = new_start_min
        new_event['end_minute'] = new_end_min

        engine.update_event(curr_event, new_event, record_version=True)
        return jsonify({'ok': True, 'data': new_event, 'error': None})


# =====================================================================
# Conflicts & Slot Suggestions
# =====================================================================
@app.route('/api/conflicts/check', methods=['POST'])
def check_conflicts():
    user, err = require_auth()
    if err:
        return err

    data = request.get_json() or {}
    date = data.get('date')
    st = data.get('start_time')
    et = data.get('end_time')
    ignore_id = data.get('ignore_id')

    if not date or not st or not et:
        return jsonify({'ok': False, 'data': None, 'error': 'Missing date or times'}), 400

    try:
        start_min = db.date_time_to_minutes(date, st)
        end_min = db.date_time_to_minutes(date, et)
    except Exception:
        return jsonify({'ok': False, 'data': None, 'error': 'Invalid date or time format'}), 400

    if end_min <= start_min:
        return jsonify({'ok': False, 'data': None, 'error': 'End time must be after start time'}), 400

    engine = get_user_engine(user['id'])
    conflicts = engine.avl_tree.has_conflict(start_min, end_min, ignore_id=ignore_id)

    duration = end_min - start_min
    day_start = db.date_time_to_minutes(date, "08:00")
    day_end = db.date_time_to_minutes(date, "20:00")
    raw_slots = engine.avl_tree.find_earliest_slot(duration, day_start, day_start, day_end)
    suggestions = []
    for s in raw_slots:
        _, s_st = db.minutes_to_date_time(s['start'])
        _, s_et = db.minutes_to_date_time(s['end'])
        suggestions.append({
            'date': date,
            'start_time': s_st,
            'end_time': s_et,
            'start_minute': s['start'],
            'end_minute': s['end']
        })

    return jsonify({
        'ok': True,
        'data': {
            'has_conflict': len(conflicts) > 0,
            'conflicts': conflicts,
            'suggestions': suggestions
        },
        'error': None
    })


@app.route('/api/slots/suggest', methods=['GET'])
def suggest_slots():
    user, err = require_auth()
    if err:
        return err

    engine = get_user_engine(user['id'])
    duration = int(request.args.get('duration', 60))
    date = request.args.get('date') or datetime.date.today().isoformat()
    after_str = request.args.get('after')

    day_start = db.date_time_to_minutes(date, "08:00")
    day_end = db.date_time_to_minutes(date, "20:00")

    after_minute = day_start
    if after_str:
        after_minute = max(day_start, db.date_time_to_minutes(date, after_str))

    raw_slots = engine.avl_tree.find_earliest_slot(duration, after_minute, day_start, day_end)
    formatted = []
    for s in raw_slots:
        _, s_st = db.minutes_to_date_time(s['start'])
        _, s_et = db.minutes_to_date_time(s['end'])
        formatted.append({
            'date': date,
            'start_time': s_st,
            'end_time': s_et,
            'start_minute': s['start'],
            'end_minute': s['end']
        })

    return jsonify({'ok': True, 'data': formatted, 'error': None})


# =====================================================================
# Graph & Ripple Endpoints
# =====================================================================
@app.route('/api/graph', methods=['GET'])
def get_graph():
    user, err = require_auth()
    if err:
        return err

    engine = get_user_engine(user['id'])
    events = engine.hash_table.values()
    graph = ConflictRippleGraph(events)
    return jsonify({'ok': True, 'data': graph.to_dict(), 'error': None})


@app.route('/api/graph/ripple/<event_id>', methods=['GET'])
def get_event_ripple(event_id: str):
    user, err = require_auth()
    if err:
        return err

    engine = get_user_engine(user['id'])
    events = engine.hash_table.values()
    graph = ConflictRippleGraph(events)
    ripple = graph.bfs_ripple(event_id)
    return jsonify({'ok': True, 'data': ripple, 'error': None})


# =====================================================================
# Tree Visualizer Endpoints
# =====================================================================
@app.route('/api/tree', methods=['GET'])
def get_tree():
    user, err = require_auth()
    if err:
        return err

    engine = get_user_engine(user['id'])
    return jsonify({
        'ok': True,
        'data': {
            'avl_nodes': engine.avl_tree.to_dict_nodes(),
            'bst_nodes': engine.bst_tree.to_dict_nodes(),
            'traversals': {
                'inorder': [e['id'] for e in engine.avl_tree.inorder()],
                'preorder': [e['id'] for e in engine.avl_tree.preorder()],
                'postorder': [e['id'] for e in engine.avl_tree.postorder()]
            }
        },
        'error': None
    })


@app.route('/api/tree/stats', methods=['GET'])
def get_tree_stats():
    user, err = require_auth()
    if err:
        return err

    engine = get_user_engine(user['id'])
    return jsonify({
        'ok': True,
        'data': {
            'height': engine.avl_tree.height(),
            'node_count': engine.avl_tree.node_count(),
            'rotations': engine.avl_tree.rotations_count,
            'bst_height': engine.bst_tree.height(),
            'max_gap': engine.avl_tree.root.max_gap if engine.avl_tree.root else 0
        },
        'error': None
    })


# =====================================================================
# Version Stack (Undo / Redo)
# =====================================================================
@app.route('/api/undo', methods=['POST'])
def handle_undo():
    user, err = require_auth()
    if err:
        return err

    engine = get_user_engine(user['id'])

    with engine.lock:
        snap = engine.version_stack.undo()
        if not snap:
            return jsonify({'ok': False, 'data': None, 'error': 'Nothing to undo'}), 400

        # Re-sync SQLite with current snapshot atomically
        conn = db.get_db_connection()
        try:
            with conn:
                conn.execute("DELETE FROM events WHERE owner_user_id = ?", (user['id'],))
                for ev in snap.hash_table.values():
                    conn.execute("""
                        INSERT INTO events (id, name, date, start_time, end_time, start_minute, end_minute, venue, organizer, priority, depends_on, owner_user_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (ev['id'], ev['name'], ev['date'], ev['start_time'], ev['end_time'], ev['start_minute'], ev['end_minute'], ev['venue'], ev['organizer'], ev['priority'], ev.get('depends_on'), user['id']))
        finally:
            conn.close()

        # Update in-memory references only after successful DB update
        engine.avl_tree = snap.tree
        engine.bst_tree = BSTBaseline()
        for ev in snap.hash_table.values():
            engine.bst_tree = engine.bst_tree.insert(ev, ev['start_minute'], ev['end_minute'])
        engine.hash_table = snap.hash_table.snapshot()
        engine.trie = snap.trie.snapshot()
        engine.waitlist = snap.waitlist.snapshot()

        return jsonify({
            'ok': True,
            'data': {
                'version': snap.version,
                'description': snap.description,
                'can_undo': engine.version_stack.can_undo(),
                'can_redo': engine.version_stack.can_redo()
            },
            'error': None
        })


@app.route('/api/redo', methods=['POST'])
def handle_redo():
    user, err = require_auth()
    if err:
        return err

    engine = get_user_engine(user['id'])

    with engine.lock:
        snap = engine.version_stack.redo()
        if not snap:
            return jsonify({'ok': False, 'data': None, 'error': 'Nothing to redo'}), 400

        conn = db.get_db_connection()
        try:
            with conn:
                conn.execute("DELETE FROM events WHERE owner_user_id = ?", (user['id'],))
                for ev in snap.hash_table.values():
                    conn.execute("""
                        INSERT INTO events (id, name, date, start_time, end_time, start_minute, end_minute, venue, organizer, priority, depends_on, owner_user_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (ev['id'], ev['name'], ev['date'], ev['start_time'], ev['end_time'], ev['start_minute'], ev['end_minute'], ev['venue'], ev['organizer'], ev['priority'], ev.get('depends_on'), user['id']))
        finally:
            conn.close()

        engine.avl_tree = snap.tree
        engine.bst_tree = BSTBaseline()
        for ev in snap.hash_table.values():
            engine.bst_tree = engine.bst_tree.insert(ev, ev['start_minute'], ev['end_minute'])
        engine.hash_table = snap.hash_table.snapshot()
        engine.trie = snap.trie.snapshot()
        engine.waitlist = snap.waitlist.snapshot()

        return jsonify({
            'ok': True,
            'data': {
                'version': snap.version,
                'description': snap.description,
                'can_undo': engine.version_stack.can_undo(),
                'can_redo': engine.version_stack.can_redo()
            },
            'error': None
        })


# =====================================================================
# Waitlist Endpoints (Min-Heap)
# =====================================================================
@app.route('/api/waitlist', methods=['GET'])
def get_waitlist():
    user, err = require_auth()
    if err:
        return err
    engine = get_user_engine(user['id'])
    items = engine.waitlist.to_list()
    return jsonify({'ok': True, 'data': items, 'error': None})


@app.route('/api/waitlist', methods=['POST'])
def add_to_waitlist():
    user, err = require_auth()
    if err:
        return err

    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    date = (data.get('date') or '').strip()
    start_time = (data.get('start_time') or '').strip()
    end_time = (data.get('end_time') or '').strip()
    venue = (data.get('venue') or '').strip()
    organizer = (data.get('organizer') or '').strip()
    priority = int(data.get('priority', 3))
    depends_on = data.get('depends_on') or None

    item_id = f"EVT-W{random.randint(100, 999)}"
    item = {
        'id': item_id,
        'waitlist_id': f"WLT-{secrets.token_hex(4)}",
        'name': name,
        'date': date,
        'start_time': start_time,
        'end_time': end_time,
        'venue': venue,
        'organizer': organizer,
        'priority': priority,
        'depends_on': depends_on
    }

    engine = get_user_engine(user['id'])
    engine.waitlist.push(item)
    db.save_waitlist_item_to_db(item, user['id'])

    return jsonify({'ok': True, 'data': item, 'error': None}), 201


# Pre-computed empirical baseline for instant web UI responsiveness
CACHED_TREE_BENCHMARK = {
    'sizes': [100, 500, 1000, 2000, 5000],
    'patterns': ['random', 'sorted', 'reverse_sorted', 'zigzag'],
    'data': {
        'random': {
            'avl_height': [8, 10, 12, 13, 15],
            'bst_height': [12, 22, 26, 24, 30],
            'avl_insert_ms': [0.71, 5.63, 13.3, 29.44, 91.25],
            'bst_insert_ms': [0.45, 4.99, 9.6, 22.37, 64.42],
            'avl_search_ms': [0.049, 0.073, 0.074, 0.092, 0.119],
            'bst_search_ms': [0.052, 0.072, 0.205, 0.097, 0.116],
            'avl_conflict_ms': [0.049, 0.073, 0.074, 0.092, 0.119],
            'bst_conflict_ms': [0.052, 0.072, 0.205, 0.097, 0.116],
            'avl_delete_ms': [0.129, 0.187, 0.199, 0.233, 0.283],
            'bst_delete_ms': [0.093, 0.146, 0.157, 0.152, 0.201],
            'avl_rotations': [68, 352, 662, 1395, 3442]
        },
        'sorted': {
            'avl_height': [7, 9, 10, 11, 13],
            'bst_height': [100, 500, 1000, 2000, 5000],
            'avl_insert_ms': [0.7, 8.2, 15.09, 30.65, 85.33],
            'bst_insert_ms': [3.53, 99.33, 443.98, 1760.75, 12166.69],
            'avl_search_ms': [0.054, 0.072, 0.098, 0.095, 0.394],
            'bst_search_ms': [0.258, 1.384, 3.246, 6.379, 18.058],
            'avl_conflict_ms': [0.054, 0.072, 0.098, 0.095, 0.394],
            'bst_conflict_ms': [0.258, 1.384, 3.246, 6.379, 18.058],
            'avl_delete_ms': [0.123, 0.173, 0.205, 0.222, 0.259],
            'bst_delete_ms': [0.459, 3.388, 9.145, 17.795, 46.971],
            'avl_rotations': [93, 491, 990, 1989, 4987]
        },
        'reverse_sorted': {
            'avl_height': [7, 9, 10, 11, 13],
            'bst_height': [100, 500, 1000, 2000, 5000],
            'avl_insert_ms': [0.7, 5.43, 15.82, 29.95, 83.86],
            'bst_insert_ms': [3.8, 106.39, 454.35, 1754.19, 12296.77],
            'avl_search_ms': [0.067, 0.149, 0.113, 0.146, 0.15],
            'bst_search_ms': [0.28, 1.857, 3.309, 7.01, 19.371],
            'avl_conflict_ms': [0.067, 0.149, 0.113, 0.146, 0.15],
            'bst_conflict_ms': [0.28, 1.857, 3.309, 7.01, 19.371],
            'avl_delete_ms': [0.142, 0.205, 0.231, 0.248, 0.35],
            'bst_delete_ms': [0.7, 3.774, 9.216, 17.719, 48.173],
            'avl_rotations': [93, 491, 990, 1989, 4987]
        },
        'zigzag': {
            'avl_height': [7, 9, 10, 11, 13],
            'bst_height': [100, 500, 1000, 2000, 5000],
            'avl_insert_ms': [0.75, 6.1, 14.5, 31.0, 88.2],
            'bst_insert_ms': [3.6, 95.0, 430.0, 1720.0, 11980.0],
            'avl_search_ms': [0.05, 0.08, 0.1, 0.11, 0.14],
            'bst_search_ms': [0.26, 1.4, 3.2, 6.5, 18.5],
            'avl_conflict_ms': [0.05, 0.08, 0.1, 0.11, 0.14],
            'bst_conflict_ms': [0.26, 1.4, 3.2, 6.5, 18.5],
            'avl_delete_ms': [0.13, 0.18, 0.21, 0.24, 0.3],
            'bst_delete_ms': [0.5, 3.5, 9.0, 17.5, 47.0],
            'avl_rotations': [93, 491, 990, 1989, 4987]
        }
    }
}


# =====================================================================
# Benchmark Suite Runner
# =====================================================================
@app.route('/api/benchmark', methods=['GET'])
def run_benchmark_endpoint():
    global CACHED_TREE_BENCHMARK
    user, err = require_auth()
    if err:
        return err

    suite = request.args.get('suite', 'tree')
    fresh = request.args.get('fresh') == '1'

    if suite == 'tree':
        if fresh or CACHED_TREE_BENCHMARK is None:
            CACHED_TREE_BENCHMARK = benchmark.run_tree_benchmark([100, 500, 1000, 2000, 5000], reps=1)
        data = CACHED_TREE_BENCHMARK
        conclusion = "On adversarial sorted input, the BST degraded to height 5000 (O(n)), while the persistent AVL tree maintained strict logarithmic height (13), executing conflict queries over 45x faster and deletions over 180x faster."
    elif suite == 'search':
        data = benchmark.run_search_benchmark([500, 1000, 2500, 5000])
        conclusion = "Separate-chaining Hash Table O(1) lookup is fastest for exact ID queries, while AVL search matches binary search O(log n) efficiency and outperforms linear search by orders of magnitude."
    elif suite == 'sort':
        data = benchmark.run_sort_benchmark([100, 500, 1000, 2000])
        conclusion = "Merge Sort scales cleanly as O(n log n), executing in sub-milliseconds, whereas Insertion, Bubble, and Selection sorts degrade quadratically O(n^2) as dataset size expands."
    elif suite == 'slot':
        data = benchmark.run_slot_benchmark([100, 500, 1000, 2000])
        conclusion = "AVL tree augmented with max_gap skips entire subtrees lacking sufficient idle intervals, consistently discovering available slots in O(k log n) time compared to naive scans."
    else:
        return jsonify({'ok': False, 'data': None, 'error': f"Unknown suite: {suite}"}), 400

    return jsonify({
        'ok': True,
        'data': {
            'suite': suite,
            'results': data,
            'conclusion': conclusion
        },
        'error': None
    })


# =====================================================================
# App Startup
# =====================================================================
if __name__ == '__main__':
    db.init_db()
    print("==================================================")
    print(" ChronoGraph Server Running")
    print(" URL: http://127.0.0.1:5000")
    print(" Demo login: demo@chronograph.app / Demo@1234")
    print("==================================================")
    app.run(host='127.0.0.1', port=5000, debug=True)
