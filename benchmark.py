"""
Benchmark Suite for ChronoGraph (25CS306 MP-01).
Compares:
1. Tree Suite: AVL vs BST (height, insert time, search time, conflict-query time, rotations)
   across patterns: random, sorted ascending, adversarial zig-zag for sizes [100, 500, 1000, 2000, 5000].
2. Search Suite: Hash table vs AVL search vs Binary search vs Interpolation search vs Linear search.
3. Sort Suite: Insertion vs Bubble vs Selection vs Merge sort across sizes [100, 500, 1000, 2000].
4. Slot Suite: AVL Gap Pruned earliest slot search vs Naive Linear Scan.
"""

from __future__ import annotations
import sys
import time
import random
from typing import Dict, Any, List

sys.setrecursionlimit(30000)

from ds.avl_gap import AVLTree
from ds.bst_baseline import BSTBaseline
from ds.hash_index import EventHashTable
from ds.sorting import insertion_sort, bubble_sort, selection_sort, merge_sort
from ds.searching import linear_search, binary_search_iterative, interpolation_search


def generate_dataset(size: int, pattern: str) -> List[Dict[str, Any]]:
    """Generates synthetic event datasets of given size and pattern."""
    events = []
    if pattern == "sorted":
        # Strictly ascending start minutes
        base = 1000
        for i in range(size):
            start = base + i * 30
            events.append({
                'id': f"EVT-B-{i}",
                'name': f"Bench Event {i}",
                'start': start,
                'end': start + 25
            })
    elif pattern == "zigzag":
        # Adversarial alternating min and max
        low = 1000
        high = 1000 + size * 60
        left_idx = low
        right_idx = high
        for i in range(size):
            if i % 2 == 0:
                start = left_idx
                left_idx += 30
            else:
                start = right_idx
                right_idx -= 30
            events.append({
                'id': f"EVT-B-{i}",
                'name': f"Bench Event {i}",
                'start': start,
                'end': start + 20
            })
    else:  # random
        rng = random.Random(42 + size)
        chosen = set()
        for i in range(size):
            start = rng.randint(100, 500000)
            while start in chosen:
                start = rng.randint(100, 500000)
            chosen.add(start)
            dur = rng.randint(15, 90)
            events.append({
                'id': f"EVT-B-{i}",
                'name': f"Bench Event {i}",
                'start': start,
                'end': start + dur
            })
    return events


def run_tree_benchmark(sizes: List[int] = [100, 500, 1000, 2000, 5000]) -> Dict[str, Any]:
    patterns = ["random", "sorted", "zigzag"]
    results: Dict[str, Any] = {
        'sizes': sizes,
        'patterns': patterns,
        'data': {}
    }

    for p in patterns:
        p_res = {
            'avl_height': [],
            'bst_height': [],
            'avl_insert_ms': [],
            'bst_insert_ms': [],
            'avl_search_ms': [],
            'bst_search_ms': [],
            'avl_conflict_ms': [],
            'bst_conflict_ms': [],
            'avl_rotations': []
        }
        for n in sizes:
            events = generate_dataset(n, p)

            # 1. AVL Insertion
            avl = AVLTree()
            t0 = time.perf_counter()
            for ev in events:
                avl = avl.insert(ev, ev['start'], ev['end'])
            avl_ins_time = (time.perf_counter() - t0) * 1000

            # 2. BST Insertion
            bst = BSTBaseline()
            t0 = time.perf_counter()
            for ev in events:
                bst = bst.insert(ev, ev['start'], ev['end'])
            bst_ins_time = (time.perf_counter() - t0) * 1000

            # Sample searches
            sample_keys = [events[i]['start'] for i in range(0, n, max(1, n // 20))]
            t0 = time.perf_counter()
            for k in sample_keys:
                avl.search_by_key(k)
            avl_search_time = (time.perf_counter() - t0) * 1000

            t0 = time.perf_counter()
            for k in sample_keys:
                bst.search_by_key(k)
            bst_search_time = (time.perf_counter() - t0) * 1000

            # Sample conflict queries
            conflict_ranges = [(events[i]['start'] - 10, events[i]['end'] + 10) for i in range(0, n, max(1, n // 20))]
            t0 = time.perf_counter()
            for s, e in conflict_ranges:
                avl.has_conflict(s, e)
            avl_conf_time = (time.perf_counter() - t0) * 1000

            t0 = time.perf_counter()
            for s, e in conflict_ranges:
                bst.has_conflict(s, e)
            bst_conf_time = (time.perf_counter() - t0) * 1000

            p_res['avl_height'].append(avl.height())
            p_res['bst_height'].append(bst.height())
            p_res['avl_insert_ms'].append(round(avl_ins_time, 2))
            p_res['bst_insert_ms'].append(round(bst_ins_time, 2))
            p_res['avl_search_ms'].append(round(avl_search_time, 3))
            p_res['bst_search_ms'].append(round(bst_search_time, 3))
            p_res['avl_conflict_ms'].append(round(avl_conf_time, 3))
            p_res['bst_conflict_ms'].append(round(bst_conf_time, 3))
            p_res['avl_rotations'].append(avl.rotations_count)

        results['data'][p] = p_res

    return results


def run_search_benchmark(sizes: List[int] = [500, 1000, 2500, 5000]) -> Dict[str, Any]:
    results = {
        'sizes': sizes,
        'hash_lookup_ms': [],
        'avl_search_ms': [],
        'binary_search_ms': [],
        'interpolation_search_ms': [],
        'linear_search_ms': []
    }

    for n in sizes:
        events = generate_dataset(n, "sorted")
        arr = [e['start'] for e in events]
        target = arr[len(arr) * 3 // 4]

        # Hash Table
        ht = EventHashTable(n * 2)
        for ev in events:
            ht.put(ev['id'], ev)

        # AVL
        avl = AVLTree()
        for ev in events:
            avl = avl.insert(ev, ev['start'], ev['end'])

        reps = 200

        # Linear search
        t0 = time.perf_counter()
        for _ in range(reps):
            linear_search(arr, target)
        results['linear_search_ms'].append(round((time.perf_counter() - t0) * 1000 / reps, 5))

        # Binary search
        t0 = time.perf_counter()
        for _ in range(reps):
            binary_search_iterative(arr, target)
        results['binary_search_ms'].append(round((time.perf_counter() - t0) * 1000 / reps, 5))

        # Interpolation search
        t0 = time.perf_counter()
        for _ in range(reps):
            interpolation_search(arr, target)
        results['interpolation_search_ms'].append(round((time.perf_counter() - t0) * 1000 / reps, 5))

        # AVL search
        t0 = time.perf_counter()
        for _ in range(reps):
            avl.search_by_key(target)
        results['avl_search_ms'].append(round((time.perf_counter() - t0) * 1000 / reps, 5))

        # Hash lookup
        target_id = events[len(arr) * 3 // 4]['id']
        t0 = time.perf_counter()
        for _ in range(reps):
            ht.get(target_id)
        results['hash_lookup_ms'].append(round((time.perf_counter() - t0) * 1000 / reps, 5))

    return results


def run_sort_benchmark(sizes: List[int] = [100, 500, 1000, 2000]) -> Dict[str, Any]:
    results = {
        'sizes': sizes,
        'insertion_sort_ms': [],
        'bubble_sort_ms': [],
        'selection_sort_ms': [],
        'merge_sort_ms': []
    }

    for n in sizes:
        rng = random.Random(101 + n)
        arr = [rng.randint(1, 100000) for _ in range(n)]

        ins = insertion_sort(arr)
        results['insertion_sort_ms'].append(ins['time_ms'])

        bub = bubble_sort(arr)
        results['bubble_sort_ms'].append(bub['time_ms'])

        sel = selection_sort(arr)
        results['selection_sort_ms'].append(sel['time_ms'])

        mrg = merge_sort(arr)
        results['merge_sort_ms'].append(mrg['time_ms'])

    return results


def run_slot_benchmark(sizes: List[int] = [100, 500, 1000, 2000]) -> Dict[str, Any]:
    results = {
        'sizes': sizes,
        'avl_gap_pruned_ms': [],
        'linear_scan_ms': []
    }

    for n in sizes:
        events = generate_dataset(n, "random")
        avl = AVLTree()
        for ev in events:
            avl = avl.insert(ev, ev['start'], ev['end'])

        duration = 60
        day_start = 1000
        day_end = 500000
        reps = 50

        # AVL slot search
        t0 = time.perf_counter()
        for _ in range(reps):
            avl.find_earliest_slot(duration, day_start, day_start, day_end)
        results['avl_gap_pruned_ms'].append(round((time.perf_counter() - t0) * 1000 / reps, 4))

        # Naive linear scan: test every 15-minute slot from day_start to day_end against all events
        t0 = time.perf_counter()
        for _ in range(reps):
            slot = day_start
            found = False
            while slot + duration <= day_start + 5000:
                conflict = False
                for ev in events[:min(len(events), 200)]:
                    if max(slot, ev['start']) < min(slot + duration, ev['end']):
                        conflict = True
                        break
                if not conflict:
                    found = True
                    break
                slot += 15
        results['linear_scan_ms'].append(round((time.perf_counter() - t0) * 1000 / reps, 4))

    return results


if __name__ == "__main__":
    print("Testing benchmark suites...")
    t_res = run_tree_benchmark([100, 500])
    print("Tree benchmark OK:", list(t_res['data'].keys()))
    s_res = run_sort_benchmark([100, 300])
    print("Sort benchmark OK:", s_res['merge_sort_ms'])
