# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

User-specified plain HTML, CSS and JavaScript, no framework, in this directory.

## Users

Managers inspecting assessed logistics orders and their supporting evidence.

## Product Purpose

Show the 20 committed sample orders with separate status, guarantee, revised
ETA, cause, fault party, late days and payment. Support evidence inspection.
Display the supplementary A2 COD refusal risk reason: high in red and medium
in amber, without changing logistics status or attributing customer fault.

## Capabilities and Constraints

Read the existing sample first and an authenticated same-origin API later.
Preserve A2 facts; missing ETA is unknown. Inspection does not approve an action
or establish source trust. All data is text; no generated orders or source writes.
The HTTP API and persistent verification workflow remain owned by Truc/platform.

## Evidence on Hand

`../sample_orders.json` contains 20 orders assessed at 2026-10-28 12:00 Vietnam
time. The existing Chợ Phố prototype provides incumbent visual context.

## Open Decisions

The team has not supplied a persistent evidence-review API for this surface.
The current button opens evidence for inspection and does not record approval.
