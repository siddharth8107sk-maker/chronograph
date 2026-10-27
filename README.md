# ChronoGraph — Real-Time Event Scheduling System
**Course:** Data Structures and Algorithms (25CS306) — Micro-Project MP-01  
**Project:** Academic Implementation, Verification, Testing, and Empirical Benchmarking of an AVL-Driven Event Scheduler

---

## 1. Project Overview

**ChronoGraph** is an academic micro-project for scheduling, conflict detection, and dynamic event rescheduling. At the core of the system is a **Persistent Gap-Augmented AVL Tree** written from scratch in pure Python without external data structure libraries.

The system demonstrates:
- Self-balancing binary search trees (AVL) maintaining $O(\log n)$ bounds on insertion, deletion, and search.
- Half-open interval conflict detection $[start, end)$ using subtree interval augmentation (`max_end`).
- Idle time slot discovery utilizing subtree gap augmentation (`max_gap`) and complement-interval calculation.
- Rigorous empirical comparison against a baseline **Unbalanced Binary Search Tree (BST)** under random, sorted, and reverse-sorted distributions.
- Persistence via SQLite with ACID transactional safety and in-memory synchronization.
- Thread-safe request handling with concurrency protection against check-then-commit race conditions.
- Institutional multi-tenancy with campus isolation across colleges (Karunya, VIT, PSG) and synchronized schedule engines.
- Rich algorithmic extensions: Separate-chaining Hash Table, Prefix Trie, Min-Heap Waitlist, Version Stack (multi-level undo/redo), and Conflict-Ripple Graph (BFS ripple, graph coloring, Kahn's topological sort).

> [!NOTE]
> **Real-Time Classification:** ChronoGraph operates as a **soft real-time** event scheduling system delivering sub-millisecond query and conflict-detection response times within a web application environment. It does **not** claim hard real-time operating system (RTOS) deterministic deadline guarantees.

---

## 2. Technology Stack

- **Backend:** Python 3.10+ (Standard Library: `sqlite3`, `hashlib`, `secrets`, `threading`, `time`, `statistics`).
- **Web Framework:** Flask (Lightweight routing, session management, JSON REST API).
- **Testing Framework:** `pytest` (29 automated test suites covering invariants, scheduling, APIs, multi-tenancy, venues, and concurrency).
- **Database:** SQLite 3 with foreign key enforcement and transactional rollbacks.
- **Frontend:** Single-page application (`templates/index.html`) using Vanilla HTML5, CSS3, SVG visualizers, and JavaScript.

---

## 3. Project Directory Structure

```
chronograph/
├── app.py                     # Flask application, REST API endpoints, thread-safe UserEngine
├── db.py                      # SQLite connection, transactions, PBKDF2 authentication, seed loader
├── benchmark.py               # Empirical benchmarking suite (AVL vs. BST, search, sort, slot finding)
├── requirements.txt           # Python dependencies (Flask, pytest)
├── README.md                  # Comprehensive documentation and benchmark reports
├── ds/                        # Pure Python Data Structure Implementations (No external DS libs)
│   ├── __init__.py
│   ├── avl_gap.py             # Persistent Gap-Augmented AVL Tree (Interval & Gap queries)
│   ├── bst_baseline.py        # Genuinely unbalanced Binary Search Tree baseline
│   ├── hash_index.py          # Separate-chaining Hash Table with dynamic resizing (0.75 load factor)
│   ├── trie.py                # Prefix tree for event title search and autocompletion
│   ├── heap.py                # Min-Heap Priority Queue for event waitlist
│   ├── version_stack.py       # Snapshot-based Version Stack for multi-level Undo/Redo
│   ├── ripple_graph.py        # Conflict graph (BFS ripple score, DFS clustering, topological sort)
│   ├── sorting.py             # Insertion sort, bubble sort, selection sort, merge sort
│   └── searching.py           # Linear search, binary search (iterative/recursive), interpolation search
├── templates/
│   └── index.html             # Web UI: SVG Tree visualizer, ripple graph, benchmarks, calendar
└── tests/                     # Dedicated automated test suite
    ├── __init__.py
    ├── test_avl_tree.py       # AVL rotations (LL, RR, LR, RL), invariants, deletions, augmentations
    ├── test_scheduling.py     # Interval boundaries [A, B), self-conflict exclusion, waitlist placement
    └── test_api_and_consistency.py # REST API status codes (400, 404, 409), DB rollback, concurrency, multi-tenancy, campus venues
```

---

## 4. Data Structure Implementations

### 4.1 Persistent Gap-Augmented AVL Tree (`ds/avl_gap.py`)
- **Key Convention:** Composite key `(start_minute, event_id)` ensuring strict determinism and co-existence of events with identical start times.
- **Node Augmentations:**
  - `height`: For AVL balance factor calculation ($balance = height(left) - height(right)$).
  - `min_start`: Minimum start time across the node's subtree.
  - `max_end`: Maximum end time across the subtree, enabling $O(\log n + k)$ interval pruning.
  - `max_gap`: Maximum idle gap between consecutive events within the subtree.
  - `rightmost_end`: End time of the latest event in the subtree.
- **Rotations:** Path-copying single rotations (LL, RR) and double rotations (LR, RL) running in $O(1)$ time and preserving root immutability for undo/redo version snapshots.
- **Deletion:** Complete support for deleting leaf nodes, nodes with 1 child, and nodes with 2 children (via in-order successor swap and path-copied tree rebalancing).
- **Free Slot Discovery:** `find_earliest_slot(duration, after_minute, day_start, day_end)` identifies candidate gaps and strictly validates `has_conflict()` on every slot, guaranteeing no returned slot overlaps any blocking event.

### 4.2 Unbalanced Binary Search Tree Baseline (`ds/bst_baseline.py`)
- Employs the identical interface as `AVLTree` (`insert`, `delete`, `search_by_key`, `has_conflict`, `inorder`, `height`).
- **Genuinely Unbalanced:** Executes zero rotations. On sorted or reverse-sorted input, insertion naturally degrades to a degenerate linked-list chain of height $N$.

### 4.3 Theoretical vs. Empirical Complexity

| Operation | AVL Tree (Theory) | BST (Theory, Avg) | BST (Theory, Worst-Case) | Measured AVL ($N=5000$, Sorted) | Measured BST ($N=5000$, Sorted) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Tree Height** | $O(\log n) \le 1.44 \log_2 n$ | $O(\log n)$ | $O(n)$ | **13** | **5,000** |
| **Insertion** | $O(\log n)$ | $O(\log n)$ | $O(n)$ | **85.33 ms** | **12,166.69 ms** (~142x slower) |
| **Search** | $O(\log n)$ | $O(\log n)$ | $O(n)$ | **0.119 ms** | **0.116 ms** (Random) |
| **Conflict Query**| $O(\log n + k)$ | $O(\log n + k)$ | $O(n + k)$ | **0.394 ms** | **18.058 ms** (~45x slower) |
| **Deletion** | $O(\log n)$ | $O(\log n)$ | $O(n)$ | **0.259 ms** | **46.971 ms** (~181x slower) |

---

## 5. Scheduling & Conflict-Detection Approach

1. **Interval Convention:** Half-open intervals $[start, end)$. Two events $[A, B)$ and $[C, D)$ overlap if and only if:
   $$\max(A, C) < \min(B, D)$$
   Adjacent events where one ends exactly when another begins ($B = C$) do not conflict.
2. **Rescheduling Workflow (Preview & Commit):**
   - **Preview (`POST /api/events/<id>/reschedule-preview`):** Evaluates the proposed time slot on a forked tree with the current event excluded (`ignore_id=event_id`), computes a Conflict Ripple Score via BFS, and suggests alternative slots.
   - **Commit (`POST /api/events/<id>/reschedule-commit`):** Validates input formats and `end > start`, re-checks conflict directly on the live tree excluding the event itself, and rejects with HTTP 409 if a conflict exists (unless `force: true`).
3. **Database and In-Memory Synchronization:**
   - Modifying operations (`add_event`, `update_event`, `delete_event`) commit to the SQLite transaction **before** in-memory data structures are mutated.
   - If SQLite encounters an error, the operation aborts and in-memory structures remain pristine.
4. **Concurrency Safety:**
   - Each user's in-memory data structures are guarded by an `RLock` on `UserEngine`.
   - Simultaneous requests attempting to claim the same exclusive time slot are serialized, preventing check-then-commit race conditions.

---

## 6. Installation and Setup

### 6.1 Prerequisites
- Python 3.10 or higher.
- Git.

### 6.2 Virtual Environment & Dependencies
```bash
# Clone the repository
git clone https://github.com/siddharth8107sk-maker/chronograph.git
cd chronograph

# Create and activate virtual environment
python -m venv .venv

# On Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate

# Install required packages
pip install -r requirements.txt
```

### 6.3 Database Initialization
The application initializes `chronograph.db` automatically on startup. To seed the demo college schedule:
```bash
python -c "import db; db.init_db()"
```

### 6.4 Running the Application
```bash
python app.py
```
Open your browser and visit:
```
http://127.0.0.1:5000
```

**Multi-Tenant College Demo Accounts:**
ChronoGraph features institutional multi-tenancy. Select or log in with any of the three pre-seeded college accounts (all passwords `Demo@1234`):

| College | Demo Email | Faculty Lead | Seeded Dataset |
| :--- | :--- | :--- | :--- |
| **Karunya Institute of Technology and Sciences** | `karunya@chronograph.app` (or `demo@chronograph.app`) | Prof. Sarah Jenkins | 20+ events, 2 waitlist items, CSE labs, Hackathon, Placement drives |
| **Vellore Institute of Technology** | `vit@chronograph.app` | Dr. Rajesh Kumar | 20 events, 2 waitlist items, Riviera fest, Gravitas hackathon, AWS drive |
| **PSG College of Arts and Science** | `psg@chronograph.app` | Dr. Ananya Iyer | 20 events, 2 waitlist items, Culturals, Science expo, FinTech labs |

> [!TIP]
> On the Sign In page, click any of the 3 college quick-login buttons to instantly authenticate into that institution's dashboard! Users registered under the same college share synchronized AVL trees, conflict ripple graphs, and waitlists.

---

## 7. Running Tests and Benchmarks

### 7.1 Running the Automated Test Suite
Execute the dedicated pytest suite:
```bash
pytest tests/ -v
```
All 29 tests cover:
- AVL rotations (LL, RR, LR, RL)
- Duplicate key ordering
- Leaf, single-child, and two-child deletions
- Height and balance invariants
- Boundary conditions and interval rules
- HTTP status codes (200, 201, 400, 404, 409)
- Concurrency race condition prevention
- College registration, multi-tenancy isolation, and cross-user shared schedules
- Pre-seeded multi-college demo account authentication and data isolation
- Custom campus venue creation, real-time sharing across peers of the same college, and cross-institution venue isolation

### 7.2 Running the Benchmarks
To execute the empirical AVL vs. BST benchmark suite:
```bash
python benchmark.py
```

---

## 8. Actual Empirical Benchmark Results

**Benchmark Environment:**
- **Platform:** Windows (Python 3.14.2 64-bit)
- **Timer:** `time.perf_counter()`
- **Statistic:** Median of 3 independent runs per data point

### 8.1 Random Distribution (Favorable BST Distribution)
```
     N |  AVL H  BST H | AVL Ins(ms) BST Ins(ms) | AVL Qry(ms) BST Qry(ms) | AVL Del(ms) BST Del(ms) | Rotations
-------------------------------------------------------------------------------------------------------------------
   100 |      8     12 |        0.71        0.45 |       0.049       0.052 |       0.129       0.093 |        68
   500 |     10     22 |        5.63        4.99 |       0.073       0.072 |       0.187       0.146 |       352
  1000 |     12     26 |       13.30        9.60 |       0.074       0.205 |       0.199       0.157 |       662
  2000 |     13     24 |       29.44       22.37 |       0.092       0.097 |       0.233       0.152 |      1395
  5000 |     15     30 |       91.25       64.42 |       0.119       0.116 |       0.283       0.201 |      3442
```

### 8.2 Sorted Ascending Input (Adversarial BST Distribution)
```
     N |  AVL H  BST H | AVL Ins(ms) BST Ins(ms) | AVL Qry(ms) BST Qry(ms) | AVL Del(ms) BST Del(ms) | Rotations
-------------------------------------------------------------------------------------------------------------------
   100 |      7    100 |        0.70        3.53 |       0.054       0.258 |       0.123       0.459 |        93
   500 |      9    500 |        8.20       99.33 |       0.072       1.384 |       0.173       3.388 |       491
  1000 |     10   1000 |       15.09      443.98 |       0.098       3.246 |       0.205       9.145 |       990
  2000 |     11   2000 |       30.65     1760.75 |       0.095       6.379 |       0.222      17.795 |      1989
  5000 |     13   5000 |       85.33    12166.69 |       0.394      18.058 |       0.259      46.971 |      4987
```

### 8.3 Reverse-Sorted Descending Input (Adversarial BST Distribution)
```
     N |  AVL H  BST H | AVL Ins(ms) BST Ins(ms) | AVL Qry(ms) BST Qry(ms) | AVL Del(ms) BST Del(ms) | Rotations
-------------------------------------------------------------------------------------------------------------------
   100 |      7    100 |        0.70        3.80 |       0.067       0.280 |       0.142       0.700 |        93
   500 |      9    500 |        5.43      106.39 |       0.149       1.857 |       0.205       3.774 |       491
  1000 |     10   1000 |       15.82      454.35 |       0.113       3.309 |       0.231       9.216 |       990
  2000 |     11   2000 |       29.95     1754.19 |       0.146       7.010 |       0.248      17.719 |      1989
  5000 |     13   5000 |       83.86    12296.77 |       0.150      19.371 |       0.350      48.173 |      4987
```

**Key Benchmark Takeaways:**
1. **Height Guarantee:** Under sorted or reverse-sorted input, the BST height escalates linearly ($Height = N$), while the AVL height remains bounded by $1.44 \log_2(5000) = 13$.
2. **Insertion Scalability:** At $N=5000$ sorted items, BST insertion takes **12.16 seconds**, while AVL insertion completes in **85.33 milliseconds** — a speedup exceeding **140x**.
3. **Query & Deletion Advantage:** On degenerate trees, AVL conflict queries and deletions run orders of magnitude faster due to logarithmic depth pruning.
4. **Random Favorable Case:** When keys arrive in random order, BST insertion overhead is slightly lower (64 ms vs 91 ms) because it skips balance-factor calculations and rotations. This aligns with academic theory: AVL trees pay a small rotation constant factor to guarantee immunity against catastrophic worst-case scenarios.

---

## 9. API Reference & Examples

### 9.1 Create Event
- **Endpoint:** `POST /api/events`
- **Request Body:**
```json
{
  "name": "Distributed Systems Lecture",
  "date": "2026-10-26",
  "start_time": "14:00",
  "end_time": "15:30",
  "venue": "CSE Lab 2",
  "organizer": "Department of Computer Science",
  "priority": 2
}
```
- **Response (201 Created):**
```json
{
  "ok": true,
  "data": {
    "id": "EVT-4821",
    "name": "Distributed Systems Lecture",
    "date": "2026-10-26",
    "start_time": "14:00",
    "end_time": "15:30",
    "start_minute": 424680,
    "end_minute": 424770,
    "venue": "CSE Lab 2",
    "organizer": "Department of Computer Science",
    "priority": 2
  },
  "error": null
}
```

### 9.2 Reschedule Preview
- **Endpoint:** `POST /api/events/<event_id>/reschedule-preview`
- **Request Body:**
```json
{
  "date": "2026-10-27",
  "start_time": "10:00",
  "end_time": "11:30"
}
```
- **Response (200 OK):**
```json
{
  "ok": true,
  "data": {
    "event_id": "EVT-1001",
    "proposed": { "date": "2026-10-27", "start_time": "10:00", "end_time": "11:30" },
    "conflicts": [],
    "ripple_score": 0,
    "alternative_slots": [
      { "date": "2026-10-27", "start_time": "08:00", "end_time": "09:30", "ripple_score": 0, "displacement": 120 }
    ]
  },
  "error": null
}
```

### 9.3 Reschedule Commit
- **Endpoint:** `POST /api/events/<event_id>/reschedule-commit`
- **Request Body:**
```json
{
  "date": "2026-10-27",
  "start_time": "10:00",
  "end_time": "11:30",
  "force": false
}
```
- **Conflict Response (409 Conflict):**
```json
{
  "ok": false,
  "data": {
    "conflicts": [{ "id": "EVT-1005", "name": "Inter-Department Quiz Prelims" }],
    "suggestions": [{ "date": "2026-10-27", "start_time": "11:30", "end_time": "13:00" }]
  },
  "error": "Conflict detected with 1 event(s)"
}
```

### 9.4 Campus Venue Management
- **List Venues (`GET /api/venues`):** Returns all default and custom campus venues registered for the authenticated user's institution.
- **Add Venue (`POST /api/venues`):**
```json
{
  "name": "IoT Innovation Center"
}
```
- **Response (201 Created):**
```json
{
  "ok": true,
  "data": {
    "name": "IoT Innovation Center",
    "college": "Karunya Institute of Technology and Sciences",
    "is_custom": true
  },
  "error": null
}
```

### 9.5 Empirical Benchmark Suite
- **Endpoint:** `GET /api/benchmark?suite=tree|search|sort|slot`
- **Optional Fresh Evaluation:** Append `&fresh=1` to re-execute empirical evaluations dynamically on the server.
- **Response (200 OK):**
```json
{
  "ok": true,
  "data": {
    "suite": "tree",
    "results": {
      "sizes": [100, 500, 1000, 2000, 5000],
      "patterns": ["random", "sorted", "reverse_sorted", "zigzag"],
      "data": { ... }
    },
    "conclusion": "On adversarial sorted input, the BST degraded to height 5000 (O(n)), while the persistent AVL tree maintained strict logarithmic height (13)..."
  },
  "error": null
}
```

---

## 10. Known Limitations

1. **In-Memory Scale:** In-memory AVL trees and version stacks are loaded per institution (`CollegeEngine`). For massive datasets exceeding tens of millions of records per institution, paginated disk-backed B-trees would be preferred over in-memory AVL nodes.
2. **Soft Real-Time Scope:** Execution runs within the Python runtime and Flask WSGI loop. While response times are sub-millisecond, it does not guarantee hard real-time hardware execution deadlines.
