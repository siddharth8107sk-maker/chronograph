"""
Trie for Event Name Prefix Autocomplete.
Allows fast search of events by title prefix (case-insensitive).
Returns up to 8 matching entries.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any, Set


class TrieNode:
    __slots__ = ('children', 'event_ids', 'is_end')

    def __init__(self):
        self.children: Dict[str, TrieNode] = {}
        self.event_ids: Set[str] = set()
        self.is_end: bool = False


class EventTrie:
    """
    Prefix tree for fast event title auto-completion.
    """

    def __init__(self):
        self.root: TrieNode = TrieNode()
        # Map event_id -> title for quick match formatting
        self._id_to_title: Dict[str, str] = {}

    def insert(self, title: str, event_id: str) -> None:
        """
        Inserts title (normalized to lowercase) into the trie.
        Time complexity: O(L) where L is len(title).
        """
        clean_title = title.strip().lower()
        self._id_to_title[event_id] = title

        curr = self.root
        for char in clean_title:
            if char not in curr.children:
                curr.children[char] = TrieNode()
            curr = curr.children[char]
            curr.event_ids.add(event_id)

        curr.is_end = True

    def delete(self, title: str, event_id: str) -> None:
        """
        Removes an event_id from the prefix paths.
        Time complexity: O(L).
        """
        clean_title = title.strip().lower()
        if event_id in self._id_to_title:
            del self._id_to_title[event_id]

        curr = self.root
        for char in clean_title:
            if char not in curr.children:
                return
            curr = curr.children[char]
            curr.event_ids.discard(event_id)

    def search_prefix(self, prefix: str, limit: int = 8) -> List[Dict[str, str]]:
        """
        Finds up to `limit` events whose titles match the given prefix.
        Time complexity: O(P + K) where P is prefix length, K is number of matches.
        """
        clean_prefix = prefix.strip().lower()
        if not clean_prefix:
            return []

        curr = self.root
        for char in clean_prefix:
            if char not in curr.children:
                return []
            curr = curr.children[char]

        matches: List[Dict[str, str]] = []
        for eid in curr.event_ids:
            if eid in self._id_to_title:
                matches.append({
                    'id': eid,
                    'name': self._id_to_title[eid]
                })
                if len(matches) >= limit:
                    break

        return matches

    def snapshot(self) -> EventTrie:
        """Returns a snapshot of the trie."""
        snap = EventTrie()
        for eid, title in self._id_to_title.items():
            snap.insert(title, eid)
        return snap
