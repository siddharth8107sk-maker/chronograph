"""
Array-based Min-Heap Priority Queue for ChronoGraph Waitlist.
Orders waitlisted events by priority (1 to 5, where 1 is highest priority).
Breaks ties with an auto-incrementing sequence number (FIFO for identical priorities).
Implemented purely by hand without heapq.
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional, Tuple


class MinHeapWaitlist:
    """
    Min-heap priority queue storing events for the waitlist.
    """

    def __init__(self):
        # Elements stored as tuples: (priority, seq, event_dict)
        self.heap: List[Tuple[int, int, Dict[str, Any]]] = []
        self._seq: int = 0

    def push(self, event: Dict[str, Any]) -> None:
        """
        Pushes an event into the min-heap.
        Time complexity: O(log n).
        """
        priority = int(event.get('priority', 3))
        self._seq += 1
        entry = (priority, self._seq, event)
        self.heap.append(entry)
        self._sift_up(len(self.heap) - 1)

    def pop(self) -> Optional[Dict[str, Any]]:
        """
        Pops the highest priority event (minimum priority integer).
        Time complexity: O(log n).
        """
        if not self.heap:
            return None
        if len(self.heap) == 1:
            return self.heap.pop()[2]

        top = self.heap[0][2]
        self.heap[0] = self.heap.pop()
        self._sift_down(0)
        return top

    def peek(self) -> Optional[Dict[str, Any]]:
        """Returns the top event without removing it. Time complexity: O(1)."""
        return self.heap[0][2] if self.heap else None

    def remove_by_id(self, event_id: str) -> Optional[Dict[str, Any]]:
        """
        Removes an event with event_id from the waitlist if present.
        Time complexity: O(n).
        """
        target_idx = -1
        for i, (_, _, ev) in enumerate(self.heap):
            if ev.get('id') == event_id:
                target_idx = i
                break

        if target_idx == -1:
            return None

        removed_event = self.heap[target_idx][2]
        last_entry = self.heap.pop()
        if target_idx < len(self.heap):
            self.heap[target_idx] = last_entry
            self._sift_down(target_idx)
            self._sift_up(target_idx)
        return removed_event

    def _sift_up(self, idx: int) -> None:
        while idx > 0:
            parent_idx = (idx - 1) // 2
            # Compare (priority, seq)
            if self.heap[idx][:2] < self.heap[parent_idx][:2]:
                self.heap[idx], self.heap[parent_idx] = self.heap[parent_idx], self.heap[idx]
                idx = parent_idx
            else:
                break

    def _sift_down(self, idx: int) -> None:
        size = len(self.heap)
        while True:
            left = 2 * idx + 1
            right = 2 * idx + 2
            smallest = idx

            if left < size and self.heap[left][:2] < self.heap[smallest][:2]:
                smallest = left
            if right < size and self.heap[right][:2] < self.heap[smallest][:2]:
                smallest = right

            if smallest != idx:
                self.heap[idx], self.heap[smallest] = self.heap[smallest], self.heap[idx]
                idx = smallest
            else:
                break

    def to_list(self) -> List[Dict[str, Any]]:
        """
        Returns a sorted list of waitlisted events from highest to lowest priority
        without mutating the heap.
        Time complexity: O(n log n).
        """
        # Shallow copy heap array and repeatedly sift down or sort
        copy_heap = list(self.heap)
        sorted_events = []

        # Sort the copy using in-place heap sort logic or extracted tuples
        temp = list(self.heap)
        temp.sort(key=lambda x: (x[0], x[1]))
        return [item[2] for item in temp]

    def is_empty(self) -> bool:
        return len(self.heap) == 0

    def __len__(self) -> int:
        return len(self.heap)

    def snapshot(self) -> MinHeapWaitlist:
        """Returns a cloned snapshot of the waitlist heap."""
        snap = MinHeapWaitlist()
        snap.heap = [(p, s, dict(ev)) for (p, s, ev) in self.heap]
        snap._seq = self._seq
        return snap
