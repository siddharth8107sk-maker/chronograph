"""
Database layer for ChronoGraph (SQLite3).
Manages persistence for users, sessions, events, and waitlist.
Seeds a realistic college dataset for the demo account on first run.
"""

from __future__ import annotations
import sqlite3
import hashlib
import secrets
import datetime
from typing import Optional, List, Dict, Any, Tuple

DB_PATH = "chronograph.db"
EPOCH = datetime.date(2026, 1, 1)


def date_time_to_minutes(date_str: str, time_str: str) -> int:
    """Converts YYYY-MM-DD and HH:MM to minutes since 2026-01-01 00:00."""
    d = datetime.date.fromisoformat(date_str)
    days = (d - EPOCH).days
    h, m = map(int, time_str.split(':'))
    return days * 1440 + h * 60 + m


def minutes_to_date_time(minutes: int) -> Tuple[str, str]:
    """Converts minutes since 2026-01-01 00:00 back to (YYYY-MM-DD, HH:MM)."""
    days = minutes // 1440
    rem = minutes % 1440
    h = rem // 60
    m = rem % 60
    d = EPOCH + datetime.timedelta(days=days)
    return d.isoformat(), f"{h:02d}:{m:02d}"


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def hash_password(password: str, salt: Optional[bytes] = None) -> Tuple[str, bytes]:
    """Hashes password with PBKDF2-HMAC-SHA256 (200,000 iterations)."""
    if salt is None:
        salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 200000)
    return dk.hex(), salt


def verify_password(password: str, password_hash: str, salt: bytes) -> bool:
    dk, _ = hash_password(password, salt)
    return secrets.compare_digest(dk, password_hash)


def init_db() -> None:
    """Initializes tables and seeds the demo account if not already present."""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        full_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        salt BLOB NOT NULL,
        created_at TEXT NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        date TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        start_minute INTEGER NOT NULL,
        end_minute INTEGER NOT NULL,
        venue TEXT NOT NULL,
        organizer TEXT NOT NULL,
        priority INTEGER NOT NULL,
        depends_on TEXT,
        owner_user_id TEXT NOT NULL,
        FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS waitlist (
        id TEXT PRIMARY KEY,
        event_id TEXT NOT NULL,
        name TEXT NOT NULL,
        date TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        venue TEXT NOT NULL,
        organizer TEXT NOT NULL,
        priority INTEGER NOT NULL,
        depends_on TEXT,
        owner_user_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    conn.commit()

    # Check if demo account exists
    cur.execute("SELECT id FROM users WHERE email = 'demo@chronograph.app'")
    demo_user = cur.fetchone()
    if not demo_user:
        seed_demo_account(conn)

    conn.close()


def seed_demo_account(conn: sqlite3.Connection) -> None:
    """Creates demo user (demo@chronograph.app / Demo@1234) and 40 realistic events."""
    cur = conn.cursor()
    user_id = "usr-demo-001"
    pwd_hash, salt = hash_password("Demo@1234")
    now_str = datetime.datetime.now().isoformat()

    cur.execute("""
        INSERT INTO users (id, full_name, email, password_hash, salt, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, "Prof. Sarah Jenkins", "demo@chronograph.app", pwd_hash, salt, now_str))

    # 40 Realistic college events spanning 2 weeks
    # Dates: 2026-10-26 to 2026-11-08
    raw_events = [
        # Week 1: Mon Oct 26
        ("EVT-1001", "Hackathon Kickoff & Briefing", "2026-10-26", "09:00", "11:00", "Main Auditorium", "ACM Student Chapter", 1, None),
        ("EVT-1002", "Placement Talk: Zoho Systems", "2026-10-26", "10:00", "12:00", "Main Auditorium", "Placement Cell", 2, None),  # Deliberate conflict with EVT-1001
        ("EVT-1003", "Data Structures Lab Viva - Batch A", "2026-10-26", "13:00", "15:00", "CSE Lab 2", "Department of Computer Science", 1, None),
        ("EVT-1004", "Robotics Club Hardware Sprint", "2026-10-26", "15:30", "18:00", "Block C Seminar Hall", "Robotics Club", 3, None),

        # Tue Oct 27
        ("EVT-1005", "Inter-Department Quiz Prelims", "2026-10-27", "09:30", "11:30", "Block C Seminar Hall", "Literary & Quiz Society", 3, None),
        ("EVT-1006", "Web3 Workshop: Smart Contracts", "2026-10-27", "11:00", "13:00", "Block C Seminar Hall", "IEEE Student Branch", 3, None),  # Deliberate conflict with EVT-1005
        ("EVT-1007", "NSS Blood Donation Camp", "2026-10-27", "09:00", "14:00", "Open Air Theatre", "NSS Unit", 1, None),
        ("EVT-1008", "Data Structures Lab Viva - Batch B", "2026-10-27", "14:00", "16:00", "CSE Lab 2", "Department of Computer Science", 1, "EVT-1003"),

        # Wed Oct 28
        ("EVT-1009", "Competitive Programming Contest", "2026-10-28", "10:00", "13:00", "CSE Lab 2", "ACM Student Chapter", 2, None),
        ("EVT-1010", "AI Ethics Panel Discussion", "2026-10-28", "14:00", "16:00", "Main Auditorium", "Department of Computer Science", 2, None),
        ("EVT-1011", "Cultural Night Dance Auditions", "2026-10-28", "16:30", "19:00", "Open Air Theatre", "Cultural Affairs", 4, None),

        # Thu Oct 29
        ("EVT-1012", "Placement Talk: Google Cloud", "2026-10-29", "09:30", "11:30", "Main Auditorium", "Placement Cell", 1, None),
        ("EVT-1013", "Cybersecurity Capture The Flag", "2026-10-29", "11:00", "15:00", "CSE Lab 2", "ACM Student Chapter", 2, None),
        ("EVT-1014", "Photography Club Photo Walk", "2026-10-29", "16:00", "18:00", "Open Air Theatre", "Cultural Affairs", 4, None),

        # Fri Oct 30
        ("EVT-1015", "Hackathon 24hr Mentor Checkpoint", "2026-10-30", "10:00", "12:00", "Block C Seminar Hall", "ACM Student Chapter", 1, "EVT-1001"),
        ("EVT-1016", "Open Source Contribution Clinic", "2026-10-30", "13:00", "15:30", "CSE Lab 2", "IEEE Student Branch", 3, None),
        ("EVT-1017", "Acoustic Jam Session", "2026-10-30", "17:00", "19:30", "Open Air Theatre", "Cultural Affairs", 4, None),

        # Sat Oct 31
        ("EVT-1018", "Hackathon Final Presentations", "2026-10-31", "10:00", "13:00", "Main Auditorium", "ACM Student Chapter", 1, "EVT-1015"),
        ("EVT-1019", "Hackathon Award Ceremony", "2026-10-31", "14:00", "16:00", "Main Auditorium", "ACM Student Chapter", 1, "EVT-1018"),

        # Sun Nov 01
        ("EVT-1020", "Campus Cleanup Green Drive", "2026-11-01", "08:00", "11:00", "Open Air Theatre", "NSS Unit", 3, None),
        ("EVT-1021", "Drone Flying Demonstration", "2026-11-01", "15:00", "17:30", "Open Air Theatre", "Robotics Club", 3, None),

        # Week 2: Mon Nov 02
        ("EVT-1022", "Guest Lecture: Quantum Algorithms", "2026-11-02", "10:00", "12:00", "Block C Seminar Hall", "Department of Computer Science", 2, None),
        ("EVT-1023", "Resume Review & Mock Interviews", "2026-11-02", "13:00", "16:00", "Block C Seminar Hall", "Placement Cell", 2, "EVT-1012"),
        ("EVT-1024", "Database Internals Hands-on Lab", "2026-11-02", "14:00", "16:30", "CSE Lab 2", "Department of Computer Science", 2, None),

        # Tue Nov 03
        ("EVT-1025", "Inter-College Debate Championship", "2026-11-03", "09:00", "12:30", "Block C Seminar Hall", "Literary & Quiz Society", 2, None),
        ("EVT-1026", "Faculty Research Symposium", "2026-11-03", "11:00", "14:00", "Block C Seminar Hall", "Department of Computer Science", 1, None),  # Deliberate conflict with EVT-1025
        ("EVT-1027", "Mobile App Development BootCamp", "2026-11-03", "14:00", "17:00", "CSE Lab 2", "ACM Student Chapter", 3, None),

        # Wed Nov 04
        ("EVT-1028", "Placement Drive: Microsoft R&D", "2026-11-04", "09:00", "12:00", "Main Auditorium", "Placement Cell", 1, None),
        ("EVT-1029", "Design Thinking & UI/UX Workshop", "2026-11-04", "13:00", "15:30", "Block C Seminar Hall", "IEEE Student Branch", 3, None),
        ("EVT-1030", "Street Play & Theatrics Rehearsal", "2026-11-04", "16:00", "18:30", "Open Air Theatre", "Cultural Affairs", 4, None),

        # Thu Nov 05
        ("EVT-1031", "Annual Tech Fest Organizers Sync", "2026-11-05", "10:00", "12:00", "Main Auditorium", "Department of Computer Science", 2, None),
        ("EVT-1032", "Compiler Design Project Reviews", "2026-11-05", "13:00", "16:00", "CSE Lab 2", "Department of Computer Science", 2, None),
        ("EVT-1033", "Debate Finals & Valedictory", "2026-11-05", "15:00", "17:00", "Block C Seminar Hall", "Literary & Quiz Society", 2, "EVT-1025"),

        # Fri Nov 06
        ("EVT-1034", "Alumni Mentorship Roundtables", "2026-11-06", "10:30", "13:00", "Main Auditorium", "Placement Cell", 2, None),
        ("EVT-1035", "Machine Learning Model Deployment", "2026-11-06", "14:00", "16:30", "CSE Lab 2", "IEEE Student Branch", 2, None),
        ("EVT-1036", "College Band Concert Night", "2026-11-06", "17:30", "20:00", "Open Air Theatre", "Cultural Affairs", 4, None),

        # Sat Nov 07
        ("EVT-1037", "High-School Outreach Robotics Demo", "2026-11-07", "09:30", "12:30", "Main Auditorium", "Robotics Club", 3, None),
        ("EVT-1038", "First Aid & Disaster Response Training", "2026-11-07", "13:00", "16:00", "Block C Seminar Hall", "NSS Unit", 2, None),

        # Sun Nov 08
        ("EVT-1039", "Stargazing Astronomy Night", "2026-11-08", "18:00", "20:30", "Open Air Theatre", "Literary & Quiz Society", 4, None),
        ("EVT-1040", "Semester Project Showcase & Mixer", "2026-11-08", "14:00", "17:00", "Main Auditorium", "Department of Computer Science", 1, None),
    ]

    for eid, name, date, st, et, venue, org, prio, dep in raw_events:
        sm = date_time_to_minutes(date, st)
        em = date_time_to_minutes(date, et)
        cur.execute("""
            INSERT INTO events (id, name, date, start_time, end_time, start_minute, end_minute, venue, organizer, priority, depends_on, owner_user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (eid, name, date, st, et, sm, em, venue, org, prio, dep, user_id))

    # Add 2 initial waitlisted events for the demo user
    waitlisted = [
        ("WLT-2001", "EVT-W1", "Cloud Infrastructure Architecture Lab", "2026-10-26", "10:30", "12:30", "CSE Lab 2", "ACM Student Chapter", 1, None),
        ("WLT-2002", "EVT-W2", "Creative Writing Open Mic Session", "2026-10-27", "15:00", "16:30", "Open Air Theatre", "Literary & Quiz Society", 3, None)
    ]
    for wid, eid, name, date, st, et, venue, org, prio, dep in waitlisted:
        cur.execute("""
            INSERT INTO waitlist (id, event_id, name, date, start_time, end_time, venue, organizer, priority, depends_on, owner_user_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (wid, eid, name, date, st, et, venue, org, prio, dep, user_id, now_str))

    conn.commit()


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, full_name, email, created_at FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def create_user(full_name: str, email: str, password_hash: str, salt: bytes) -> Dict[str, Any]:
    conn = get_db_connection()
    cur = conn.cursor()
    user_id = f"usr-{secrets.token_hex(6)}"
    now_str = datetime.datetime.now().isoformat()
    cur.execute("""
        INSERT INTO users (id, full_name, email, password_hash, salt, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, full_name, email.strip().lower(), password_hash, salt, now_str))
    conn.commit()
    conn.close()
    return {'id': user_id, 'full_name': full_name, 'email': email.strip().lower(), 'created_at': now_str}


def create_session(user_id: str) -> str:
    conn = get_db_connection()
    cur = conn.cursor()
    token = secrets.token_hex(32)
    now = datetime.datetime.now()
    expires = now + datetime.timedelta(days=7)
    cur.execute("""
        INSERT INTO sessions (token, user_id, created_at, expires_at)
        VALUES (?, ?, ?, ?)
    """, (token, user_id, now.isoformat(), expires.isoformat()))
    conn.commit()
    conn.close()
    return token


def validate_session(token: str) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    conn = get_db_connection()
    cur = conn.cursor()
    now_str = datetime.datetime.now().isoformat()
    cur.execute("""
        SELECT u.id, u.full_name, u.email, s.token
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.token = ? AND s.expires_at > ?
    """, (token, now_str))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_session(token: str) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()
    conn.close()


def load_user_events_from_db(user_id: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM events WHERE owner_user_id = ? ORDER BY start_minute ASC", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_event_to_db(event: Dict[str, Any], user_id: str) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO events (id, name, date, start_time, end_time, start_minute, end_minute, venue, organizer, priority, depends_on, owner_user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            date = excluded.date,
            start_time = excluded.start_time,
            end_time = excluded.end_time,
            start_minute = excluded.start_minute,
            end_minute = excluded.end_minute,
            venue = excluded.venue,
            organizer = excluded.organizer,
            priority = excluded.priority,
            depends_on = excluded.depends_on
    """, (
        event['id'], event['name'], event['date'], event['start_time'], event['end_time'],
        event['start_minute'], event['end_minute'], event['venue'], event['organizer'],
        int(event['priority']), event.get('depends_on'), user_id
    ))
    conn.commit()
    conn.close()


def delete_event_from_db(event_id: str, user_id: str) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM events WHERE id = ? AND owner_user_id = ?", (event_id, user_id))
    conn.commit()
    conn.close()


def load_waitlist_from_db(user_id: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM waitlist WHERE owner_user_id = ? ORDER BY priority ASC, created_at ASC", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_waitlist_item_to_db(item: Dict[str, Any], user_id: str) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    w_id = item.get('waitlist_id') or f"WLT-{secrets.token_hex(4)}"
    now_str = datetime.datetime.now().isoformat()
    cur.execute("""
        INSERT OR REPLACE INTO waitlist (id, event_id, name, date, start_time, end_time, venue, organizer, priority, depends_on, owner_user_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        w_id, item['id'], item['name'], item['date'], item['start_time'], item['end_time'],
        item.get('venue', ''), item.get('organizer', ''), int(item.get('priority', 3)),
        item.get('depends_on'), user_id, now_str
    ))
    conn.commit()
    conn.close()


def remove_waitlist_item_from_db(event_id: str, user_id: str) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM waitlist WHERE (event_id = ? OR id = ?) AND owner_user_id = ?", (event_id, event_id, user_id))
    conn.commit()
    conn.close()
