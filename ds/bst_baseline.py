"""
Unbalanced Binary Search Tree (Baseline for ChronoGraph).
Implements the exact same interface as AVLTree but without self-balancing rotations.
Used for performance comparison in the benchmark suite and visual comparison in the tree visualizer.
"""

from __future__ import annotations
from typing import Optional, List, Dict, Any, Tuple


class BSTNode:
    __slots__ = ('event', 'start', 'end', 'left', 'right', 'height', 'max_end', 'min_start')

    def __init__(
        self,
        event: Dict[str, Any],
        start: int,
        end: int,
        left: Optional[BSTNode] = None,
        right: Optional[BSTNode] = None
    ):
        self.event = event
        self.start = start
        self.end = end
        self.left = left
        self.right = right
        self.height = 1
        self.min_start = start
        self.max_end = end


def get_bst_height(node: Optional[BSTNode]) -> int:
    return node.height if node else 0


def update_bst(node: BSTNode) -> None:
    """Updates height, min_start, and max_end in O(1)."""
    left = node.left
    right = node.right
    node.height = 1 + max(get_bst_height(left), get_bst_height(right))
    node.min_start = left.min_start if left else node.start
    node.max_end = node.end
    if left and left.max_end > node.max_end:
        node.max_end = left.max_end
    if right and right.max_end > node.max_end:
        node.max_end = right.max_end


class BSTBaseline:
    """
    Unbalanced BST baseline matching the AVL interface.
    """

    def __init__(self, root: Optional[BSTNode] = None):
        self.root: Optional[BSTNode] = root
        self.rotations_count: int = 0
        self.nodes_visited_last_op: int = 0

    def insert(self, event: Dict[str, Any], start: int, end: int) -> BSTBaseline:
        """
        Inserts an event into the unbalanced BST.
        Time complexity: O(h) where h can be O(n) on skewed inputs.
        """
        visited = [0]
        event_id = event.get('id', '')

        def _insert(node: Optional[BSTNode]) -> BSTNode:
            visited[0] += 1
            if not node:
                new_node = BSTNode(event, start, end)
                update_bst(new_node)
                return new_node

            node_id = node.event.get('id', '')
            if (start, event_id) < (node.start, node_id):
                new_left = _insert(node.left)
                new_node = BSTNode(node.event, node.start, node.end, left=new_left, right=node.right)
            elif (start, event_id) > (node.start, node_id):
                new_right = _insert(node.right)
                new_node = BSTNode(node.event, node.start, node.end, left=node.left, right=new_right)
            else:
                new_node = BSTNode(event, start, end, left=node.left, right=node.right)

            update_bst(new_node)
            return new_node

        new_root = _insert(self.root)
        new_tree = BSTBaseline(new_root)
        new_tree.nodes_visited_last_op = visited[0]
        return new_tree

    def _find_min_node(self, node: BSTNode) -> BSTNode:
        curr = node
        while curr.left:
            curr = curr.left
        return curr

    def delete(self, event_id: str, start: int) -> BSTBaseline:
        """
        Deletes an event from the unbalanced BST.
        Time complexity: O(h).
        """
        visited = [0]

        def _delete(node: Optional[BSTNode]) -> Optional[BSTNode]:
            if not node:
                return None
            visited[0] += 1
            node_id = node.event.get('id', '')

            if (start, event_id) < (node.start, node_id):
                new_left = _delete(node.left)
                new_node = BSTNode(node.event, node.start, node.end, left=new_left, right=node.right)
                update_bst(new_node)
                return new_node
            elif (start, event_id) > (node.start, node_id):
                new_right = _delete(node.right)
                new_node = BSTNode(node.event, node.start, node.end, left=node.left, right=new_right)
                update_bst(new_node)
                return new_node
            else:
                if not node.left:
                    return node.right
                elif not node.right:
                    return node.left
                else:
                    succ = self._find_min_node(node.right)
                    succ_id = succ.event.get('id', '')
                    new_right = _delete_succ(node.right, succ.start, succ_id)
                    new_node = BSTNode(succ.event, succ.start, succ.end, left=node.left, right=new_right)
                    update_bst(new_node)
                    return new_node

        def _delete_succ(curr: BSTNode, s_start: int, s_id: str) -> Optional[BSTNode]:
            visited[0] += 1
            c_id = curr.event.get('id', '')
            if (s_start, s_id) < (curr.start, c_id):
                new_left = _delete_succ(curr.left, s_start, s_id)
                new_node = BSTNode(curr.event, curr.start, curr.end, left=new_left, right=curr.right)
                update_bst(new_node)
                return new_node
            elif (s_start, s_id) > (curr.start, c_id):
                new_right = _delete_succ(curr.right, s_start, s_id)
                new_node = BSTNode(curr.event, curr.start, curr.end, left=curr.left, right=new_right)
                update_bst(new_node)
                return new_node
            else:
                return curr.right

        new_root = _delete(self.root)
        new_tree = BSTBaseline(new_root)
        new_tree.nodes_visited_last_op = visited[0]
        return new_tree

    def search_by_key(self, start: int) -> Optional[Dict[str, Any]]:
        """Search by key. Time complexity: O(h)."""
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
        """Conflict search using max_end pruning. Time complexity: O(h + k)."""
        conflicts: List[Dict[str, Any]] = []
        visited = [0]

        def _search(node: Optional[BSTNode]):
            if not node:
                return
            visited[0] += 1
            if node.left and node.left.max_end > start:
                _search(node.left)
            if node.event.get('id') != ignore_id:
                if max(node.start, start) < min(node.end, end):
                    conflicts.append(node.event)
            if node.right and node.start < end:
                _search(node.right)

        _search(self.root)
        self.nodes_visited_last_op = visited[0]
        return conflicts

    def inorder(self) -> List[Dict[str, Any]]:
        """In-order traversal. Time complexity: O(n)."""
        res: List[Dict[str, Any]] = []

        def _traverse(node: Optional[BSTNode]):
            if not node:
                return
            _traverse(node.left)
            res.append(node.event)
            _traverse(node.right)

        _traverse(self.root)
        return res

    def height(self) -> int:
        """Returns tree height. Time complexity: O(1)."""
        return get_bst_height(self.root)

    def node_count(self) -> int:
        """Returns node count. Time complexity: O(n)."""
        def _count(node: Optional[BSTNode]) -> int:
            if not node:
                return 0
            return 1 + _count(node.left) + _count(node.right)
        return _count(self.root)

    def to_dict_nodes(self) -> List[Dict[str, Any]]:
        """Serializes BST nodes for tree visualizer comparison."""
        nodes: List[Dict[str, Any]] = []

        def _walk(node: Optional[BSTNode]):
            if not node:
                return
            nodes.append({
                'id': node.event.get('id', ''),
                'name': node.event.get('name', ''),
                'start': node.start,
                'end': node.end,
                'height': node.height,
                'balance': get_bst_height(node.left) - get_bst_height(node.right),
                'max_end': node.max_end,
                'left_id': node.left.event.get('id', '') if node.left else None,
                'right_id': node.right.event.get('id', '') if node.right else None,
            })
            _walk(node.left)
            _walk(node.right)

        _walk(self.root)
        return nodes
