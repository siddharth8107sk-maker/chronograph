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


DEFAULT_COLLEGE_VENUES = {
    'Karunya Institute of Technology and Sciences': [
        'Main Auditorium',
        'Block C Seminar Hall',
        'CSE Lab 2',
        'Open Air Theatre'
    ],
    'Vellore Institute of Technology': [
        'Anna Auditorium',
        'Technology Tower Lab 1',
        'SJT Seminar Hall',
        'Outdoor Amphitheatre'
    ],
    'PSG College of Arts and Science': [
        'GRD Auditorium',
        'Commerce Computer Lab',
        'Science Block Seminar Hall',
        'Kalaikarangal Quadrangle'
    ]
}


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
        created_at TEXT NOT NULL,
        college TEXT NOT NULL DEFAULT 'Karunya Institute of Technology and Sciences'
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
        college TEXT DEFAULT 'Karunya Institute of Technology and Sciences',
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
        college TEXT DEFAULT 'Karunya Institute of Technology and Sciences',
        FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # Ensure schema migrations for existing database files
    cur.execute("PRAGMA table_info(users)")
    u_cols = [r[1] for r in cur.fetchall()]
    if 'college' not in u_cols:
        cur.execute("ALTER TABLE users ADD COLUMN college TEXT NOT NULL DEFAULT 'Karunya Institute of Technology and Sciences'")
    cur.execute("UPDATE users SET college = 'Karunya Institute of Technology and Sciences' WHERE college = 'MIT College of Engineering' OR college IS NULL OR college = ''")

    cur.execute("PRAGMA table_info(events)")
    e_cols = [r[1] for r in cur.fetchall()]
    if 'college' not in e_cols:
        cur.execute("ALTER TABLE events ADD COLUMN college TEXT DEFAULT 'Karunya Institute of Technology and Sciences'")
    cur.execute("UPDATE events SET college = 'Karunya Institute of Technology and Sciences' WHERE college = 'MIT College of Engineering' OR college IS NULL OR college = ''")

    cur.execute("PRAGMA table_info(waitlist)")
    w_cols = [r[1] for r in cur.fetchall()]
    if 'college' not in w_cols:
        cur.execute("ALTER TABLE waitlist ADD COLUMN college TEXT DEFAULT 'Karunya Institute of Technology and Sciences'")
    cur.execute("UPDATE waitlist SET college = 'Karunya Institute of Technology and Sciences' WHERE college = 'MIT College of Engineering' OR college IS NULL OR college = ''")

    # Venues table for college-specific campus venues
    cur.execute("""
    CREATE TABLE IF NOT EXISTS venues (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        college TEXT NOT NULL,
        created_at TEXT NOT NULL,
        created_by_user_id TEXT,
        UNIQUE(name, college)
    );
    """)

    # Populate default venues for the three colleges
    now_ts = datetime.datetime.now().isoformat()
    for col_name, v_names in DEFAULT_COLLEGE_VENUES.items():
        for vn in v_names:
            v_id = f"ven-{hashlib.md5(f'{col_name}:{vn}'.encode()).hexdigest()[:10]}"
            cur.execute("""
                INSERT OR IGNORE INTO venues (id, name, college, created_at, created_by_user_id)
                VALUES (?, ?, ?, ?, ?)
            """, (v_id, vn, col_name, now_ts, 'system'))

    # Backfill venues from existing events
    cur.execute("SELECT DISTINCT venue, college FROM events WHERE venue IS NOT NULL AND venue != ''")
    for r in cur.fetchall():
        vn = r['venue'].strip()
        col_name = r['college'] or 'Karunya Institute of Technology and Sciences'
        v_id = f"ven-{hashlib.md5(f'{col_name}:{vn}'.encode()).hexdigest()[:10]}"
        cur.execute("""
            INSERT OR IGNORE INTO venues (id, name, college, created_at, created_by_user_id)
            VALUES (?, ?, ?, ?, ?)
        """, (v_id, vn, col_name, now_ts, 'system'))

    conn.commit()

    # Check and seed demo accounts for all three colleges
    seed_demo_accounts(conn)

    conn.close()


def seed_demo_accounts(conn: sqlite3.Connection) -> None:
    """Seeds demo accounts and realistic events for all three colleges."""
    pwd_hash, salt = hash_password("Demo@1234")
    now_str = datetime.datetime.now().isoformat()

    seed_karunya_account(conn, pwd_hash, salt, now_str)
    seed_vit_account(conn, pwd_hash, salt, now_str)
    seed_psg_account(conn, pwd_hash, salt, now_str)


# Backward compatibility alias
seed_demo_account = seed_demo_accounts


def seed_karunya_account(conn: sqlite3.Connection, pwd_hash: str, salt: bytes, now_str: str) -> None:
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE email = 'demo@chronograph.app'")
    demo_row = cur.fetchone()
    user_id = demo_row['id'] if demo_row else "usr-demo-001"

    if not demo_row:
        cur.execute("""
            INSERT INTO users (id, full_name, email, password_hash, salt, created_at, college)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, "Prof. Sarah Jenkins", "demo@chronograph.app", pwd_hash, salt, now_str, "Karunya Institute of Technology and Sciences"))

    # Also register karunya@chronograph.app alias
    cur.execute("SELECT id FROM users WHERE email = 'karunya@chronograph.app'")
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO users (id, full_name, email, password_hash, salt, created_at, college)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("usr-demo-karunya", "Prof. Sarah Jenkins", "karunya@chronograph.app", pwd_hash, salt, now_str, "Karunya Institute of Technology and Sciences"))

    # Seed events if none exist for Karunya
    cur.execute("SELECT COUNT(*) as cnt FROM events WHERE college = 'Karunya Institute of Technology and Sciences'")
    if cur.fetchone()['cnt'] == 0:
        raw_events = [
            ("EVT-1001", "Hackathon Kickoff & Briefing", "2026-10-26", "09:00", "11:00", "Main Auditorium", "ACM Student Chapter", 1, None),
            ("EVT-1002", "Placement Talk: Zoho Systems", "2026-10-26", "10:00", "12:00", "Main Auditorium", "Placement Cell", 2, None),
            ("EVT-1003", "Data Structures Lab Viva - Batch A", "2026-10-26", "13:00", "15:00", "CSE Lab 2", "Department of Computer Science", 1, None),
            ("EVT-1004", "Robotics Club Hardware Sprint", "2026-10-26", "15:30", "18:00", "Block C Seminar Hall", "Robotics Club", 3, None),
            ("EVT-1005", "Inter-Department Quiz Prelims", "2026-10-27", "09:30", "11:30", "Block C Seminar Hall", "Literary & Quiz Society", 3, None),
            ("EVT-1006", "Web3 Workshop: Smart Contracts", "2026-10-27", "11:00", "13:00", "Block C Seminar Hall", "IEEE Student Branch", 3, None),
            ("EVT-1007", "NSS Blood Donation Camp", "2026-10-27", "09:00", "14:00", "Open Air Theatre", "NSS Unit", 1, None),
            ("EVT-1008", "Data Structures Lab Viva - Batch B", "2026-10-27", "14:00", "16:00", "CSE Lab 2", "Department of Computer Science", 1, "EVT-1003"),
            ("EVT-1009", "Competitive Programming Contest", "2026-10-28", "10:00", "13:00", "CSE Lab 2", "ACM Student Chapter", 2, None),
            ("EVT-1010", "AI Ethics Panel Discussion", "2026-10-28", "14:00", "16:00", "Main Auditorium", "Department of Computer Science", 2, None),
            ("EVT-1011", "Cultural Night Dance Auditions", "2026-10-28", "16:30", "19:00", "Open Air Theatre", "Cultural Affairs", 4, None),
            ("EVT-1012", "Placement Talk: Google Cloud", "2026-10-29", "09:30", "11:30", "Main Auditorium", "Placement Cell", 1, None),
            ("EVT-1013", "Cybersecurity Capture The Flag", "2026-10-29", "11:00", "15:00", "CSE Lab 2", "ACM Student Chapter", 2, None),
            ("EVT-1014", "Photography Club Photo Walk", "2026-10-29", "16:00", "18:00", "Open Air Theatre", "Cultural Affairs", 4, None),
            ("EVT-1015", "Hackathon 24hr Mentor Checkpoint", "2026-10-30", "10:00", "12:00", "Block C Seminar Hall", "ACM Student Chapter", 1, "EVT-1001"),
            ("EVT-1016", "Open Source Contribution Clinic", "2026-10-30", "13:00", "15:30", "CSE Lab 2", "IEEE Student Branch", 3, None),
            ("EVT-1017", "Acoustic Jam Session", "2026-10-30", "17:00", "19:30", "Open Air Theatre", "Cultural Affairs", 4, None),
            ("EVT-1018", "Hackathon Final Presentations", "2026-10-31", "10:00", "13:00", "Main Auditorium", "ACM Student Chapter", 1, "EVT-1015"),
            ("EVT-1019", "Hackathon Award Ceremony", "2026-10-31", "14:00", "16:00", "Main Auditorium", "ACM Student Chapter", 1, "EVT-1018"),
            ("EVT-1020", "Campus Cleanup Green Drive", "2026-11-01", "08:00", "11:00", "Open Air Theatre", "NSS Unit", 3, None),
        ]
        for eid, name, date, st, et, venue, org, prio, dep in raw_events:
            sm = date_time_to_minutes(date, st)
            em = date_time_to_minutes(date, et)
            cur.execute("""
                INSERT INTO events (id, name, date, start_time, end_time, start_minute, end_minute, venue, organizer, priority, depends_on, owner_user_id, college)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (eid, name, date, st, et, sm, em, venue, org, prio, dep, user_id, "Karunya Institute of Technology and Sciences"))

        waitlisted = [
            ("WLT-2001", "EVT-W1", "Cloud Infrastructure Architecture Lab", "2026-10-26", "10:30", "12:30", "CSE Lab 2", "ACM Student Chapter", 1, None),
            ("WLT-2002", "EVT-W2", "Creative Writing Open Mic Session", "2026-10-27", "15:00", "16:30", "Open Air Theatre", "Literary & Quiz Society", 3, None)
        ]
        for wid, eid, name, date, st, et, venue, org, prio, dep in waitlisted:
            cur.execute("""
                INSERT INTO waitlist (id, event_id, name, date, start_time, end_time, venue, organizer, priority, depends_on, owner_user_id, created_at, college)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (wid, eid, name, date, st, et, venue, org, prio, dep, user_id, now_str, "Karunya Institute of Technology and Sciences"))

    conn.commit()


def seed_vit_account(conn: sqlite3.Connection, pwd_hash: str, salt: bytes, now_str: str) -> None:
    cur = conn.cursor()
    user_id = "usr-demo-vit"
    college = "Vellore Institute of Technology"

    cur.execute("SELECT id FROM users WHERE email = 'vit@chronograph.app'")
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO users (id, full_name, email, password_hash, salt, created_at, college)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, "Dr. Rajesh Kumar", "vit@chronograph.app", pwd_hash, salt, now_str, college))

    cur.execute("SELECT COUNT(*) as cnt FROM events WHERE college = ?", (college,))
    if cur.fetchone()['cnt'] == 0:
        raw_events = [
            ("EVT-V1001", "Riviera 2026 Steering Committee Briefing", "2026-10-26", "09:00", "11:00", "Anna Auditorium", "Cultural Affairs Council", 1, None),
            ("EVT-V1002", "Placement Drive: Microsoft India Core", "2026-10-26", "10:00", "12:00", "Anna Auditorium", "PAT Placement Center", 1, None),
            ("EVT-V1003", "Algorithms & Data Structures Lab - Slot L1", "2026-10-26", "13:00", "15:00", "Technology Tower Lab 1", "School of Computer Science", 1, None),
            ("EVT-V1004", "Gravitas Robotics Arena Hardware Sprint", "2026-10-26", "15:30", "18:00", "SJT Seminar Hall", "Robotics Club", 3, None),
            ("EVT-V1005", "Cloud Architecture & Kubernetes Sprint", "2026-10-27", "09:30", "11:30", "SJT Seminar Hall", "ACM Student Chapter", 3, None),
            ("EVT-V1006", "Smart Contract Security & Web3 Audit", "2026-10-27", "11:00", "13:00", "SJT Seminar Hall", "IEEE Computer Society", 3, None),
            ("EVT-V1007", "Youth Red Cross Blood Donation Camp", "2026-10-27", "09:00", "14:00", "Outdoor Amphitheatre", "Red Cross Society", 1, None),
            ("EVT-V1008", "Algorithms Lab - Slot L2 Advanced", "2026-10-27", "14:00", "16:00", "Technology Tower Lab 1", "School of Computer Science", 1, "EVT-V1003"),
            ("EVT-V1009", "Competitive Programming League - Round 1", "2026-10-28", "10:00", "13:00", "Technology Tower Lab 1", "ACM Student Chapter", 2, None),
            ("EVT-V1010", "Autonomous Robotics & LiDAR Keynote", "2026-10-28", "14:00", "16:00", "Anna Auditorium", "School of Mechanical Engg", 2, None),
            ("EVT-V1011", "Battle of the Bands Music Prelims", "2026-10-28", "16:30", "19:00", "Outdoor Amphitheatre", "Music Club", 4, None),
            ("EVT-V1012", "Placement Orientation: Amazon AWS", "2026-10-29", "09:30", "11:30", "Anna Auditorium", "PAT Placement Center", 1, None),
            ("EVT-V1013", "Cybersecurity Capture The Flag (CTF)", "2026-10-29", "11:00", "15:00", "Technology Tower Lab 1", "IEEE Computer Society", 2, None),
            ("EVT-V1014", "Photography Walk & Heritage Shoot", "2026-10-29", "16:00", "18:00", "Outdoor Amphitheatre", "Photography Club", 4, None),
            ("EVT-V1015", "Gravitas 36-hr Hackathon Checkpoint", "2026-10-30", "10:00", "12:00", "SJT Seminar Hall", "Innovation Cell", 1, "EVT-V1004"),
            ("EVT-V1016", "Open Source Kernel Patching Clinic", "2026-10-30", "13:00", "15:30", "Technology Tower Lab 1", "Open Source Society", 3, None),
            ("EVT-V1017", "Acoustic Sunset Jam Session", "2026-10-30", "17:00", "19:30", "Outdoor Amphitheatre", "Music Club", 4, None),
            ("EVT-V1018", "Gravitas Hackathon Grand Presentations", "2026-10-31", "10:00", "13:00", "Anna Auditorium", "Innovation Cell", 1, "EVT-V1015"),
            ("EVT-V1019", "Gravitas Award Ceremony & Trophies", "2026-10-31", "14:00", "16:00", "Anna Auditorium", "Innovation Cell", 1, "EVT-V1018"),
            ("EVT-V1020", "Clean Campus Swachhathon Drive", "2026-11-01", "08:00", "11:00", "Outdoor Amphitheatre", "Sports Council", 3, None),
        ]
        for eid, name, date, st, et, venue, org, prio, dep in raw_events:
            sm = date_time_to_minutes(date, st)
            em = date_time_to_minutes(date, et)
            cur.execute("""
                INSERT INTO events (id, name, date, start_time, end_time, start_minute, end_minute, venue, organizer, priority, depends_on, owner_user_id, college)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (eid, name, date, st, et, sm, em, venue, org, prio, dep, user_id, college))

        waitlisted = [
            ("WLT-V2001", "EVT-VW1", "Quantum Cryptography Masterclass", "2026-10-26", "10:30", "12:30", "Technology Tower Lab 1", "School of Computer Science", 1, None),
            ("WLT-V2002", "EVT-VW2", "Literary Debate Open Mic", "2026-10-27", "15:00", "16:30", "Outdoor Amphitheatre", "English Literary Club", 3, None)
        ]
        for wid, eid, name, date, st, et, venue, org, prio, dep in waitlisted:
            cur.execute("""
                INSERT INTO waitlist (id, event_id, name, date, start_time, end_time, venue, organizer, priority, depends_on, owner_user_id, created_at, college)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (wid, eid, name, date, st, et, venue, org, prio, dep, user_id, now_str, college))

    conn.commit()


def seed_psg_account(conn: sqlite3.Connection, pwd_hash: str, salt: bytes, now_str: str) -> None:
    cur = conn.cursor()
    user_id = "usr-demo-psg"
    college = "PSG College of Arts and Science"

    cur.execute("SELECT id FROM users WHERE email = 'psg@chronograph.app'")
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO users (id, full_name, email, password_hash, salt, created_at, college)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, "Dr. Ananya Iyer", "psg@chronograph.app", pwd_hash, salt, now_str, college))

    cur.execute("SELECT COUNT(*) as cnt FROM events WHERE college = ?", (college,))
    if cur.fetchone()['cnt'] == 0:
        raw_events = [
            ("EVT-P1001", "Culturals 2026 Inauguration & Welcome", "2026-10-26", "09:00", "11:00", "GRD Auditorium", "Students Union", 1, None),
            ("EVT-P1002", "Campus Recruitment: Deloitte Advisory", "2026-10-26", "10:00", "12:00", "GRD Auditorium", "Placement Council", 1, None),
            ("EVT-P1003", "Financial Modeling & Analytics Lab - Batch 1", "2026-10-26", "13:00", "15:00", "Commerce Computer Lab", "Department of Commerce", 1, None),
            ("EVT-P1004", "State-Level Science Exhibition Setup", "2026-10-26", "15:30", "18:00", "Science Block Seminar Hall", "Physics & Chemistry Dept", 3, None),
            ("EVT-P1005", "National Budget & Fiscal Policy Symposium", "2026-10-27", "09:30", "11:30", "Science Block Seminar Hall", "Economics Association", 2, None),
            ("EVT-P1006", "FinTech & Algorithmic Trading Workshop", "2026-10-27", "11:00", "13:00", "Science Block Seminar Hall", "Commerce Forum", 2, None),
            ("EVT-P1007", "NSS Free Health & Eye Care Camp", "2026-10-27", "09:00", "14:00", "Kalaikarangal Quadrangle", "NSS Unit", 1, None),
            ("EVT-P1008", "Financial Modeling - Advanced Portfolio Batch", "2026-10-27", "14:00", "16:00", "Commerce Computer Lab", "Department of Commerce", 1, "EVT-P1003"),
            ("EVT-P1009", "Data Analytics with R Practical Contest", "2026-10-28", "10:00", "13:00", "Commerce Computer Lab", "Computer Applications Dept", 2, None),
            ("EVT-P1010", "Digital Media & Investigative Journalism Panel", "2026-10-28", "14:00", "16:00", "GRD Auditorium", "Visual Communication Dept", 2, None),
            ("EVT-P1011", "Bharatanatyam & Classical Dance Prelims", "2026-10-28", "16:30", "19:00", "Kalaikarangal Quadrangle", "Fine Arts Club", 4, None),
            ("EVT-P1012", "Placement Drive: KPMG Assurance & Tax", "2026-10-29", "09:30", "11:30", "GRD Auditorium", "Placement Council", 1, None),
            ("EVT-P1013", "UI/UX & Web Prototype Hack", "2026-10-29", "11:00", "15:00", "Commerce Computer Lab", "Computer Science Dept", 2, None),
            ("EVT-P1014", "Watercolor & Fine Arts Open Exhibition", "2026-10-29", "16:00", "18:00", "Kalaikarangal Quadrangle", "Fine Arts Club", 4, None),
            ("EVT-P1015", "Science Paper Presentations - Session 1", "2026-10-30", "10:00", "12:00", "Science Block Seminar Hall", "Science Association", 1, "EVT-P1004"),
            ("EVT-P1016", "Applied Biotechnology Research Showcase", "2026-10-30", "13:00", "15:30", "Commerce Computer Lab", "Biotechnology Dept", 3, None),
            ("EVT-P1017", "Carnatic Music & Western Acoustic Night", "2026-10-30", "17:00", "19:30", "Kalaikarangal Quadrangle", "Music Association", 4, None),
            ("EVT-P1018", "Annual Inter-College Cultural Gala", "2026-10-31", "10:00", "13:00", "GRD Auditorium", "Students Union", 1, "EVT-P1001"),
            ("EVT-P1019", "Culturals Award Distribution & Valedictory", "2026-10-31", "14:00", "16:00", "GRD Auditorium", "Students Union", 1, "EVT-P1018"),
            ("EVT-P1020", "Rotaract Campus Green Plantation Drive", "2026-11-01", "08:00", "11:00", "Kalaikarangal Quadrangle", "Rotaract Club", 3, None),
        ]
        for eid, name, date, st, et, venue, org, prio, dep in raw_events:
            sm = date_time_to_minutes(date, st)
            em = date_time_to_minutes(date, et)
            cur.execute("""
                INSERT INTO events (id, name, date, start_time, end_time, start_minute, end_minute, venue, organizer, priority, depends_on, owner_user_id, college)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (eid, name, date, st, et, sm, em, venue, org, prio, dep, user_id, college))

        waitlisted = [
            ("WLT-P2001", "EVT-PW1", "Corporate Taxation Masterclass", "2026-10-26", "10:30", "12:30", "Commerce Computer Lab", "Commerce Dept", 1, None),
            ("WLT-P2002", "EVT-PW2", "Tamil Literary Debate Prelims", "2026-10-27", "15:00", "16:30", "Kalaikarangal Quadrangle", "Literary Society", 3, None)
        ]
        for wid, eid, name, date, st, et, venue, org, prio, dep in waitlisted:
            cur.execute("""
                INSERT INTO waitlist (id, event_id, name, date, start_time, end_time, venue, organizer, priority, depends_on, owner_user_id, created_at, college)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (wid, eid, name, date, st, et, venue, org, prio, dep, user_id, now_str, college))

    conn.commit()


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, full_name, email, password_hash, salt, college, created_at FROM users WHERE email = ?", (email.strip().lower(),))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, full_name, email, college, created_at FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def create_user(full_name: str, email: str, password_hash: str, salt: bytes, college: str = 'Karunya Institute of Technology and Sciences') -> Dict[str, Any]:
    conn = get_db_connection()
    cur = conn.cursor()
    user_id = f"usr-{secrets.token_hex(6)}"
    now_str = datetime.datetime.now().isoformat()
    cur.execute("""
        INSERT INTO users (id, full_name, email, password_hash, salt, created_at, college)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, full_name, email.strip().lower(), password_hash, salt, now_str, college))
    conn.commit()
    conn.close()
    return {'id': user_id, 'full_name': full_name, 'email': email.strip().lower(), 'college': college, 'created_at': now_str}


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
        SELECT u.id, u.full_name, u.email, u.college, s.token
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


def load_user_events_from_db(user_id_or_college: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM events WHERE college = ? OR owner_user_id = ? ORDER BY start_minute ASC", (user_id_or_college, user_id_or_college))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_event_to_db(event: Dict[str, Any], user_id: str, college: Optional[str] = None) -> None:
    conn = get_db_connection()
    try:
        col = college or event.get('college')
        if not col:
            cur = conn.cursor()
            cur.execute("SELECT college FROM users WHERE id = ?", (user_id,))
            r = cur.fetchone()
            col = r['college'] if r and r['college'] else 'Karunya Institute of Technology and Sciences'
        with conn:
            conn.execute("""
                INSERT INTO events (id, name, date, start_time, end_time, start_minute, end_minute, venue, organizer, priority, depends_on, owner_user_id, college)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    depends_on = excluded.depends_on,
                    college = excluded.college
            """, (
                event['id'], event['name'], event['date'], event['start_time'], event['end_time'],
                event['start_minute'], event['end_minute'], event['venue'], event['organizer'],
                int(event['priority']), event.get('depends_on'), user_id, col
            ))
    finally:
        conn.close()


def delete_event_from_db(event_id: str, user_id_or_college: str) -> None:
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("DELETE FROM events WHERE id = ? AND (owner_user_id = ? OR college = ?)", (event_id, user_id_or_college, user_id_or_college))
    finally:
        conn.close()


def load_waitlist_from_db(user_id_or_college: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM waitlist WHERE college = ? OR owner_user_id = ? ORDER BY priority ASC, created_at ASC", (user_id_or_college, user_id_or_college))
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def save_waitlist_item_to_db(item: Dict[str, Any], user_id: str, college: Optional[str] = None) -> None:
    conn = get_db_connection()
    try:
        w_id = item.get('waitlist_id') or f"WLT-{secrets.token_hex(4)}"
        now_str = datetime.datetime.now().isoformat()
        col = college or item.get('college')
        if not col:
            cur = conn.cursor()
            cur.execute("SELECT college FROM users WHERE id = ?", (user_id,))
            r = cur.fetchone()
            col = r['college'] if r and r['college'] else 'Karunya Institute of Technology and Sciences'
        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO waitlist (id, event_id, name, date, start_time, end_time, venue, organizer, priority, depends_on, owner_user_id, created_at, college)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                w_id, item['id'], item['name'], item['date'], item['start_time'], item['end_time'],
                item.get('venue', ''), item.get('organizer', ''), int(item.get('priority', 3)),
                item.get('depends_on'), user_id, now_str, col
            ))
    finally:
        conn.close()


def remove_waitlist_item_from_db(event_id: str, user_id: str) -> None:
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("DELETE FROM waitlist WHERE (event_id = ? OR id = ?) AND (owner_user_id = ? OR college = ?)", (event_id, event_id, user_id, user_id))
    finally:
        conn.close()


def promote_waitlist_to_event(waitlist_id: str, event: Dict[str, Any], user_id: str, college: Optional[str] = None) -> None:
    """Atomically removes waitlist record and creates scheduled event record in one transaction."""
    conn = get_db_connection()
    try:
        col = college or event.get('college')
        if not col:
            cur = conn.cursor()
            cur.execute("SELECT college FROM users WHERE id = ?", (user_id,))
            r = cur.fetchone()
            col = r['college'] if r and r['college'] else 'Karunya Institute of Technology and Sciences'
        with conn:
            conn.execute("DELETE FROM waitlist WHERE (event_id = ? OR id = ?) AND (owner_user_id = ? OR college = ?)", (waitlist_id, waitlist_id, user_id, col))
            conn.execute("""
                INSERT INTO events (id, name, date, start_time, end_time, start_minute, end_minute, venue, organizer, priority, depends_on, owner_user_id, college)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event['id'], event['name'], event['date'], event['start_time'], event['end_time'],
                event['start_minute'], event['end_minute'], event['venue'], event['organizer'],
                int(event['priority']), event.get('depends_on'), user_id, col
            ))
    finally:
        conn.close()


def get_venues_for_college(college: str) -> List[str]:
    """Returns sorted unique venue names for a specific college."""
    col = college or 'Karunya Institute of Technology and Sciences'
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT name FROM venues
            WHERE college = ?
            ORDER BY name ASC
        """, (col,))
        rows = cur.fetchall()
        venues = [r['name'] for r in rows if r['name']]
        if not venues:
            venues = DEFAULT_COLLEGE_VENUES.get(col, ['Main Auditorium', 'Seminar Hall', 'Computer Lab'])
        return venues
    finally:
        conn.close()


def add_venue_for_college(name: str, college: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    """Adds a new campus venue for a college."""
    clean_name = (name or '').strip()
    if not clean_name:
        raise ValueError("Venue name cannot be empty")
    if len(clean_name) > 80:
        raise ValueError("Venue name must be 80 characters or fewer")

    col = college or 'Karunya Institute of Technology and Sciences'
    conn = get_db_connection()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute("SELECT id, name FROM venues WHERE college = ? AND LOWER(name) = LOWER(?)", (col, clean_name))
            row = cur.fetchone()
            if row:
                return {'id': row['id'], 'name': row['name'], 'college': col, 'already_existed': True}

            v_id = f"ven-{secrets.token_hex(6)}"
            now_ts = datetime.datetime.now().isoformat()
            conn.execute("""
                INSERT INTO venues (id, name, college, created_at, created_by_user_id)
                VALUES (?, ?, ?, ?, ?)
            """, (v_id, clean_name, col, now_ts, user_id))
            return {'id': v_id, 'name': clean_name, 'college': col, 'already_existed': False}
    finally:
        conn.close()


