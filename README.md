# ChronoGraph — Real-Time Event Scheduling System
**Course:** Data Structures and Algorithms (25CS306) — Micro-Project MP-01  
**Author:** Senior Full-Stack Engineering & DSA Implementation

---

## Architecture Overview
ChronoGraph is built on a persistent, gap-augmented AVL tree that maintains strict logarithmic height balance and augments every node with `max_end` (for $O(\log n + k)$ interval conflict queries) and `max_gap` (for fast subtree pruning during free-slot discovery). Unbalanced BST baselines, separate-chaining hash tables, trie autocomplete, min-heap priority waitlists, version stacks for multi-level undo/redo, and conflict-ripple graphs (BFS/DFS/Coloring/Topological Sort) are all written from scratch in pure Python without external data structure libraries.

```
chronograph/
  ├── app.py                  # Flask app, REST JSON API & per-user memory engine
  ├── db.py                   # SQLite schema, queries, PBKDF2 auth, seed data loader
  ├── benchmark.py            # Empirical benchmarks (AVL vs BST, searches, sorts, slots)
  ├── ds/
  │   ├── avl_gap.py          # Gap-augmented persistent AVL tree (interval + max_gap)
  │   ├── bst_baseline.py     # Unbalanced BST baseline
  │   ├── hash_index.py       # Separate-chaining hash table (0.75 load factor resize)
  │   ├── trie.py             # Event-name prefix autocomplete trie
  │   ├── heap.py             # Min-heap priority queue for waitlisted events
  │   ├── version_stack.py    # Stack-based undo/redo and FIFO request queue
  │   ├── ripple_graph.py     # Conflict graph: BFS ripple, DFS clusters, coloring, Kahn topo
  │   ├── sorting.py          # Insertion, bubble, selection, merge sort
  │   └── searching.py        # Linear, binary (iter/rec), interpolation search
  ├── templates/
  │   └── index.html          # Self-contained frontend (SVG tree/graph/benchmark charts)
  ├── requirements.txt        # Flask dependency
  └── README.md
```

---

## Quick Start Guide

### 1. Requirements & Setup
Make sure Python 3.10+ is installed:
```bash
pip install -r requirements.txt
```

### 2. Start the Server
```bash
python app.py
```
Open your browser and navigate to:
```
http://127.0.0.1:5000
```

### 3. Demo Account Credentials
- **Email:** `demo@chronograph.app`
- **Password:** `Demo@1234`
*(Pre-loaded with 40 realistic college events spanning two weeks, deliberate conflicts, and dependency chains).*

---

## Key Features & Algorithms
1. **Gap-Augmented Persistent AVL Tree (`ds/avl_gap.py`)**:
   - Path-copying persistence ensuring old tree roots remain immutable.
   - Rotations (LL, RR, LR, RL) recompute `height`, `min_start`, `max_end`, and `max_gap` in $O(1)$ time.
   - Interval conflict detection runs in $O(\log n + k)$ using subtree `max_end` pruning.
   - Earliest free slot discovery uses `max_gap` to bypass subtrees lacking sufficient idle gaps.
2. **Unbalanced BST Baseline (`ds/bst_baseline.py`)**:
   - Identical interface for empirical height and runtime comparisons.
3. **Conflict-Ripple Graph (`ds/ripple_graph.py`)**:
   - Models time overlaps, shared venue conflicts, shared organizer clashes, and prerequisite dependencies.
   - BFS generates layered blast radiuses and ripple impact scores.
   - Greedy graph coloring suggests conflict-free venue reassignments.
   - Kahn's algorithm validates topological execution order and flags cycles.
4. **Undo / Redo Version Stack (`ds/version_stack.py`)**:
   - Atomic state transitions across persistent tree roots, hash indexes, and waitlist states.
5. **Waitlist Auto-Placement (`ds/heap.py`)**:
   - Min-heap priority queue; deleting an event automatically attempts to fit the highest-priority waitlisted event into the freed gap.
6. **Built-in Benchmark Suite (`benchmark.py`)**:
   - Tests AVL vs BST across random, sorted, and zig-zag adversarial inputs up to $N = 5000$.
   - Interactive SVG line/bar charts with log-scale toggling and CSV dataset exports.
