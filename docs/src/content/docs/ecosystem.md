---
title: Ecosystem
description: How the tools connect — only through Khala.
---

The three producer tools never call each other directly. They connect **only through Khala**.

```mermaid
graph TD
  subgraph Khala["Khala (the link)"]
    Nexus[Nexus<br/>grounded knowledge]
  end
  Archon -->|claims / values| Nexus
  specledger -->|approved specs| Nexus
  Probe -->|queries| Nexus
  Dev[Developer] --> Archon
  Agent[Agent / Probe] --> Archon
```

- **Archon** is the single authority window: people and agents come to it to ask for domain truth.
- **Probe** is one client of that window, alongside developers.
- **specledger** publishes approved specs into Khala; it is not the source of truth (frontmatter is).
