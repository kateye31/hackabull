# Design

Written from the built residents' page (`web/index.html`) and the reviewer theme (`.streamlit/config.toml`).

## World

A high-visibility safety vest: the most legible thing on a street after a storm. A charcoal masthead frames a fluorescent yellow-green wordmark, reflective edge, and primary action. The photo and location sit side by side on desktop and stack on narrow screens.

## Tokens (residents' page, `:root`)

| Token | Light | Dark | Use |
| --- | --- | --- | --- |
| `--hivis` | `#d4f000` | same | header band, primary action only |
| `--hivis-ink` | `#1b1d0e` | same | text on hi-vis (14:1) |
| `--reflect` | `#c9ced3` | `#8d949a` | the two reflective stripes |
| `--hazard` | `#b3261e` | `#ffb4a9` | downed-power-line notice only |
| `--ink` / `--ink-2` | `#16181a` / `#464c52` | `#f1f3f4` / `#b6bdc3` | text / secondary text (≥8.6:1) |
| `--ground` / `--panel` | `#f9faf5` / `#eff1e8` | `#121416` / `#1d2023` | page / inputs, photo well |

Type: Atkinson Hyperlegible (Braille Institute's legibility face), system sans fallback. Radius 12px. Tap targets ≥48px; the send button 60px.

## Signature

The retroreflective band under the header (two silver stripes), echoed as the stripe on the Send button; light sweeps across it once when a report is sent (off under reduced motion).

## Rules

- Hi-vis only on the band and the one primary action. Hazard red only for the power-line notice and errors.
- The 911 notice is always visible above the form.
- Reviewer app (Streamlit): same family, restrained: dark olive `#4a5900` primary, white ground, `#eff1e8` panels.
