# SOP & Knowledge Retention Platform — Architecture and Plan

Status: proposal (architecture + plan only, no code yet) · updated 2026-11-20

> **Since 2026-11-25 the platform runs fully local.** The owner removed Claude:
> every tier (answering included) runs on local Ollama models and the Anthropic
> connector is gone from the code. Where this plan describes Claude tiers,
> API keys or cloud costs, read it as design history; see the status table (§12).

## 1. Goal

Turn llm-wiki (today an agent plugin that runs inside Claude Code, Codex and
similar tools) into a self-hosted service:

- Employees chat with one **assistant bot**, the *Concierge*.
- The Concierge passes questions to **department agents** (Core delivery, IT,
  HR…). It only reaches the agents the user is permitted to use.
- Each department keeps a governed SOP and knowledge base: ingest, compile,
  review, approve, publish, expire.
- Knowledge does not leave with people. There are handover notes for
  in-flight client work, gap detection and staleness tracking.

**Frontend decision (updated 2026-11-20):** the web app (chat, library,
editor, review, dashboards) is built **in this repository**, in its own
`frontend/` folder next to `backend/`, alongside each backend phase. The
backend stays **API-first**, so other clients can be added later (§8.1).

**Decisions taken:** built-in users and roles (SSO later), a Python backend
(FastAPI), Postgres, Docker Compose, and the Claude API for agents.

### Context and decisions (2026-11-20)

| Topic | Decision |
|---|---|
| Company | Personal branding and training business. Internal use only. |
| First space | **`core`**: branding methodology, training programmes, client-delivery processes, and the **content used in training** (slides, workbooks, exercises, scripts). It is the company's core IP, so it gets the **strictest** access. `it` and `hr` follow as ordinary spaces. *(Confirmed.)* |
| Access to `core` | A small **public tier** that everyone can read (e.g. "how to book a training room"). Everything else is core-staff only, and the most sensitive material is restricted to named roles. Notes with missing or invalid access metadata **fail closed** (treated as restricted). |
| Source of truth | **One Obsidian-format vault for the whole company**, stored as a git repository on the company device. |
| Who edits where | **All staff read and write SOPs through the app**, in the office or remotely, so permissions apply everywhere. **Only the CEO/admin** opens the vault directly in Obsidian, on the device itself. Obsidian would put a full copy of the vault on every laptop that syncs it, bypassing permissions (§3.2). |
| Who can see what | An **AI Classifier** reads each note and **proposes** which department owns it and how sensitive it is. It can make access tighter on its own, but **only a human can make access wider** (§4.1). |
| Team | Core is **2–3 staff plus the CEO**. The CEO is `core-lead` and platform admin; the staff are `core-staff`. The vault is small but growing as SOPs are written. |
| Classifier model | **Local from day one** at the company deployment (it reads every note, including the most restricted). Answering agents stay on Claude for now (§4.1 data note). |
| AI models | **Claude API now**, behind a **model gateway**, so the system can move to **local models** later without code changes (§5.1). Embeddings run locally from day one. |
| Host machine | Likely a **Mac mini with 16 GB** memory (still under discussion; memory budget in §3.4), otherwise a Windows PC, in the office. It runs the app, the database and the vault. Remote staff reach **only the app**, over a private network link (§3.3). |
| Authorship | Every save made through the app is a git commit **under the logged-in user's name**, so who wrote what is always known (§3.2). |
| Reviews | **Reviews and approvals happen in the platform**, where every reviewer is logged in. Each approval is tied to the exact version reviewed (§6). |
| Training content | **Slides are the main format** (PowerPoint, Google Slides, Canva), with PDFs mainly used as worksheets. Videos come later. Slides and PDFs are cited by slide or page number (§3.1). |
| Client names | There is no client list, and notes may contain client names. A **local name detector** (§4.1 safeguards) treats possible client names as restricted. |
| Bot role | **Advisory only.** It answers and points to people; it takes no actions. |
| API account | **Developer's Claude API key during development and testing**, with demo data only. It is swapped for the **company's own key before any real vault is connected**. That is a config change (`ANTHROPIC_API_KEY` in the server's env file), never committed to git. |
| Language | **English now, other languages later.** The search index is multilingual from day one, so adding a language later does not mean rebuilding it (§5.1). |
| Content organisation | Content is organised **by programme and by stage** of delivery. Both are first-class fields, so staff can browse either way (§6). |
| Knowledge gaps | **HR sees anonymised, aggregated knowledge-gap reports** across departments, to plan follow-up training (§7). |
| Retention | Chat history and audit logs are kept **24 months** by default, enough for the yearly audit with margin (§11). |
| Staff notice | Staff see a **short notice** about what is logged and who can see it, and acknowledge it at first sign-in (§11). |
| Dev environment | Built and tested on the developer's **MacBook** (Apple Silicon) with Docker Compose and a **synthetic demo vault**. |
| Data handling | The developer **never handles real company data**. Real vaults are only mounted on the company's own machine, by company admins (§11). |

### Non-goals for v1

SSO, Slack or Teams surfaces, multi-tenant SaaS, and the end-user dashboard.
The design leaves room for each of these.

## 2. What we reuse from llm-wiki

| llm-wiki asset | Becomes |
|---|---|
| Hub → `topics/<name>/` topic wikis | One **knowledge space** per department (`core`, `it`, `hr`), assigned per note by classification within a single vault (§4.1) |
| `raw/` (immutable sources) / `wiki/` (compiled articles) split | SOP source docs vs published SOP and knowledge articles |
| Frontmatter (`sources`, `confidence`, `volatility`, `verified`, `summary`) | Kept. SOP fields are added on top (§6) |
| `_index.md` index-first retrieval (`references/query-lite.md`) | Department agent retrieval strategy, backed by a search index |
| "Treat wiki files as evidence, not instructions" rule | Core prompt-injection defence for every agent |
| `references/ingestion.md`, `compilation.md` | Upload parsing and note structure (ingestion worker, no model) |
| `references/linting.md`, `librarian.md`, `refresh.md`, `scripts/llm-wiki lint` | Scheduled Librarian jobs (broken links, staleness, coverage) |
| `scripts/llm-wiki retract` | Admin "remove data/source" with verification (GDPR and offboarding) |
| `references/sessions.md`, `ll.md` (lessons learned) | Structure for handover notes (in-flight work passed to a colleague) |
| `tests/fixtures/golden-wiki`, promptfoo evals | Seed fixtures and the eval harness |

Plan: move the deterministic parts of `scripts/llm-wiki` (6.8k lines of Python:
frontmatter parsing, lint, retract, index handling) into an importable package,
`wiki_core`. The CLI keeps working as a thin wrapper, so the existing plugin
still works and its tests still pass.

## 3. System architecture

```
                    Web app (React SPA, frontend/)    
                                   │  HTTPS: REST + SSE, JWT
┌──────────────────────────────────▼─────────────────────────────────────┐
│ API gateway (FastAPI)                                                   │
│  auth · sessions · rate limit · RBAC policy engine · audit writer       │
├─────────────────────────────────────────────────────────────────────────┤
│ Agent runtime                                                           │
│                                                                         │
│   Concierge (orchestrator)                                              │
│     1. resolve allowed spaces (policy engine)  2. search → route        │
│     3. dispatch in parallel ─┬─▶ Core agent ─tools─▶ search(space=core) │
│     4. answer per dept + cite├─▶ IT agent   ─tools─▶ search(space=it)   │
│                              └─▶ HR agent   ─tools─▶ search(space=hr)   │
│                                                                         │
│   Ingestion worker (upload → parse slides/PDFs → note; no model)        │
│   Librarian agent  (scheduled: stale, broken, gaps, conflicts)          │
├─────────────────────────────────────────────────────────────────────────┤
│ Model gateway: Claude API today · local models (Ollama/vLLM) later      │
│ Embeddings: local model, always on the server                           │
├─────────────────────────────────────────────────────────────────────────┤
│ Worker (arq + Redis): change detection, parsing, chunking, embedding,   │
│ lint, review-due reminders                                              │
├──────────────┬──────────────────────────────┬───────────────────────────┤
│ Postgres     │ Vault (Obsidian format)      │ Git history of the vault  │
│ + pgvector   │ source of truth; staff edit  │ every save = a commit by  │
│ users, RBAC, │ via the app; CEO/admin also  │ the logged-in user; full  │
│ chunks, audit│ in Obsidian on the device    │ versions for audit        │
└──────────────┴──────────────────────────────┴───────────────────────────┘
```

### 3.1 The vault is the source of truth

The vault is a normal Obsidian vault (markdown files and attachments) kept in a
git repository on the company device. Staff edit it **through the app**. The
CEO/admin can also open it in Obsidian on the device. The platform keeps
everything in Obsidian format, so the vault always stays a usable Obsidian
vault.

- **Writes:** the app's editor saves notes and uploads attachments through the
  API. The API checks the user's `contribute` permission, then writes the file
  and makes a git commit in that user's name.
- **Change detection from git commits, not file watching:** after every
  commit, the worker re-indexes only the changed files. Changes made in
  Obsidian are committed by the Obsidian Git plugin on the device. A nightly
  check commits any stray changes as *unattributed* and re-indexes them. This
  also avoids a known problem with watching Windows folders from Docker.
- **Format:** the parser understands Obsidian conventions:
  - YAML frontmatter
  - `[[wikilinks]]` and `[[note|alias]]`
  - `![[embeds]]`
  - `#tags`
  - attachments, processed locally (nothing leaves the device):
    - **Slide decks (main training format):** `.pptx` is read **slide by
      slide**: title, body text, tables and **speaker notes**. Each slide is
      its own searchable chunk, so answers cite "*Brand Foundations deck, slide
      14*". Text inside images (diagrams, screenshots of frameworks) is read
      with local OCR.
      - **PowerPoint:** read directly.
      - **Google Slides:** v1 uploads a `.pptx` download (File → Download →
        PowerPoint), which keeps speaker notes. Later: optional automatic
        export through a Google Drive connector.
      - **Canva:** v1 uploads a `.pptx` or PDF export. Canva designs often turn
        text into shapes or images when exported, so local OCR is the fallback.
        Export quality should be checked on a few real decks early on. Later:
        optional automatic export through Canva's Connect API.
      - The upload screen notes the original tool and keeps a link to the
        original design, so a reviewer can open the source.
    - **PDF worksheets:** text **and fillable form-field labels** are
      extracted, cited by page. Scanned PDFs go through local OCR.
    - **Word** (`.docx`) and images.
    - **Videos and audio** come later, using local transcription (e.g. Whisper
      on the device).
    - **Access:** each attachment is classified like a note, and defaults to
      `restricted`. Embedding a deck in a public note does **not** make the
      deck public.

  It ignores `.obsidian/`, `.trash/` and `_templates/`. llm-wiki's link and
  frontmatter handling already covers most of this.
- **One vault, logical spaces:** the vault does not have to be pre-sorted
  into department folders. Which space a note belongs to is decided by
  classification (§4.1) and stored in the platform's database. Notes are
  **never moved or renamed** by the platform, so Obsidian links, staff
  bookmarks and folder habits keep working. Folders still help: an optional
  rule in `vault.yaml` (e.g. `Training Content/ → core`) counts as a human
  decision.
- **Versioning:** see §3.2. Every change to every note and attachment is a
  git commit, so any past version can be shown and compared.
- **Rebuildable:** Postgres is only an index. Deleting it and re-scanning the
  vault restores everything except users, permissions and the audit log, which
  are backed up separately.

### 3.2 Who wrote and who edits: the app for everyone, Obsidian only for the admin

**Why not Obsidian for all staff:** Obsidian keeps a **full copy of the vault
on every laptop that syncs it**. With one company vault, every syncing laptop
would hold all restricted core IP and all HR notes, and the platform's
permissions couldn't protect files already on a laptop. So:

| Who | Edits through | Sees |
|---|---|---|
| Core staff, other staff | **The app** (office or remote) | Only what their grants allow; edit only where they have `contribute` |
| CEO / admin | The app, **or** Obsidian **on the device itself** | Everything (as vault owner) |

**Authorship:**

- **App saves:** every save is a git commit **in the logged-in user's name**,
  made by the server. Staff never handle git. Because the server records who
  was logged in, the author can't be faked by typing another name.
- **Obsidian edits on the device:** the Obsidian Git plugin commits them in the
  admin's name.
- **Anything else** (e.g. a file copied directly into the folder) is caught by
  the nightly check and recorded as *unattributed* in the governance report.
- **No per-person git accounts or git server are needed.** The git repo is
  local to the device.

**Edit clashes:** every app save carries the version the user started from. If
the note changed in the meantime (another user, or the admin in Obsidian), the
save is refused and the app shows both versions to merge, so nothing is
silently overwritten.

**Creating notes:**

- A new note created in the app starts as a draft in the author's own space.
- The author can choose its space and sensitivity. The Classifier suggests
  them, and the one-way rule (§4.1) still applies.
- Only a `contribute` grant allows editing. In Obsidian, anyone with the vault
  can edit anything, so this is stricter.

### 3.3 Remote access

Remote staff reach **only the app**. The database, the vault files and Ollama
are never exposed.

| Option | Who can see the traffic | Third-party dependency | Fit |
|---|---|---|---|
| **Cloudflare Tunnel** | **Cloudflare decrypts it.** Every SOP and answer passes through their servers in readable form | Cloudflare for everything | **Rejected:** conflicts with keeping data local |
| **Tailscale** (start here) | Only the two devices. Traffic is end-to-end encrypted (WireGuard) and usually goes directly device-to-device. Relays, when needed, carry only encrypted packets | Tailscale's coordination service handles logins and key exchange, not your data | Easiest start; per-user pricing beyond the free tier |
| **Headscale** (scale-up path) | Only the two devices | **None.** It is an open-source, self-hosted replacement for Tailscale's coordination server, and staff keep the same Tailscale apps | Best long-term fit for "local only". Must itself be reachable from the internet: router port-forward with a public or dynamic-DNS address |
| Plain WireGuard on the office router | Only the two devices | None | Fine for a handful of people; manual key management gets painful as staff grow |

**Decision: self-hosted Headscale from day one**, so there is no later switch.

- **Where it runs:** Headscale runs on the office machine, next to the app.
  Staff install the official Tailscale app once and point it at the company's
  Headscale address. The macOS, Windows, iOS and Android apps all support a
  custom server.
- **Relays are self-hosted too:** Headscale's **embedded relay (DERP)** is
  turned on and Tailscale's public relays are turned off. So even connections
  that can't go direct never touch Tailscale's infrastructure.
- **Access rules (ACLs):** staff devices can only reach the app's HTTPS port,
  nothing else on the office machine.
- **Requirements, checked before Phase 6:**
  - The office internet connection must accept incoming connections. Some
    ISPs use carrier-grade NAT (CGNAT), which blocks this. The fix is to ask
    the ISP for a public IP, usually a cheap add-on.
  - A router port-forward: TCP 443 for the control server and UDP 3478 for the
    relay.
  - A stable address: a domain name, or dynamic DNS if the IP changes.
  - A TLS certificate (e.g. Let's Encrypt, which only issues the certificate
    and sees no traffic).
- **Responsibility:** Headscale is an internet-facing service the company runs
  itself. It must be kept updated, and that is part of the runbook.
- **Fallback:** if the connection is stuck behind CGNAT and no public IP is
  available, use Tailscale's hosted service. The apps are the same, and moving
  to Headscale later is just changing the server address.

**Either way:**
- HTTPS inside the private network.
- **Two-factor sign-in (TOTP) required for all users.**
- Short sessions, with lockout after repeated failed logins.
- Remote sign-ins are recorded in the audit log.

> Remote access can never be completely free of outside parties: at minimum,
> traffic crosses the office internet provider. With Headscale and its own
> relay, encrypted traffic is all that ever leaves the building. The other external dependency
> is the Claude API, until the answering tiers move to local models (§5.2).

### 3.4 Host machine: Mac mini or Windows

Both are supported with the same Docker Compose setup:

| | Mac mini (recommended) | Windows PC |
|---|---|---|
| Containers | Docker Desktop (or OrbStack) | Docker Desktop with WSL2 |
| Local AI (Ollama) | Runs natively and uses the Apple GPU (Metal) | Runs natively; fast with an NVIDIA GPU, slow on CPU only |
| Obsidian for the admin | Yes | Yes |
| Notes | Quiet, low power, always on. 24 GB+ memory is comfortable for the local Classifier and embeddings; 32–64 GB leaves room to move answering agents local later | Keep the vault and Docker data **inside WSL2**, not on a `C:\` folder, for speed. Check sleep/update settings so it stays on |

#### Memory budget on a 16 GB Mac mini

| Component | Approx. memory |
|---|---|
| macOS and background services | 3–4 GB |
| Docker: Postgres, Redis, API, worker (parsing, OCR) | 3–4 GB |
| Embedding model (`qwen3-embedding:0.6b`) | ~0.6 GB |
| Name detector (small local model) | ~0.5–1 GB |
| **Classifier model** | **~3 GB (4B-class) or ~5 GB (8B-class)** |
| **Total** | **~10.5–11.5 GB with a 4B Classifier**; ~12.5–14.5 GB with an 8B one (only if it unloads when idle) |

What this means on 16 GB:

- **The Classifier uses a 4B-class model by default.** It loads when there is
  work and unloads when idle (Ollama `keep_alive`). Notes are classified one
  at a time from a queue.
- If the 4B model misses the accuracy bar on the demo vault, the **8B model
  runs in a scheduled window** (e.g. after hours) with other heavy jobs
  paused. This is safe because unclassified notes stay quarantined, so a delay
  never exposes anything; new notes just take longer to be released.
- **Answering stays on the Claude API** on this machine. Local answering
  models good enough to keep the logic sound need roughly 32 GB or more.
- **Mac mini memory can't be upgraded after purchase.** If the budget allows,
  **24 GB** gives comfortable headroom (8B Classifier always loaded, no
  scheduling), and **32 GB+** keeps the door open to moving the everyday
  answering tier local later (§5.2). Phase 2b measures the 4B and 8B
  Classifiers on the demo vault, which will settle whether 16 GB is enough.
- Storage: the vault, slides, database and indexes are small. 512 GB is ample,
  plus an external drive for backups.

Backups (both): nightly encrypted copies of the git repo and the database to
an external drive or the company's chosen storage.

## 4. Permission model (the core requirement)

### Entities

- **User:** has one or more roles and one home department.
- **Role:** e.g. `employee`, `it-staff`, `hr-staff`, `hr-confidential`,
  `manager`, `space-admin`, `platform-admin`.
- **Space:** a department knowledge base (`it`, `hr`, `finance`…).
- **Sensitivity level** on every document and chunk: `public` (whole company),
  `internal` (department members), `restricted` (named roles only).
- **Grant:** `(role, space, max_sensitivity, actions)`. Actions are a subset of
  `ask | contribute | review | approve | admin`.

Example grants, with `core` as the strictest space:

| Role | Space | Max sensitivity | Actions |
|---|---|---|---|
| employee | core, it, hr | public | ask |
| core-staff | core | internal | ask, contribute |
| core-lead (the CEO) | core | restricted | ask, review, approve |
| it-staff | it | internal | ask, contribute |
| hr-staff | hr | internal | ask, contribute, review |
| hr-staff | *(all spaces)* | — | `view_gap_reports` (anonymised, aggregated only, §7) |
| space-admin:core | core | restricted | all |

So every employee can ask "how do I book a training room?" (a public `core`
SOP). Only core staff can read the delivery playbooks, and only core leads can
read restricted material such as proprietary frameworks, pricing logic or
client-specific delivery notes.

### 4.1 How a note gets its space and sensitivity

With a single vault, every note needs two labels:

- **owning space:** `core`, `it` or `hr`
- **sensitivity:** `public`, `internal` or `restricted`

A note can also be **shared with** extra spaces (e.g. a client-onboarding SOP
owned by `core` but shared with `hr` at `internal`).

Authors shouldn't have to label everything, so an **AI Classifier** proposes
the labels. Because a wrong label could leak core IP, the AI's power is limited
by these rules.

**Order of authority** (highest wins):

1. **Human labels in the note's frontmatter:** `space:`, `sensitivity:`,
   `shared_with:`.
2. **Human folder rules** in `vault.yaml`.
3. **AI classifications approved by a human** in the review queue.
4. **Automatic safeguards** (below).
5. **Default:** `restricted` and **unassigned**. Only reviewers can retrieve
   the note, so it is effectively quarantined.

**The one-way rule.** The AI may make a note **more restricted** by itself. It
may **never make a note less restricted**, or give access to another
department, without a human approving it:

| AI proposal | What happens |
|---|---|
| `restricted` in a space (confidence ≥ threshold) | Applied automatically. Only that space's leads can see it |
| `internal` or `public`, or `shared_with` another space | Goes to the **review queue**. Until approved, the note stays restricted |
| Low confidence or "unsure" | Stays quarantined and goes to the review queue with the AI's reasoning |
| Re-classification after an edit makes it **stricter** | Applied immediately |
| Re-classification after an edit makes it **looser** | Queued for approval. The current, stricter label stays in force |

**Automatic safeguards** (deterministic, no AI involved) force `restricted`
whatever the AI says, when a note contains:

- personal data patterns: NRIC/FIN, phone numbers, email addresses, bank details
- **possible client names:** there is no client list, so a **local name
  detector** (a small on-device model) finds people's and organisations' names.
  Names of the company's own staff (from the user list) are ignored. Any
  remaining name in a `core` note marks the note `restricted` until a reviewer
  confirms it's safe. Confirmed names can be added to a client list, which
  builds up over time.
- terms that are flagged in `vault.yaml` (e.g. "pricing", "rate card", "contract")

Notes with missing, misspelled or unparseable labels resolve to `restricted`,
never `public`.

**Reviewing the AI's suggestions:**

- **The review queue** shows each proposal with:
  - the AI's reasoning
  - the passages it relied on
  - a one-click approve, edit or reject
- **Grouping:** similar notes are grouped (by folder, tags and topic), so a
  reviewer can approve, say, "these 40 workshop worksheets → `core`/`internal`"
  in one action.
- **Who reviews:**
  - **Notes the AI couldn't place** go to the note's **author** (the person
    who created it), or else the department lead. The author is taken from the
    note's `author:` frontmatter (pre-filled by the Obsidian template), or from
    the git commit author if the vault uses git. If neither exists, the note
    goes to the lead.
  - **Authors can approve** placing their own note in their **own department**
    at `internal` or `restricted`.
  - **Only the department lead** (the CEO, for `core`) can approve the two
    decisions that widen access the most: making a note **`public`**, or
    **sharing it with another department**. In a small team this keeps the
    lead's workload light and still puts IP-exposing decisions with one
    accountable person.
- **First run:** the initial pass over the whole vault produces one review
  queue, grouped this way, to work through once.
- **Optional write-back:** an approved label can be written into the note's
  frontmatter, so the decision is visible in Obsidian too. This is the only
  change the platform makes to existing notes, and it is off by default.

**Accuracy is measured, not assumed.** The demo vault comes with correct labels
for every note, and the Classifier is tested against them on every change. Two
numbers are tracked separately:

- **over-exposure rate:** labelled looser than it should be. The target is
  **0**. This is the dangerous error.
- **over-restriction rate:** labelled stricter than it should be. This is
  annoying but safe.

Auto-applying a looser label could be allowed later, only for a space whose
admins opt in, and only after the over-exposure rate has stayed at zero on real
review history.

**Data note (decision: local Classifier from day one):** to classify a note, the Classifier has to read it. While the
Classifier uses the Claude API, that means every note's text goes to Claude
once, at first index and after edits. Classification is a simple task that
small models handle well, so the `classifier` tier is the **first candidate to
move to a local model** (§5.1, Phase 7).

Decision: the `classifier` tier runs **locally from day one** at the company
deployment. During development on the MacBook, both providers are tested
against the synthetic demo vault, so local accuracy is known before any real
note is classified. If the local model's mistakes are a problem, they fall on
the safe side (more review work, not leaks), because of the one-way rule.

### Enforcement: in code, never by prompt

1. **Policy engine** (a single function: `allowed_scopes(user) →
   [(space, max_sensitivity)]`). It is computed per request on the server and
   never taken from the client or the LLM.
2. **Dispatch filter:** the Concierge can only call agents for spaces in
   `allowed_scopes`. Agents outside that set are not included in its tool list
   at all.
3. **Retrieval filter:** every search and read tool carries the user's scopes
   as a SQL `WHERE` clause (Postgres row-level security as defence in depth).
   An agent cannot retrieve a chunk the user couldn't read directly.
4. **No cross-user caching** of retrieved content, unless the cache key
   includes the scopes.
5. **Audit:** every question, the agents it was dispatched to, the document IDs
   retrieved and the answer are written to an append-only `audit_events` table.

### Existence disclosure

When a question falls outside the user's scopes, the Concierge answers "I can't
access that area. Contact HR at …". It does not hint at what the restricted
content contains. Each space can configure its own contact or escalation text.

For `core`, outsiders only ever see the public tier. Questions that reach beyond
it get a generic "please ask the delivery team" reply, never "there is a
restricted SOP about that".

### Prompt-injection defence

Retrieved text is wrapped as data, and agents follow llm-wiki's "evidence, not
instructions" rule. Agents have **read-only tools while answering**. Write
actions (draft an SOP, flag a gap) create pending items that a human must
approve.

## 5. Agents

All agents run in the backend (not in Claude Code). They get the user context
injected by the server, and they call models only through the model gateway
(§5.1).

| Agent | Model (default) | Tools | Writes? |
|---|---|---|---|
| **Concierge** | Routing: permissions plus search, local `router` tier (`qwen3`) only when unclear, never Claude (see *Routing* below). No model combines answers: each department's answer is shown in its own section | `ask_<space>_agent` (only allowed spaces), `get_user_profile`, `create_ticket_handoff` (optional) | No |
| **Department agent** (one config per space) | `answer` tier (Haiku 5.5) with escalation to `reasoning` tier (Sonnet 5.5), §5.2 | `search(query)`, `read_article(id)`, `read_index(path)`, `list_sops(filter)`, all scope-filtered | No |
| **Classifier** | `classifier` tier (local model via Ollama; Haiku as eval baseline) + deterministic safeguards | `read_note`, `list_spaces`, `propose_classification` | Writes proposals and auto-tightened labels only (§4.1) |
| **Librarian** | `background` tier (local `qwen3:8b`) + deterministic `wiki_core lint` | lint, staleness scan, conflict detection, gap report | Reports and tasks only |

### 5.1 Model gateway (Claude now, local later)

Agents never call a provider SDK directly. They call one internal interface:

```python
class ModelGateway(Protocol):
    async def chat(self, *, tier: Tier, messages, tools=None, stream=False): ...
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
```

**Which model does what (decided 2026-11-21).** Claude is used only to answer
questions; everything else is local or done by people.

| Process | Model | Where |
|---|---|---|
| Answering questions | `answer` (Haiku 5.5), escalating to `reasoning` (Sonnet 5.5) | Claude; the local answering eval (§5.2) decides whether it moves local |
| Writing SOPs | **People**, in the editor from the SOP template. No AI drafting: staff know the systems and the pain points | — |
| Routing | permissions + search; `router` (`qwen3:8b`) only when unclear | Local |
| Combining answers from several departments | no model: one section per department | Local |
| Librarian reports, review summaries, handover checks | `background` (`qwen3:8b`) | Local |
| Classifier | `classifier` (`qwen3:4b` or `qwen3:8b`, Phase 2b eval) | Local |
| Embeddings and search | `embedding` (`qwen3-embedding:0.6b`) | Local |
| Name detector, slide/PDF parsing | rules and parsers | Local |

Local jobs share the loaded `qwen3` models and run one at a time; live
questions take priority over background work.

**Routing: permissions plus search, model only when unclear (decided 2026-11-20).**
Claude is never used to route.

1. **Permissions decide where to look.** Search only covers spaces the user
   may read (policy engine + retrieval filters). A user with one space is
   routed to that space's agent, no further step.
2. **Search decides where the answer is, with no model.** Results carry their
   space. If the strong matches clearly come from one space, only that agent
   answers; if they clearly come from two, both answer and the Concierge
   combines them.
3. **Unclear cases only go to the local `router` tier** (`qwen3:8b`; was `qwen3:4b`, thinking
   off). "Unclear" means: strong matches split across three or more spaces
   with no clear leader, or every match below the relevance threshold (vague
   question). The model sees the question and one-line agent descriptions
   (no vault content) and picks the agents. If the 4B is busy, the request
   waits briefly or `qwen3:8b` takes it, whichever the eval shows is faster.
4. **If Ollama is down, no model is used:** every permitted space that
   appears in the results is asked, and the Concierge combines the answers.

Every routing decision logs its reason (`single_space`, `search`, `model`,
`fallback`) and the chosen spaces, never the question, so "why was HR asked?"
is auditable. The thresholds are tuned in the Phase 3 eval, which also tracks
how often step 3 runs, routing accuracy and latency. If step 3 runs rarely,
it stays; with many more departments it may be needed more often.

- **Tiers, not model names:** agents ask for `answer`, `reasoning`, `router` or `background`.
  `models.yaml` maps each tier to a provider and model:

  ```yaml
  router:     {provider: openai_compat, location: local, model: qwen3:8b}  # local; same model as answering and the Classifier
  classifier: {provider: openai_compat, base_url: http://host.docker.internal:11434/v1, model: qwen3:4b, keep_alive: 5m}  # local (Ollama); 8B and Claude Haiku as eval baselines
  background: {provider: openai_compat, location: local, model: qwen3:8b}  # Librarian, review summaries, handover checks
  answer:   {provider: anthropic, model: claude-haiku-5-5}
  reasoning: {provider: anthropic, model: claude-sonnet-5-5}
  # later, e.g.:
  # answer: {provider: openai_compat, base_url: http://ollama:11434/v1, model: qwen3:32b}
  ```

- **Two adapters:** `anthropic`, plus `openai_compat`. The second covers Ollama,
  vLLM, LM Studio and llama.cpp servers, which all speak the OpenAI-compatible
  API. Switching to local models is a config change.
- **Per-space override:** `core` can be pinned to a local provider the day it
  is ready, while other spaces stay on Claude. A space can also be set to
  `local_only: true`. The gateway then refuses to send that space's text to any
  cloud provider, even if the config is wrong.
- **Embeddings are local from day one.** **`qwen3-embedding:0.6b`** runs on
  the server via Ollama, which uses Apple Silicon's GPU (Metal). It was chosen
  over `bge-m3` (decided 2026-11-20) because it uses about half the memory
  (~0.6 GB), reads very long passages (32k tokens) and is **multilingual**.
  Search queries are embedded with a short instruction prefix; documents are
  embedded as-is. Both output 1024-dimension vectors, so the index schema is
  the same. Being multilingual means: English content now, and Chinese, Malay and other
  languages later, all land in the same index without re-indexing. A question
  in one language can even find an SOP written in another. Indexing never
  sends text out, and moving the chat model to local later does not mean
  re-indexing. Each chunk also stores its detected language, so language-aware
  full-text search can be added when a second language arrives.
- **Portable tool use:** agent loops use a provider-neutral tool and message
  format. The adapters translate it. Local models with weaker tool-calling get
  a stricter JSON-mode fallback.
- **Quality gate before switching:** the same eval set (§12, Phase 3) runs
  against each candidate local model, and a tier only moves to local when it
  meets the pass threshold.

### 5.2 Cost efficiency (without weakening answers)

Every lever here is **measured against the eval set** (Phase 3). A lever is
only kept if answer accuracy and citation validity stay at the bar.

1. **Cheapest capable model first, with escalation:**
   - Department agents answer with **Haiku 5.5** by default. They escalate to
     **Sonnet 5.5** only when the question needs real reasoning: the evidence
     conflicts, the answer spans several SOPs, confidence is low, or the user
     asks for a step-by-step plan.
   - At list prices, Haiku 5.5 input is about 20× cheaper than Sonnet 5.5.
   - The escalation rule is tuned on the eval set, not guessed.
2. **Prompt caching:** system prompts, tool definitions and space configs are
   frozen and placed first, so repeat requests read them from cache. Cache
   reads cost a fraction of normal input.
3. **Tight context:** only the top passages, at slide or section level, are
   sent, never whole documents. Each agent has a per-question token cap.
4. **Skip work that adds nothing:** answers are never merged by a model.
   One department's answer streams straight to the user; with several, each
   streams into its own section with its own citations.
   Routing needs no model in most cases and never uses Claude (*Routing*).
5. **Answer reuse:** an identical question, asked with the same access scopes
   against the same document versions, reuses the stored answer. It is
   invalidated automatically when any cited SOP changes. SOP questions repeat a
   lot.
6. **No scheduled work on Claude:** Librarian reports, review summaries and
   gap labels all run on local tiers.
7. **Everything that reads the whole vault is already local:** embeddings, the
   Classifier, OCR, the name detector, the Librarian and routing.
8. **Visibility:** each request logs tokens and cost. A cost dashboard shows
   cost per user, per space and per question. Budgets give a soft warning and
   a hard daily cap.

**Rough cost per question** (to be replaced by measured numbers from Phase 3):

| Path | Approximate cost |
|---|---|
| Haiku answer (most questions) | ≈ $0.003–0.01 |
| Sonnet escalation | ≈ $0.04–0.08 |
| Blended (about 20% escalated) | ≈ **$0.015** |

**When local models make sense:** switch an answering tier to local when
**both** of these hold:
- the monthly API bill for that tier, multiplied by 12–18 months, exceeds the
  cost of the hardware that can serve it at peak concurrency
- the local model passes the same evals

Until then, staying on the API is cheaper and gives better answers. The cost
dashboard shows when the crossover arrives.

#### Local answering eval (decided 2026-11-21; runs in Phase 3)

Goal: find out whether a local model can replace Haiku for answering and
Sonnet for hard questions, and how much memory the Mac mini needs for it.
Candidates live in `config/eval/answer-candidates.yaml`:

| Candidate | Type | Smallest Mac | Why it's in the test |
|---|---|---|---|
| `qwen3:8b` | dense 8B | 16 GB | The realistic ceiling on 16 GB |
| `qwen3.5:9b` | dense 9B | 16 GB | Newer generation, same size |
| `qwen3:14b` | dense 14B | 32 GB | Strongest dense model at usable speed |
| `qwen3:30b-a3b` | MoE, 3B active | 32 GB | **Likeliest Haiku replacement**: big-model knowledge, near-4B speed |
| `gpt-oss:20b` | MoE, 3.6B active | 32 GB | Strong reasoning and tool use; reasoning-tier candidate |
| `hermes4:14b` | dense 14B | 32 GB | Tuned for tool use and structured instructions |

References: Haiku 5.5 (answering) and Sonnet 5.5 (hard subset). Ollama tags
are checked at run time and newer releases can be added to the file.

**Question sets** (demo vault only, fictional data):

1. **Answering** (~50 per demo space): single-SOP questions, slide and
   speaker-note questions, programme/stage-filtered questions.
2. **Logic and reasoning** (~30): conflicting SOPs (which version wins and
   why), multi-step procedures ("client missed two sessions and the strategy
   session is next week: what happens?"), cross-department questions, numbers
   and dates (lead times, floor prices, leave rules).
3. **Abstention** (~20): questions the vault does not cover, or covers only in
   spaces the user can't read. The right answer is "no SOP covers this".
4. **Tool use** (~20): the agent must search, read the right note and cite it.

**Measured:**

| Metric | Pass bar for replacing Haiku |
|---|---|
| Correct answers (graded per question) | within 5 points of Haiku |
| Valid citations (cited passage supports the claim) | ≥ 95% |
| Correct abstention | ≥ Haiku (a confident wrong answer is the worst failure) |
| Logic and reasoning set | within 5 points of Haiku; compared with Sonnet for the reasoning tier |
| Valid tool calls | ≥ 98% |
| Time to first word (realistic prompt) | ≤ 4 s on the target Mac |
| Peak memory | fits the target Mac next to the stack |

**How it runs:** quality doesn't depend on the machine (same model, same
quantization), so models too big for the 16 GB dev MacBook can be tested on a
rented machine; the data is fictional, so nothing real leaves. Speed is
measured on the Mac mini, or estimated from its memory bandwidth before
buying. Each model gets its own prompt tuning (§5.3, point 1) before it is
judged. The result decides two things: whether answering moves local, and
whether the Mac mini needs 32 GB.

### 5.3 Making the models better over time (especially local ones)

Model weights don't improve just from being used. Answers improve through
four mechanisms, in order of payoff:

1. **Better retrieval and prompts per model** (cheapest, biggest gains):
   chunking, filters (programme and stage), passage count and the prompt
   wording are tuned against the eval set **for each model**, because local
   models usually need tighter context and more explicit instructions.
2. **Reviewed playbooks** (learning at the agent layer). When a type of
   question keeps getting good answers by a certain route (which notes,
   which filters, what answer shape), the Librarian **proposes a playbook**
   for that space, e.g. "*for pricing questions in the delivery stage, check
   the Rate Card SOP first, then the programme's commercial notes*".
   - A lead approves or rejects each playbook. It is versioned and scoped to
     one space, and tested with the evals before it goes live.
   - Agents never write their own instructions unsupervised. That keeps
     behaviour auditable, and stops something learned in one user's or
     space's conversations from leaking into another's.
3. **A data flywheel from human decisions** (on the company machine only):
   - **Classifier:** every reviewer *approve / edit / reject* of an AI label
     is a correctly labelled example.
   - **Answers:** 👍/👎 feedback, plus answers that a lead marked as correct
     or corrected.
   - **Search:** which result a user actually opened for a query.

   These are stored as a versioned dataset alongside the evals. They never
   leave the company machine and are covered by the retention rules (§11).
4. **Fine-tuning small local models** (Phase 7+):
   - **The Classifier goes first.** It has the cleanest training data (reviewer
     decisions) and is a small model.
   - LoRA fine-tuning runs **on the Mac itself with Apple's MLX**. On 16 GB
     this is realistic for the 3–4B Classifier, scheduled after hours. Larger
     answering models need 32 GB+ or a rented GPU for the training run.
   - **Training data comes from the company's own material:** approved SOPs,
     human-approved or human-corrected answers, and reviewer labels.
     **Fine-tuning on raw Claude outputs is not planned** until the company
     has checked Anthropic's commercial terms on using outputs to train
     models.
   - **Every fine-tuned model must pass the full eval set** (for the
     Classifier: **zero over-exposures**) before it replaces the current one.
     Models are versioned, with one-click rollback in `models.yaml`.

**Candidate local models** are chosen by eval results, not by name. Examples
to include in the Phase 7 comparison:

- general open-weight models (e.g. the Qwen family)
- **Nous Research's Hermes 4 / 4.3** (14B and 36B open weights, strong at
  tool calling and structured output)

On 16 GB only the small Classifier fits. 14B-class answering models need
roughly 24–32 GB; 36B-class models need 48 GB+.

**Hermes Agent** (Nous Research's open-source self-improving agent framework)
was considered and **not adopted as the runtime**. Its self-written skills and
cross-session memory don't fit per-user permission enforcement, fail-closed
access or an auditable trail. Its useful idea, reusable learned procedures, is
adopted in the controlled, human-approved form above (reviewed playbooks).

### Department agent configuration

Each department agent is defined by `config/spaces/<space>.yaml`: persona,
scope, escalation contact, glossary, answer rules (for example, HR always links
the official policy), and an optional extra system prompt. A new department is
added by creating a space and a config, with no code change.

### Answer contract

Every answer includes:

- **citations:** `doc_id`, title, version, effective date
- **confidence**
- **"no answer found":** when the evidence is missing, the agent says so
  instead of falling back to model memory (llm-wiki's evidence rule)

Unanswered questions are logged as **knowledge gaps** for that space.

### Request flow

1. The user asks the Concierge a question.
2. The policy engine resolves the user's allowed spaces.
3. Search runs inside those spaces; the results decide which agents answer
   (local `qwen3` only when unclear, never Claude; see *Routing*, §5).
4. The Concierge dispatches to the chosen department agents in parallel.
5. Each agent runs hybrid retrieval inside its scope and drafts a cited answer.
6. The Concierge shows each department's answer in its own section with its
   citations (no model; a source cited twice is listed once).
7. The answer streams back over SSE.
8. Audit and gap events are written.

## 6. SOP lifecycle and schema (in Obsidian frontmatter)

Authors write notes in the app (the CEO/admin may also use Obsidian). The SOP
metadata lives in each note's frontmatter, which extends llm-wiki's article
schema. The app's "New SOP" form fills it in. The same template is available in
Obsidian as `_templates/SOP.md`.

```yaml
doc_type: sop            # sop | guide | checklist | faq | template
sop_id: CORE-TRN-004
title: "Running a Personal Brand Discovery Workshop"
version: 1.2
status: published        # draft | in_review | published | retired
space: core              # optional; human label overrides the AI Classifier (§4.1)
sensitivity: internal    # public | internal | restricted (missing → restricted)
owner: "[[Jane Tan]]"
# author is not stored here: it comes from the git commit of the logged-in user (§3.2)
# reviewer / approved_by / approved_on are written by the platform after review
reviewer: "[[Alex Lim]]"
approved_by: "[[Alex Lim]]"
approved_on: 2026-11-02
review_cycle_days: 180
review_due: 2027-05-01
programme: "[[Signature Personal Brand Programme]]"   # browse by programme
stage: discovery         # discovery | strategy | content | delivery | follow-up (configurable)
tags: [workshop, discovery, onboarding]
```

### Organising by programme and stage

Content can be browsed **by programme** (e.g. *Signature Personal Brand
Programme*, *Executive Presence Workshop*) or **by stage** of delivery (e.g.
discovery → strategy → content → delivery → follow-up; the stage list lives in
`config/vault.yaml` and can be changed).

- Both are frontmatter fields, so a single note sits in one place in the vault
  but appears in both views.
- The suggested folder layout for new content is
  `Programmes/<Programme>/<NN Stage>/…`, with cross-programme material under
  `Methodology/` and `Shared Templates/`. The platform doesn't depend on it.
- For notes missing these fields, the Classifier proposes them along with
  space and sensitivity. Adding them carries no exposure risk, so they are
  applied after the author confirms, with no lead approval needed.
- Agents use programme and stage as search filters. "What's step 3 of the
  discovery stage for the Signature programme?" goes straight to the right
  notes.

### Workflow: write in the app, review in the app

```
Author writes in the app ─▶ clicks "Submit for review" (status: in_review)
                                         │
                                         ▼
          Reviewer opens it in the platform (logged in), sees the changes
          compared with the last approved version, then approves or
          requests changes
                                         │ approve
                                         ▼
          Platform records reviewer, time, exact version ─▶ published
          (optional: writes reviewed_by / approved_on into the note's
           frontmatter as a commit by the "platform" account)
                                         │
                Librarian flags review_due ─▶ new version | retired
```

- **Who reviewed is recorded by the platform, not typed into the note.**
  Reviewing requires a logged-in platform session. Each approval is stored with
  the reviewer, the time, the git commit and the content hash. In the
  frontmatter, `reviewer:` and `approved_by:` are **outputs** written back by
  the platform; if someone types them by hand, they are ignored.
- **An approval covers one exact version.** If the note is edited after
  approval:
  - The new version goes back to **pending review**.
  - The bot **keeps citing the last approved version**, retrieved from git,
    until the change is approved.

  Published SOPs can't change silently.
- **Who can approve:**
  - In `core`, the **CEO (core lead)** approves SOPs.
  - When the lead writes an SOP, they may approve it themselves. It is recorded
    as *self-approved* and shown as such in reports.
- **Only approved content is used in answers.** Drafts and in-review notes
  are visible only to their author and to users with `review` on that space.
- **Every version is kept,** with its author (from git), its reviewer (from the
  platform) and its approval state. The bot cites the current approved version.
- **Notes without frontmatter** (existing ordinary notes) are still indexed as
  `doc_type: guide`. They get their access from the classification rules in
  §4.1, but are only cited after someone approves them.

## 7. Knowledge-retention features

- **Handover notes (decided 2026-11-21, replacing AI capture interviews):**
  exit interviews stay with a person, and how the work is done should already
  be in SOPs. What gets lost is *in-flight work*: a client part-way through a
  programme, or follow-up someone else must pick up. A handover note covers
  that.
  - **Template:** client and programme, current stage, what's done, open
    actions with dates, upcoming sessions, client preferences and
    sensitivities, files and links, contacts, risks.
  - **Access:** always `restricted` (it names clients). It is visible to the
    author, the named receivers, the space lead and the CEO. Receivers are
    granted access to that note only.
  - **Acknowledgement:** each receiver confirms "read and understood", reusing
    required-reading sign-off. Questions go in comments while the author is
    still around.
  - **Completeness check:** the local `background` tier flags gaps before
    sending ("no date for the next session", "open action has no owner").
    It is local because the note names a client.
  - **If a handover shows missing *how-to* knowledge,** the author or lead
    uses "Start a draft" to turn it into an SOP through the normal review.
  - Exit-interview notes, if any, are filed through the app like any other
    note and classified as usual.
- **Gap detection, used by HR for follow-up training:**
  - **What's collected:** unanswered or low-confidence questions, and answers
    marked "not helpful", are grouped into **gap topics** per space, programme
    and stage. For example: "*Delivery stage, Executive Presence, handling
    camera-shy clients*: 9 questions from 4 people this month".
  - **Space leads** see their space's gap topics, with example questions, to
    write missing SOPs.
  - **HR sees anonymised, aggregated gap reports across all spaces:**
    - **topics and counts only,** broken down by team or role, never by
      person
    - a topic is shown only once it involves **at least 3 people**, so no
      individual can be singled out
    - **no restricted content:** a topic's label is written from the
      questions, never from restricted SOP text
  - **Follow-up tracking:** each gap topic has a status: open → training
    planned → addressed. It is marked addressed when an SOP is published or
    the training is delivered, and HR and leads can see whether questions on
    that topic actually drop afterwards.
- **"Gaps from your searches" (personal recommendations):**
  - **Signals:**
    - Library searches with no or weak results.
    - Rephrasing the same search several times.
    - Chat questions with no or low-confidence answers.
    - 👎 feedback.
    - Opening several results and leaving without using any.
  - **What the user sees:** a "Gaps from your searches" panel on their Home
    page, e.g. "*You've looked for 'handling camera-shy clients in the
    delivery stage' 4 times this month; no SOP covers it.*" Each suggestion
    comes with one-click actions:
    - **Request an SOP:** notifies the space lead, with the anonymised search
      context.
    - **Start a draft:** opens a new SOP from the template, pre-filled with
      the programme, stage and links to related SOPs the user can access. The
      person writes it; no AI text.
    - **Suggest an expert:** the authors of the most closely related SOPs, as
      the people to ask or to write the missing SOP.
  - **Privacy:** personal suggestions are visible **only to that user**. They
    also feed the anonymised aggregate gap topics (minimum 3 people for HR,
    §7 above).
  - **No leaks through suggestions:** if a topic *is* covered, but only by an
    SOP the user can't access, the user sees an ordinary gap ("no SOP you can
    access covers this; ask the delivery team"), which never confirms that the
    restricted SOP exists. Separately, the lead sees an **access gap**: "*people
    without access keep asking about something covered by a restricted SOP;
    consider publishing a public or internal version*".
  - **Cost:** grouping runs nightly as a batch job. Embeddings are local, and
    topic labels are written by the local `router` tier, so gap data never
    leaves the server.
- **Coverage map (gaps nobody has searched for yet):** a programme × stage
  grid showing which cells have no published SOPs, or only stale ones (e.g.
  *Executive Presence → follow-up: 0 SOPs*). It is shown to leads and the
  CEO, and HR sees the same grid without document titles.
- **Staleness:** a `review_due` dashboard, plus llm-wiki `volatility` and
  `verified` checks.
- **Bus-factor report:** SOPs whose only owner or contributor is one person,
  and owners who are leaving.
- **Conflict detection:** the Librarian flags SOPs that contradict each other
  (for example, two different versions of the client onboarding steps).
- **Retract:** admins can purge a note or PII from the index, caches,
  conversation history and audit excerpts. This reuses `llm-wiki retract`
  verification. The vault itself is edited by its owners.

## 8. API surface (contract for the web app)

All endpoints are under `/api/v1` and documented in an OpenAPI spec generated
by FastAPI.

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/login` (password → step token), `POST /auth/totp/verify`, `POST /auth/totp/enroll` + `/enroll/confirm` (first sign-in), `POST /auth/refresh` (rotating HttpOnly cookie; reuse revokes the session), `POST /auth/logout`, `POST /auth/invite/accept`; `GET /me` (incl. effective scopes), `GET /notice`, `POST /notice/acknowledge`, `GET /spaces` |
| Chat | `POST /conversations`, `GET /conversations`, `POST /conversations/{id}/messages` (SSE stream: tokens, `agent_dispatched`, `citation`, `done`), `POST /messages/{id}/feedback` |
| Knowledge | `GET /spaces`, `GET /spaces/{s}/documents`, `GET /documents/{id}` (+`/versions`), `POST /spaces/{s}/uploads` (parsed by the ingestion worker, no model; saved in the uploader's name, then classified) |
| Editing | `POST /notes` (new draft), `GET /notes/{id}/source`, `PUT /notes/{id}` (with `base_version`; refused if the note changed meanwhile), `POST /notes/{id}/attachments` (PPTX/PDF/DOCX/images, with source tool + original link), `POST /notes/{id}/submit`, `GET /notes/{id}/diff?from=&to=`. All are permission-checked and committed in the user's name |
| Classification | `GET /classifications/queue` (grouped), `POST /classifications/{id}/approve`, `/reject`, `/edit`, `POST /classifications/bulk-approve`, `GET /reports/classification-accuracy` |
| Workflow | `GET /reviews` (in-review notes + proposals), `GET /reports/governance` (unapproved publishes, unclassified notes), `POST /admin/reindex` |
| Retention | `GET /spaces/{s}/gaps`, `GET /spaces/{s}/stale`, `POST /handovers`, `POST /handovers/{id}/acknowledge`, `GET /reports/bus-factor` |
| Admin | `/admin/users` (create → one-time invite, update roles/active, `/invite`, `/reset-totp`, `/unlock`), `/admin/roles` (+ `/grants`), `/admin/grants/{id}`; `GET /admin/audit` (filterable), `GET /admin/audit/verify` (hash chain); `POST /retractions`. Spaces come from `config/spaces/*.yaml` |
| Ops | `GET /health`, `GET /metrics` (Prometheus) |

Outbound webhooks (review requested, SOP published, review due) let the future
app, email, Slack or Teams subscribe without changes to the core.

## 8.1 Frontend (web app)

The full screen-by-screen spec, wireframes and the v1 extras (onboarding
paths, required reading with sign-off, PDF export, bookmarks and Ctrl+K) are
in [`frontend-spec.md`](frontend-spec.md).

### Decisions (2026-11-20)

| Topic | Decision |
|---|---|
| Devices | **Desktop web only** (laptops and desktops, modern Chrome, Edge, Safari or Firefox). Layouts target 1280 px+ wide and stay usable down to 1024 px. No phone or PWA support in v1. |
| Editor | **Visual (Word-like) editor** that saves **Obsidian-compatible markdown** |
| Look | **Clean, neutral default.** Theme values (colours, fonts, logo) live in one place, so company branding can be dropped in later without touching screens |
| Code location | Same repository: **`backend/`** and **`frontend/`** as separate top-level folders |

### Tech stack (chosen for the 16 GB Mac mini)

- **React + TypeScript, built with Vite into static files.** No Node server
  runs in production. The files are served by the same web server (Caddy)
  that handles HTTPS in front of the API, so the frontend costs essentially no
  memory on the host. All logic and permission checks stay in the backend.
- **UI components:** shadcn/ui (Radix + Tailwind), which is accessible and
  neutral, with theming through CSS variables for later branding.
- **Data:** TanStack Query for server state, and a **typed API client
  generated from the backend's OpenAPI spec**. When the backend changes, the
  build fails if the frontend is out of date.
- **Streaming chat** over SSE. **Charts** for dashboards with a small charting
  library.
- **Routing:** React Router.

### Visual editor and Obsidian compatibility

- Built on **Milkdown** (ProseMirror + the remark markdown parser). It is
  markdown-first, so what's saved is clean markdown, not HTML.
- **Custom nodes for Obsidian syntax:**
  - `[[wikilinks]]` and `[[note|alias]]`, with autocomplete from the notes the
    user can see
  - `![[embeds]]`, shown as slide or PDF previews
  - `#tags`
  - callouts (`> [!note]`)
- **Frontmatter is not shown as raw YAML.** It appears as a form above the
  editor (owner, programme, stage, review cycle and so on). Platform-written
  fields such as `approved_by` are read-only.
- **Anything the editor doesn't understand is preserved untouched** as a raw
  block, so the CEO's Obsidian-only syntax survives app edits.
- **Round-trip test:** every note in the demo vault is opened and saved
  without changes in CI, and the file must come out **identical**. This
  guards Obsidian compatibility on every change.
- **Edit clashes:** if a note changed since the user opened it, saving opens a
  side-by-side merge screen (§3.2).

### Slide and worksheet viewers

- **Slides:**
  - At upload, the worker renders each slide to an image using LibreOffice in
    headless mode, run on demand and then exited, so it isn't resident in
    memory.
  - The viewer shows the slide image beside its extracted text and speaker
    notes.
  - Citations jump straight to the slide.
- **PDF worksheets:** shown in the browser's PDF viewer, at the cited page.
- **Images are permission-checked** like the documents they come from. URLs
  are short-lived and tied to the signed-in user.

### Screens

| Area | Screens | Who |
|---|---|---|
| **Home** | Role-based dashboard: ask box; recent SOPs for my programmes; my drafts; reviews waiting for me | Everyone (cards vary by role) |
| **Ask** | Chat with streaming answers; citations with version, author and approver badges that open the exact section or slide; programme/stage filters; 👍/👎 feedback; history; "who to contact" | Everyone |
| **Library** | Browse by programme, stage or department; search; reading view with links and backlinks; slide and PDF viewers; version history with side-by-side changes | Everyone (filtered by permissions) |
| **Write** | New SOP form; visual editor; attachment upload (with the original tool and a link back to the Google Slides or Canva design); submit for review; my drafts; merge screen | Staff with `contribute` |
| **Review** | SOP changes shown against the last approved version; AI label suggestions (grouped, bulk approve, reasoning shown); unplaced notes; governance report | Leads; authors for their own notes |
| **Retain** | "Gaps from your searches" panel with request / draft / suggest-expert actions; coverage map (programme × stage); handover notes (create, mine, awaiting my acknowledgement); gap dashboards (leads: own space with example questions; **HR: anonymised cross-company view with follow-up status**); review-due list; bus-factor report | Leads, HR, CEO |
| **Admin** | Users, roles and grants; invites with TOTP enrolment; staff notice editor; audit log search and export; retention settings; cost and usage dashboard; Classifier accuracy; system health; API key status | CEO / platform admin |
| **Account** | Two-factor setup; staff notice acknowledgement; profile | Everyone |

**Notifications:** in-app only in v1 (a bell icon for review requested,
approved, review due, and gap follow-ups). Email would need an outside mail
service, so it is left for later and kept optional.

### Frontend testing

- Component tests (Vitest + Testing Library).
- End-to-end tests (Playwright) of the key journeys against the demo vault:
  - ask → open citation
  - write → submit → approve → cited
  - permission checks: a core-staff user never sees restricted links or
    badges
- The editor round-trip test.
- Accessibility checks on core screens.

## 9. Data model (Postgres)

- `users`
- `roles`
- `user_roles`
- `spaces`
- `grants(role_id, space_id, max_sensitivity, actions[])`
- `documents(id, vault_path, doc_type, sop_id, title, status, owner, review_due, content_hash)`
- `document_access(document_id, space_id, role: owner|shared, sensitivity, source: frontmatter|folder_rule|approved_ai|auto_tighten|safeguard|default, decided_by, decided_at)`: the labels actually in force
- `classification_proposals(document_id, content_hash, proposed_space, proposed_sensitivity, proposed_shared_with, confidence, rationale, evidence_spans, model, status, reviewed_by, reviewed_at)`
- `document_versions(document_id, version, content_hash, git_commit, authored_by, author_source: git_push|frontmatter|unattributed, indexed_at)`
- `reviews(document_id, content_hash, git_commit, reviewer_id, decision: approved|changes_requested, self_approved, comment, decided_at)`: an approval applies only to that exact version
- `one_time_tokens(user_id, purpose: invite, token_hash, expires_at, used_at)`: set-password links; only the hash is stored
- `refresh_tokens(user_id, family_id, token_hash, expires_at, revoked_at)`: rotation with reuse detection
- `attachment_parts(document_id, part: slide|page, number, title, speaker_notes)`: slide- and page-level citations
- `document_links(from_id, to_id)` (resolved `[[wikilinks]]`, used for related SOPs and broken-link reports)
- `chunks(id, document_id, version, text, embedding vector, tsv tsvector)`. Access comes from `document_access` via a join, and RLS is enforced there, so changing a label applies instantly without re-indexing.
- `uploads`
- `conversations`
- `messages`
- `message_citations`
- `gap_topics(id, space_id, programme, stage, label, question_count, distinct_people, status: open|training_planned|addressed, owner_id)`
- `gap_events(gap_topic_id, message_id, reason: no_answer|low_confidence|not_helpful)`: links to messages; never exposed to HR
- `notice_acknowledgements(user_id, notice_version, acknowledged_at)`
- `handovers(id, note_id, from_user_id, programme, client_ref, status: draft|sent|acknowledged, due_date)`
- `handover_receivers(handover_id, user_id, acknowledged_at)`
- `audit_events` (append-only, hash-chained)

**Retrieval** is hybrid: pgvector similarity plus Postgres full-text, with
titles, tags and linked-note context as boosts. Scope filters are applied before ranking.
pgvector keeps v1 at one database. A dedicated vector database is only needed
at very large scale.

## 10. Repository layout

```
backend/                        # Python (FastAPI); everything server-side
  app/
    api/        routers, auth, policy engine, SSE
    agents/     concierge, department, classifier, librarian + prompt templates
    models/     model gateway: anthropic + openai_compat adapters
    retrieval/  chunking, local embeddings, hybrid search
    vault/      parsers (MD/PPTX/PDF/DOCX + OCR), labels, git layer, indexer, renditions
    classify/, governance/, retention/, projects/, eval/   domain services
    workers/    arq jobs: git change detection, nightly checks, retention and review-due
                (slide rendering to images: planned)
    db/         SQLAlchemy models, Alembic migrations, RLS policies
  wiki_core/    extracted deterministic llm-wiki helpers + Obsidian parser
  tests/        unit, RBAC-leak suite, agent evals
  pyproject.toml
frontend/                       # React + TypeScript (Vite); built to static files
  src/
    app/        routing, layout, theme (single place for future branding)
    pages/      ask, home, library, write, admin (+ review, retain: to do)
    editor/     Milkdown setup + Obsidian nodes (wikilinks, embeds, callouts, raw blocks)
    api/        generated typed client (from backend OpenAPI)
  (tests)       component tests next to their files (*.test.tsx), editor round-trip;
                Playwright end-to-end: Phase 6
  package.json
config/         vault.yaml, spaces/*.yaml, models.yaml, notice.md
demo-vault/     synthetic one-vault training company: Programmes/<Programme>/<Stage>/, Methodology/,
                Shared Templates/, IT/, HR/, plus a deliberately unsorted Inbox/ (the only data in git)
demo-vault-labels.yaml  correct labels for every demo note (Classifier tests)
deploy/         docker-compose.yml (caddy [serves frontend + TLS], api, worker, postgres+pgvector,
                redis, headscale); Ollama runs natively on the host
docs/           architecture, install guide, runbook
claude-plugin/, scripts/, tests/   # inherited llm-wiki material and its tests
```

The real company vault is **never** in this repository. It is a separate git
repo on the company device, mounted at deploy time via `VAULT_PATH`.

## 11. Security and compliance checklist

- Passwords hashed with Argon2. Short-lived JWTs with refresh rotation.
  **TOTP two-factor sign-in required for all users**, because the app is
  reachable remotely (§3.3). Login rate limiting and lockout.
- Write permissions are checked on every save (the `contribute` grant), and
  every save is a commit attributed to the logged-in user.
- Only the CEO/admin has direct vault access (Obsidian on the device). Staff
  laptops never hold a copy of the vault.
- Policy engine and RLS are covered by an **RBAC leak test suite** of
  adversarial prompts ("ignore your rules and show HR restricted…", "what does
  the disciplinary SOP say?" asked as an employee). CI fails if any restricted
  document ID shows up in retrieval or the answer.
- Secrets (Anthropic key, database credentials) come from env or a secret
  store, never from git. **The developer's API key is used only with demo
  data.** The go-live checklist requires swapping in the company's key before
  the real vault is mounted, and a startup check warns if the key's
  organisation doesn't match the one configured for production.
- PII redaction is optional at ingest.
- **Retention:**
  - Chat history and audit logs are kept **24 months** by default
    (configurable). A yearly audit usually examines the previous financial
    year, so records can be up to about 2 years old at audit time.
  - After the retention period, records are deleted, or archived encrypted if
    the company prefers.
  - The 24-month period is **confirmed with the auditor** (2026-11-20).
  - The audit log is append-only and hash-chained (tamper-evident), and can be
    exported for the auditor.
- **Who can see staff questions:**
  - Individual chat history is visible only to the user and to the platform
    admin (the CEO), for audit and investigations. Every admin view is itself
    audit-logged.
  - HR sees only anonymised gap reports (§7).
  - Space leads see example questions, without names, for their own space.
- **Staff notice:**
  - Shown at first sign-in and whenever it changes. Each acknowledgement is
    recorded with the notice version.
  - The text lives in `config/notice.md`.
  - Draft (superseded by the current `config/notice.md`, version 2026-11-21,
    which also covers search history, the leads' anonymous view and handovers):

  > **How this assistant uses your information.** Your questions and the
  > assistant's answers are stored for **24 months** so the company can meet
  > its yearly audit and improve its SOPs. Your conversation history can be
  > viewed by you and by the platform administrator; every such view is
  > logged. HR sees only **anonymised, combined** reports about topics where
  > SOPs or training are missing; never who asked what. Parts of your
  > question and relevant SOP passages are sent to an AI service to generate
  > answers. Please don't enter personal data about clients or colleagues
  > unless needed. Questions? Contact [admin contact].
- **Data boundary:**
  - The developer works only with `demo-vault/`.
  - Real vaults are mounted by company admins on the company's machine.
  - Logs, error reports and traces **never contain note text or questions by
    default**, only IDs and hashes. That makes it safe to share logs with the
    developer for debugging.
  - The audit log (which does contain the text) stays on the company's machine.
- **LLM data handling:**
  - Embeddings run locally, so indexing sends nothing out.
  - At answer time, only the scope-filtered passages needed for that question
    go to the Claude API. Ask Anthropic about zero-data-retention terms.
  - A space marked `local_only` can never be sent to a cloud model; the
    gateway refuses (§5.1).
- **Client data:** a personal-branding business will hold personal data about
  its clients. Keep client-identifying details out of SOPs where possible, or
  file them under a `restricted` folder. Retract covers removal (PDPA).
- License: llm-wiki is MIT. Keep its notice in `backend/wiki_core`.

## 12. Phased plan

**Status at a glance (2026-11-25).** Details per phase follow below.

| Phase | Backend | Frontend |
|---|---|---|
| 0. Foundations | Done | Done |
| 1. Identity and RBAC | Done | Done (sign-in, two-factor, notice, Admin users/roles/grants) |
| 2. Indexing and retrieval | Done, incl. local OCR | Done: Library, editor, upload, merge, versions (notes, decks, PDFs), bookmarks, Ctrl+K, images in notes, slide pictures (headless LibreOffice, rendered once per deck version, cached; text fallback without it) |
| 2b. AI Classifier | Done | Done: Review → AI label suggestions (grouped, bulk approve, edit, plain-words widening warning), unplaced notes |
| 3. Agents | Done | Done: Ask (streaming, citations panel, filters, follow-ups, no-answer actions, feedback, history) and Home |
| 4. SOP governance | Done (approvals, reviews, notifications, governance report, webhooks, required reading and sign-off with append-only acknowledgements, material-change flag, PDF export with watermark and audit, per-space `pdf_export` switch) | Done: Review → SOP changes (side-by-side, material-change option), governance report, notifications bell, reader sign-off banner and "Assign reading", Export PDF (note or programme stage), print CSS |
| 5. Retention | Done (handovers, gaps, coverage, stale, bus factor, conflicts, retract, retention job, onboarding paths, cost and usage: daily `model_usage` totals priced from `config/models.yaml`) | Done: Retain (gaps incl. HR view, coverage, review due, required-reading status with CSV export, bus factor, conflicts), handover notes, onboarding paths (learner, lead editor, HR completion), Admin → audit log and cost and usage, Home cards (CEO cost, leads, HR, required reading, onboarding) |
| Project spaces | Done | Done: project list and detail, members, share requests and lead approval |
| 6. Company deployment | Not started | Playwright end-to-end suite and accessibility pass not started; nothing tried in a real browser yet |
| 7. Local models | **Fully local since 2026-11-25** (owner's decision): every tier, answering included, runs on `qwen3:8b` / `qwen3:14b` / `qwen3-embedding`; no Claude. Improvement loop not started | Cost dashboard reads $0 |

Tried 2026-11-24 (§7): a `qwen3:14b` confirm stage with thinking on cuts conflict-check false alarms (dev 12.5% → 4.2%, held out 13.0% → 5.6%) with no lost catches. In the nightly job since 2026-11-24 (`conflict-confirm` tier). Since 2026-11-25 the 14B judges a night's pairs on its own when there are at most 100 (fresh held-out set: 85.2% vs 81.5% accurate, 75.9% vs 63.0% of conflicts caught).

**Progress:** Phase 0 *backend* done (2026-11-20): the gateway with its data
boundary, the Docker stack, migrations, the demo vault, CI and a content-free
logging policy. Phase 0 *frontend* done (2026-11-23): `frontend/` with Vite +
React + TypeScript, shadcn-style components, a neutral theme in
`src/app/theme`, an i18n layer, a typed client generated from the OpenAPI spec
(CI fails when it is stale), the layout shell with permission-aware menus, and
the sign-in page (password, then TOTP; the access token is kept in memory only,
and the refresh cookie restores the session after a reload). The `web` service
(Caddy) serves the build at http://localhost:8080, proxies `/api`, and sets a
strict CSP, with no access log. The API trusts `X-Forwarded-For` only from Caddy's
fixed address, so the sign-in rate limit counts each person separately. Initial
JS is 122 KB gzipped (budget 300 KB). The TOTP enrolment screen comes in Phase 1.

Phase 1 *backend* done (2026-11-21): sign-in with password then mandatory
TOTP (enrolment on first sign-in, replay protection, lockout after 5
failures, per-address rate limit), rotating refresh cookie with reuse
detection, invite links (no email needed), the policy engine
(`app/policy/engine.py`: fail-closed sensitivity, scopes, grant validation),
Postgres RLS via the `sop_reader` role (`app/db/scoped.py`), append-only
hash-chained audit log, staff notice acknowledgement, admin API with
last-admin protection, default roles in `config/roles.yaml`, and a CLI
(`python -m app.cli`). Phase 1 *UI* done (2026-11-23): two-factor setup at
first sign-in (QR code drawn in the browser, so the secret never goes to an
outside service), set-password page for invite links (token in the URL
fragment, removed from the address bar on load), the staff notice as a gate
until acknowledged (markdown without raw HTML) and on its own page, an account
page, and Admin → users (invite with a one-time link, edit, new password link,
reset two-factor, unlock; no new roles for yourself) and roles and grants
(company-wide grants offer only company actions). New endpoint
`GET /admin/options` (manage_users): every space and the allowed actions, since
`/spaces` lists only spaces the caller can read. Admin screens and the markdown
renderer load on demand; initial JS 127 KB gzipped.

Phase 2 *backend* done (2026-11-21); local OCR followed on 2026-11-23 (below):
- **Parsers** (`app/vault/parse.py`): Obsidian notes (frontmatter, wikilinks,
  embeds, tags, heading-path chunks), PPTX slide by slide with speaker notes,
  PDF pages with form-field labels, and DOCX.
- **Labels from rules** (`config/vault.yaml` folder rules, then frontmatter,
  then safeguards: email, phone, NRIC, bank account and flagged terms force
  `restricted`). Anything else is unassigned and quarantined. On the demo
  vault this gives 0 over-exposures and quarantines the 4 Inbox notes.
- **Git layer** (`app/vault/git.py`): path safety, an `SOP-User:` trailer,
  the platform as committer, and an `SOP-Unattributed:` trailer for the
  nightly check.
- **Migration 0003**: versions, chunks (pgvector HNSW plus a weighted
  tsvector), links, slide/page parts and tags. RLS on every derived table goes
  through `sop_doc_visible()`, so drafts are visible only to their author and
  the space's reviewers.
- **Indexer**: incremental via git diff; human label decisions are kept;
  embeddings failed while Ollama was down are filled in later.
- **Hybrid search** `GET /search`: RRF over vector and keyword results, with a
  0.65 cosine cutoff so a question nothing answers returns nothing, and
  keyword-only search when embeddings are down.
- **Editing API** `/notes`: create, source, save with `base_version` (409 on
  an edit clash), and attachment upload. Each save is committed in the user's
  name and re-indexed immediately. The one-way rule applies to people's saves
  too.
- **Library endpoints**: filters, `/parts`, `/versions` and `/file`.
- **Worker**: indexes Obsidian commits every minute; nightly 02:05 check.

Local OCR done (2026-11-23), `app/vault/ocr.py`: RapidOCR (ONNX models inside
the package, CPU only, no downloads) reads image files, pictures on slides
(including groups and placeholders), scanned PDF pages (pages with under 30
characters of text) and images in Word files, marked "Text in image". The text
goes through the same labels, safeguards and name detector. Repeated images
(logos) are read once, at most 60 per file; tiny images are skipped. About 0.4 s
per image after a one-off 2-7 s load. The Docker image uses headless OpenCV.
Off switch: `ocr.enabled` in `vault.yaml`.
Phase 2 *UI*, slice 1 of 3 done (2026-11-23): the Library (browse by
programme with stage columns and ⚠ for stages without SOPs, by stage, or by
department; search with slide/page hits and counts-only outcome reporting) and
the reader (Obsidian links resolved only against documents the reader can see;
unknown and unreadable links both show "(note not available)", so a restricted
title never appears; programme names open that programme's Library page;
embeds as cards; tables; no raw HTML or script links), a deck viewer (each
slide's text and speaker notes, `?slide=N`), PDFs in the browser viewer from a
blob (`?page=N`; CSP now allows `frame-src blob:`), downloads fetched on click,
"Used in" backlinks and version history. New endpoints: `GET /documents/stages`
(order from `config/vault.yaml`) and `GET /documents/{id}/backlinks` (linking
notes the reader can't see are left out; covered by the red-team IDOR loop).
Initial JS 129 KB gzipped.

Phase 2 *UI*, slice 2 of 3 done (2026-11-23): the editor (Milkdown, loaded
only when editing; 137 KB gzipped). Obsidian syntax (links, embeds, tags,
callout markers, comments, highlights, block ids) is held as verbatim chips.
Before saving, every block the person didn't change is put back from the
original source, so open-and-save changes nothing and a one-word fix is a
one-line change; the round-trip test checks this on every demo-vault note.
Also: metadata as a form (YAML comments and unknown fields kept; broken YAML
is never overwritten), "needs lead approval" when loosening access, autosave
of drafts 8 s after the last change, templates (SOP, checklist, run-sheet,
playbook), new notes pre-filled from a gap (`/write/new?programme=&stage=&related=`),
upload with the tool name and original-design link, link/embed picker
listing only readable documents, a leave-without-saving warning, and the
merge screen: changes in different blocks merge automatically, the same block
changed on both sides is chosen per block (theirs or yours), nothing is merged
by a model. Edit appears in the reader for contributors (cosmetic; the save
endpoint checks again).

Known limits of slice 2: each autosave is a commit (history gets busy on long
drafts; squashing in-progress commits is a later option); images aren't shown
inside the editor (they stay as `![[...]]` chips); the AI's label suggestion
isn't shown inline yet (it needs a per-note suggestion endpoint); moving a
note to another space isn't in the form (it needs the lead anyway).

Phase 2 *UI*, slice 3 of 3 done (2026-11-23):
- **Version history for readers.** `GET /documents/{id}/versions` now lists
  only versions the person may read: approved ones (every version for the
  note's editors), each judged by the labels it had
  (`app/governance/history.py`, shared with the review diff). Before this,
  anyone who could read a note saw every commit's author and time, unapproved
  ones included. `GET /documents/{id}/versions/{commit}` returns one version's
  text under the same rules (full 40-character commit of this note only; every
  refusal is a 404). The reader opens an older version with a banner; the
  compare page shows two versions side by side (line diff in the browser,
  unchanged runs folded), by default the latest against the live one.
- **Bookmarks** (`bookmarks` table, migration 0012; `GET/POST /me/bookmarks`,
  `DELETE /me/bookmarks/{id}`): ★ on a document or one slide/page, listed on
  Home and in the Library. Private to the user; each target is re-checked
  against today's access on every list (hidden targets are left out, not
  deleted); bookmarking something you can't open is a 404.
- **Ctrl+K / ⌘K** (`GET /quick-search?q=`): titles of readable documents,
  programmes and stages from them, your bookmarks and your own conversations,
  plus actions shown only where the menu is. `%`, `_` and `\` match
  literally; queries are never stored or logged. The dialog loads on first
  use (initial JS 135 KB).
- Red-team: the IDOR loop covers the version and bookmark endpoints, and the
  old-restricted-version attack now also tries the versions list and
  `/versions/{commit}` with a commit taken from the lead's view.

Deck and PDF versions (2026-11-23):
- Each attachment version keeps the labels it was indexed under
  (`document_versions.access`, migration 0013), so an old deck or PDF is
  judged by those labels like an old note. Versions indexed before 0013 have
  no snapshot and fail closed (owner-space approver only).
- `GET /documents/{id}/versions/{commit}` returns a text rendition of any kind
  ("## Slide n: title" with notes, "## Page n"), made on demand with the
  indexer's parsers (`app/vault/renditions.py`, in-memory LRU of 16, cleared on
  retract); `/versions/{commit}/file` serves that version's file. The reader
  shows old decks slide by slide and old PDFs in the viewer; compare diffs the
  text renditions.

Not done in Phase 2 (carried forward):
- **Slide pictures:** render each slide to an image at upload (LibreOffice,
  headless, run on demand), served permission-checked; the viewer shows text
  and notes until then. Images inside notes aren't shown yet either.

Phase 2b *backend* done (2026-11-21):
- **Classifier** (`app/classify/`): one local model call per document version.
  It proposes space and sensitivity, quotes evidence and lists names; the note
  text is passed as data.
- **One-way rule** (`rules.decide`): on a note that already has labels, the AI
  may only tighten them; anything looser, a different space or sharing waits
  in the review queue. An *unplaced* note gets no access from the AI at all,
  not even `restricted`: the blind eval showed the model picking the wrong
  space, which would have shown the note to that space's leads. It stays
  visible to its author only. An exhaustive test checks both rules.
- **Name detector**: names from the same local call, minus staff (from the user
  list), the company's own names (`vault.yaml`) and names a reviewer marked
  safe. Names the model reports that aren't in the text are ignored. In
  `name_check_spaces` (core) every new version stays `restricted` until it is
  checked, and an unreadable model reply never counts as checked.
- **Safeguards are a floor applied at read time**, in RLS and in the policy
  engine: the labels people approved are kept and come back when a safeguard
  clears.
- **Review queue** (`/classifications/...`): grouped, with approve (optionally
  edited), reject, bulk approve, name review and an accuracy report. Who
  approves follows §4.1. A proposal quotes the note, so it is shown only to
  the author or to someone who can already read the note and reviews its
  current or proposed space; never to the proposed space alone. Unplaced
  notes go to their author (or, if unknown, the `core` lead), who *places*
  them: approving labels they lack the rights for applies `restricted` in
  that space and forwards the rest to that space's reviewers.
- **Eval** (`python -m app.cli eval-classifier --repeats 3 --out x.json`, then
  `compare-evals a.json b.json`): the 32 demo-vault files plus 88 fictional
  cases (`config/eval/classifier-cases.yaml`), shown blind as `Inbox/<name>`
  with labels stripped, with 95% confidence intervals and a paired McNemar
  test. Blind, 3 runs: `qwen3:8b` 76.4% (CI 71.7-80.5%), `qwen3:4b-instruct`
  63.3% (CI 58.2-68.1%), p = 0.002. Both are below the 85% bar, which is why
  the AI only suggests for unplaced notes. (An earlier 32-file run that showed
  real folder paths scored 94%; the folder names gave the answer away.)
- **Few-shot from human labels** (built, off by default): the Classifier can be
  shown up to 4 similar notes that people labelled (frontmatter, folder rule
  or approved AI label; distance ≤ 0.6). Evidence that isn't in the note is
  dropped, and so is a rationale copied from an example. Blind eval, 1 run, pools of
  0/30/60/120 labelled notes: 79.2 / 71.7 / 79.2 / 77.5% placed correctly,
  over-exposed 11.7 / 15.0 / 10.8 / 10.8%. None of the differences is
  significant (McNemar p ≥ 0.11), so `ClassifierService(use_examples=False)`
  is the default. Caveat: the eval cases come in clusters, so neighbours
  are unusually close; re-run `eval-classifier --example-pool N` on
  real reviewer labels before switching it on. A LoRA fine-tune on those labels
  (Phase 7) is the likelier path to a real gain.
- **Local models and thinking**: `qwen3:4b` on Ollama is now the 2507
  *Thinking* build, which can't switch thinking off. The `router` and
  `classifier` tiers therefore use `qwen3:4b-instruct`. Thinking is switched
  off with `reasoning_effort: none`, because Ollama 0.34 ignores `/no_think`.

Phase 3 *backend* done (2026-11-21):
- **Concierge** (`app/agents/`): permissions, then search, then the local
  router only when unclear. Department agents follow the answer contract
  (sources only, [n] citations, `NO_ANSWER`, a confidence line, escalation to
  `reasoning` only when Claude is available).
- **Data boundary**: each agent call's scope covers every space attached to
  its passages, including shared-in ones.
- **Chat API** (`/conversations`, SSE events, feedback): conversations are
  private to their owner, and gap events and audit events hold ids only.
- **Local fallback**: `answer` and `reasoning` fall back to the local
  `answer-local` tier (`qwen3:8b`) when Claude has no key or is down.
- **Answering eval**: `python -m app.cli eval-answers [--model TAG] [--repeats N]`
  runs 226 tuning questions in `config/eval/questions.yaml`, graded
  deterministically with 95% CIs. Model comparisons use the 54 held-out
  questions in `questions-holdout.yaml`, which are never used for tuning.
  Held-out, 2 runs: `qwen3:8b` 87.0% vs `qwen3:4b-instruct` 77.8%. The 4B
  wrongly says "no answer" more often (14% vs 4%) and covers fewer required facts.
  Decision: 8B answers, 4B routes.
- **Search expansion** (`retrieval.search.expand`): a matched document of
  ≤ 4000 characters is passed whole, in order. Longer ones get the matched chunks
  plus their neighbours, within 8000 characters per space, and only documents
  already in the RLS-filtered hits are read. `eval-retrieval`: questions with
  every required fact in the context went from 77.3% to 99.5% (tuning set) and
  97.6% (held-out), and the median context went from about 1.8k to 4k characters. Held-out answers,
  8B, 2 runs: 86.1% vs 87.0% before (p = 1.0). Wrong "no answer" replies fell
  from 4% to 0%, and the remaining failures are answers that leave out a required fact
  although it is in the context. That is model answer quality, not search. First
  word: median 5.5 s, p90 11.3 s on the 16 GB MacBook.
- **Outage handling**: when an agent's model call fails, its section is marked
  `unavailable`. The user is told to try again and no knowledge gap is logged.
- **Answer reuse** (cost lever 5, 2026-11-23), `app/agents/reuse.py`, migration
  0011: a department answer is stored under a hash of its exact prompt (the
  question, normalised for case and spacing; the approved passages retrieved
  for *this* user, with their document versions and chunk ids; the space's
  rules), the models and the link allowlist. It is served only after the
  asker's own retrieval returned the same passages, so it never crosses access.
  Any change to a cited SOP gives a new key. Rows go at once on retract or a
  "not helpful" vote, and after `answers.reuse_days` (30, 0 = off). Outages,
  fallback-model answers and answers the output guard trimmed are never stored.
  Reused answers are marked `reused` in the stream, the message and the audit.
- The Ask UI followed on 2026-11-23 and 2026-11-24 (below).

Phase 3 *UI*, slice 1 of 2 done (2026-11-23):
- **Ask screen** (`/ask`, `frontend/src/pages/ask/`): answers stream in
  (fetch + ReadableStream through `authFetch`, so the token stays in memory),
  with live steps from `routing`/`agent_dispatched`, one section per department
  (never merged), and numbered citations. Clicking a citation opens a side
  panel with the cited note section highlighted, or the slide with its speaker
  notes and neighbours, or the PDF page, plus version, author and approver.
  Answer markdown renders with no raw HTML, no images and no links except
  citation markers (the output guard already removes them server-side).
- **Stop** aborts the stream; **Copy** copies the text with its sources.
- **No answer** says so plainly and offers Request an SOP (`/me/gaps/request`
  keyed on the question id, now sent in the `done` event), Start a draft (only
  for people who can write) and Suggest an expert (authors from `/me/gaps`).
- **Unavailable** (stream error or outage) says the Library still works and
  links to a Library search for the same question.
- **👎 reasons** (wrong / outdated / missing steps / unclear / other):
  `message_feedback.reason`, migration 0014, refused on 👍.
- Home's ask box opens `/ask?q=`; conversations are listed by day.
- Measured live (8B, M-series Mac, warm): first words after ~5–15 s, a short
  answer done in ~15 s.

Phase 3 *UI*, slice 2 of 2 done (2026-11-24):
- **History**: `GET /conversations?q=` matches titles and your own questions
  (wildcards literal, never logged); `PATCH /conversations/{id}` renames;
  `POST /conversations/{id}/hide` hides (migration 0015, `hidden_at`). A hidden
  conversation is a 404 everywhere (messages, asking, rename, quick search,
  bookmarks) but stays in the database and audit until the 24-month job.
- **Programme and stage filters** (`MessageIn.programme/stage`) narrow both the
  routing search and each department's search; access still comes from RLS.
  They carry over to the next question and from Home; stored in the message's
  route record.
- **Follow-up chips** (`app/agents/followups.py`), no model call: up to three
  other sections of the SOPs the answer cited, nearest after the cited one,
  read under the asker's RLS scope from live text only. Sent in `done` and
  re-made on the latest answer in history (so lost access removes them).
- **Citation panel**: "newer version pending review" for people who can see
  unapproved changes (`pending_change`).
- **Home cards** (only when they have something): Gaps from your searches
  (Request / Draft / Expert), Waiting for you (`GET /me/waiting`: reviews you
  can do, your unsubmitted drafts, AI label suggestions you can see), Recently
  approved (`GET /me/recent`: approvals in 30 days, each document re-checked
  under RLS and the policy engine), Bookmarks.

Left for their own phases: Export PDF of an answer (Phase 4, with `/exports`);
Required reading and Onboarding path cards (Phases 4 and 5, no backend yet);
CEO and HR cards (unplaced notes, stale SOPs, coverage, cost, gap topics,
onboarding completion) with the Retain screens (Phase 5). "Recently updated in
your programmes" lists recent approvals you can read: there is no user →
programme link yet. Speed targets in the spec (first words < 2 s) assume the
cloud path; the local 8B measures ~5–15 s to first words.

Phase 4 *backend* done (2026-11-21):
- **Version-bound approvals** (`app/governance/`): an approval covers one
  *governed hash*. That is the file without the keys the platform writes itself
  (`status`, `reviewer`, `approved_by`, `approved_on`, `review_due`). So
  write-back, or someone typing `approved_by:` by hand, never changes what was
  approved, and any other edit does.
- **Last approved version stays live**: chunks carry `live` (approved, used in
  answers) and `current` (latest). After an edit, answers keep citing the
  approved text until a lead approves the new version. The Library and file
  downloads show the change only to its editors (the author, or people with
  contribute/review on the space); everyone else gets the approved version.
  This is enforced in RLS (`sop_doc_wip_visible`, `sop_doc_editor`) and in the
  policy engine (`can_see_unapproved`). Retired notes are never cited.
- **Status is decided by the platform**: approved means published. Never
  approved means draft or in review as written, otherwise *unreviewed*
  (readable, never cited). On first connection, notes already marked
  `published` (and all attachments) are approved once as `baseline`. The
  governance report lists them as "published outside the platform".
  Attachments embedded in a note are approved together with it.
- **Review API** (`/notes/{id}/submit|diff|approve|retire`,
  `/reviews/...`): the diff is against the last approved version; a change
  summary is written by the local `background` tier in the worker. Approving
  is refused (409) if the note changed after it was submitted.
  Self-approval is allowed for leads and recorded as `self`.
- **Citations** carry `written_by`, `approved_by`, `approval` and `approved_on`.
- **Governance report** (`/reports/governance`): unattributed edits, changes
  awaiting review, never approved, published outside the platform,
  self-approved, review overdue.
- **Notifications** (`/notifications`, ids only), **review-due reminders**
  (daily, each due date once), **webhooks** (`config/webhooks.yaml`, an outbox,
  HMAC-signed, payloads hold ids only), and **write-back** of the approval
  into the frontmatter as a platform commit (`governance.write_back`).
- Note: in name-checked spaces (`core`), a new version stays `restricted`
  until the name check runs (about a minute), as before.

Router on the 8B (2026-11-21): with routing, answering and classification on
`qwen3:8b`, only one chat model (plus the embedder) stays loaded on a 16 GB
machine, so Ollama no longer swaps models. Dev set, 226 questions: routing
100% with either router; answers 94.2% (8B router) vs 94.7% (4B), McNemar
p=1.0; first token median 5.1 s vs 5.7 s, total 6.1 s vs 6.8 s.

Phase 5 *backend* done (2026-11-21):
- **Handover notes** (`/handovers`): rendered from the template into
  `Handovers/<space>/`, with no space access rows. They are readable only by
  the author, the receivers, the space's leads and the CEO roles
  (`handovers.always_visible_roles`), through per-person `document_readers`
  rows. This is visibility v3, in both RLS and the policy engine. Handovers are
  never used in answers and skip the Classifier. There is a deterministic
  completeness check (missing sections, actions without owner or date,
  sessions without date) plus an optional local-model check, send,
  acknowledgement and comments.
- **Gap topics** (nightly `group_gaps`): gap events now record the asker and
  the question. Similar questions in a space are grouped with local
  embeddings, and labelled by the local router from the questions only.
  Programme and stage come from the nearest approved SOP. An *access gap*
  records a document that covers the topic but the askers couldn't read
  (leads only).
  - Leads see topics with anonymous example questions (`/spaces/{s}/gaps`).
  - HR sees topics only once at least 3 people asked, by role (roles with
    fewer than 3 people are grouped as "other"), with a before/after trend
    once a topic is addressed (`/reports/gaps`).
  - Topic status: open, then training planned, then addressed.
- **Gaps from your searches** (`/me/gaps`): Library searches are kept per
  user, as private history covered by the retention period. Weak searches and
  unanswered questions are grouped. Related SOPs and experts come only from
  what the user can read, so a restricted SOP is never confirmed.
  "Request an SOP" tells the leads anonymously. "Opened results but used
  none": the Library reports `POST /search/{id}/outcome` (counts only, no
  document ids); opening 2+ results and using none is a gap on its own.
- **Coverage map** (`/reports/coverage`; titles for leads, counts for HR),
  **staleness** (`/spaces/{s}/stale`), **bus factor** (`/reports/bus-factor`;
  sole human author, and people with a `leaving_on` date set by the admin).
- **Conflict detection** (nightly, up to 500 local-model checks): the closest
  passage pairs between approved SOPs. Each pair of approved versions is
  checked once. Results go to people who can read both SOPs and lead one of
  their spaces.
  - **Eval (2026-11-23)**, `python -m app.cli eval-conflicts [--stage search]`:
    48 labelled fictional pairs for tuning (`config/eval/conflicts.yaml`) and
    36 held out (`conflicts-holdout.yaml`), half conflicts each. They include
    conflicts buried in long passages, implicit ones (units, roles) and
    same-topic pairs that agree. The held-out set has now been used once;
    later tuning needs fresh held-out pairs.
  - **Search settings** (tuned on dev): the old 0.25 cutoff with 3 neighbours
    let only 7/24 dev and 2/18 held-out conflicts reach the model. Now 0.55
    with 10 neighbours: 24/24 dev, 16/18 held out. Up to 500 checks a night
    (~3 s each, ~25 min; job timeout 1 h). Already-checked pairs are skipped
    inside the query, so they no longer use up the row limit and starve new SOPs.
  - **The 8B judge** (current prompt, 3 runs): dev 91.7% of conflicts caught,
    12.5% false alarms; held out 83.3% caught, 22.2% false alarms. Weak spots:
    one contradicting sentence inside a long passage (held out 3/9), and the
    same rule in other words or units ("every quarter" vs "four times a
    year": 3/9). A revised prompt aimed at both made no difference (1 of 144
    trials, p = 1.0), and an over-flagging screen prompt did worse (93.8% vs
    100% on the first 32 pairs); neither is used.
  - **End to end on held-out pairs:** 15 of 18 conflicts found, up from 2.
  - **Deferred (to do, 2026-11-23):** a stronger second-stage model has a real
    job now (equivalent or reworded pairs the 8B flags). Try a 14B in Ollama
    overnight on the dev set before AirLLM. Buried conflicts are misses, so a
    confirm stage can't fix them; smaller passages or a stronger first stage
    could. Listed under "Deferred work" below.
  - **14B confirm stage, tried 2026-11-24 (dev set, 3 runs, thinking off):**
    `qwen3:14b` alone: recall 95.8% (69/72), false alarms 16.7% (12/72),
    accuracy 89.6%, 6.1 s per pair. It catches more buried conflicts (9/12 vs
    6/12) but flags *every* equivalent pair (0/12 vs 3/12). As a confirm stage
    after the 8B it agreed with every 8B flag, so the two-stage result equals
    the 8B alone (129/144 both, no item differs, McNemar p = 1.0) and only adds
    time. Not used; `conflicts-holdout2.yaml` (36 fresh pairs) stays unread for
    the next candidate. Both models treat "two weeks" vs "10 working days" or
    "6 months" vs "180 days" as contradictions, so this is unit reasoning, not
    model size.
  - **Second round, 2026-11-24 (dev set, 3 runs each; 8B alone: 89.6%,
    false alarms 12.5%):**

    | Setup | Caught | False alarms | Accuracy | vs 8B |
    |---|---|---|---|---|
    | 8B + unit notes (`app/retention/units.py`) | 91.7% | 8.3% | 91.7% | p = 0.25 |
    | 8B → 14B, thinking on | 91.7% | 4.2% | 93.8% | p = 0.03 |
    | 8B + units → 14B thinking + units | 90.3% | 4.2% | 93.1% | — |

    Unit notes write a conversion after each duration, time or frequency
    ("two weeks [= 14 days, 10 working days]"). They help on their own but not
    on top of the 14B, which then reads "three months [≈ 13 weeks]" against
    "12 weekly sessions" as a mismatch. They stay an eval option
    (`--units`), off in the nightly job. The 14B with thinking takes about
    30 s per flagged pair, versus 6 s without.
  - **Held out once (`conflicts-holdout2.yaml`, 3 runs):** 8B alone caught
    72.2% (39/54) with 13.0% false alarms; 8B → 14B thinking caught the same
    39 with 5.6% false alarms (83.3% vs 79.6% accuracy, p = 0.125: two
    pairs, same direction as dev). The 14B never cleared a real conflict. The
    bigger gap is now misses, which a confirm stage can't fix: a deadline, an
    owner, buried and implicit conflicts the 8B cleared.
  - **In the nightly job (2026-11-24):** 8B on every pair, then the 14B with
    thinking on the 8B's flags (`conflict-confirm` tier, at most 60 a night).
    A live check on demo passages from the worker: 8 s per 8B check, 50-80 s
    per 14B check; the one pair the 8B flagged, the 14B cleared.
  - **Missed conflicts, three fixes tried 2026-11-24** (8B → 14B pipeline, 3
    runs each). Fix 1: a rule for one group that differs from a general rule
    is a conflict unless a passage says it's an allowed exception (both
    stages), and the 8B is told it is a screen ("flag if unsure"). Fix 2:
    sentence focus (`app/retention/focus.py`): the three most alike sentence
    pairs, found with the embedding model, shown before the passages. Fix 3:
    both. Holdout2 was used as a second tuning set (its misses had been read);
    `conflicts-holdout3.yaml` was written before any fix ran.

    | Accuracy (caught / false alarms) | Dev | Holdout2 | Holdout3 (once) |
    |---|---|---|---|
    | Current: 8B → 14B thinking | 93.8% (91.7 / 4.2) | 83.3% (72.2 / 5.6) | 80.6% (61.1 / 0.0) |
    | Fix 1 | 93.8% (91.7 / 4.2) | 88.0% (79.6 / 3.7) | 83.3% (66.7 / 0.0) |
    | Fix 2 | 95.1% (95.8 / 5.6) | 80.6%* (68.5 / 3.7) | — |
    | Fix 3 | 93.1% (91.7 / 5.6) | 88.9% (79.6 / 1.9) | — |

    \* 6 errors: Ollama's Metal backend crashed twice (17:25, 21:17), both
    times in a 14B stage with focus, which swaps the embedding model and the
    14B on every pair. Focus didn't help buried conflicts reliably (dev 6 → 9
    of 12, holdout2 3 → 1-2 of 9), so it stays an eval option (`--focus`).
    Fix 1 helped unstated group overrides (deadline, implicit) without new
    false alarms (explicit exceptions 12/12) or more 14B work (47 vs 45 flags).
    Held out it gained 5 checks and lost 2 (p = 0.45; holdout2 +5/−0): small
    but consistent, so it is on in the nightly job. Without the confirm tier
    the 8B gets the strict rule but not the screening wording.
  - **14B alone, tried 2026-11-25** (thinking on, strict rule, 3 runs).
    Holdout2 and holdout3 were already used, so they count as tuning sets;
    `conflicts-holdout4.yaml` was written before this run and run once.

    | Accuracy (caught / false alarms) | Dev | Holdout2 | Holdout3 | Holdout4 (once) |
    |---|---|---|---|---|
    | 8B → 14B, fix 1 | 93.8% (91.7 / 4.2) | 88.0% (79.6 / 3.7) | 83.3% (66.7 / 0.0) | 81.5% (63.0 / 0.0) |
    | 14B alone | 96.5% (100 / 6.9) | 93.5% (94.4 / 7.4) | 96.3% (98.1 / 5.6) | 85.2% (75.9 / 5.6) |

    Holdout3: 17 checks gained, 3 lost (p = 0.003); holdout4: +9/−5
    (p = 0.42). Same direction on all four sets. On holdout4 it caught more
    buried (13 vs 10 of 15), implicit and deadline conflicts, for 3 false
    alarms in 54. Both still miss changed tools (0/3) and most changed
    numbers (1/3). The 14B takes about 40 s a pair against the pipeline's 5 s.
  - **In the nightly job (2026-11-25):** if a night has at most 100 pairs to
    check (`SOLO_PAIRS`), the 14B judges each one alone. A normal night only
    has pairs from edited SOPs: the demo vault has about 5 pairs per note, so
    about 1-2 hours at most. More pairs (the first full run, a bulk import)
    use the 8B → 14B pipeline so the job still finishes in one night. The job
    limit is 3 hours.
  - **What's left:** changed tools and numbers are still missed (holdout4,
    0/3 and 1/3). All four held-out sets are now used; write a fresh one
    before the next comparison.
- **Retract** (`POST /retractions`, `manage_users`): a document, or a value
  plus its common encodings (llm-wiki's `retract_patterns`).
  - What it purges: the index, answers that cited the document, chat text,
    titles, searches, review summaries, handover text, AI proposals and
    conflicts.
  - It then re-scans and returns the remaining counts (they must be 0), and
    counts the vault files still holding the value (llm-wiki's scanner), so
    the owners know what to edit.
  - The value is stored only as a hash. The indexer skips a retracted file
    until its content changes.
- **Retention** (nightly, `retention_months: 24`): deletes old conversations,
  searches, gap events, notifications, webhook deliveries and audit events. The
  audit chain stays verifiable through a stored anchor hash. Handovers and SOPs
  are kept.
- **Staff notice** updated (version 2026-11-21) to cover search history,
  anonymous leads' view and handovers. Everyone is asked to acknowledge it
  again.

Prompt-injection hardening (2026-11-21/22):
- **Data marking** (`app/agents/untrusted.py`): every model prompt puts
  people's text (passages, notes, diffs, handovers, questions) inside tags,
  escaped so it can't close or open a tag. The system prompt says tagged text
  is never an instruction, and a reminder follows the data. Dev eval: 93.4% vs
  94.2% before (p=0.69); first token 5.5 s vs 5.1 s.
- **Quiet flag** (`app/governance/injection.py`): fixed patterns, no model.
  Matching pattern ids (never text) are stored on the document. They show in
  the governance report (`possible_instructions`) and on the note's review.
  No notifications, and the note is not blocked. The demo vault has no flags.
- **Output guard** (`app/agents/output_guard.py`): links are removed from
  answers while they stream unless allowlisted (`answers.allowed_link_domains`),
  images are always removed, and uncited lines are dropped from the final
  answer. Prompt marking alone did not stop the 8B: the guard was added after
  live tests showed it copying a phishing link and a "DAN MODE ON" line from a
  planted note.

Project spaces (2026-11-22), `app/projects/`, `app/api/projects.py`, migration 0010:
- **Who:** space leads create projects and name any person as project lead
  (a per-project position, not a role). The project lead adds and removes
  members, approves the project's notes, asks departments to share, renews and
  can hand the lead over. A `create_project` permission can be added later if
  waiting for a space lead becomes a bottleneck.
- **Project space:** `p-<slug>`, notes under `Projects/<slug>/`, whatever their
  frontmatter says (no moving them into a department, no `shared_with`). It is
  local-only for the model gateway.
- **Sharing:** nothing from a department is shared until *that department's*
  lead approves. The check uses their own roles, never project access, so a
  project can't be used to reach another department (red-team rule). On
  approval they choose the whole space or selected folders/SOPs, at internal
  unless they pick restricted. Shares are read-only and cover published SOPs
  only, with the safeguard floor. Selected folders/SOPs are passed per request
  (`sop.partial`) and checked by `sop_doc_visible()` v4 and
  `can_view_document(..., path, doc_id)`. The lead can revoke at any time,
  effective at once.
- **Time limit:** at most 6 months (`projects.max_days: 184`), with one reminder
  to the project lead 14 days before the end. Renewing asks each department's
  lead once to confirm; until they do, a share runs to its old date.
- **After the end** (or closing): department shares stop. Members keep
  read-only access, at internal level, to the project's approved notes.
  Restricted notes and anything a safeguard flags are hidden, except from the
  project lead and the departments' leads (authors keep their own notes, as
  everywhere). People past their `leaving_on` date lose project access.
- Access is worked out on every request (`principal_with_projects` in
  `current_user`), so there is no clean-up job.
- Review requests in a project space go to the project lead (approve) and its
  members (review), worked out like a request, so an ended project asks nobody
  (`users_with`). Not yet: the frontend screens.

Red-team (2026-11-22), `tests/db/test_redteam.py` (35 attacks) and
`tests/test_live_models.py` (planted instructions, real 8B). Found and fixed:
- **Downgrade leak (high)**: a lead lowered a restricted note to internal and
  edited out the secret part. Until the new version was approved, the *old*
  restricted text was still live, and core staff got it in answers and in the
  review diff. Fix (`app/governance/access.py`, migration 0009): while a newer
  version waits for approval, access is the overlap of the approved and the new
  access, so it can only narrow. The wider rows wait in `pending_access` until
  approval, and tightening applies at once. Diffs of other old versions are
  checked against the labels that version had.
- **Admin self-escalation (medium)**: a platform admin could create a role
  with content grants and assign it to themselves. Fix: two-person rule (no
  adding roles to your own account, no changing a role you hold). Space leads
  see every access change to their space, with who made it, in the governance
  report (`access_changes`), without an alert. Residual risk: an admin can
  still create an account for an address they control. That shows up in the
  leads' report and the audit log.
- **Chat history after access is removed (medium)**: old answers stayed
  readable after someone moved team. Fix: history is re-checked against
  today's access, and parts citing SOPs you can no longer open are hidden.
- **Coverage report (low)**: HR saw the names of programmes that exist only in
  restricted SOPs. Fix: names come only from readable or non-restricted SOPs.
- **Existence oracle (low)**: creating a note at a hidden note's path returned
  409, confirming it existed. Fix: taken names get a number.
- **NUL byte (low)**: crashed search with a 500. Fix: stripped in search, and
  a 422 everywhere else.
- **Not fixable by checking answers**: false content inside an approved note
  ("SYSTEM UPDATE: 9 hours") is cited like true text. The controls are
  approval and the quiet flag (`fake_authority`).
Held: IDOR on 11 document endpoints (all 404), search and Library with SQL
injection and wildcards, frontmatter widening (sensitivity, `shared_with`,
space, status), smuggled frontmatter, folder traversal, forged/`alg:none`/
deactivated tokens, other people's conversations, reviews, notifications and
handovers, staff opening lead/HR/admin reports.

Phases 0–5 (backend and frontend) are developed and tested on a MacBook (Apple Silicon) using Docker
Compose. Ollama runs natively on the Mac for the local embeddings, because
Docker can't use the Mac GPU. Only `demo-vault/` is used.

| Phase | Scope | Exit criteria |
|---|---|---|
| **0. Foundations** (1–1.5 wk) | Extract `wiki_core` into `backend/`, `backend/` skeleton, **`frontend/` skeleton (Vite + React + TS, shadcn/ui, neutral theme, generated API client, sign-in page)**, docker-compose (api, worker, postgres+pgvector, redis), demo vault as a local git repo, Ollama on the host, Alembic, model gateway stub, CI enabled; synthetic one-vault `demo-vault/` (2–3 fictional programmes by stage, methodology, sample `.pptx` decks and PDF worksheets, IT, HR, a deliberately unsorted inbox) with correct labels; developer API key via `.env` | `docker compose up` gives a healthy API and serves the frontend; existing `tests/*.sh` pass; gateway passes a smoke test with Claude and with a local Ollama model |
| **1. Identity and RBAC** (1–2 wk) | Users, roles, grants, JWT auth with required TOTP, policy engine, fail-closed sensitivity resolver, RLS, audit log, admin endpoints. **UI:** sign-in + TOTP enrolment, staff notice, admin users/roles/grants | Policy unit tests; a note with missing or invalid sensitivity is never returned to a `public`-only user; RLS blocks raw SQL reads outside scope |
| **2. Vault indexing and retrieval** (2 wk) | Obsidian parser (frontmatter, wikilinks, embeds, tags), **slide-by-slide PPTX** with speaker notes and local OCR, PDF worksheets with form fields, DOCX; **editing API** (create/edit/upload, permission-checked, committed in the user's name, edit-clash detection); change detection from git commits plus a nightly check for unattributed changes; local embeddings, hybrid search; new notes enter quarantine. **UI:** Library (browse by programme/stage/department, reading view, slide and PDF viewers, version history), **visual editor** with Obsidian nodes and the round-trip test, upload, merge screen | A note saved through the API is committed in the user's name and searchable within about 1 minute (to permitted users); an edit clash is refused, not overwritten; a user without `contribute` can't save; leak suite at retrieval level passes |
| **2b. AI Classifier** (1–2 wk) | Classifier agent, deterministic safeguards incl. the local name detector (staff names excluded), one-way rule, review queue with grouping and bulk approve, re-classification on edit, optional frontmatter write-back. **UI:** Review → AI label suggestions and unplaced notes | **`qwen3:4b` vs `qwen3:8b` compared** on the demo vault (8B unloads when idle on 16 GB); the smaller model that passes is chosen. On the demo vault: **0 over-exposures**; ≥ 85% of notes correctly placed without edits; a looser re-classification never takes effect without approval |
| **3. Agents** (2 wk) | Core agent first, then IT and HR; Concierge routing (permissions + search, local model only when unclear), one answer section per department, SSE streaming, citations, "no answer" handling, gap logging. **UI:** Ask (streaming chat, citation badges that open the slide or section, feedback, history), role-based Home | Eval set (about 50 Q&A per demo space) ≥ 90% correct with valid citations; zero leaks in the adversarial suite; **local answering eval** (§5.2) for every candidate in `config/eval/answer-candidates.yaml`, plus routing accuracy, to decide whether answering moves local and how much memory the host needs |
| **4. SOP governance** (1–2 wk) | In-platform review with changes shown against the last approved version and a short summary of the change (local `background` tier, generated on save), version-bound approvals, "last approved version stays live", self-approval flag, frontmatter write-back, governance report (unattributed edits, unreviewed changes), review-due reminders, Obsidian SOP template, webhooks. **UI:** Review → SOP changes with side-by-side diff, approve/request changes; in-app notifications | Demo: staff A edits an SOP → staff B (lead) approves in the platform → the bot cites it with "written by A, approved by B"; an edit after approval is not cited until re-approved |
| **5. Retention features** (1–2 wk) | Handover notes (template, receiver-only access, acknowledgement, local completeness check), gap topics with HR's anonymised view (minimum 3 people) and follow-up tracking, staleness and bus-factor reports, conflict detection, retract, 24-month retention job, staff notice and acknowledgement, **personal gap recommendations from searches, access gaps, coverage map**. **UI:** Retain (handover notes, gap dashboards incl. HR's anonymised view, review-due, bus factor), cost and usage dashboard, audit log viewer | Reports exposed via API; retract verified across index, caches and history |
| **6. Company deployment** (1 wk) | Install guide for company admins (Mac mini and Windows/WSL2 variants, Obsidian + Obsidian Git on the device for the admin, Headscale with embedded relay and ACLs (CGNAT/public-IP check, port-forward, domain + TLS), TOTP enrolment, backups); deploy on the company machine with the real vault mounted by them; backups; rate limits; metrics; frozen OpenAPI v1; Playwright end-to-end suite green on the deployed machine | Admin-run install succeeds; logs confirmed free of note text; API contract frozen |
| **7. Local models and the improvement loop** (when hardware is ready) | Model comparison including Qwen-family and Hermes 4/4.3 candidates; the data flywheel (reviewer labels, approved/corrected answers, search clicks); **MLX LoRA fine-tune of the Classifier** on its reviewer decisions; reviewed playbooks; switch tiers in `models.yaml` (`classifier` first, then answering tiers when memory allows), with versioned models and rollback | Each switched or fine-tuned model meets the eval threshold (Classifier: zero over-exposures) before it goes live; no cloud calls for `local_only` spaces (verified from gateway logs) |

**Later:** SSO (Entra/Google/OIDC: groups map onto roles, so the grants model
is unchanged), Slack/Teams adapters, the dashboard app, ticketing integrations
(Jira/ServiceNow handoff when the bot can't answer), and multi-tenant support.

### Deferred work (to do)

- **Conflict check, second stage:** done 2026-11-24 and 2026-11-25 (§7).
  With the `conflict-confirm` tier (`qwen3:14b`, thinking on), a night with
  at most 100 pairs (`SOLO_PAIRS`) is judged by the 14B alone. A bigger night
  runs every 8B check first, then the 14B on the 8B's flags (at most 60,
  `MAX_CONFIRMS`), so each model loads once; only pairs both flag are stored.
  A failed check or one over the cap is not stored and is checked again the
  next night. The job limit is 3 hours. Without the tier in
  `config/models.yaml` the job is the 8B alone. Unit notes and sentence focus
  are built but off; the strict exception rule is on. All four held-out sets
  are now used; write a fresh one before the next comparison.
  Next: changed tools and numbers are still mostly missed (§7).

## 13. Open questions for the owner

Resolved on 2026-11-20 (see §1):

- `core` covers methodology, training programmes, client delivery and training
  content, with strict access and a public tier.
- Core team of 2–3 staff plus the CEO (CEO = core lead).
- One Obsidian-format vault, a git repo on a local company device. Every app
  save is a commit in the logged-in user's name (no separate git server).
- Access labels are AI-proposed and human-approved. Unplaced notes are reviewed
  by their author or the department lead.
- Reviews and approvals happen in the platform and apply to one exact version.
- Slides are the main training format, with PDF worksheets.
- Claude is used only to answer questions (Haiku, escalating to Sonnet);
  routing, classification, search and background writing are local, and
  people write SOPs (2026-11-21).
- Development on a MacBook with a synthetic vault; the developer does not
  handle real data.
- All staff edit through the app; only the CEO/admin uses Obsidian, on the
  device. Remote staff reach only the app.
- Slides come from PowerPoint, Google Slides and Canva (v1: upload a
  `.pptx`/PDF export).
- There is no client list; a local name detector is used instead.
- Host is a Mac mini or a Windows PC. The bot is advisory only.

Also resolved: developer API key for testing, company key before go-live;
English with a multilingual index; organisation by programme and stage;
anonymised gap reports for HR; 24-month retention; a staff notice.

Also resolved: 24-month retention confirmed with the auditor; the host is
likely a 16 GB Mac mini (§3.4).

Still open (none block Phases 0–5):

1. **Usage:** expected users and questions per day, to refine cost estimates
   (the cost dashboard will measure this anyway).
2. **Host memory:** settled (2026-11-22): one local model, `qwen3:8b`, serves
   answering, classifying and routing, with `qwen3-embedding:0.6b` for search.
   Both stay loaded at once (about 8.3 GB). OCR adds about 0.5 GB on the
   worker. 16 GB runs this; 32 GB leaves room for a larger local answering
   model in Phase 7. Decide before buying, since Mac memory can't be upgraded.
3. **Office internet:** does it have a public IP (no CGNAT)? Needed for
   Headscale (§3.3).
4. **Programme and stage names:** the real list, or keep the placeholders
   until go-live.
