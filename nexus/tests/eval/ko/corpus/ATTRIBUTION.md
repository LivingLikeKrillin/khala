# Corpus attribution — Kubernetes Korean documentation

This directory contains a **modified** snapshot of Korean documentation from the Kubernetes
website, redistributed here as an evaluation corpus for
[`SPEC-nexus-korean-retrieval-eval`](../../../../../specs/SPEC-nexus-korean-retrieval-eval.md).

- **Source:** <https://github.com/kubernetes/website> — `content/ko/docs/**`
- **Pinned commit:** `b035ea80a2f666e0a60923560984458806788104` (2026-08-01)
- **Copyright:** The Kubernetes Authors
- **Licence:** [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) — the licence under which
  the upstream documentation content is published. This snapshot is redistributed under the same
  licence.

## Modifications made

The files here are **not** verbatim upstream content. Each was transformed by
`nexus/scripts/ko_eval_pack.py` (rules fixed in the SPEC §4.1):

- Unicode normalised to NFC; CRLF → LF; trailing whitespace removed; single final newline
- YAML front matter removed, with its `title:` kept as a top-level `#` heading
- Hugo shortcodes resolved: a tag carrying `text="…"` becomes that text (so
  `{{< glossary_tooltip text="파드" … >}}` → `파드`), paired tags are removed keeping their inner
  content, and all other tags are removed
- HTML comments removed

Selection is by rule, not by hand: `concepts`, `tasks`, `tutorials` and `setup` sections, excluding
`_index.md`, keeping files whose **upstream** size is between 2 KiB and 40 KiB. `manifest.json`
records the resulting 265 documents with their upstream blob SHA-1 and packed SHA-256.

## Notes

- This snapshot is used **only as retrieval-evaluation material**. It is not documentation of this
  project, is not kept current with upstream, and describes Kubernetes versions as of the pinned
  commit.
- Neither the Kubernetes project nor The Linux Foundation endorses this project or this use.
  Kubernetes is a registered trademark of The Linux Foundation.
- To re-derive or verify: `python -m scripts.ko_eval_pack check` (against upstream) and
  `python -m scripts.ko_eval_pack verify` (offline, against `manifest.json`).
