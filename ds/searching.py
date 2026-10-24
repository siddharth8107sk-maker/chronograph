"""
Pure Python Searching Algorithms for ChronoGraph.
Operates on sorted arrays of start-time integers.
Implements:
1. Linear Search
2. Binary Search (Iterative)
3. Binary Search (Recursive)
4. Interpolation Search
Returns the target index, comparison count, and elapsed time.
"""

from __future__ import annotations
from typing import List, Optional, Dict, Any
import time


def linear_search(arr: List[int], target: int) -> Dict[str, Any]:
    """
    Linear Search on list.
    Time complexity: O(n). Space: O(1).
    """
    t0 = time.perf_counter()
    comparisons = 0
    found_idx = -1

    for i, val in enumerate(arr):
        comparisons += 1
        if val == target:
            found_idx = i
            break

    elapsed_ms = (time.perf_counter() - t0) * 1000
    return {
        'index': found_idx,
        'comparisons': comparisons,
        'time_ms': round(elapsed_ms, 6)
    }


def binary_search_iterative(arr: List[int], target: int) -> Dict[str, Any]:
    """
    Iterative Binary Search on sorted list.
    Time complexity: O(log n). Space: O(1).
    """
    t0 = time.perf_counter()
    comparisons = 0
    low = 0
    high = len(arr) - 1
    found_idx = -1

    while low <= high:
        mid = (low + high) // 2
        comparisons += 1
        mid_val = arr[mid]
        if mid_val == target:
            found_idx = mid
            break
        elif mid_val < target:
            low = mid + 1
        else:
            high = mid - 1

    elapsed_ms = (time.perf_counter() - t0) * 1000
    return {
        'index': found_idx,
        'comparisons': comparisons,
        'time_ms': round(elapsed_ms, 6)
    }


def binary_search_recursive(arr: List[int], target: int) -> Dict[str, Any]:
    """
    Recursive Binary Search on sorted list.
    Time complexity: O(log n). Space: O(log n) call stack.
    """
    t0 = time.perf_counter()
    comparisons = [0]

    def _rec(low: int, high: int) -> int:
        if low > high:
            return -1
        mid = (low + high) // 2
        comparisons[0] += 1
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            return _rec(mid + 1, high)
        else:
            return _rec(low, mid - 1)

    found_idx = _rec(0, len(arr) - 1)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return {
        'index': found_idx,
        'comparisons': comparisons[0],
        'time_ms': round(elapsed_ms, 6)
    }


def interpolation_search(arr: List[int], target: int) -> Dict[str, Any]:
    """
    Interpolation Search on uniformly distributed sorted list.
    Formula: pos = low + ((target - arr[low]) * (high - low)) // (arr[high] - arr[low])
    Time complexity: O(log log n) average, O(n) worst. Space: O(1).
    """
    t0 = time.perf_counter()
    comparisons = 0
    low = 0
    high = len(arr) - 1
    found_idx = -1

    while low <= high and target >= arr[low] and target <= arr[high]:
        comparisons += 1
        if low == high:
            if arr[low] == target:
                found_idx = low
            break

        # Estimate probe position based on value distribution
        denom = arr[high] - arr[low]
        if denom == 0:
            if arr[low] == target:
                found_idx = low
            break

        pos = low + int(((target - arr[low]) * (high - low)) // denom)

        if pos < low or pos > high:
            break

        if arr[pos] == target:
            found_idx = pos
            break
        elif arr[pos] < target:
            low = pos + 1
        else:
            high = pos - 1

    elapsed_ms = (time.perf_counter() - t0) * 1000
    return {
        'index': found_idx,
        'comparisons': comparisons,
        'time_ms': round(elapsed_ms, 6)
    }
