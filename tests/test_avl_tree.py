"""
Unit Tests for Persistent Gap-Augmented AVL Tree (Course 25CS306 MP-01).
Tests AVL balancing invariants, all 4 rotation cases, deletion scenarios,
subtree augmentations, and interval conflict detection.
"""

import pytest
import random
from ds.avl_gap import AVLTree, AVLNode, get_balance, get_height


def is_avl_valid(node: AVLNode | None) -> tuple[bool, str]:
    """Recursively validates height, balance factor, BST ordering, and augmentations."""
    if not node:
        return True, ""

    left_h = get_height(node.left)
    right_h = get_height(node.right)
    expected_h = 1 + max(left_h, right_h)

    if node.height != expected_h:
        return False, f"Node {node.event.get('id')} height {node.height} != expected {expected_h}"

    bal = left_h - right_h
    if bal < -1 or bal > 1:
        return False, f"Node {node.event.get('id')} balance factor {bal} outside [-1, 1]"

    # BST ordering
    node_key = (node.start, node.event.get('id', ''))
    if node.left:
        left_key = (node.left.start, node.left.event.get('id', ''))
        if left_key >= node_key:
            return False, f"BST violation: left {left_key} >= node {node_key}"
    if node.right:
        right_key = (node.right.start, node.right.event.get('id', ''))
        if right_key <= node_key:
            return False, f"BST violation: right {right_key} <= node {node_key}"

    # Augmentation checks: max_end
    def get_subtree_events(n: AVLNode | None) -> list[AVLNode]:
        if not n:
            return []
        return get_subtree_events(n.left) + [n] + get_subtree_events(n.right)

    all_descendants = get_subtree_events(node)
    actual_max_end = max(d.end for d in all_descendants)
    actual_min_start = min(d.start for d in all_descendants)

    if node.max_end != actual_max_end:
        return False, f"max_end {node.max_end} != actual {actual_max_end}"
    if node.min_start != actual_min_start:
        return False, f"min_start {node.min_start} != actual {actual_min_start}"

    # Check children
    left_ok, left_msg = is_avl_valid(node.left)
    if not left_ok:
        return False, left_msg
    return is_avl_valid(node.right)


def test_ll_rotation():
    """Right rotation when left-heavy with left-heavy child."""
    tree = AVLTree()
    tree = tree.insert({'id': 'E3', 'name': '30'}, 30, 40)
    tree = tree.insert({'id': 'E2', 'name': '20'}, 20, 30)
    tree = tree.insert({'id': 'E1', 'name': '10'}, 10, 20)

    assert tree.height() == 2
    assert tree.root.start == 20
    assert tree.root.left.start == 10
    assert tree.root.right.start == 30
    valid, msg = is_avl_valid(tree.root)
    assert valid, msg


def test_rr_rotation():
    """Left rotation when right-heavy with right-heavy child."""
    tree = AVLTree()
    tree = tree.insert({'id': 'E1', 'name': '10'}, 10, 20)
    tree = tree.insert({'id': 'E2', 'name': '20'}, 20, 30)
    tree = tree.insert({'id': 'E3', 'name': '30'}, 30, 40)

    assert tree.height() == 2
    assert tree.root.start == 20
    assert tree.root.left.start == 10
    assert tree.root.right.start == 30
    valid, msg = is_avl_valid(tree.root)
    assert valid, msg


def test_lr_rotation():
    """Left-Right double rotation."""
    tree = AVLTree()
    tree = tree.insert({'id': 'E3', 'name': '30'}, 30, 40)
    tree = tree.insert({'id': 'E1', 'name': '10'}, 10, 20)
    tree = tree.insert({'id': 'E2', 'name': '20'}, 20, 30)

    assert tree.height() == 2
    assert tree.root.start == 20
    assert tree.root.left.start == 10
    assert tree.root.right.start == 30
    valid, msg = is_avl_valid(tree.root)
    assert valid, msg


def test_rl_rotation():
    """Right-Left double rotation."""
    tree = AVLTree()
    tree = tree.insert({'id': 'E1', 'name': '10'}, 10, 20)
    tree = tree.insert({'id': 'E3', 'name': '30'}, 30, 40)
    tree = tree.insert({'id': 'E2', 'name': '20'}, 20, 30)

    assert tree.height() == 2
    assert tree.root.start == 20
    assert tree.root.left.start == 10
    assert tree.root.right.start == 30
    valid, msg = is_avl_valid(tree.root)
    assert valid, msg


def test_duplicate_keys_composite_ordering():
    """Events starting at the exact same minute but with different IDs coexist properly."""
    tree = AVLTree()
    tree = tree.insert({'id': 'EVT-A', 'name': 'Lecture A'}, 100, 160)
    tree = tree.insert({'id': 'EVT-B', 'name': 'Lecture B'}, 100, 150)

    assert tree.node_count() == 2
    inorder_ids = [e['id'] for e in tree.inorder()]
    assert inorder_ids == ['EVT-A', 'EVT-B']
    valid, msg = is_avl_valid(tree.root)
    assert valid, msg


def test_deletion_leaf_node():
    """Deleting a leaf node."""
    tree = AVLTree()
    for s in [20, 10, 30]:
        tree = tree.insert({'id': f'E{s}', 'name': f'Event {s}'}, s, s + 5)

    tree = tree.delete('E10', 10)
    assert tree.node_count() == 2
    assert [e['id'] for e in tree.inorder()] == ['E20', 'E30']
    valid, msg = is_avl_valid(tree.root)
    assert valid, msg


def test_deletion_single_child_node():
    """Deleting a node with one child."""
    tree = AVLTree()
    for s in [30, 20, 40, 10]:
        tree = tree.insert({'id': f'E{s}', 'name': f'Event {s}'}, s, s + 5)

    # Node 20 has only left child 10
    tree = tree.delete('E20', 20)
    assert tree.node_count() == 3
    assert [e['id'] for e in tree.inorder()] == ['E10', 'E30', 'E40']
    valid, msg = is_avl_valid(tree.root)
    assert valid, msg


def test_deletion_two_children_node():
    """Deleting a node with two children (successor replacement)."""
    tree = AVLTree()
    for s in [50, 30, 70, 20, 40, 60, 80]:
        tree = tree.insert({'id': f'E{s}', 'name': f'Event {s}'}, s, s + 5)

    # Node 50 (root) has two children (30 and 70)
    tree = tree.delete('E50', 50)
    assert tree.node_count() == 6
    assert [e['id'] for e in tree.inorder()] == ['E20', 'E30', 'E40', 'E60', 'E70', 'E80']
    valid, msg = is_avl_valid(tree.root)
    assert valid, msg


def test_repeated_insertions_and_deletions_invariants():
    """Repeated random insertions and deletions maintain AVL invariant <= 1.44 log2(N)."""
    tree = AVLTree()
    rng = random.Random(42)
    events = []

    for i in range(200):
        start = rng.randint(100, 10000)
        end = start + rng.randint(10, 60)
        ev = {'id': f'EVT-{i}', 'name': f'Event {i}', 'start': start, 'end': end}
        events.append(ev)
        tree = tree.insert(ev, start, end)

    assert tree.node_count() == 200
    valid, msg = is_avl_valid(tree.root)
    assert valid, msg

    # Delete 80 events
    to_delete = rng.sample(events, 80)
    for ev in to_delete:
        tree = tree.delete(ev['id'], ev['start'])

    assert tree.node_count() == 120
    valid, msg = is_avl_valid(tree.root)
    assert valid, msg


def test_interval_half_open_boundaries():
    """Half-open intervals [A, B) and [B, C) must NOT conflict."""
    tree = AVLTree()
    tree = tree.insert({'id': 'E1', 'name': 'First'}, 100, 200)

    # Adjacent: [200, 300) touches boundary at 200
    assert tree.has_conflict(200, 300) == []

    # Adjacent: [0, 100) touches boundary at 100
    assert tree.has_conflict(0, 100) == []

    # Overlap by 1 minute: [199, 300) overlaps [100, 200)
    conf = tree.has_conflict(199, 300)
    assert len(conf) == 1
    assert conf[0]['id'] == 'E1'

    # Contained inside: [120, 180)
    assert len(tree.has_conflict(120, 180)) == 1

    # Completely enclosing: [50, 250)
    assert len(tree.has_conflict(50, 250)) == 1


def test_free_slot_queries_never_overlap():
    """Ensures find_earliest_slot never returns a slot that overlaps a blocking event."""
    tree = AVLTree()
    # Schedule several events
    tree = tree.insert({'id': 'E1'}, 600, 720)   # 10:00 - 12:00
    tree = tree.insert({'id': 'E2'}, 780, 900)   # 13:00 - 15:00
    tree = tree.insert({'id': 'E3'}, 1020, 1140) # 17:00 - 19:00

    slots = tree.find_earliest_slot(duration=60, after_minute=480, day_start=480, day_end=1200)
    assert len(slots) > 0
    for s in slots:
        assert not tree.has_conflict(s['start'], s['end']), f"Slot {s} overlapped an event!"
        assert s['start'] >= 480
        assert s['end'] <= 1200
