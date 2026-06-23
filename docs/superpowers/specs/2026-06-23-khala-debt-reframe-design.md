# Design Spec — khala 정체성 재정의: the three-debts reframe

> Working title only. The mission tagline is deliberately left open and decided inside
> ADR-0002 (see §3).

- **Date:** 2026-06-23
- **Status:** Design (brainstorming output) — pending spec review + user approval
- **Author:** LivingLikeKrillin (with Claude)
- **Source of insight:** Margaret-Anne Storey, "From Technical Debt to Cognitive and Intent Debt" (ACM Queue 2026 / arXiv:2603.22106) — peer-reviewed Triple Debt Model; plus general industry discourse on the AI era. (No external copyrighted talk material is reproduced.)
- **Deliverable (정본):** `adr/ADR-0002-reframe-system-command-debt.md`, gated through specledger's own approval flow; reflected in root `README.md` identity line + docs site landing.

---

## 1. Purpose

This is **not a code feature**. It is a **positioning/philosophy reframe** of the khala
ecosystem, captured as an Architecture Decision Record. It re-anchors khala's identity
around a single mission and names the **one structural gap** that mission exposes.

The reframe must satisfy khala's own governing discipline:

- **demand-pull, not build-push** — the reframe ships **zero new code**; any feature it
  names is gated on a real pulling signal.
- **taste = subtraction** — the value here is naming what khala *is* and what it will
  *not* build yet, not adding surface.
- **accuracy over narrative** — every claim about what khala already does is grounded in
  existing code, not aspiration.

## 2. The shift (왜 지금)

AI has become the *producer*. Output arrives in bulk, and the natural, incidental
understanding that came from building things by hand evaporates. Storey's peer-reviewed Triple Debt Model names three debts
that accumulate as a result; left untreated, they push a team through a value trough before
any payoff, and often into rollbacks.

khala's users are, in the user's own words, **"people who want to understand their own
service/system better."** That is the through-line. The debts are precisely the forces
that erode that understanding.

## 3. Mission (the reframe)

**One-line identity (candidates — to be decided *inside* the ADR):**

1. **"AI가 짓고, 당신이 이해한다."** — *AI builds it. You understand it.*
   (Captures the core split: production → AI, understanding/verification → human.) — **recommended**
2. **"당신의 시스템을 끝까지 장악하라."** — *Stay in command of your own system.*
3. **"이해를 잃지 않게."** — *Never lose understanding.*

**Framing (chosen: synthesis "C"):**

- **Mission (positive):** keep humans in *command and comprehension* of their own system
  in the AI era.
- **The enemy:** the three debts, which erode that comprehension.
- **The mechanism:** khala is the **"세금 납부 창구" (debt-servicing window)** — the place
  that makes paying down the unavoidable AI-era tax *cheap*.
- **Why this beats a pure "debt repayment" frame:** it keeps the positive goal central,
  avoids a purely negative "pay your pain" pitch, and — critically — does **not demote**
  nexus's grounded-retrieval value. Grounding, governance, and verification all become
  expressions of the one mission (understanding), not separate tools.

## 4. The enemy: three debts ↔ khala modules (grounded mapping)

Each row must cite a real primitive. No aspirational mapping.

| Debt (Storey) | What it is | khala's servicing window | Grounding (real code) |
|---|---|---|---|
| **기술부채 Technical** | Artifacts pile up faster than they can be maintained; next work slows | **mutqa** + **probe** | mutqa: mutation testing surfaces **survivors** = behavior no test covers, recorded in a verdict **ledger**. probe: PR-boundary **scope-drift** detection + **API contract** lint/diff (oasdiff/spectral) |
| **의도부채 Intent** | Why a thing was built — constraints, trade-offs — becomes unrecoverable | **specledger** | ADR/SPEC capture + **`content_hash`** sign-off (`art.meta["content_hash"]`; surfaces as `approved_hash` on the A2A publish envelope) + critique → disposition → approval; PreToolUse gate (`hooks/pretooluse_gate.py`) blocks edits until approved |
| **인지부채 Cognitive** | *Nobody understands the system the org ships* | **— EMPTY LEG —** | nexus provides the *substrate* (grounded retrieval, evidence, provenance; **`search_log` / `v_search_health`** signals) but **nothing measures or enforces human comprehension** |

Supporting roles (not debts themselves):

- **nexus** = the **Queryable** substrate — grounded answers carry evidence + provenance +
  confidence; `search_log`/`v_search_health` already collect demand signals.
- **Workflow (adversarial sub-agent pattern)** = the engine for **paying the Verification
  tax** cheaply (parallel critical review × N, repeated until findings converge).

## 5. The empty leg: cognitive debt

- **Definition:** the team (or, for khala built by AI, the single human director) can no
  longer understand or *vouch for* the system being shipped (cognitive surrender).
- **Why khala has no window for it:** every other debt has an enforcement point
  (specledger gate, mutqa ledger, probe checks). Comprehension has **none** — it is
  assumed, never measured.
- **Why it is the center of the mission:** cognitive debt is the *purest form* of the
  enemy "losing command of your own system." Closing this leg **completes the reframe**.
- **Scope here:** name the direction only — *"이해도/장악도 계측 (comprehension /
  command instrumentation)."* **No design in this document.**

## 6. Re-placing existing principles under the mission

The reframe must show that khala's existing principles still hold, now subordinated to the
mission:

- **grounded answers only / "system decides, LLM narrates"** → the *integrity layer* that
  makes understanding trustworthy.
- **default-deny + quarantine** → protecting the substrate the understanding rests on.
- **demand-pull, not build-push** → restated as: *gate each debt-servicing feature on "is
  this debt actually accumulating? show the signal."* (This is how nexus already gated
  GraphRAG behind `search_log`.)

## 7. Follow-on backlog (names + gate signals ONLY — not designed here)

Three candidate directions for the cognitive-debt window. Each lists the **signal that
must pull** before any design work starts. **None is designed in this session.**

| # | Direction | Gate signal (must observe before building) |
|---|---|---|
| ⓐ | **이해도 계측 (comprehension meter / periodic quiz)** — probe whether a human can vouch for a shipped artifact | Repeated evidence (in khala dogfooding) of merging AI-built changes nobody can explain |
| ⓑ | **시스템 이해 맵 (system-understanding map)** — who/what understands which parts, org-level heatmap, built on nexus | A multi-person consumer exists; single-director khala does not pull this yet |
| ⓒ | **run-time 검증 레이어** — continuous verification of non-deterministic AI agents in production | khala (or a consumer) ships an AI *agent product* whose run-time behavior needs guarding |

**First consumer = khala itself** (dogfooding): khala is built AI-native, so cognitive
debt is real and present here. This makes the demand signal genuine rather than
speculative — the failure mode that stopped A2A.

## 8. Decision & status (for the ADR)

- ADR-0002 records this reframe; frontmatter follows ADR-0001 convention (`id`, `type:
  adr`, `title`, `status`, `date`, `tags`, `linked_adrs: [ADR-0001]`, `approved_by`,
  `reviewed_at`, `content_hash`).
- **Process (dogfood):** route ADR-0002 through specledger — `record` → `critique` →
  human disposition → `approve` (stamps `content_hash`). khala thereby pays its *own*
  intent-debt at its own window.
- **Reflection:** once approved, update root `README.md` identity line and the docs site
  landing to the chosen tagline + mission.
- **Out of scope:** no external copyrighted talk material or PDF is committed or reproduced;
  rest on Storey's peer-reviewed framework + Khala's own reasoning.

## 9. Non-goals (taste = subtraction)

- No new code, schema, endpoint, or skill in this session.
- No design of the comprehension meter / quiz (that is a separate, signal-gated session).
- No mapping that the current code does not actually support.
- No demotion of nexus's standalone retrieval value.

## 10. Success criteria

- A reader of ADR-0002 can state, in one sentence, what khala is and which debt it does
  *not yet* service.
- Every module→debt mapping is checkable against real code.
- The document adds **zero** maintenance surface and names its own build gates.
- The reframe is reversible: it is a positioning decision, superseded by a future ADR if
  the framing proves wrong.

---

## Implementation outline (for writing-plans)

1. Write `adr/ADR-0002-reframe-system-command-debt.md` per sections 2–9 above.
2. Decide the final tagline (section 3) within the ADR.
3. Route it through specledger (`record` → `critique` → `approve`); stamp `content_hash`.
4. Update root `README.md` identity line + docs site landing to match.
5. (Optional) add a one-line pointer from `adr/README.md`.
