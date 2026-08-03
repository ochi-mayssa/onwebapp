# Branding Service App

Django app for the enterprise **Branding Service** — a client-facing 4-step wizard for brand identity intake, plus a full staff team dashboard for reviewing, assigning, prioritizing and tracking branding requests on a drag-and-drop board.

**URL Prefix:** `/branding/`
**App Namespace:** `branding`

---

## Table of Contents

- [Overview](#overview)
- [File Structure](#file-structure)
- [Models](#models)
- [Views & URLs](#views--urls)
- [Templates](#templates)
- [Static Assets](#static-assets)
- [Admin](#admin)
- [Seed Command](#seed-command)
- [Access Control](#access-control)
- [User Flow](#user-flow)
- [Tests](#tests)
- [Dependencies](#dependencies)
- [Known Issues](#known-issues)

---

## Overview

The Branding Service lets clients submit a structured brand identity request through a **4-step wizard**:

1. **Company Information** — company name, industry, website, country, business description.
2. **Brand Identity** — company description, target audience, brand values, preferred colors, current branding assets.
3. **Upload Assets** — drag-and-drop file uploads (logos, guidelines, inspiration, documents) plus notes.
4. **Brand Collection** — pick a curated identity collection from a filterable library.

After submission the request enters the staff pipeline:
`PENDING_REVIEW → IN_REVIEW → ASSIGNED → DESIGNING → WAITING_CLIENT → REVISION → APPROVED → COMPLETED` (or `ARCHIVED`), all tracked in a timeline.

Staff workflow tools include a **filters + stat-cards dashboard**, a **drag-and-drop Kanban board**, per-request **milestone stepper**, **priority** and **estimated-delivery** controls, **internal notes**, **asset versioning** (replace + snapshot), and an in-app **notification center** with unread badge in the header.

---

## File Structure

```
branding/
├── admin.py                 # Admin registrations (request + assets/timeline/versions/notifications)
├── apps.py
├── context_processors.py    # branding_context: unread notification count for the header badge
├── forms.py                 # Staff edit form (BrandingRequestForm incl. priority + EDD)
├── management/
│   └── commands/
│       └── seed_brand_collections.py   # Seeds 24 collections + generated covers
├── migrations/
│   ├── 0001_initial.py
│   └── 0002_brandingassetversion_brandingnotification_and_more.py
├── models.py                # BrandCollection, BrandingRequest, BrandingAsset,
│                            # BrandingAssetVersion, BrandingTimeline, BrandingNotification
├── templatetags/
│   └── branding_extras.py   # get_item, status_label, join_display, duration_display filters
├── templates/
│   └── branding/
│       ├── base.html
│       ├── dashboard.html
│       ├── kanban.html
│       ├── landing.html
│       ├── notifications.html
│       ├── partials/
│       │   ├── collection_card.html
│       │   └── wizard_step.html
│       ├── request_detail.html
│       ├── request_edit.html
│       ├── submitted.html
│       └── wizard.html
├── tests.py                 # 24 wizard + dashboard/kanban/notification tests
├── urls.py                  # app_name = 'branding'
└── views.py
```

---

## Models

### `BrandCollection`
A curated brand identity collection shown in the Step 4 library.

| Field | Type | Notes |
| --- | --- | --- |
| `category` | CharField | `COLLECTION_CATEGORIES` codes (manufacturing, healthcare, restaurant, construction, education, finance, real_estate, saas) |
| `name` | CharField | Display name |
| `slug` | SlugField | Unique |
| `industry` | CharField | Target industry label |
| `description` | TextField | |
| `style_tags` | JSONField | List of style labels |
| `examples` | JSONField | List of deliverable examples |
| `preview_image` | ImageField | Stored under `media/branding/collections/` |
| `accent_color` | CharField | Hex, default `#6366f1` |
| Preview kit | ImageField | `hero_image`, `logo`, `typography`, `business_card`, `presentation`, `letterhead`, `email_signature`, `social_media`, `brand_guidelines` |
| Palette/fonts | | `color_palette` (JSON), `fonts` (JSON) |
| `is_active` | BooleanField | Default `True` |
| `sort_order` | PositiveIntegerField | |

Helper: `preview_items` property groups the kit images for the detail page.

### `BrandingRequest`
The branding project intake captured through the wizard.

| Field | Type | Notes |
| --- | --- | --- |
| `request_number` | CharField | Auto `BR-{year}-{pk:05d}`, unique |
| `user` | FK → AUTH_USER_MODEL | related_name `branding_requests` |
| `status` | CharField | `STATUS_CHOICES`: DRAFT, PENDING_REVIEW, IN_REVIEW, ASSIGNED, DESIGNING, WAITING_CLIENT, REVISION, APPROVED, COMPLETED, ARCHIVED |
| `priority` | CharField | `PRIORITY_CHOICES`: LOW, MEDIUM, HIGH, URGENT (default MEDIUM, indexed with status) |
| `estimated_delivery_date` | DateField | Nullable |
| `completed_at` | DateTimeField | Nullable, set when a request is marked COMPLETED |
| `current_step` | PositiveIntegerField | Default 1 |
| Step 1 fields | | `company_name`, `industry`, `website`, `country`, `business_description` |
| Step 2 fields | | `company_description`, `target_audience`, `brand_values` (JSON), `preferred_colors` (JSON), `current_branding` (JSON) |
| Step 3 fields | | `additional_notes` |
| Step 4 | | `collection` FK → BrandCollection |
| Workflow | | `designer` FK → user, `internal_notes` |

Helpers: `log()` appends a timeline entry; `is_draft` property; `completion_time_display` formats turnaround; `save()` assigns `request_number` on first save.

### `BrandingAsset`
A file uploaded as part of a request. Stored at `media/branding/requests/<pk>/assets/<filename>`. Auto-detects `asset_type` (logo, brand_guidelines, inspiration, document, image, archive, other) from content-type/extension. `is_image` property, `size_display` formatting. Has many `versions` (see below).

### `BrandingAssetVersion`
Snapshot of an asset created by staff via "replace" — the old file becomes a version.

| Field | Notes |
| --- | --- |
| `asset` | FK → BrandingAsset (related_name `versions`) |
| `file` | Stored under the asset folder |
| `version_number` | Sequential, starts at 1 |
| `original_name`, `content_type`, `size` | Snapshot of the replaced file |
| `note` | Reason / changelog |
| `uploaded_by` | FK → user |
| `created_at` | |

### `BrandingTimeline`
Audit trail of `CREATED`, `STATUS_CHANGE`, `ASSIGNMENT`, `NOTE`, `UPLOAD`, `FILE_UPDATE`, `COLLECTION_CHANGE`, `PRIORITY_CHANGE`, `DELIVERY_CHANGE`, `COMMENT` events with `action`, `description`, `actor`, `created_at`.

### `BrandingNotification`
In-app notification with `recipient`, `request`, `notification_type` (`DESIGNER_ASSIGNED`, `NEW_REQUEST`, `STATUS_CHANGED`, `COMPLETED`, `COMMENT`, …), `message`, `url`, `is_read`, `created_at`. `mark_read()` convenience method. Emails are sent best-effort when an `email_subject` is supplied to `_notify`.

---

## Views & URLs

All routes under `app_name = 'branding'`:

| URL | Name | View | Access |
| --- | --- | --- | --- |
| `/branding/` | `landing` | `landing` | Public |
| `/branding/wizard/` | `wizard` | `wizard` | Login required |
| `/branding/wizard/step/<int:step>/` | `wizard_step` | `wizard_step` | Login required |
| `/branding/wizard/autosave/` | `wizard_autosave` | `wizard_autosave` | Login required (JSON) |
| `/branding/wizard/upload/` | `upload_file` | `upload_file` | Login required |
| `/branding/upload/<int:asset_id>/delete/` | `delete_asset` | `delete_asset` | Owner |
| `/branding/requests/<str:request_number>/` | `submitted` | `submitted` | Owner or staff |
| `/branding/dashboard/` | `dashboard` | `dashboard` | Staff |
| `/branding/kanban/` | `kanban` | `kanban` | Staff |
| `/branding/kanban/move/` | `kanban_update` | `kanban_update` | Staff (POST JSON) |
| `/branding/requests/<int:pk>/` | `request_detail` | `request_detail` | Staff |
| `/branding/requests/<int:pk>/assign/` | `assign_designer` | `assign_designer` | Staff |
| `/branding/requests/<int:pk>/status/` | `update_status` | `update_status` | Staff |
| `/branding/requests/<int:pk>/priority/` | `update_priority` | `update_priority` | Staff |
| `/branding/requests/<int:pk>/delivery/` | `update_delivery` | `update_delivery` | Staff |
| `/branding/requests/<int:pk>/notes/` | `update_internal_notes` | `update_internal_notes` | Staff |
| `/branding/requests/<int:pk>/note/` | `add_note` | `add_note` | Staff |
| `/branding/requests/<int:pk>/archive/` | `archive_request` | `archive_request` | Staff |
| `/branding/requests/<int:pk>/edit/` | `edit_request` | `edit_request` | Staff |
| `/branding/assets/<int:asset_id>/download/` | `download_asset` | `download_asset` | Staff |
| `/branding/assets/<int:asset_id>/replace/` | `replace_asset` | `replace_asset` | Staff (POST) |
| `/branding/asset-versions/<int:version_id>/download/` | `download_asset_version` | `download_asset_version` | Staff |
| `/branding/notifications/` | `notifications` | `notifications` | Login required |
| `/branding/notifications/<int:pk>/read/` | `mark_notification_read` | `mark_notification_read` | Owner (POST JSON) |

> **Note:** the `<int:pk>` staff routes are registered **before** the `<str:request_number>` submitted route so numeric paths resolve to request detail.

### Key behaviors

- `wizard_step` supports `action=next | prev | submit`, AJAX responses via `X-Requested-With`, per-step validation (`_validate_step`), and clamps `step` to `1..4`. Invalid step data is discarded (`refresh_from_db`) so previously saved fields survive failed submissions.
- `wizard_autosave` reads JSON `{step, data}` and whitelists fields per step.
- `upload_file` caps files at **50 MB**, detects asset type, and returns JSON `{ok, id}`.
- `dashboard` excludes `DRAFT` and supports **all** filters — `?q=` (company/request number/client), `?status=`, `?industry=`, `?collection=`, `?designer=`, `?priority=`, `?date_from=` / `?date_to=` — paginates by 12, and computes per-status counts plus monthly volume and average completion time.
- `kanban` groups requests into 7 columns (ARCHIVED excluded); `kanban_update` handles drag-and-drop JSON moves and logs/notifies via `_set_status`.
- `_set_status` centralizes transitions: timeline logging, client notification on status change, `completed_at` bookkeeping, and manager notification on completion.
- `assign_designer` flips `PENDING_REVIEW`/`IN_REVIEW` → `ASSIGNED` and notifies the designer.
- `replace_asset` snapshots the previous file as a `BrandingAssetVersion`, then swaps in the new file and logs `FILE_UPDATE`.
- `context_processors.branding_context` (registered in `websity_project/settings.py`) exposes `unread_notifications` for the header bell badge.

---

## Templates

- `base.html` — extends the project root `base.html`, adds `branding.css` / `branding.js` via `extra_css` / `extra_js` blocks; header shows a notification bell with unread badge, theme toggle, and staff-only Dashboard/Board links.
- `landing.html` — public marketing/landing page for the service.
- `wizard.html` + `partials/wizard_step.html` — progress bar + 4 step panels; step 4 renders collection cards.
- `partials/collection_card.html` — collection card with select radio.
- `submitted.html` — confirmation page; requires `branding_request` context var.
- `dashboard.html` — 8 quick-filter stat cards, monthly/avg-completion/archived metric cards, full filter toolbar, requests table (request id, company, industry, collection, designer, priority, status, created/updated, actions incl. inline assign modal), pagination + empty state.
- `kanban.html` — draggable board; cards post `{request_id, status}` to `kanban_update`, columns re-count on drop.
- `notifications.html` — read/unread list with per-item mark-read.
- `request_detail.html` — milestone stepper, status/priority/delivery/designer toolbar, 7 tabs (company, identity, uploads with download/replace/version dropdown, selected collection, internal notes editor + timeline notes, timeline, status history).
- `request_edit.html` — staff edit form (includes priority + estimated delivery date).

`partials/wizard_step.html` must `{% load branding_extras %}` at the top before using the `get_item`/`join_display` filters.

---

## Static Assets

- `static/css/branding.css` — premium styling (wizard panels, collection cards, drag-drop, stat cards, metric cards, priority badges, status pills, Kanban board, milestone stepper, notification list, filter toolbar, utilities).
- `static/js/branding.js` — drag-and-drop uploads, debounced autosave, collection filter/preview/select, panel swap. (Drag-drop wiring for the board lives inline in `kanban.html`.)

---

## Admin

`branding/admin.py` registers `BrandCollection`, `BrandingRequest` (with inline `BrandingAssetInline` and `BrandingTimelineInline`), `BrandingAssetVersion` and `BrandingNotification`. The request fieldsets include workflow fields (`priority`, `estimated_delivery_date`, `completed_at`, `designer`, `internal_notes`).

---

## Seed Command

```bash
python manage.py seed_brand_collections
```

Seeds 24 brand collections across the 8 categories, generates placeholder cover images into `media/branding/collections/`, and fills the preview-kit image fields where available. Slugs are derived from names (`&- and-` normalized).

---

## Access Control

- Wizard, autosave and uploads: `@login_required`.
- Asset delete: owner only (403 otherwise).
- Submitted page: owner or staff.
- Dashboard, Kanban, request detail, assign, status, priority, delivery, notes, archive, edit, asset download/replace: `@staff_member_required`.
- Notifications page: any authenticated user; mark-read restricted to the notification's recipient.

---

## User Flow

1. Client visits `/branding/`, reads the landing page, starts the wizard.
2. Fills steps 1–4 (data auto-saved), uploads assets, picks a collection.
3. Submits → request becomes `PENDING_REVIEW`, all staff are notified, redirect to `/branding/requests/<request_number>/`.
4. Staff see it on `/branding/dashboard/` (or the Kanban board), open the detail, set priority + delivery date, assign a designer, change status, add internal notes, replace asset files.
5. Designers and the client receive in-app notifications (and best-effort email) on assignment and status changes; completion notifies managers.
6. Timeline records every status change, assignment, note, upload, file replacement, priority change and delivery update.

---

## Tests

```bash
python manage.py test branding
```

`branding/tests.py` (24 tests) covers: landing, wizard auth + draft creation, full 4-step flow + validation + submit, prev navigation, autosave, upload/delete + oversize rejection, dashboard access/filtering (status + priority), detail tabs, assign/status/note/archive, edit form, Kanban columns + drag update + invalid-status rejection, priority/delivery updates, and notifications + mark-read.

---

## Dependencies

- Django 5.x, Pillow (for generated covers).
- WeasyPrint emits GTK `libgobject` warnings on some machines (harmless, unrelated to this app).
- Uses project theme vars (`--b-*` in `static/css/theme.css`), Inter + Plus Jakarta Sans, Lucide, Bootstrap 5.3, Font Awesome 6, Bootstrap Icons.
- Run Django via `venv\Scripts\python.exe manage.py ...` (`.venv` is broken on other machines; both venvs are git-committed).

---

## Known Issues

- The wizard JS and Kanban drag-drop should still be exercised in a real browser end-to-end (server-side rendering and route reachability are covered by tests).
- No production email backend configured; `_send_email` falls back to console/`fail_silently` (SMTP settings researched but not applied).
