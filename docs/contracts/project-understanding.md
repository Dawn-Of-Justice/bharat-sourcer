# Project understanding, titles and inferred details (v0.19.0)

Makers should not have to supply what the project already implies. After analysing a
video or project page, the backend now returns what the model understood about the
project, an editable title and description, quantities decided from context, and
pre-filled part requirements ("build details"). Everything inferred is labelled; nothing
is presented as verified.

## `Job.project` (nullable)

```json
{
  "title": "Obstacle-avoiding robot car",
  "title_source": "ai",
  "description": "A two-wheel Arduino robot that steers around obstacles.",
  "description_source": "ai",
  "summary": "An Arduino UNO reads an HC-SR04 and drives two BO motors through an L298N...",
  "power": "2x 18650 cells (7.4 V)",
  "controller": "Arduino UNO (5 V logic)",
  "interfaces": ["PWM to motor driver", "GPIO trigger/echo"],
  "assumptions": ["Motor driver is fed from the battery pack"],
  "origin": "ai_inferred"
}
```

Example values are illustrative, not real output.

- `title` (≤ 120 chars) and `description` (≤ 600 chars) are written by the model and are
  **editable by the owner**. `*_source` is `ai` or `user` (who wrote the current value).
- `summary` is the model's understanding after watching or reading the source. It is
  **not editable**. Show it to the user, labelled as AI understanding to check.
- `power`, `controller`, `interfaces` and `assumptions` are optional context. Show
  `assumptions` so users can spot wrong inferences.
- `project` is `null` for projects analysed before v0.19.0 and while extraction runs.
  Any field may be `null`.
- Demo jobs return a project titled `Demo: …`; keep the demo label visible.

## Editing the title or description

`POST /v1/jobs/{job_id}/project` with the usual access headers (job token, or the account
or guest session plus the `X-Requested-With` CSRF header when auth is enabled):

```json
{"title": "My robot", "description": "Weekend build for my nephew"}
```

- Send either field or both. Values are trimmed; blank values and an empty body return
  422. Limits: title 1–120, description 1–600 characters.
- Returns the full `Job`. The edited field's `*_source` becomes `user`; the summary is
  unchanged. Works in any job status, including on older jobs without a project.
- Edits do not consume the daily action quota and never call the model.

## Saved projects list

`GET /v1/projects` items gain nullable `title`, `description` and `summary`.

Recommended project card, replacing "www.youtube.com project" plus the raw URL:
1. Title: `title`, falling back to the current host-based label when null.
2. Below it: `description`, falling back to the source URL when null. Keep the source URL
   available as a secondary link.
3. Offer rename/edit on the project page, using the endpoint above.

## Inferred quantities

`items[].qty` is now always a positive integer after extraction.

- `qty_source`: `stated` (the source gives the count), `inferred` (decided from project
  context, for example two wheels for two motors) or `user` (edited by the owner).
- `qty_reason`: short explanation for inferred counts, otherwise `null`.
- Show an "inferred" marker and the reason; the user can still change the count. Editing
  the quantity to a different value sets `qty_source: "user"`.
- Confirmation no longer fails with `UNKNOWN_QUANTITY`. Any remaining null count (older
  jobs) is set to 1 with `qty_source: "inferred"` and a reason on confirmation.

## Inferred requirements ("build details")

`items[].requirements[]` entries gain:

- `origin`: `user` (default) or `inferred` (proposed by the model from project context).
- `reason`: why the requirement applies in this project, for inferred entries.

Inferred requirements are measurable specs with units (v0.19.1), prefer ranges (`at_least` / `at_most`) and never name a brand or
exact model the source does not show. They feed seller research and AI assessments like
user requirements do. The requirements list is replaced as a whole on update: send
untouched inferred entries back with their `origin` and `reason`, and send edited entries
without `origin` so they become `user`.

## Frontend status

The review page already shows `project` (summary, power, controller, interfaces,
assumptions), inferred quantity markers and AI-inferred build details. The title and
description display, the project-list card change and the edit control are not yet built
in the frontend.

## Live check (5 October 2026, v0.19.0)

A YouTube Short of an ESP32-S3 piezo drum trigger produced the title "ESP32-S3 USB-MIDI
Piezo Drum Trigger", an accurate summary (piezo → resistor conditioning → ADC → native
USB-MIDI, LED feedback), power and interfaces, and an inferred count of four jumper wires
with a reason. Requirements were mostly descriptive ("type: piezo disc"), which v0.19.1's
prompt addresses. One video does not establish accuracy.
