"""Config-driven semantic domain loaders.

A domain takes datasets that the generic format dispatch would store as
opaque long-format rows and loads them into a typed domain table instead,
using curated semantics (e.g. election_definitions.json maps the anonymous
'Offene Wahldaten' columns to parties). The pattern: a committed config file,
a route_for() check consulted FIRST in pipeline._dispatch, and a sync_*()
that reconciles registry tables on scheduler startup.
"""
