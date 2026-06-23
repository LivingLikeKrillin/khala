# ken — cognitive-debt meter

`ken` (Scots/English: "to know, to understand") measures whether a *named human* can
currently **vouch** for an artifact — not via a rubber-stamp click, but by passing
graded, grounded comprehension questions generated from the artifact's actual content.

A passing vouch is bound to the artifact's `content_hash` and has a TTL, so it goes
**stale** when the artifact changes or the vouch ages out (mirrors specledger's
`approved_hash` staleness). The org-level metric is **cognitive-debt coverage**: the
fraction of registered critical artifacts with at least one *fresh* vouch — plus the
**orphan list** (artifacts with no fresh voucher) = the cognitive-debt hotlist. It never
consults git history, so it is AI-authorship-safe.

## CLI

```bash
ken register PATH                       # register an artifact into the manifest, prints its artifact_id
ken probe ARTIFACT_ID --as PERSON       # generate grounded questions, grade answers, record a vouch on pass
ken coverage                            # report covered/total, ratio, and the orphan hotlist
```
