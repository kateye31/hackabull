# Product

<!-- impeccable:product-schema 1 -->

> Written from the team's brief without an interview (the user asked to proceed without questions). Items marked *(inferred)* are assumptions to confirm.

## Platform

web

## Stack

Delegated *(inferred)*: Python. Streamlit for the reviewer app (`app.py`), FastAPI for the residents' backend and website (`api/`, `web/`), plain HTML/CSS/JS for the residents' page (no framework, no build step), SQLite shared by both.

## Users

- **Residents** of a neighborhood in the days after a hurricane. On a phone, outdoors, often in bright sun, maybe low battery and patchy signal, possibly stressed. Job: tell someone that a street, sidewalk or walkway is blocked, in under a minute.
- **The reviewer** (a neighborhood volunteer or city coordinator). On a laptop. Job: check every report, confirm the details, send it to the right office, and close it once the route is cleared.

## Product Purpose

After a hurricane, show which neighborhood routes are blocked, what's blocking them, what it takes to clear them, and who nearby can help, then confirm they were cleared. Success: a resident's photo becomes a confirmed, routed report with a response plan, and the route is later marked cleared from an after-cleanup photo.

## Positioning

Every report is compared against a photo of the same spot from before the storm (ground photo plus USGS aerial imagery), so damage is measured, not just described: share of the walkway blocked, narrowest clear width, damage index. A person confirms everything before it goes out.

## Operating Context

Before hurricane season, the reviewer photographs key routes (bus stops, curb ramps, the walkway to a shelter). After the storm, residents send photos; the reviewer works a queue: needs review → ready to report → awaiting cleanup → closed. Reports go to verified official channels only (city/county storm debris, emergency management, the electric utility).

## Capabilities and Constraints

- Residents send one photo, an optional note and their location; they never see other people's photos or notes.
- ML suggestions (DINOv2 change map, CLIP damage type, SegFormer walkway, OpenStreetMap resources, Gemini plan) are drafts for the reviewer, never facts.
- Downed power lines: always tell people to stay 35 feet away and call 911 first.
- Photos are stripped of EXIF/GPS when saved; GPS is read once to place the report.
- No login yet *(inferred: out of scope for the hackathon)*; the residents' site is separate from the reviewer app.

## Evidence on Hand

Synthetic storm-damage evaluation and a small campus pilot (README). No real neighborhood photos yet, no testimonials, no partner organizations. Do not invent any.

## Product Principles

1. Safety first: the 911 / power-line message is never hidden.
2. One minute for a resident: one photo, one tap to send.
3. A person confirms; the machine suggests.
4. Works on bad days: offline fallbacks, cached maps, no hard dependency on Gemini.

## Accessibility & Inclusion

WCAG 2.2 AA *(inferred)*. Large tap targets, readable in sunlight, works one-handed, plain language, light and dark.
