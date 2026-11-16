# Design guide

The landing page (`site/`) and the demo console (`capabilities/demo-console/`) follow this guide. EcoTrace is a reporting tool for accountants and auditors, so it should read like one: plain, dense, and exact about numbers.

## Fonts

| Use | Font | Weights | License |
|---|---|---|---|
| Headings and text | [Be Vietnam Pro](https://fonts.google.com/specimen/Be+Vietnam+Pro) | 400, 500, 600, 700 | OFL-1.1 |
| Figures, file names, code | [IBM Plex Mono](https://fonts.google.com/specimen/IBM+Plex+Mono) | 400, 500 | OFL-1.1 |

Load both from Google Fonts with `display=swap`. Fallbacks: `Arial, sans-serif` and `monospace`.

| Text | Size | Weight |
|---|---|---|
| Landing page title | 52 px | 700 |
| Section title | 34 px | 700 |
| Screen title (console) | 26 px | 700 |
| Card title | 16–18 px | 600 |
| Body | 15 px, line height 1.55 | 400 |
| Labels, captions | 13 px | 500 |

## Colours

| Token | Value | Use |
|---|---|---|
| `--bg` | `#F7F6F2` | Page background |
| `--surface` | `#FFFFFF` | Cards, tables |
| `--surface-muted` | `#FAFAF7` | Table header rows |
| `--text` | `#1D2420` | Text, top bar of the console |
| `--text-muted` | `#5A615C` | Secondary text |
| `--accent` | `#2E6B4F` | Primary buttons, links, the active menu item |
| `--accent-soft` | `#E9EFE9` | Active menu item background, the total figure |
| `--warning` | `#A84E28` | Fields below the confidence threshold, items waiting for an action |
| `--warning-soft` | `#FBF1EC` | Background of a flagged table row |
| `--border` | `#DCD9D0` | Card and section borders |
| `--rule` | `#ECEAE3` | Lines between table rows |

All text and background pairs above reach a 4.5:1 contrast ratio.

## Layout

- Content is at most 1200 px wide on the landing page and 1180 px in the console.
- Spacing steps: 4, 8, 12, 16, 24, 32, 48, 80 px.
- The console has a dark top bar and a side menu. Below 600 px wide, the menu stacks above the content.
- Wide tables scroll inside their own box; the page never scrolls sideways at 360 px.

## Components

- **Buttons:** 44 px high, 4 px radius. One primary (filled `--accent`) button per screen or card; the others are outlined or text buttons.
- **Cards:** `--surface`, 1 px `--border`, 4 px radius, no shadow.
- **Tables:** header row in `--surface-muted` with 13 px muted labels. Figures are in IBM Plex Mono and right-aligned.
- **Status:** text in the status colour, or a 1 px outlined badge. No filled pills.
- **Confidence:** a 4 px bar with the percentage next to it; it uses `--warning` when it is below the company's threshold.

## Rules

- No gradients, shadows, blur, emoji or decorative icons.
- Use one accent colour; the warning colour is only for things that need attention.
- Show real values from the demo data, never invented statistics.
- Every control is a real `<button>`, `<a>` or `<input>` with a label.
