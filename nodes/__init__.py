"""Node classes live in submodules so the package root can import them.

This file stays importable on its own. ``python3 -m unittest`` loads every
package under the repo root, and a relative import of ``..schema`` from here
would fail in that top-level import.
"""
