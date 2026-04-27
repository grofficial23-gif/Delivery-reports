# RAG_READY_DATA_MODEL.md
> Future searchable data entities for PM Digest / Delivery Reports.
> Purpose: define fields for future vector indexing / search.
> Do NOT implement RAG here — this is a schema reference only.

---

## How to use

When implementing search or AI retrieval in the future:
- Index the `text_body` fields into a vector store.
- Use `metadata` fields as filters (by user, project, plan, date).
- Use `relations` to build context windows (e.g. "draft + its notes").

---

## Entities

---

### user

**Purpose:** A registered Telegram user with a subscription plan.

**Fields to index:**
- `display_name` — for personalization context

**Metadata (filter fields):**
- `telegram_user_id` (int, unique)
- `username` (str, nullable)
- `user_plan` (`free` | `pro` | `team`)
- `is_super_admin` (bool)
- `created_at` (datetime)
- `last_active_at` (datetime)

**Relations:**
- has many `project`
- has many `note`
- has many `subscription`
- has many `audit_event`

---

### project

**Purpose:** A named delivery project grouping notes, drafts, and reports.

**Fields to index:**
- `name` (str)
- `description` (str, nullable)

**Metadata:**
- `project_id` (int)
- `user_id` (int, FK → user)
- `team_id` (int, nullable, FK → team)
- `status` (`active` | `archived`)
- `created_at` (datetime)

**Relations:**
- belongs to `user`
- belongs to `team` (optional)
- has many `note`, `draft`, `final_report`, `task`

---

### note

**Purpose:** A raw input unit — text note, voice transcript, task import, or template fill.

**Fields to index:**
- `content` (str) — the raw text; primary search target

**Metadata:**
- `note_id` (int)
- `user_id` (int, FK → user)
- `project_id` (int, nullable, FK → project)
- `source_type` (`text` | `voice` | `task_import` | `template`)
- `created_at` (datetime)
- `is_processed` (bool) — whether included in a draft

**Relations:**
- belongs to `user`, `project`
- may link to `transcript`
- may be included in `draft`

---

### transcript

**Purpose:** Processed output of a voice memo — text produced by transcription pipeline.

**Fields to index:**
- `text` (str) — full transcription text

**Metadata:**
- `transcript_id` (int)
- `note_id` (int, FK → note)
- `user_id` (int, FK → user)
- `duration_seconds` (float)
- `language` (str, e.g. `ru`, `en`)
- `created_at` (datetime)

**Relations:**
- belongs to `note`
- indirectly feeds into `draft`

---

### draft

**Purpose:** An AI/rule-assembled structured report draft, before finalization.

**Fields to index:**
- `content` (str) — structured draft text; primary search target
- `title` (str)

**Metadata:**
- `draft_id` (int)
- `user_id` (int, FK → user)
- `project_id` (int, nullable, FK → project)
- `status` (`pending` | `preview` | `approved` | `discarded`)
- `created_at` (datetime)
- `updated_at` (datetime)

**Relations:**
- belongs to `user`, `project`
- generated from many `note`
- may be promoted to `final_report`

---

### final_report

**Purpose:** A finalized delivery report, sent or exported.

**Fields to index:**
- `content` (str) — final report text
- `title` (str)

**Metadata:**
- `report_id` (int)
- `user_id` (int, FK → user)
- `project_id` (int, nullable, FK → project)
- `draft_id` (int, nullable, FK → draft)
- `delivery_channel` (`telegram_self` | `copy` | `export`)
- `sent_at` (datetime, nullable)
- `created_at` (datetime)

**Relations:**
- belongs to `user`, `project`
- derived from `draft`

---

### task

**Purpose:** An action item or blocker tracked within a project.

**Fields to index:**
- `title` (str)
- `description` (str, nullable)

**Metadata:**
- `task_id` (int)
- `user_id` (int, FK → user)
- `project_id` (int, nullable, FK → project)
- `status` (`open` | `in_progress` | `done` | `blocked`)
- `priority` (`low` | `medium` | `high`)
- `due_date` (date, nullable)
- `created_at` (datetime)

**Relations:**
- belongs to `user`, `project`

---

### subscription

**Purpose:** Tracks a user's current plan, payment history, and expiry.

**Fields to index:** (none — not a search entity)

**Metadata:**
- `subscription_id` (int)
- `user_id` (int, FK → user)
- `plan` (`free` | `pro` | `team`)
- `payment_method` (`telegram_stars` | `manual`)
- `started_at` (datetime)
- `expires_at` (datetime, nullable)
- `telegram_payment_charge_id` (str, nullable)
- `is_active` (bool)

**Relations:**
- belongs to `user`

---

### team

**Purpose:** A group of users sharing projects (TEAM plan feature).

**Fields to index:**
- `name` (str)

**Metadata:**
- `team_id` (int)
- `owner_user_id` (int, FK → user)
- `created_at` (datetime)
- `plan` (`team`)

**Relations:**
- has many `user` (members)
- has many `project`

---

### template

**Purpose:** A reusable report structure (e.g. "Sprint Review", "Weekly Digest").

**Fields to index:**
- `name` (str)
- `description` (str, nullable)
- `body` (str) — template text with placeholders

**Metadata:**
- `template_id` (int)
- `owner_user_id` (int, nullable — null = system template)
- `is_system` (bool)
- `created_at` (datetime)

**Relations:**
- optionally owned by `user`
- used when creating `note` (source_type = `template`) or `draft`

---

### audit_event

**Purpose:** Security / activity log. Records sensitive actions.

**Fields to index:** (none — security log, not a search entity)

**Metadata:**
- `event_id` (int)
- `user_id` (int, nullable, FK → user)
- `event_type` (str, e.g. `report_sent`, `plan_upgraded`, `admin_action`, `login`)
- `entity_type` (str, nullable — e.g. `note`, `draft`, `report`)
- `entity_id` (int, nullable)
- `ip_address` (str, nullable)
- `created_at` (datetime)

**Relations:**
- belongs to `user` (optional)
- references any other entity via `entity_type` / `entity_id`
