# Khala Docs — Design System

The visual system for the Khala documentation site (`docs/`, Astro Starlight).
Canonical source for tokens, type, and component rules. The implementation lives
in `src/styles/theme.css` (wired via `customCss` in `astro.config.mjs`).

> Note: this file is a repo guardrail. It sits outside the Astro content tree,
> so it is **not** published or link-checked on the site.

## Design language

Restraint over decoration: Swiss-typographic (Vercel/Linear) meets engineering
blueprint (Stripe/Warp). Quality is signalled by confident typography, precise
spacing, and 1px hairlines — **not** by glow, gradients, or ornament.

## Color tokens

Defined in `theme.css` under `:root` / `[data-theme]`. Dark is the default;
light is a derived Swiss-paper variant.

| Token | Dark | Light | Use |
|---|---|---|---|
| `--kh-bg` | `#0a0c10` | `#fbfbfc` | Page background (flat) |
| `--kh-surface` | `#0e1117` | `#ffffff` | Cards, code, diagram nodes |
| `--kh-surface-2` | `#11161d` | `#f4f6f8` | Hover / raised |
| `--kh-hairline` | `rgba(255,255,255,.10)` | `rgba(20,24,31,.10)` | Borders / rules |
| `--kh-hairline-strong` | `rgba(255,255,255,.16)` | `rgba(20,24,31,.18)` | Hover / emphasis |
| `--kh-grid` | `rgba(255,255,255,.05)` | `rgba(20,24,31,.05)` | Blueprint grid |
| `--kh-fg` | `#e9ecf1` | `#14181f` | Headings / primary text |
| `--kh-fg-muted` | `#aab2bf` | `#3a424e` | Body text |
| `--kh-fg-dim` | `#7b8492` | `#6b7480` | Captions / labels |
| `--kh-accent` | `#6fb0e6` | `#2f6fa8` | The one accent — lines, marks, links |
| `--kh-accent-line` | `rgba(111,176,230,.55)` | `rgba(47,111,168,.50)` | Diagram accent strokes |
| `--kh-verified` | `#d8b25c` | `#d8b25c` | Rare semantic — verified/approved only |

## Typography

- **Sans**: Hanken Grotesk Variable (self-hosted). Headings use the same family,
  weight 600–700, negative tracking, flat color.
- **Mono**: JetBrains Mono Variable. Promoted to a functional role — eyebrows,
  section labels, diagram labels, code.
- Sora (display) is **removed**. No gradient clip-text.

## Components

- **Buttons**: one solid foreground button (`--kh-fg` background, `--kh-bg` text)
  + text links with an arrow. `--kh-radius-sm` corners. No pill curvature, no glow.
- **Cards**: flat `--kh-surface` + `--kh-hairline`; hover lifts the border to
  `--kh-hairline-strong` and the fill to `--kh-surface-2`. No translucent
  gradients, no top-accent glow line, no drop-shadow lift.
- **Blueprint grid**: `.kh-blueprint` utility — hero/landing surfaces only,
  never body content.
- **Motion**: simple 0.15s color/border transitions. No glow animation, no
  perpetual transforms.

## Do / Don't

| Do | Don't |
|---|---|
| Flat surfaces, hairlines | Atmospheric / radial background gradients |
| Accent on 1px lines, marks, links | Accent as fill, background, or glow |
| Confident flat headings | Gradient clip-text headlines |
| Mono labels as structure | Decorative "chip" clutter |
| Line-art schematic diagrams | Glowing box-and-arrow flowcharts |
| Gold only for verified/approved | Gold (or any 2nd color) as decoration |
