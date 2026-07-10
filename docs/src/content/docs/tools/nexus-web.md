---
title: Using the Nexus web app
description: A reader's guide to the Nexus web UI, covering questions, the evidence panel, and trust badges.
---

This is a guide for **using** the Nexus web app — no setup required. If you need to run it first, see the [Quickstart](/tools/nexus/#quickstart).

Open `http://localhost:8000/` in your browser. Nexus answers questions **only from the documents it has indexed**, and every answer comes **with its sources** — no guessing.

## Ask a question (Chat)

The **Chat** tab is the main surface. Type a question in plain language and press send.

- **Cite an entity** with `@name` (e.g. `@payment-service`) to focus the search on a specific service or entity.
- The empty screen offers **example questions** — click one to try it.

## Read the answer

Every answer is **grounded**: each claim carries a citation like `[source: document title, section]`. The document title is the human-readable name (not a file path).

If nothing supports an answer, Nexus tells you it **could not find the information in the provided documents** rather than inventing one. That refusal is the point: Nexus never fabricates.

## The evidence panel

The right-hand panel lists the **evidence** behind the answer. Each item shows:

- the **document title**,
- a **trust badge** (see below),
- a **relevance bar** (how strongly it matched, as a percentage), and
- the matching **text snippet**.

At the bottom, the **Sources** list links each source document by title; hover to see the original path.

## Trust badges — how much to trust a source

Each source is tagged with a governance grade so you know how much weight it carries:

| Badge | Meaning |
|---|---|
| **Governed** (green) | An approved, canonical decision that passed a review gate (e.g. ADR, design doc, RFC). Highest trust. |
| **Tracked** (amber) | Reviewed but with no approval gate; watch for drift or staleness (e.g. PRD, runbook, postmortem). |
| **Memo** (grey) | A non-governance note. Useful reference, but not canonical (e.g. an imported note). |

Unknown or untyped documents default to **Memo** (conservative).

## Documents

The **Documents** tab lists everything Nexus has indexed, each with its document-type trust badge, so you can see at a glance how governed the corpus is.

Search by title, and filter by state (indexed / hidden / deleted in Notion / superseded). The **origin** column shows whether a document came from Notion, an upload, or a file, and Notion documents link straight back to the page they came from.

**Hiding** takes a document out of search. It does not delete it — the document and its chunks stay, and **되돌리기** brings them back. A confirm panel says exactly that before you commit. A superseded document names, by title, whatever replaced it, and undoing that requires a reason.

## Add documents (Upload)

The **Upload** tab adds documents to the index one at a time.

## Connect Notion (Sources)

Paste a Notion page URL into the **Sources** tab and its whole subtree enters search. No terminal.

- The panel at the top reports the **connection**: whether the token is valid, and which integration and workspace it belongs to. A revoked token says so instead of showing green.
- Each registered root is marked **reachable or not**. If you never invited the integration to that page in Notion, you learn it here rather than after a sync walks the tree.
- **지금 동기화** walks the tree. Use it for the first run.
- To take pages you deleted in Notion out of search, press **삭제 반영 미리보기** first. It lists what would go, by title, and nothing is applied until you confirm that list.

## Explore relationships (Graph)

The **Graph** tab shows entity relationships, both **designed** (from documents) and **observed** (from telemetry), when graph data is available.

## When results look empty

If you connect without an access token, Nexus runs in **anonymous mode** and shows **PUBLIC documents only** — an empty or partial result there is a security boundary, not a bug. Sign in with a token to see INTERNAL content.
