"""Deterministic lab-interpretation producer — FOUNDATION (4a).

A pure producer over (a) newest+prior per marker and (b) marker_groups.json +
the `min_meaningful_delta` attribute of lever_dictionary.json. Emits the
group-primary skeleton with the 4a-owned fields populated and every 4b field
absent.

PHASE-FREE, RELATION-FREE, current_state-FREE. No endpoint, no frontend, no LLM.
The 4b line (verdict / relations / levers / mechanism / phase / news demotion)
is drawn in producer.py and enforced by the boundary tests.
"""
