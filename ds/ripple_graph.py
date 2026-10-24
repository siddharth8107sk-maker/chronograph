"""
Conflict-Ripple Graph for ChronoGraph.
Models events as vertices and relationships as edges:
- time_overlap: two events overlap in time interval
- venue_conflict: two events share the same venue on the same date
- organizer_conflict: two events share the same organizer on the same date
- dependency: directed edge indicating depends_on prerequisite

Implements:
1. Adjacency lists (undirected for conflicts, directed for dependencies)
2. Breadth-First Search (BFS) for ripple propagation layers and ripple score
3. Depth-First Search (DFS) for connected component clustering
4. Greedy graph coloring for conflict-free venue suggestion
5. Kahn's Topological Sort with cycle detection for dependency graphs
"""

from __future__ import annotations
from typing import Dict, List, Set, Any, Optional, Tuple


class ConflictEdge:
    __slots__ = ('source', 'target', 'type')

    def __init__(self, source: str, target: str, edge_type: str):
        self.source = source
        self.target = target
        self.type = edge_type

    def to_dict(self) -> Dict[str, str]:
        return {
            'source': self.source,
            'target': self.target,
            'type': self.type
        }


class ConflictRippleGraph:
    """
    Graph of event relationships and conflicts.
    """

    def __init__(self, events: List[Dict[str, Any]]):
        self.events: Dict[str, Dict[str, Any]] = {e['id']: e for e in events}
        # Undirected conflict adjacency: eid -> set of (neighbor_id, type)
        self.adj: Dict[str, Dict[str, str]] = {e['id']: {} for e in events}
        # Directed dependency adjacency: u -> list of v (where v depends on u, or u depends on v)
        # If B depends_on A, then A must happen before B: edge A -> B
        self.dep_adj: Dict[str, List[str]] = {e['id']: [] for e in events}
        self.in_degree: Dict[str, int] = {e['id']: 0 for e in events}
        self.edges: List[ConflictEdge] = []

        self._build_graph(events)

    def _build_graph(self, events: List[Dict[str, Any]]) -> None:
        n = len(events)
        for i in range(n):
            e1 = events[i]
            id1 = e1['id']

            # Check dependencies
            dep_id = e1.get('depends_on')
            if dep_id and dep_id in self.events:
                # dep_id -> id1 (dep_id must precede id1)
                self.dep_adj[dep_id].append(id1)
                self.in_degree[id1] += 1
                edge = ConflictEdge(dep_id, id1, 'dependency')
                self.edges.append(edge)
                self.adj[id1][dep_id] = 'dependency'
                self.adj[dep_id][id1] = 'dependency'

            for j in range(i + 1, n):
                e2 = events[j]
                id2 = e2['id']

                edge_type = None

                # 1. Time overlap
                s1, e1_end = e1['start_minute'], e1['end_minute']
                s2, e2_end = e2['start_minute'], e2['end_minute']
                has_time_overlap = max(s1, s2) < min(e1_end, e2_end)

                if has_time_overlap:
                    edge_type = 'time_overlap'
                # 2. Shared venue on same date
                elif e1.get('date') == e2.get('date') and e1.get('venue') and e1.get('venue') == e2.get('venue'):
                    edge_type = 'venue_conflict'
                # 3. Shared organizer on same date
                elif e1.get('date') == e2.get('date') and e1.get('organizer') and e1.get('organizer') == e2.get('organizer'):
                    edge_type = 'organizer_conflict'

                if edge_type:
                    self.adj[id1][id2] = edge_type
                    self.adj[id2][id1] = edge_type
                    self.edges.append(ConflictEdge(id1, id2, edge_type))

    def get_connected_components(self) -> List[List[Dict[str, Any]]]:
        """
        DFS to partition the events into connected conflict components (clusters).
        Time complexity: O(V + E).
        """
        visited: Set[str] = set()
        components: List[List[Dict[str, Any]]] = []

        for event_id in self.events:
            if event_id not in visited:
                # Only cluster nodes that have edges or count all
                cluster_ids: List[str] = []
                stack = [event_id]
                visited.add(event_id)

                while stack:
                    curr = stack.pop()
                    cluster_ids.append(curr)
                    for neighbor in self.adj.get(curr, {}):
                        if neighbor not in visited:
                            visited.add(neighbor)
                            stack.append(neighbor)

                # Include cluster if it has multiple events or any edge
                component_events = [self.events[eid] for eid in cluster_ids]
                components.append(component_events)

        # Sort components by size descending
        components.sort(key=lambda c: len(c), reverse=True)
        return components

    def bfs_ripple(self, start_id: str) -> Dict[str, Any]:
        """
        BFS computing ripple layers (distance 1, 2, 3...) and overall ripple score.
        Time complexity: O(V + E).
        """
        if start_id not in self.events:
            return {'start_id': start_id, 'ripple_score': 0, 'layers': {}}

        visited: Set[str] = {start_id}
        queue: List[Tuple[str, int]] = [(start_id, 0)]
        layers: Dict[int, List[Dict[str, Any]]] = {}

        while queue:
            curr_id, dist = queue.pop(0)

            if dist > 0:
                if dist not in layers:
                    layers[dist] = []
                layers[dist].append({
                    'id': curr_id,
                    'name': self.events[curr_id]['name'],
                    'venue': self.events[curr_id].get('venue'),
                    'relation': self.adj[start_id].get(curr_id, 'indirect')
                })

            for neighbor in self.adj.get(curr_id, {}):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, dist + 1))

        ripple_score = sum(len(evts) for evts in layers.values())
        return {
            'start_id': start_id,
            'ripple_score': ripple_score,
            'layers': layers
        }

    def greedy_coloring(self, cluster_ids: Optional[List[str]] = None) -> Dict[str, int]:
        """
        Greedy graph coloring for venue assignment suggestions.
        Ensures conflicting events receive distinct color integers (venues).
        Time complexity: O(V^2 + E).
        """
        nodes = cluster_ids if cluster_ids is not None else list(self.events.keys())
        colors: Dict[str, int] = {}

        # Sort nodes by degree descending (Welsh-Powell heuristic)
        sorted_nodes = sorted(nodes, key=lambda nid: len(self.adj.get(nid, {})), reverse=True)

        for node in sorted_nodes:
            neighbor_colors = {
                colors[nbr] for nbr in self.adj.get(node, {})
                if nbr in colors
            }
            # Find smallest available color >= 0
            color = 0
            while color in neighbor_colors:
                color += 1
            colors[node] = color

        return colors

    def topological_sort(self) -> Dict[str, Any]:
        """
        Kahn's algorithm using in-degree array and queue.
        Validates dependency order and detects cycles.
        Time complexity: O(V + E).
        """
        in_deg = dict(self.in_degree)
        queue: List[str] = [eid for eid, deg in in_deg.items() if deg == 0]
        topo_order: List[str] = []

        while queue:
            u = queue.pop(0)
            topo_order.append(u)

            for v in self.dep_adj.get(u, []):
                in_deg[v] -= 1
                if in_deg[v] == 0:
                    queue.append(v)

        if len(topo_order) == len(self.events):
            return {
                'has_cycle': False,
                'order': topo_order,
                'cycle_nodes': []
            }
        else:
            # Nodes with in_degree > 0 participate in or follow a cycle
            cycle_nodes = [eid for eid, deg in in_deg.items() if deg > 0]
            return {
                'has_cycle': True,
                'order': [],
                'cycle_nodes': cycle_nodes,
                'error': f"Cyclic dependency detected among {len(cycle_nodes)} events"
            }

    def to_dict(self) -> Dict[str, Any]:
        """Serializes full graph structure for frontend SVG rendering."""
        return {
            'nodes': list(self.events.values()),
            'edges': [e.to_dict() for e in self.edges],
            'components': self.get_connected_components(),
            'coloring': self.greedy_coloring(),
            'topological_sort': self.topological_sort()
        }
