"""``dra ui``: a local page over the run directory (docs/design/ui_design.md, shape A).

The page starts runs as ``dra review`` subprocesses, streams their ``progress.jsonl`` as
server-sent events, renders the finished ``report.json`` and offers a grounded chat that is a
reading aid, not the review. Nothing here is on the evaluated path: the server writes only under
``runs/<id>/ui/``, and the report, the manifest and ``dra replay`` are the same with or without it.

Modules: :mod:`.events` (the progress event contract the page reads), :mod:`.rundata` (run
directories read for the page), :mod:`.launcher` (the ``dra review`` subprocess), :mod:`.chat`
(the grounded chat) and :mod:`.server` (the Starlette app and ``serve``).
"""
