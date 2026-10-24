"""
Pure Python Sorting Algorithms for ChronoGraph.
Implements:
1. Insertion Sort
2. Bubble Sort
3. Selection Sort
4. Merge Sort
Each algorithm returns the sorted array along with comparisons count and swaps count.
"""

from __future__ import annotations
from typing import List, Tuple, Any, Dict
import time


def insertion_sort(arr: List[Any], key=lambda x: x) -> Dict[str, Any]:
    """
    Insertion Sort.
    Time complexity: O(n^2) worst/average, O(n) best. Space: O(1).
    """
    a = list(arr)
    n = len(a)
    comparisons = 0
    moves = 0
    t0 = time.perf_counter()

    for i in range(1, n):
        current = a[i]
        curr_key = key(current)
        j = i - 1
        while j >= 0:
            comparisons += 1
            if key(a[j]) > curr_key:
                a[j + 1] = a[j]
                moves += 1
                j -= 1
            else:
                break
        a[j + 1] = current
        moves += 1

    elapsed_ms = (time.perf_counter() - t0) * 1000
    return {
        'sorted': a,
        'comparisons': comparisons,
        'moves': moves,
        'time_ms': round(elapsed_ms, 4)
    }


def bubble_sort(arr: List[Any], key=lambda x: x) -> Dict[str, Any]:
    """
    Bubble Sort with early exit flag.
    Time complexity: O(n^2) worst/average, O(n) best. Space: O(1).
    """
    a = list(arr)
    n = len(a)
    comparisons = 0
    swaps = 0
    t0 = time.perf_counter()

    for i in range(n):
        swapped = False
        for j in range(0, n - i - 1):
            comparisons += 1
            if key(a[j]) > key(a[j + 1]):
                a[j], a[j + 1] = a[j + 1], a[j]
                swaps += 1
                swapped = True
        if not swapped:
            break

    elapsed_ms = (time.perf_counter() - t0) * 1000
    return {
        'sorted': a,
        'comparisons': comparisons,
        'swaps': swaps,
        'time_ms': round(elapsed_ms, 4)
    }


def selection_sort(arr: List[Any], key=lambda x: x) -> Dict[str, Any]:
    """
    Selection Sort.
    Time complexity: O(n^2) all cases. Space: O(1).
    """
    a = list(arr)
    n = len(a)
    comparisons = 0
    swaps = 0
    t0 = time.perf_counter()

    for i in range(n):
        min_idx = i
        for j in range(i + 1, n):
            comparisons += 1
            if key(a[j]) < key(a[min_idx]):
                min_idx = j
        if min_idx != i:
            a[i], a[min_idx] = a[min_idx], a[i]
            swaps += 1

    elapsed_ms = (time.perf_counter() - t0) * 1000
    return {
        'sorted': a,
        'comparisons': comparisons,
        'swaps': swaps,
        'time_ms': round(elapsed_ms, 4)
    }


def merge_sort(arr: List[Any], key=lambda x: x) -> Dict[str, Any]:
    """
    Merge Sort (Divide and Conquer).
    Time complexity: O(n log n). Space: O(n).
    """
    a = list(arr)
    comparisons = [0]
    t0 = time.perf_counter()

    def _merge_sort_recursive(lst: List[Any]) -> List[Any]:
        if len(lst) <= 1:
            return lst

        mid = len(lst) // 2
        left = _merge_sort_recursive(lst[:mid])
        right = _merge_sort_recursive(lst[mid:])

        merged = []
        i = j = 0
        while i < len(left) and j < len(right):
            comparisons[0] += 1
            if key(left[i]) <= key(right[j]):
                merged.append(left[i])
                i += 1
            else:
                merged.append(right[j])
                j += 1

        merged.extend(left[i:])
        merged.extend(right[j:])
        return merged

    sorted_arr = _merge_sort_recursive(a)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return {
        'sorted': sorted_arr,
        'comparisons': comparisons[0],
        'swaps': 0,
        'time_ms': round(elapsed_ms, 4)
    }
