# Cat's Cradle — design language

Taken from the reference plate: an engraved tabby asleep on a cushion, under a sunburst, inside a
filigree border, printed in a single aubergine ink on pale ground. Everything below is derived from
that plate — one ink, one ground, one highlight, and hairline line work doing all the ornament.

## Palette

| Token | Value | Use |
|---|---|---|
| `--cc-ink` | `#1B0F26` | page ground |
| `--cc-panel` | `#241432` | cards, inputs |
| `--cc-panel-2` | `#2E1A3F` | hover, nested rows |
| `--cc-rule` | `#4A2F63` | hairlines, borders, engraved separators |
| `--cc-paper` | `#EFE3F2` | primary text |
| `--cc-muted` | `#B79BC8` | secondary text, metadata |
| `--cc-accent` | `#B48CD9` | one accent: primary action, focus ring, verdict `runs` |
| `--cc-warn` | `#D9A66B` | `needs a key`, `upstream` — the only non-purple, used sparingly |
| `--cc-fail` | `#C9637A` | `broken`, destructive |

Rules: never more than one accent-coloured element per region. Never a pure black or pure white.
Borders are 1px `--cc-rule`; the double rule (1px / 3px gap / 1px) is reserved for the page frame
and the hero.

## Type

- **Display** — a serif with old-style proportions (Cormorant, EB Garamond, or `Iowan Old Style`
  if installed). Page name, section headings. Letter-spacing `+0.01em`, never bold-heavy.
- **Body** — the app's UI sans. 0.8–0.85rem, line-height 1.45.
- **Metadata** — monospace, 0.6–0.68rem, `--cc-muted`. Versions, tool names, file counts,
  verdict times. Monospace is the "ledger" voice: everything a judge can verify is monospace.

## Ornament

- **Sunburst**: fine radial hatch behind the hero only, 1px lines at `--cc-rule` at 12% opacity.
  It marks the one "hero" moment; do not repeat it on tiles.
- **Filigree**: CSS corner sprays or a small engraved-style divider SVG between sections. Nothing
  decorative inside a card — the engraving stays at the frame.
- **Hairline discipline**: content is separated by 1px rules and spacing, never by drop shadows.
  No `box-shadow`, no rounded corners above 4px, no gradients except the single hero scrim.

## The cat

One engraving per page, in the header, left of the wordmark — the asleep tabby at ~96px, ink-on-
paper inverted for the dark ground (the plate's ground becomes transparent, the ink becomes
`--cc-paper` at 70%). Never repeated per tile; the only other cat is a 12px paw print as a section
terminator if one is needed.

## Layout

- Page frame: 1px double rule inset 16px, page content inside it. That frame is the plate's border.
- Header: `[cat] CAT'S CRADLE` in display serif + one line of thesis under it, verdict counts
  right-aligned in monospace (`3 run · 1 needs a key`).
- Build: source pills (a skill / a cron job / describe it), one primary action. No dropdown where a
  pill row fits.
- Tiles: 2-up grid. Title + verdict pill on one line, the verdict sentence directly under it,
  description clamped to two, then monospace metadata, then actions (visible on hover, always
  visible on focus).
- Result card: a ledger — `spec · files · validate · dispatch` — each row monospace with a tick or
  the exact failing line. Never a green "all good" badge without the line beneath it.

## Verdict vocabulary (colour + word, never colour alone)

| Verdict | Pill | Sentence |
|---|---|---|
| `works` | accent | "search_wikipedia returned real results" |
| `needs-key` | warn | "sound package, needs a key: set TENOR_API_KEY" |
| `upstream` | warn | "request works, far end refused it: HTTP 403" |
| `scaffold` | fail | "broken: scaffold — handler never got written" |
| `broken` | fail | "broken: <the loader's own error line>" |

Colour is a hint; the sentence carries the fact. A reviewer must be able to read the page in
greyscale and still know which plugin runs.
