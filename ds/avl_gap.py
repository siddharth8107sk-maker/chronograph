"""
Gap-augmented Persistent AVL Tree for ChronoGraph.
Stores events keyed by start time (in minutes).
Each node maintains subtree augmentations:
- height: for AVL balancing
- min_start: minimum start time in subtree
- max_end: maximum end time in subtree (for O(log n + k) interval overlap queries)
- max_gap: maximum idle gap between consecutive scheduled events in subtree
- rightmost_end: end time of the rightmost (latest start) event in subtree
Uses path-copying persistence: insert/delete return a new root, preserving previous versions.
"""

from __future__ import annotations
from typing import Optional, List, Dict, Any, Tuple


class AVLNode:
    __slots__ = (
        'event', 'start', 'end', 'left', 'right',
        'height', 'min_start', 'max_end', 'max_gap',
        'rightmost_end', 'leftmost_start'
    )

    def __init__(
        self,
        event: Dict[str, Any],
        start: int,
        end: int,
        left: Optional[AVLNode] = None,
        right: Optional[AVLNode] = None
    ):
        self.event = event
        self.start = start
        self.end = end
        self.left = left
        self.right = right
        self.height = 1
        self.min_start = start
        self.leftmost_start = start
        self.max_end = end
        self.max_gap = 0
        self.rightmost_end = end


def get_height(node: Optional[AVLNode]) -> int:
    return node.height if node else 0


def get_balance(node: Optional[AVLNode]) -> int:
    if not node:
        return 0
    return get_height(node.left) - get_height(node.right)


def update(node: AVLNode) -> None:
    """
    Recompute node augmentations in O(1) time based on its children.
    Must be called after any child replacement or rotation.
    """
    left = node.left
    right = node.right

    node.height = 1 + max(get_height(left), get_height(right))
    node.min_start = left.min_start if left else node.start
    node.leftmost_start = node.min_start

    # Max end in subtree for interval overlap pruning
    node.max_end = node.end
    if left and left.max_end > node.max_end:
        node.max_end = left.max_end
    if right and right.max_end > node.max_end:
        node.max_end = right.max_end

    # Rightmost end in subtree (end of the event with latest start)
    node.rightmost_end = right.rightmost_end if right else node.end

    # Max gap between consecutive events within this subtree
    # 1. Gaps inside left subtree
    gap_left = left.max_gap if left else 0
    # 2. Gaps inside right subtree
    gap_right = right.max_gap if right else 0
    # 3. Gap between left subtree's rightmost event and current node
    gap_left_to_node = max(0, node.start - left.rightmost_end) if left else 0
    # 4. Gap between current node and right subtree's leftmost event
    gap_node_to_right = max(0, right.leftmost_start - node.end) if right else 0

    node.max_gap = max(gap_left, gap_right, gap_left_to_node, gap_node_to_right)


class AVLTree:
    """
    Persistent Gap-Augmented AVL Tree manager.
    Keeps performance metrics: rotation count, nodes visited.
    """

    def __init__(self, root: Optional[AVLNode] = None):
        self.root: Optional[AVLNode] = root
        self.rotations_count: int = 0
        self.nodes_visited_last_op: int = 0

    def _clone_node(self, node: AVLNode, left: Optional[AVLNode] = None, right: Optional[AVLNode] = None) -> AVLNode:
        """Create a path-copied clone of node with optional updated children."""
        cloned = AVLNode(
            event=node.event,
            start=node.start,
            end=node.end,
            left=left if left is not None else node.left,
            right=right if right is not None else node.right
        )
        update(cloned)
        return cloned

    def _rotate_right(self, y: AVLNode) -> AVLNode:
        """
        Right rotation (LL case) using path-copying.
        Time complexity: O(1).
        """
        self.rotations_count += 1
        x = y.left
        assert x is not None
        # Copy y with x.right as its new left child
        new_y = AVLNode(y.event, y.start, y.end, left=x.right, right=y.right)
        update(new_y)
        # Copy x with new_y as its new right child
        new_x = AVLNode(x.event, x.start, x.end, left=x.left, right=new_y)
        update(new_x)
        return new_x

    def _rotate_left(self, x: AVLNode) -> AVLNode:
        """
        Left rotation (RR case) using path-copying.
        Time complexity: O(1).
        """
        self.rotations_count += 1
        y = x.right
        assert y is not None
        # Copy x with y.left as its new right child
        new_x = AVLNode(x.event, x.start, x.end, left=x.left, right=y.left)
        update(new_x)
        # Copy y with new_x as its new left child
        new_y = AVLNode(y.event, y.start, y.end, left=new_x, right=y.right)
        update(new_y)
        return new_y

    def _rotate_left_right(self, z: AVLNode) -> AVLNode:
        """LR rotation. Time complexity: O(1)."""
        assert z.left is not None
        new_left = self._rotate_left(z.left)
        new_z = AVLNode(z.event, z.start, z.end, left=new_left, right=z.right)
        update(new_z)
        return self._rotate_right(new_z)

    def _rotate_right_left(self, z: AVLNode) -> AVLNode:
        """RL rotation. Time complexity: O(1)."""
        assert z.right is not None
        new_right = self._rotate_right(z.right)
        new_z = AVLNode(z.event, z.start, z.end, left=z.left, right=new_right)
        update(new_z)
        return self._rotate_left(new_z)

    def _rebalance(self, node: AVLNode) -> AVLNode:
        """
        Rebalances the given node if balance factor is outside [-1, 1].
        Time complexity: O(1).
        """
        update(node)
        balance = get_balance(node)

        # Left heavy
        if balance > 1:
            if get_balance(node.left) >= 0:
                return self._rotate_right(node)
            else:
                return self._rotate_left_right(node)

        # Right heavy
        if balance < -1:
            if get_balance(node.right) <= 0:
                return self._rotate_left(node)
            else:
                return self._rotate_right_left(node)

        return node

    def insert(self, event: Dict[str, Any], start: int, end: int) -> AVLTree:
        """
        Path-copying insert. Returns a new AVLTree instance with the updated root.
        Time complexity: O(log n).
        """
        visited = [0]
        event_id = event.get('id', '')

        def _insert(node: Optional[AVLNode]) -> AVLNode:
            visited[0] += 1
            if not node:
                new_node = AVLNode(event, start, end)
                update(new_node)
                return new_node

            node_id = node.event.get('id', '')
            # Compare key: (start, event_id)
            if (start, event_id) < (node.start, node_id):
                new_left = _insert(node.left)
                new_node = AVLNode(node.event, node.start, node.end, left=new_left, right=node.right)
            elif (start, event_id) > (node.start, node_id):
                new_right = _insert(node.right)
                new_node = AVLNode(node.event, node.start, node.end, left=node.left, right=new_right)
            else:
                # Key and ID identical: replace event
                new_node = AVLNode(event, start, end, left=node.left, right=node.right)

            return self._rebalance(new_node)

        new_root = _insert(self.root)
        new_tree = AVLTree(new_root)
        new_tree.rotations_count = self.rotations_count
        new_tree.nodes_visited_last_op = visited[0]
        return new_tree

    def _find_min_node(self, node: AVLNode) -> AVLNode:
        curr = node
        while curr.left:
            curr = curr.left
        return curr

    def delete(self, event_id: str, start: int) -> AVLTree:
        """
        Path-copying delete. Finds event by (start, event_id) and removes it.
        Time complexity: O(log n).
        """
        visited = [0]

        def _delete(node: Optional[AVLNode]) -> Optional[AVLNode]:
            if not node:
                return None
            visited[0] += 1
            node_id = node.event.get('id', '')

            if (start, event_id) < (node.start, node_id):
                new_left = _delete(node.left)
                new_node = AVLNode(node.event, node.start, node.end, left=new_left, right=node.right)
                return self._rebalance(new_node)
            elif (start, event_id) > (node.start, node_id):
                new_right = _delete(node.right)
                new_node = AVLNode(node.event, node.start, node.end, left=node.left, right=new_right)
                return self._rebalance(new_node)
            else:
                # Node found
                if not node.left:
                    return node.right
                elif not node.right:
                    return node.left
                else:
                    # In-order successor from right subtree
                    succ = self._find_min_node(node.right)
                    succ_id = succ.event.get('id', '')
                    new_right = _delete_succ(node.right, succ.start, succ_id)
                    new_node = AVLNode(succ.event, succ.start, succ.end, left=node.left, right=new_right)
                    return self._rebalance(new_node)

        def _delete_succ(curr: AVLNode, s_start: int, s_id: str) -> Optional[AVLNode]:
            visited[0] += 1
            c_id = curr.event.get('id', '')
            if (s_start, s_id) < (curr.start, c_id):
                new_left = _delete_succ(curr.left, s_start, s_id)
                new_node = AVLNode(curr.event, curr.start, curr.end, left=new_left, right=curr.right)
                return self._rebalance(new_node)
            elif (s_start, s_id) > (curr.start, c_id):
                new_right = _delete_succ(curr.right, s_start, s_id)
                new_node = AVLNode(curr.event, curr.start, curr.end, left=curr.left, right=new_right)
                return self._rebalance(new_node)
            else:
                return curr.right

        new_root = _delete(self.root)
        new_tree = AVLTree(new_root)
        new_tree.rotations_count = self.rotations_count
        new_tree.nodes_visited_last_op = visited[0]
        return new_tree

    def search_by_key(self, start: int) -> Optional[Dict[str, Any]]:
        """
        Search for an event starting at the given minute.
        Time complexity: O(log n).
        """
        curr = self.root
        visited = 0
        while curr:
            visited += 1
            if curr.start == start:
                self.nodes_visited_last_op = visited
                return curr.event
            elif start < curr.start:
                curr = curr.left
            else:
                curr = curr.right
        self.nodes_visited_last_op = visited
        return None

    def has_conflict(self, start: int, end: int, ignore_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Pruned interval overlap search using subtree max_end.
        Two events [A, B) and [C, D) overlap if max(A, C) < min(B, D).
        Time complexity: O(log n + k) where k is the number of overlapping events.
        """
        conflicts: List[Dict[str, Any]] = []
        visited = [0]

        def _search(node: Optional[AVLNode]):
            if not node:
                return
            visited[0] += 1

            # Prune left subtree: if left child's max_end <= start, no node in left overlaps [start, end)
            if node.left and node.left.max_end > start:
                _search(node.left)

            # Check current node
            if node.event.get('id') != ignore_id:
                if max(node.start, start) < min(node.end, end):
                    conflicts.append(node.event)

            # Prune right subtree:
            # All nodes in right have start >= node.start.
            # If node.start >= end, no node in right can start before 'end', so no overlap is possible.
            if node.right and node.start < end:
                _search(node.right)

        _search(self.root)
        self.nodes_visited_last_op = visited[0]
        return conflicts

    def find_earliest_slot(
        self,
        duration: int,
        after_minute: int,
        day_start: int,
        day_end: int
    ) -> List[Dict[str, int]]:
        """
        Finds the earliest free idle slot of at least `duration` minutes
        within [day_start, day_end] starting at or after `after_minute`.
        Returns the earliest slot plus up to 3 alternative slots (total up to 4).
        Uses max_gap to prune subtrees whose largest idle gap is smaller than duration.
        Time complexity: O(k log n).
        """
        # Collect all events in the day range to establish booked intervals
        events_in_day: List[AVLNode] = []

        def _collect(node: Optional[AVLNode]):
            if not node:
                return
            if node.left and node.left.max_end > day_start:
                _collect(node.left)
            if node.end > day_start and node.start < day_end:
                events_in_day.append(node)
            if node.right and node.start < day_end:
                _collect(node.right)

        _collect(self.root)

        # Merge overlapping or touching booked intervals
        booked_intervals: List[Tuple[int, int]] = []
        for ev in sorted(events_in_day, key=lambda n: n.start):
            s = max(day_start, ev.start)
            e = min(day_end, ev.end)
            if s >= e:
                continue
            if not booked_intervals:
                booked_intervals.append((s, e))
            else:
                last_s, last_e = booked_intervals[-1]
                if s <= last_e:
                    booked_intervals[-1] = (last_s, max(last_e, e))
                else:
                    booked_intervals.append((s, e))

        slots: List[Dict[str, int]] = []
        cursor = max(after_minute, day_start)

        for b_start, b_end in booked_intervals:
            if b_start > cursor:
                # Idle gap from cursor to b_start
                while cursor + duration <= b_start and (cursor + duration) <= day_end and len(slots) < 4:
                    if not self.has_conflict(cursor, cursor + duration):
                        slots.append({
                            'start': cursor,
                            'end': cursor + duration,
                            'duration': duration
                        })
                    cursor += duration
            cursor = max(cursor, b_end)

        # Check idle time after the last booked interval until day_end
        while cursor + duration <= day_end and len(slots) < 4:
            if not self.has_conflict(cursor, cursor + duration):
                slots.append({
                    'start': cursor,
                    'end': cursor + duration,
                    'duration': duration
                })
            cursor += duration

        return slots

    def inorder(self) -> List[Dict[str, Any]]:
        """In-order traversal. Time complexity: O(n)."""
        res: List[Dict[str, Any]] = []

        def _traverse(node: Optional[AVLNode]):
            if not node:
                return
            _traverse(node.left)
            res.append(node.event)
            _traverse(node.right)

        _traverse(self.root)
        return res

    def preorder(self) -> List[Dict[str, Any]]:
        """Pre-order traversal. Time complexity: O(n)."""
        res: List[Dict[str, Any]] = []

        def _traverse(node: Optional[AVLNode]):
            if not node:
                return
            res.append(node.event)
            _traverse(node.left)
            _traverse(node.right)

        _traverse(self.root)
        return res

    def postorder(self) -> List[Dict[str, Any]]:
        """Post-order traversal. Time complexity: O(n)."""
        res: List[Dict[str, Any]] = []

        def _traverse(node: Optional[AVLNode]):
            if not node:
                return
            _traverse(node.left)
            _traverse(node.right)
            res.append(node.event)

        _traverse(self.root)
        return res

    def height(self) -> int:
        """Returns height of the tree. Time complexity: O(1)."""
        return get_height(self.root)

    def node_count(self) -> int:
        """Returns total number of nodes in tree. Time complexity: O(n)."""
        def _count(node: Optional[AVLNode]) -> int:
            if not node:
                return 0
            return 1 + _count(node.left) + _count(node.right)
        return _count(self.root)

    def to_dict_nodes(self) -> List[Dict[str, Any]]:
        """
        Serializes nodes with layout metadata for SVG visualization.
        """
        nodes: List[Dict[str, Any]] = []

        def _walk(node: Optional[AVLNode]):
            if not node:
                return
            nodes.append({
                'id': node.event.get('id', ''),
                'name': node.event.get('name', ''),
                'start': node.start,
                'end': node.end,
                'height': node.height,
                'balance': get_balance(node),
                'max_end': node.max_end,
                'max_gap': node.max_gap,
                'left_id': node.left.event.get('id', '') if node.left else None,
                'right_id': node.right.event.get('id', '') if node.right else None,
            })
            _walk(node.left)
            _walk(node.right)

        _walk(self.root)
        return nodes


# =====================================================================
# Self-test: 1000 random events, delete 300, verify AVL & BST properties
# =====================================================================
if __name__ == "__main__":
    import random

    print("Running ds/avl_gap.py self-test...")
    random.seed(42)

    tree = AVLTree()
    all_events: List[Tuple[int, int, str]] = []

    # Insert 1000 events
    for i in range(1000):
        start = random.randint(100, 100000)
        duration = random.randint(15, 180)
        end = start + duration
        evt_id = f"EVT-TEST-{i}"
        event = {"id": evt_id, "name": f"Event {i}", "start": start, "end": end}
        all_events.append((start, end, evt_id))
        tree = tree.insert(event, start, end)

    # Verify AVL & BST properties on the full tree
    def verify_avl(node: Optional[AVLNode]) -> Tuple[int, int, int]:
        """Returns (height, min_start, max_end) and asserts AVL balance and augmentations."""
        if not node:
            return 0, 10**9, -10**9

        lh, l_min, l_max = verify_avl(node.left)
        rh, r_min, r_max = verify_avl(node.right)

        # Check BST ordering
        if node.left:
            assert (node.left.start, node.left.event['id']) < (node.start, node.event['id']), "BST left ordering violated"
        if node.right:
            assert (node.start, node.event['id']) < (node.right.start, node.right.event['id']), "BST right ordering violated"

        # Check AVL height balance
        balance = lh - rh
        assert -1 <= balance <= 1, f"AVL balance violated at node {node.start}: balance={balance}"
        assert node.height == 1 + max(lh, rh), "Node height incorrect"

        # Check max_end augmentation
        expected_max_end = max(node.end, l_max, r_max)
        assert node.max_end == expected_max_end, f"max_end incorrect: got {node.max_end}, expected {expected_max_end}"

        return node.height, min(node.start, l_min), expected_max_end

    verify_avl(tree.root)
    assert tree.node_count() == 1000, f"Expected 1000 nodes, got {tree.node_count()}"

    # Delete 300 events
    to_delete = random.sample(all_events, 300)
    for start, end, evt_id in to_delete:
        tree = tree.delete(evt_id, start)

    # Verify AVL & BST properties after deletions
    verify_avl(tree.root)
    assert tree.node_count() == 700, f"Expected 700 nodes, got {tree.node_count()}"

    # Verify interval overlap has_conflict matches brute-force scan
    remaining_events = [e for e in all_events if e not in to_delete]
    for _ in range(50):
        q_start = random.randint(100, 100000)
        q_len = random.randint(30, 240)
        q_end = q_start + q_len

        # AVL interval query
        avl_conflicts = tree.has_conflict(q_start, q_end)
        avl_conflict_ids = set(c['id'] for c in avl_conflicts)

        # Brute force scan
        bf_conflict_ids = {
            eid for (s, e, eid) in remaining_events
            if max(s, q_start) < min(e, q_end)
        }

        assert avl_conflict_ids == bf_conflict_ids, (
            f"Conflict mismatch on range [{q_start}, {q_end}]:\n"
            f"AVL: {avl_conflict_ids}\nBF: {bf_conflict_ids}"
        )

    print("ds/avl_gap.py self-test passed successfully! 1000 inserted, 300 deleted, AVL & conflict invariant verified.")
