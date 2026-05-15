"""Business-logic helpers extracted from server.py.

These modules know about the database and may use config, but they
NEVER import from the routers or from each other in cycles. The
dependency graph is:

    routers/  →  services/  →  schemas/ + database + config
"""
