# Manager order list

The user relayed the new assignment on 2026-10-31: merge A2 handoff to main,
then implement a plain HTML/CSS/JavaScript manager list under
`logistics_an_nguyen/ui`, showing the 20 committed sample orders before 13:00
Asia/Ho_Chi_Minh. This explicitly assigns this new UI to An for this task.

Each order independently exposes status, guaranteed date, revised ETA, cause,
fault party, late days, payment and an evidence inspection button. Preserve A2
facts. Null ETA stays unknown; a revised ETA never replaces the guarantee.
Evidence inspection opens source records and feed provenance; it does not grant
approval, create authority or mutate source/runtime state.

Default source is `../sample_orders.json`. A separate loader supports the same
envelope from same-origin `GET /api/orders` when the HTTP owner supplies it.
An API error must be visible, never silently replaced by sample results.
Include loading/error/empty states, search, status/payment filtering, keyboard
access, Vietnamese labels and dates in Asia/Ho_Chi_Minh. Treat all data as text.

Inherit the existing Chợ Phố prototype's restrained green/ivory visual language.
Use a broad, legible table on desktop and labeled order records on mobile.
No framework, new dependency, other-owner implementation change or hosted Site.
