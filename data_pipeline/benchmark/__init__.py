"""Auditor workload-reduction benchmark (issue #7).

Compares a documented manual evidence-reconstruction estimate
(`manual_estimate.py`) against a real, timed run of this repo's automated
pipeline (`automated_run.py`) for the *same* representative case. `report.py`
combines both into the comparison this issue asks for.

Scope: this benchmarks the environmental evidence-reconstruction task for
one FireEvent -- retrieving FIRMS history, clustering it into an event,
pulling weather and peat context, finding neighbouring events and imagery
metadata, and assembling an evidence summary. It does not measure, and this
package makes no claim about, the audit workflow beyond that task (auditor
scope definition, screening judgement, field verification, report sign-off).
See the "Important" note in issue #7 and `README.md`'s benchmark section.
"""
