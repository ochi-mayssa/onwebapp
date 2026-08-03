# Community App

Django app for client-facing community services featuring the **13-step Smart Client Onboarding Wizard** with auto-estimation, workspace generation, and save/resume.

**URL Prefix:** `/community/`
**App Namespace:** `community`

---

## Table of Contents

- [Overview](#overview)
- [File Structure](#file-structure)
- [Models](#models)
- [Services (Estimation Engine)](#services-estimation-engine)
- [Views & URLs](#views--urls)
- [Templates](#templates)
- [Admin](#admin)
- [Seed Command](#seed-command)
- [Access Control](#access-control)
- [User Flow](#user-flow)
- [Tests](#tests)
- [Dependencies](#dependencies)
- [Known Issues](#known-issues)

---

## Overview

The Community app provides a simplified portal for clients who need Community services. It centers on a **13-step Smart Onboarding Wizard** that guides clients through:

1. Welcome & resume
2. Service selection
3. Business information
4. Project details
5. Design preferences
6. Features & integrations
7. Auto-estimation (AI-ready engine)
8. Package selection
9. Add-ons
10. Summary review
11. Proposal
12. Payment
13. Workspace completion

The wizard features autosave (debounced AJAX), progress tracking, keyboard navigation, and generates a full project workspace (Project, Phases, Tasks, Customer record, ActivityLog) with a confirmation email on completion.

The app is gated to users with `service_type == 'community'` on their `UserProfile`.

---

## File Structure

```
community/
  __init__.py
  admin.py              # 3 models registered (ServiceType, OnboardingAddon, OnboardingSession)
  apps.py               # CommunityConfig
  forms.py              # Legacy forms (WebsiteIntakeForm, Step*Form) still used by website_building view
  models.py             # WebsiteIntake, ServiceType, OnboardingSession, OnboardingAddon
  services.py           # Estimation engine: calculate(), get_package_comparison(), EstimationResult
  urls.py               # Wizard routes + legacy URLs
  views.py              # 13 wizard step handlers + legacy views + autosave + workspace generation
  tests.py              # 36 tests (estimation engine, model, wizard view, e2e walkthrough)
  migrations/
    __init__.py
    0001_initial.py     # Creates WebsiteIntake table
    0002_*.py           # Creates ServiceType, OnboardingAddon, OnboardingSession
    0003_*.py           # Adds 11 fields to OnboardingSession
  management/
    commands/
      seed_community.py # Seeds ServiceType, OnboardingAddon, PaymentPlan

templates (global):
  templates/community/
    base_community.html        # Community-specific base layout
    home.html                  # Landing page with hero CTA → wizard
    dashboard.html             # Dashboard with Smart Onboarding card
    website_intake.html        # Legacy intake form
    website_building.html      # Legacy alternate intake form
    package_selection.html     # Legacy pricing page
    brand_assist.html          # Brand assist placeholder
    project_detail.html        # Single project view
    wizard/
      base_wizard.html         # Wizard layout: topbar, progress bar, autosave JS
      step_01_welcome.html     # Welcome / resume screen
      step_02_services.html    # Service selection cards
      step_03_business.html    # Business info form
      step_04_project.html     # Project details
      step_05_design.html      # Design preferences + color picker
      step_06_features.html    # Feature checkboxes
      step_07_estimate.html    # Auto-estimation results
      step_08_package.html     # Package comparison table
      step_09_addons.html      # Add-on selection
      step_10_summary.html     # Full project summary
      step_11_proposal.html    # Proposal view
      step_12_payment.html     # Payment details
      step_13_workspace.html   # Completion / success screen
```

---

## Models

### WebsiteIntake (Legacy)

Stores client website project requirements collected during the legacy intake process. See previous documentation.

### ServiceType

| Field | Type | Description |
|---|---|---|
| `name` | CharField(100) | Service name (e.g. "Website Development") |
| `slug` | SlugField(unique) | URL-safe identifier |
| `description` | TextField(blank) | Short description |
| `icon` | CharField(100, blank) | Icon class |
| `category` | CharField(50, choices) | `community` or `branding` |
| `is_active` | BooleanField | Toggle visibility |
| `sort_order` | PositiveIntegerField | Display ordering |

### OnboardingSession

The core model — stores all wizard state as a single row.

**Key Fields (30+ total):**

| Field | Type | Purpose |
|---|---|---|
| `user` | FK → User | Session owner |
| `session_key` | CharField(64, unique) | UUID4 session identifier |
| `status` | CharField | `draft`, `in_progress`, `completed`, `abandoned` |
| `current_step` | IntegerField(1–13) | Current wizard step |
| `completed_steps` | JSONField | List of completed step numbers |
| `selected_services` | ManyToMany → ServiceType | Step 2 |
| `business_name` | CharField(255) | Step 3 |
| `industry` | CharField(100) | Step 3 |
| `business_description` | TextField | Step 3 |
| `target_audience` | CharField(255) | Step 3 |
| `project_name` | CharField(255) | Step 4 |
| `project_goals` | TextField | Step 4 |
| `budget_range` | CharField(50) | Step 4 |
| `design_style` | CharField(100) | Step 5 |
| `primary_color` | CharField(20) | Step 5 |
| `typography_style` | CharField(100) | Step 5 |
| `selected_features` | JSONField | Step 6 |
| `estimation_data` | JSONField | Step 7 (computed) |
| `selected_package` | CharField(50) | Step 8 |
| `selected_addons` | JSONField | Step 9 |
| `payment_method` | CharField(50) | Step 12 |
| `linked_project` | FK → Project | Generated workspace |

**Helper methods:** `mark_step_complete()`, `get_progress_pct()`, `get_step_name()`, `get_estimated_time_left()`, `get_selected_services_list()`, `get_features_list()`, `get_addons_list()`, `get_package_display()`, `get_design_style_display()`, `complete()`

### OnboardingAddon

| Field | Type | Description |
|---|---|---|
| `name` | CharField(200) | Add-on name |
| `slug` | SlugField(unique) | Identifier |
| `description` | TextField(blank) | Details |
| `price` | DecimalField(10, 2) | Monthly price |
| `is_active` | BooleanField | Toggle visibility |
| `sort_order` | PositiveIntegerField | Display ordering |

---

## Services (Estimation Engine)

**File:** `community/services.py`

### EstimationResult

Dataclass with fields: `budget_low`, `budget_high`, `timeline_weeks`, `complexity`, `recommended_package`, `selected_features`, `package_scores`

Properties:
- `total_cost` → average budget string
- `total_days` → `timeline_weeks * 7`

### calculate(session)

Rule-based estimation engine (AI-ready — `calculate()` internals are swappable):

- Base cost from `selected_services` (first service slug determines base)
- Complexity multiplier from `selected_features` count (5+ → Complex)
- Design style multiplier (modern/bold → 1.3x, elegant → 1.2x)
- Package scores map to `basic_pkg`/`standard_pkg`/`advanced_pkg`/`enterprise_pkg`

### get_package_comparison(session)

Returns a dict with `recommended`, `reason`, and a list of packages each with a `fits` key (boolean), cost, timeline, features, and description.

---

## Views & URLs

### Wizard Views (Primary Flow)

| URL Pattern | View | Step | Description |
|---|---|---|---|
| `/community/onboarding/` | `wizard_start` | 1 | Welcome screen; creates or resumes session |
| `/community/onboarding/step/<int:step>/` | `wizard_step` | 2–13 | Dispatches to `_handle_step2` through `_handle_step13` |
| `/community/onboarding/autosave/` | `wizard_autosave` | — | AJAX endpoint: debounced JSON save |

**All wizard views** require `login_required` + `is_community_user`.

### Step Handler Details

Each handler reads raw `request.POST` (no Django forms), validates minimum data, saves to `session.*` fields, calls `session.mark_step_complete(n)`, advances `session.current_step`, and redirects.

| Handler | POST Fields Saved | Special Behavior |
|---|---|---|
| `_handle_step2` | `services` (list of slugs) | Clears M2M, adds selected services |
| `_handle_step3` | `business_name`, `industry`, `business_description`, `target_audience` | — |
| `_handle_step4` | `project_name`, `project_goals`, `budget_range`, `target_launch_date` | — |
| `_handle_step5` | `design_style`, `primary_color`, `accent_color`, `typography_style` | — |
| `_handle_step6` | `selected_features` (list or comma string) | Handles both list and string input |
| `_handle_step7` | — | Runs `calculate()`, saves `estimation_data` on GET + POST |
| `_handle_step8` | `package` | Saves `selected_package` + `recommended_package` |
| `_handle_step9` | `addons` (list of slugs) | Resolves `OnboardingAddon` objects, computes total |
| `_handle_step10` | — | Saves `estimation_data` if missing before advancing |
| `_handle_step11` | — | Saves `estimation_data` + `recommended_package` before advancing |
| `_handle_step12` | — | Sets `payment_completed`, calls `_generate_workspace()` |
| `_handle_step13` | — | Renders completion page; POST calls `session.complete()` |

### Legacy Views (Still Present)

| URL Pattern | View | Status |
|---|---|---|
| `/community/` | `home` | Updated — hero CTA redirects to wizard |
| `/community/dashboard/` | `dashboard` | Updated — Smart Onboarding card + empty state |
| `/community/website-building/` | `website_building` | Preserved for backward compat |
| `/community/website-building/packages/` | `package_selection` | Preserved |
| `/community/brand-assist/` | `brand_assist` | Placeholder |

### Autosave Endpoint

`POST /community/onboarding/autosave/` accepts JSON `{step: N, data: {...}}`. Saves only non-empty values from `data` to the session. Returns `{"success": true}`.

### Workspace Generation (`_generate_workspace`)

Called on step 12 POST. Creates:

1. **Project** — title from `business_name`, description with industry/target info, status `PLANNING`, brand color from session
2. **5 ProjectPhases** — PLANNING, DESIGN, DEVELOPMENT, TESTING, LAUNCH
3. **4 PhaseTasks** — in PLANNING phase (review requirements, sitemap, environment, wireframes)
4. **Customer record** — via `get_or_create` with name, company, industry, source
5. **ActivityLog** — "Onboarding completed" entry
6. **Confirmation email** — HTML+plain text with project details, budget, timeline (sent via `send_mail` with `fail_silently=True`)

---

## Templates

### Wizard Template Hierarchy

```
base.html
  -> community/wizard/base_wizard.html  (hides navbar, breadcrumb, footer)
       -> step_01_welcome.html  through  step_13_workspace.html
```

### base_wizard.html Features

- Glassmorphism topbar with logo, step badge, autosave dot, exit button
- Gradient progress bar (dynamic width from `get_progress_pct`)
- Centered step content (900px max-width, fade-in animation)
- Sticky bottom bar with Back button, time remaining, progress percentage
- **Autosave JS**: debounced (1500ms) AJAX POST on input/change events; green pulsing dot indicator (yellow when saving)
- **Enter key handler**: submits the visible wizard form (skips `.d-none` and `[id^="advance"]` forms)
- CSS for: `.wizard-card`, `.wizard-input`, `.wizard-option-card`, `.wizard-check-*`, `.wizard-radio-*`, `.btn-wizard-next`, `.wizard-section-label`

### Step Template Details

| Step | File | Content |
|---|---|---|
| 1 | `step_01_welcome.html` | Rocket icon, 3 benefits cards, "Start Project"/"Continue Previous" button, last-saved timestamp |
| 2 | `step_02_services.html` | Service type selection cards (radio-style, JS highlight) |
| 3 | `step_03_business.html` | Text inputs for name, industry, description, audience |
| 4 | `step_04_project.html` | Project name, goals, budget range dropdown, target date |
| 5 | `step_05_design.html` | Design style cards, color pickers (input ↔ hex sync JS), typography select |
| 6 | `step_06_features.html` | Feature checkboxes with icons |
| 7 | `step_07_estimate.html` | Budget, timeline, complexity results; feature breakdown; Next button |
| 8 | `step_08_package.html` | Package comparison table with fit indicator, radio selection |
| 9 | `step_09_addons.html` | Add-on cards with price, checkbox selection, running total |
| 10 | `step_10_summary.html` | 4 summary cards (Business, Project, Services/Features, Design/Package) + estimation preview |
| 11 | `step_11_proposal.html` | Proposal document view with Next button |
| 12 | `step_12_payment.html` | Package price, addon cost, total, payment schedule, Next button |
| 13 | `step_13_workspace.html` | Green check icon (pop animation), 3 feature cards, "Open Project Board" and "Go to Dashboard" buttons, confirmation email notice |

### Integration Points

| File | Location | Change |
|---|---|---|
| `templates/base.html` | Lines ~587, 629 | Community nav link added |
| `templates/community/home.html` | Hero CTA + service card | Redirects to `wizard_start` |
| `templates/community/dashboard.html` | Smart Onboarding card | Shows status, step, progress; empty state CTA → wizard |
| `templates/community/base_community.html` | Nav | "New Project" link → `wizard_start` |

---

## Admin

**File:** `community/admin.py`

All 3 new models registered with full fieldsets:

- **ServiceTypeAdmin**: list display (name, slug, category, is_active), search, list filter (category, is_active)
- **OnboardingAddonAdmin**: list display (name, price, is_active), search, list filter (is_active)
- **OnboardingSessionAdmin**: list display (user, session_key, current_step, status, linked_project), search (user email, business_name, project_name), list filter (status, current_step), fieldsets organized by step group (Status, Business, Project, Design, Estimation, Payment)

---

## Seed Command

**File:** `community/management/commands/seed_community.py`

```
python manage.py seed_community
```

Creates:
- **10 ServiceTypes** (Website Development, SEO Optimization, Custom Web App, Mobile App, Brand Identity, UI/UX Design, Content Writing, Social Media, Email Marketing, Consultation)
- **5 OnboardingAddons** (Priority Support, SEO Package, Content Package, Social Media Integration, Extended Warranty)
- **4 PaymentPlans** (Basic $499, Standard $999, Advanced $1,999, Enterprise $4,999)

All use `get_or_create` so the command is idempotent.

---

## Access Control

```python
def is_community_user(user):
    return user.is_authenticated and hasattr(user, 'profile') and user.profile.service_type == 'community'
```

- All views decorated with `@login_required` and `@user_passes_test(is_community_user)`
- Failure redirects to `users:onboarding` with no redirect field
- Seed command guards: exits if profile service_type is not 'community'

---

## User Flow

```
[Login] --> /users/onboarding (sets service_type='community')
    |
    v
/community/  (home - landing page)
    |
    +-- "Start Project" --> /community/onboarding/  (Wizard Step 1: Welcome)
    |                           |
    |                           +-- POST --> creates/resumes session
    |                           v
    |                       Step 2: Services
    |                           |
    |                           v
    |                       Step 3: Business Info
    |                           |
    |                           v
    |                       Step 4: Project Details
    |                           |
    |                           v
    |                       Step 5: Design Preferences
    |                           |
    |                           v
    |                       Step 6: Features
    |                           |
    |                           v
    |                       Step 7: Auto-Estimation
    |                           |
    |                           v
    |                       Step 8: Package Selection
    |                           |
    |                           v
    |                       Step 9: Add-ons
    |                           |
    |                           v
    |                       Step 10: Summary Review
    |                           |
    |                           v
    |                       Step 11: Proposal
    |                           |
    |                           v
    |                       Step 12: Payment
    |                           |
    |                           +-- POST --> generates workspace
    |                           v
    |                       Step 13: Workspace Ready
    |                           |
    |                           +-- "Open Project Board" --> /projects/{id}/
    |                           +-- "Go to Dashboard"  --> /community/dashboard/
    |
    +-- "Go to Dashboard" --> /community/dashboard/
    |                           |
    |                           +-- View projects, alerts, activity
    |                           +-- Smart Onboarding card (resume if draft)
    |                           +-- Click project --> /projects/{id}/ (Project detail)
    |
    +-- "Get Branding" --> /community/brand-assist/  (placeholder)
```

**Save/Resume:** Sessions persist with status `in_progress`. Returning to `/community/dashboard/` shows the Smart Onboarding card with "Resume Step N". Clicking "Start Project" on the wizard welcome page shows "Continue Previous" if a draft session exists.

**Autosave:** Every input change triggers a debounced AJAX POST to `wizard_autosave` after 1.5s of inactivity. Green dot indicator pulses in the top bar.

---

## Tests

**File:** `community/tests.py` — **36 tests, all passing.**

| Test Class | Tests | Coverage |
|---|---|---|
| `EstimationEngineTest` | 7 | calculate(), to_dict(), package comparison, complexity, multipliers |
| `ServiceTypeModelTest` | 1 | Model creation |
| `OnboardingAddonModelTest` | 1 | Model creation |
| `OnboardingSessionModelTest` | 9 | str, progress, step name, mark_step_complete, get_estimated_time_left, helper methods (dict + string addons), complete |
| `WizardViewTest` | 18 | All 12 step POST handlers (renders + redirects), autosave, session redirect, cannot skip steps, workspace generation, e2e walkthrough |

---

## Dependencies

**Internal app imports:**

| Import | From | Used In |
|---|---|---|
| `UserProfile`, `ActivityLog`, `UserSubscription` | `users.models` | views |
| `UserPaymentSelection`, `PaymentPlan` | `payments.models` | views |
| `Project`, `ProjectPhase`, `PhaseTask` | `projects.models` | views, workspace generation |
| `Customer` | `crm.models` | Workspace generation |

---

## Known Issues

### 1. Missing URL: `community:project_detail`
`templates/community/project_detail.html:318` references `{% url 'community:project_detail' project.id %}` but no such URL pattern exists in `community/urls.py`. Use `projects:project_detail` instead.

### 2. Missing URL: `community:project_message`
Same template references `{% url 'community:project_message' project.id %}` — not defined in `community/urls.py`.

### 3. Duplicate Dashboard Templates
Two `dashboard.html` files exist (`community/templates/community/dashboard.html` and `templates/community/dashboard.html`). Since `DIRS` is searched before `APP_DIRS`, the global version wins.

### 4. Inconsistent Template Inheritance
Some legacy templates extend `base.html` directly instead of `base_community.html`.

### 5. Two Intake Form Implementations
Legacy `website_intake.html` (ModelForm) and `website_building.html` (raw HTML) co-exist.

### 6. `brand_assist` Is a Placeholder
No actual branding functionality implemented.

### 7. Step 12 Payment Is a Passthrough
Payment step sets `payment_completed = True` without real Stripe integration. Replace with actual Stripe Checkout session creation for production.

### 8. No Rate Limiting on Autosave
The `wizard_autosave` endpoint accepts unlimited POST requests. Consider adding throttling.

### 9. Email Only on Console Backend
`EMAIL_BACKEND` defaults to console unless `EMAIL_HOST_USER/PASSWORD` env vars are set. Real emails require SMTP configuration.