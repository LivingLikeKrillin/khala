---
title: Using the Nexus web app
description: A reader's guide to the Nexus web UI — asking questions, reading the evidence panel, and understanding trust badges.
---

This is a guide for **using** the Nexus web app — no setup required. If you need to run it first, see the [Quickstart](/tools/nexus/#quickstart).

Open `http://localhost:8000/` in your browser. Nexus answers questions **only from the documents it has indexed**, and every answer comes **with its sources** — no guessing.

## Ask a question (Chat)

The **채팅 / Chat** tab is the main surface. Type a question in plain language and press send.

- **Cite an entity** with `@name` (e.g. `@payment-service`) to focus the search on a specific service or entity.
- The empty screen offers **example questions** — click one to try it.

## Read the answer

Every answer is **grounded**: each claim carries a citation like `[출처: document title, section]`. The document title is the human-readable name (not a file path).

If there is no supporting evidence, Nexus says **"제공된 문서에서 해당 정보를 찾을 수 없습니다" (not found in the provided documents)** instead of inventing an answer. That refusal is the feature, not a failure — Nexus never fabricates.

## The evidence panel

The right-hand panel lists the **evidence** behind the answer. Each item shows:

- the **document title**,
- a **trust badge** (see below),
- a **relevance bar** (how strongly it matched, as a percentage), and
- the matching **text snippet**.

At the bottom, the **출처 (sources)** list links each source document by title; hover to see the original path.

## Trust badges — how much to trust a source

Each source is tagged with a governance grade so you know how much weight it carries:

| Badge | Meaning |
|---|---|
| **거버넌스 / Governed** (green) | An approved, canonical decision that passed a review gate (e.g. ADR, design doc, RFC). Highest trust. |
| **추적 / Tracked** (amber) | Reviewed but with no approval gate — watch for drift / staleness (e.g. PRD, runbook, postmortem). |
| **메모 / Memo** (grey) | A non-governance note — useful reference, but not canonical (e.g. an imported note). |

Unknown or untyped documents default to **Memo** (conservative).

## Documents

The **문서 / Documents** tab lists everything Nexus has indexed, each with its document-type trust badge — so you can see at a glance how governed the corpus is.

## Add documents (Upload)

The **업로드 / Upload** tab lets you add documents to the index. (Bulk or automated ingest is a CLI/operator task — see the [Quickstart](/tools/nexus/#quickstart).)

## Explore relationships (Graph)

The **그래프 / Graph** tab shows entity relationships — both **designed** (from documents) and **observed** (from telemetry) — when graph data is available.

## When results look empty

If you connect without an access token, Nexus runs in **anonymous mode** and shows **PUBLIC documents only** — an empty or partial result there is a security boundary, not a bug. Sign in with a token to see INTERNAL content.
