"""
Hash Table with Separate Chaining for ChronoGraph.
Maps event_id (string) -> event (dict).
Implements a custom polynomial rolling hash function and automatic dynamic resizing
when load factor exceeds 0.75.
"""

from __future__ import annotations
from typing import Optional, List, Dict, Any, Tuple


class HashNode:
    __slots__ = ('key', 'value', 'next')

    def __init__(self, key: str, value: Dict[str, Any], next_node: Optional[HashNode] = None):
        self.key: str = key
        self.value: Dict[str, Any] = value
        self.next: Optional[HashNode] = next_node


class EventHashTable:
    """
    Custom Hash Table using separate chaining.
    """

    INITIAL_CAPACITY = 16
    LOAD_FACTOR_THRESHOLD = 0.75

    def __init__(self, capacity: int = INITIAL_CAPACITY):
        self.capacity: int = max(capacity, 16)
        self.size: int = 0
        self.buckets: List[Optional[HashNode]] = [None] * self.capacity

    def _hash(self, key: str) -> int:
        """
        Polynomial rolling hash function.
        Time complexity: O(L) where L is key length.
        """
        h = 0
        for char in key:
            h = (h * 31 + ord(char)) & 0xFFFFFFFF
        return h % self.capacity

    def _resize(self, new_capacity: int) -> None:
        """
        Doubles capacity and rehashes all elements.
        Time complexity: O(n).
        """
        old_buckets = self.buckets
        self.capacity = new_capacity
        self.buckets = [None] * new_capacity
        self.size = 0

        for head in old_buckets:
            curr = head
            while curr:
                self.put(curr.key, curr.value)
                curr = curr.next

    def put(self, key: str, value: Dict[str, Any]) -> None:
        """
        Inserts or updates (key, value). Resizes if load factor >= 0.75.
        Average time complexity: O(1).
        """
        if (self.size + 1) / self.capacity >= self.LOAD_FACTOR_THRESHOLD:
            self._resize(self.capacity * 2)

        idx = self._hash(key)
        curr = self.buckets[idx]

        # Check if key already exists
        while curr:
            if curr.key == key:
                curr.value = value
                return
            curr = curr.next

        # Insert new node at head of chain
        new_node = HashNode(key, value, next_node=self.buckets[idx])
        self.buckets[idx] = new_node
        self.size += 1

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves event by key.
        Average time complexity: O(1).
        """
        idx = self._hash(key)
        curr = self.buckets[idx]
        while curr:
            if curr.key == key:
                return curr.value
            curr = curr.next
        return None

    def delete(self, key: str) -> bool:
        """
        Removes key from table. Returns True if removed, False if not found.
        Average time complexity: O(1).
        """
        idx = self._hash(key)
        curr = self.buckets[idx]
        prev: Optional[HashNode] = None

        while curr:
            if curr.key == key:
                if prev is None:
                    self.buckets[idx] = curr.next
                else:
                    prev.next = curr.next
                self.size -= 1
                return True
            prev = curr
            curr = curr.next
        return False

    def contains(self, key: str) -> bool:
        """Returns True if key is present. Average time complexity: O(1)."""
        return self.get(key) is not None

    def items(self) -> List[Tuple[str, Dict[str, Any]]]:
        """Returns all (key, value) pairs. Time complexity: O(n)."""
        result = []
        for head in self.buckets:
            curr = head
            while curr:
                result.append((curr.key, curr.value))
                curr = curr.next
        return result

    def values(self) -> List[Dict[str, Any]]:
        """Returns all event values. Time complexity: O(n)."""
        result = []
        for head in self.buckets:
            curr = head
            while curr:
                result.append(curr.value)
                curr = curr.next
        return result

    def __len__(self) -> int:
        return self.size

    def snapshot(self) -> EventHashTable:
        """Returns a cloned snapshot of the hash table for versioning."""
        snap = EventHashTable(self.capacity)
        for k, v in self.items():
            snap.put(k, dict(v))
        return snap
