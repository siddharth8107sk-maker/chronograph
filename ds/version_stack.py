"""
Version Stack (Undo/Redo) and FIFO Request Queue for ChronoGraph.
Maintains persistent tree roots, hash index, trie, and waitlist snapshots.
Supports multi-level undo and redo with sequential version numbering.
Also implements a hand-written FIFO Queue for pending reschedule requests.
"""

from __future__ import annotations
from typing import Optional, List, Dict, Any
from ds.avl_gap import AVLTree
from ds.hash_index import EventHashTable
from ds.trie import EventTrie
from ds.heap import MinHeapWaitlist


class SystemSnapshot:
    """Represents a coherent state snapshot across all data structures."""
    __slots__ = ('version', 'description', 'tree', 'hash_table', 'trie', 'waitlist')

    def __init__(
        self,
        version: int,
        description: str,
        tree: AVLTree,
        hash_table: EventHashTable,
        trie: EventTrie,
        waitlist: MinHeapWaitlist
    ):
        self.version = version
        self.description = description
        self.tree = tree
        self.hash_table = hash_table
        self.trie = trie
        self.waitlist = waitlist


class VersionStack:
    """
    Undo/Redo manager using stack semantics.
    """

    def __init__(self, initial_snapshot: SystemSnapshot):
        self.undo_stack: List[SystemSnapshot] = [initial_snapshot]
        self.redo_stack: List[SystemSnapshot] = []
        self._current_version: int = initial_snapshot.version

    def current(self) -> SystemSnapshot:
        return self.undo_stack[-1]

    def push(
        self,
        description: str,
        tree: AVLTree,
        hash_table: EventHashTable,
        trie: EventTrie,
        waitlist: MinHeapWaitlist
    ) -> SystemSnapshot:
        """
        Pushes a new system state onto the undo stack and clears redo history.
        Time complexity: O(1).
        """
        self._current_version += 1
        snapshot = SystemSnapshot(
            version=self._current_version,
            description=description,
            tree=tree,
            hash_table=hash_table,
            trie=trie,
            waitlist=waitlist
        )
        self.undo_stack.append(snapshot)
        self.redo_stack.clear()
        return snapshot

    def undo(self) -> Optional[SystemSnapshot]:
        """
        Reverts to previous state. Returns None if at bottom of stack.
        Time complexity: O(1).
        """
        if len(self.undo_stack) <= 1:
            return None
        current = self.undo_stack.pop()
        self.redo_stack.append(current)
        return self.undo_stack[-1]

    def redo(self) -> Optional[SystemSnapshot]:
        """
        Re-applies reverted state. Returns None if redo stack is empty.
        Time complexity: O(1).
        """
        if not self.redo_stack:
            return None
        next_snap = self.redo_stack.pop()
        self.undo_stack.append(next_snap)
        return next_snap

    def can_undo(self) -> bool:
        return len(self.undo_stack) > 1

    def can_redo(self) -> bool:
        return len(self.redo_stack) > 0

    @property
    def version(self) -> int:
        return self.undo_stack[-1].version


class QueueNode:
    __slots__ = ('value', 'next')

    def __init__(self, value: Dict[str, Any], next_node: Optional[QueueNode] = None):
        self.value = value
        self.next = next_node


class RequestQueue:
    """
    Pure Python FIFO Queue implemented with linked nodes.
    Used for processing batch or queued reschedule requests in order.
    """

    def __init__(self):
        self.head: Optional[QueueNode] = None
        self.tail: Optional[QueueNode] = None
        self.size: int = 0

    def enqueue(self, item: Dict[str, Any]) -> None:
        """Enqueues item at tail. Time complexity: O(1)."""
        new_node = QueueNode(item)
        if not self.tail:
            self.head = new_node
            self.tail = new_node
        else:
            self.tail.next = new_node
            self.tail = new_node
        self.size += 1

    def dequeue(self) -> Optional[Dict[str, Any]]:
        """Dequeues item from head. Time complexity: O(1)."""
        if not self.head:
            return None
        item = self.head.value
        self.head = self.head.next
        if not self.head:
            self.tail = None
        self.size -= 1
        return item

    def peek(self) -> Optional[Dict[str, Any]]:
        return self.head.value if self.head else None

    def is_empty(self) -> bool:
        return self.head is None

    def __len__(self) -> int:
        return self.size
