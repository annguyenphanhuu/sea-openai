---
name: "Chợ Phố logistics"
description: "A compact operational order list with inline evidence inspection."
colors:
  green: "#236148"
  forest: "#183d30"
  ink: "#24372f"
  muted: "#596b60"
  line: "#dce3db"
  paper: "#fff"
  ivory: "#f5f6f2"
  table-head: "#f3f5ef"
  hover: "#edf3eb"
  selected: "#edf3e9"
  evidence: "#f6f8f2"
  focus: "#a26a19"
  late-ink: "#973e2d"
  late-surface: "#fae9e3"
  risk-ink: "#81510d"
  risk-surface: "#fcf0d6"
  customer-ink: "#71503c"
  customer-surface: "#f2ebe2"
  unknown-ink: "#475d75"
  unknown-surface: "#e9eff5"
  watch-ink: "#5c6332"
  watch-surface: "#f0f1dc"
  track-ink: "#2d6541"
  track-surface: "#e8f0e3"
typography:
  body:
    fontFamily: "Segoe UI, Arial, sans-serif"
  headline:
    fontSize: "28px"
    fontWeight: 650
    letterSpacing: "-.6px"
  title:
    fontSize: "18px"
  subtitle:
    fontSize: "15px"
  table-body:
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
  supporting:
    fontSize: "12px"
  status:
    fontSize: "11px"
    fontWeight: 650
    lineHeight: 1.4
  code:
    fontFamily: "Consolas, monospace"
    fontSize: "11px"
rounded:
  chip: "4px"
  inset: "5px"
  control: "6px"
  section: "8px"
spacing:
  small: "8px"
  compact: "12px"
  regular: "16px"
  section: "20px"
  spacious: "24px"
components:
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "9px 13px"
  button-text:
    backgroundColor: "transparent"
    textColor: "{colors.green}"
    rounded: "{rounded.control}"
    padding: "5px 8px"
  button-evidence:
    backgroundColor: "transparent"
    textColor: "{colors.green}"
    rounded: "{rounded.control}"
    padding: "6px 8px"
  button-evidence-expanded:
    backgroundColor: "{colors.green}"
    textColor: "{colors.paper}"
    rounded: "{rounded.control}"
    padding: "6px 8px"
  search:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "9px 12px 9px 39px"
    height: "42px"
  status-late:
    backgroundColor: "{colors.late-surface}"
    textColor: "{colors.late-ink}"
    rounded: "{rounded.chip}"
    padding: "4px 7px"
    typography: "{typography.status}"
  orders-section:
    backgroundColor: "{colors.paper}"
    rounded: "{rounded.section}"
  evidence-panel:
    backgroundColor: "{colors.evidence}"
    padding: "24px"
---

# Design System: Chợ Phố logistics

## Overview

**Creative North Star: "Chợ Phố operations desk"**

The implemented surface inherits Chợ Phố's green and ivory operational identity. Compact rows, restrained status fills and visible separators support repeated comparison; evidence opens directly under its order.

**Key Characteristics:**

- Green identity with quiet ivory and white surfaces.
- Dense, explicitly labelled operational facts.
- Flat containers and evidence shown in context.

This record is extracted from `styles.css`, `index.html` and `app.js`. It records source behavior; rendered appearance has not been visually verified.

## Colors

### Primary

Forest anchors the masthead. Green identifies evidence controls and text actions; an expanded evidence control uses a solid green fill.

### Secondary

Status pairs communicate exception/late, risk, customer fault, unknown feed, watch/slow-safe and on-track states. Status text accompanies every fill. Amber is reserved for the visible focus outline.

### Neutral

Ivory surrounds white work surfaces. Ink carries primary facts; muted green-gray carries context. Pale table headers, selected rows and evidence surfaces separate information without shadows.

**The Labelled Status Rule.** Every status color is accompanied by a readable status label.

## Typography

Segoe UI with Arial and sans-serif fallbacks is the implemented interface stack. Consolas with a monospace fallback identifies raw codes and records. The frontmatter records the actual source values, without introducing a separate display face.

The hierarchy steps from the page headline to section titles, subsection titles, table facts and supporting labels. Paragraphs use a line-height of 1.55; table facts use their dedicated compact rhythm. Dates and lateness use tabular numerals. Evidence explanatory copy is limited to 75ch. At the phone breakpoint the headline becomes 25px and input/select text becomes 16px.

## Layout

The centered main container has a maximum width of 1760px and desktop side padding of 32px. The masthead has a minimum height of 68px. Toolbar spacing uses a wrapping flex row; the search can grow while filters retain usable widths. The desktop order table has nine fixed columns, a minimum width of 1220px and a horizontal scroll wrapper.

At 1000px and below, page gutters become 20px and search occupies a full toolbar row. At 680px and below, gutters become 12px, the heading stacks, the workspace label hides and the filters form a two-column grid with full-width search and sorting. Each order becomes a two-column labelled record: cause and evidence action span both columns. The underlying table headings remain available to assistive technology.

Evidence stays inline at both widths. Its inner tables keep a 740px minimum width and scroll within a bounded area: 370px tall on desktop, 390px on phones. Their headers are sticky. The evidence metadata and footer stack on phones.

**The Separate Dates Rule.** Keep the guaranteed date and revised ETA visibly separate at every breakpoint.

## Elevation & Depth

The source defines no shadows or animation. Thin borders, surface tones and an expanded-row fill establish grouping. Evidence is inserted in document flow, without a modal or floating layer.

## Shapes

Controls use gently rounded corners; section containers are slightly softer and status labels remain compact. Borders are generally one pixel. The existing radius scale is recorded in the frontmatter. Small stroke SVGs accompany search and reload; they supplement text and are not glyph substitutes.

## Components

- **Buttons:** secondary controls use white surfaces and borders; text actions use green on transparent backgrounds. Hover uses the pale green surface and a stronger border. The shared keyboard treatment is an amber 3px outline with a 3px offset. Disabled buttons use 0.6 opacity.
- **Evidence action:** a bordered green-text control fills green when expanded. It is at least 36px tall on desktop and 44px on phones. The selected order receives a pale green row fill. Opening evidence is inspection, not a recorded approval.
- **Fields:** labelled search and native selects use white surfaces, one-pixel borders, rounded corners and 42px height. The search icon sits inside a reserved left inset.
- **Status labels:** short text on lightly tinted rectangular chips. Exception and late share a pair; watch and slow-safe share a pair.
- **Order container:** one bordered white section contains filters, result count, list and load/empty/error feedback. Desktop row cells use 17px vertical and 12px horizontal padding.
- **Evidence panel:** a pale inset section with a heading, close control, metadata, source tables and native JSON disclosure. Text and raw values wrap; wide evidence tables scroll independently.
- **Masthead:** a compact identity and workspace header with a source badge. It is not a navigation menu.

## Do's and Don'ts

- Do preserve Chợ Phố's green and ivory identity.
- Do retain textual status labels and explicit field labels on phones.
- Do show evidence in the context of its order.
- Don't merge guaranteed dates and revised estimates into one value.
- Don't present evidence inspection as an approval or trust grant.
- Don't introduce a new visual identity for this manager surface.
