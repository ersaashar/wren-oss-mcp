"""Strict startup synchronization of derived query memory.

The Markdown files under ``knowledge/sql/`` are the source of truth; the LanceDB
store under ``<project>/.wren/memory`` is a derived artifact. This module
rebuilds that artifact from the compiled manifest and the curated Markdown pairs
before the server starts listening.

Two upstream behaviours make a bespoke indexer unnecessary:

* ``MemoryStore.index_schema`` embeds the schema items from the manifest.
* ``MemoryStore.sync_markdown_queries`` upserts every Markdown pair and forgets
  the ones it previously wrote that no longer exist in Markdown.

``seed_queries=False`` suppresses Wren's auto-generated seed pairs, and the
explicit ``forget_queries_by_source("seed")`` clears seed rows written by an
older index so a previously seeded volume converges to curated-only memory.

Any failure propagates: the container entrypoint must not start the server with
a stale or partially rebuilt index.
"""

from __future__ import annotations

import json
from pathlib import Path

from wren.memory.markdown import load_query_pairs
from wren.memory.store import MemoryStore

_MANIFEST_RELATIVE_PATH = Path("target") / "mdl.json"
_MEMORY_RELATIVE_PATH = Path(".wren") / "memory"
_SEED_SOURCE_TAG = "seed"


def initialize_memory(project: Path) -> None:
    """Rebuild the project's derived memory from source assets.

    Raises ``FileNotFoundError`` when the compiled manifest is missing, and
    propagates embedding, import, and modification errors unchanged.
    """
    project = Path(project)
    manifest_path = project / _MANIFEST_RELATIVE_PATH
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    store = MemoryStore(path=project / _MEMORY_RELATIVE_PATH)
    store.index_schema(manifest, replace=True, seed_queries=False)
    store.forget_queries_by_source(_SEED_SOURCE_TAG)
    store.sync_markdown_queries(load_query_pairs(project))


if __name__ == "__main__":
    initialize_memory(Path("/app/project"))
