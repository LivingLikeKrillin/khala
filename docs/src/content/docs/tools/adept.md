---
title: Adept
description: The cognitive-debt meter. Measures whether a named human can still vouch for an artifact, via graded comprehension checks grounded in its actual content.
---

Adept is the ledger half of Khala's answer to cognitive debt. The rest of the ecosystem keeps the org's knowledge governed — approved, current, cited. Adept reads that same substrate from the other side and asks the uncomfortable question: **can a named human still explain this?** Not via a rubber-stamp "I understand" click, but by passing graded comprehension questions generated from the artifact's actual content.

The framing is a ledger. Registered critical artifacts are the **denominator** — what must be known. Current vouches are the **numerator** — what someone can still explain. The gap is cognitive debt, and because it is measured, it can be repaid deliberately instead of discovered during an incident.

<svg class="kh-fig" viewBox="0 0 560 230" role="img" aria-label="Adept reads the warehouse as the denominator: of 12 registered critical artifacts, 9 carry a current vouch and 3 do not. Coverage is 9 of 12; the artifact with no voucher tops the repayment hotlist.">
<defs><marker id="ad-a" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path class="kh-fig-ah" d="M0 0 L10 5 L0 10 z"/></marker></defs>
<rect class="kh-fig-panel" x="24" y="28" width="250" height="180" rx="8"/>
<text class="kh-fig-h" x="42" y="52">CRITICAL ARTIFACTS · 12</text>
<line class="kh-fig-rule" x1="42" y1="64" x2="256" y2="64"/>
<rect class="kh-fig-track" x="44" y="80" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="82" y="80" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="120" y="80" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="158" y="80" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="44" y="110" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="82" y="110" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="120" y="110" width="30" height="22" rx="3"/>
<rect class="kh-fig-box-acc" x="158" y="110" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="44" y="140" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="82" y="140" width="30" height="22" rx="3"/>
<rect class="kh-fig-box-acc" x="120" y="140" width="30" height="22" rx="3"/>
<rect class="kh-fig-box-acc" x="158" y="140" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="42" y="180" width="12" height="12" rx="2"/>
<text class="kh-fig-s" x="60" y="187">vouched ×9</text>
<rect class="kh-fig-box-acc" x="150" y="180" width="12" height="12" rx="2"/>
<text class="kh-fig-s" x="168" y="187">stale / none ×3</text>
<path class="kh-fig-line-acc" d="M274 118 L300 118" marker-end="url(#ad-a)"/>
<rect class="kh-fig-panel" x="300" y="28" width="236" height="180" rx="8"/>
<text class="kh-fig-h" x="318" y="52">COVERAGE</text>
<line class="kh-fig-rule" x1="318" y1="64" x2="518" y2="64"/>
<text class="kh-fig-ans" x="318" y="94">9 / 12</text>
<text class="kh-fig-d" x="318" y="122">retry-policy.md</text>
<text class="kh-fig-s" x="318" y="144">no current voucher</text>
<text class="kh-fig-d" x="318" y="176">→ repay first</text>
</svg>

## Core concepts

- **Vouch.** A passing, graded comprehension check by a named person, bound to the artifact's `content_hash`. When the artifact changes, the vouch goes **stale** automatically — understanding of an old version doesn't silently carry over.
- **Spaced repetition.** Per-question mastery sits on a repetition ladder; questions resurface for re-testing until passed again. A vouch is a state you maintain, not a badge you earn once.
- **Coverage.** The org-level metric: the fraction of registered critical artifacts with a current vouch. Its complement is the **orphan hotlist** — artifacts nobody can currently vouch for. Repay those first.
- **AI-authorship-safe.** Adept never consults git history. Whether a human or an agent wrote the artifact is irrelevant; the only question is whether a human understands it *now*.

## Quickstart

```bash
uv tool install ./adept    # or: pipx install ./adept — installs the global `adept` command
```

Run `adept` from anywhere in your project — the root is the nearest `adept.manifest.yaml` (walking up from the current directory). Artifact paths are stored relative to that root, so the manifest is clone-portable.

```bash
adept register PATH                    # register a critical artifact; prints its artifact_id
adept due --as PERSON                  # due questions / artifacts needing questions
adept coverage --as PERSON             # coverage, orphan hotlist, weakness map
adept review ARTIFACT_ID --as PERSON   # headless self-drive (needs ANTHROPIC_API_KEY)
```

The agent-driven loop (`due` → `save-questions` → `record-attempt` → `coverage`) needs no API key — a Claude Code session supplies the cognition (question generation, grading, remediation). Only `adept review` calls the model directly.

A browser + server-backed team surface lives in [`adept-web`](https://github.com/LivingLikeKrillin/khala/tree/master/adept-web) — the same meter with a shared backend (file or Postgres).

:::note[Last verified]
Transcribed from `adept/README.md`. Site re-run verification pending.
:::
