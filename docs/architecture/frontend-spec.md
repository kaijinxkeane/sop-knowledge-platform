# Frontend Specification (web app)

Status: proposal · 2026-11-20 · Companion to `sop-platform-plan.md` (§8.1)

## 1. Decisions

| Topic | Decision |
|---|---|
| Devices | Desktop web only (1280 px+ target, usable down to 1024 px) |
| Stack | React + TypeScript, Vite static build served by Caddy; shadcn/ui; TanStack Query; typed client generated from OpenAPI |
| Look | Clean neutral default; all brand values in one theme file |
| Editor | Visual editor (Milkdown) saving Obsidian-compatible markdown |
| **Polish priority** | **Ask (chat)** first |
| Home | **Ask-first** for everyone (CEO and HR get extra cards below the ask box) |
| Citations | **Side panel** beside the answer |
| v1 extras | Onboarding paths · Required reading with sign-off · PDF/print export · Bookmarks and Ctrl+K quick search |

## 2. Navigation and global elements

```
┌───────────────────────────────────────────────────────────────────────┐
│ ◧ SOP Assistant  Ask  Library  Write  Review(3)  Retain  Admin  ⌘K 🔔 ◉│
└───────────────────────────────────────────────────────────────────────┘
```

- **The top bar shows only what the user may use.** A user without
  `contribute` sees no *Write* menu, and only leads and authors see *Review*.
  *Admin* is CEO/admin only. Hiding a menu is cosmetic; the backend still
  enforces every permission.
- **Ctrl+K / ⌘K quick search** (from any page):
  - jump to an SOP, deck, programme, stage, bookmark or recent conversation
  - run an action ("New SOP", "Ask…", "My drafts", "Review queue")
  - results are permission-filtered by the backend
- **🔔 Notifications** (in-app): review requested or approved, required
  reading assigned, an SOP you must re-read changed, onboarding path
  assigned, gap follow-up updated, review due.
- **◉ User menu:** Account (two-factor, profile), staff notice, bookmarks,
  sign out.
- **Keyboard:**
  - Enter sends, Shift+Enter adds a new line
  - Esc closes the side panel
  - `/` focuses search
  - `g a` / `g l` jump to Ask / Library

## 3. Home (ask-first)

```
┌───────────────────────────────────────────────────────────────────────┐
│                     What do you need to know?                         │
│        ┌─────────────────────────────────────────────────────┐        │
│        │ Ask about any programme, stage or SOP…            ⏎ │        │
│        └─────────────────────────────────────────────────────┘        │
│        Programme ▾   Stage ▾        Try: "How do we open a discovery…"│
│                                                                       │
│ ┌─ Required reading (2) ─────┐ ┌─ Your onboarding path ─────────────┐ │
│ │ Client Data Handling v2 ⚠  │ │ New Trainer · 6 / 10 ▓▓▓▓▓▓░░░░    │ │
│ │ Discovery Workshop v1.3    │ │ Next: Brand Foundations deck       │ │
│ └────────────────────────────┘ └────────────────────────────────────┘ │
│ ┌─ Gaps from your searches ──┐ ┌─ Waiting for you ──────────────────┐ │
│ │ camera-shy clients (4×)    │ │ 2 reviews · 1 draft · 3 AI labels  │ │
│ │ [Request] [Draft] [Expert] │ │                                    │ │
│ └────────────────────────────┘ └────────────────────────────────────┘ │
│ ┌─ Recently updated in your programmes · ★ Bookmarks ───────────────┐ │
│ └────────────────────────────────────────────────────────────────────┘│
└───────────────────────────────────────────────────────────────────────┘
```

- Cards appear only when they have content (no empty boxes).
- **CEO:** extra cards for unplaced notes, stale SOPs, coverage map summary
  and cost this month.
- **HR:** extra cards for anonymised gap topics and onboarding completion.

## 4. Ask (chat): the polished centrepiece

### Layout

```
┌──────────────┬─────────────────────────────────────┬──────────────────────┐
│ Conversations│ You: How do we open a discovery     │ Brand Foundations    │
│ + New        │ workshop for Signature?             │ deck · Slide 14/32 ◀▶│
│ Today        │                                     │ ┌──────────────────┐ │
│  Discovery…  │ ◌ Checking Core · Signature ·       │ │  [slide image]   │ │
│  Rate card…  │   Discovery…           (live steps) │ └──────────────────┘ │
│ This week    │                                     │ Speaker notes:       │
│  …           │ Start with the 3-minute brand story │ "Ask each partici-   │
│              │ exercise [1], then run the values   │ pant to…" (cited     │
│ 🔍 Search    │ card sort in pairs [2]. Time-box    │ passage highlighted) │
│  history     │ each to 15 minutes [2].             │                      │
│              │                                     │ v2.0 · by A ·        │
│              │ [1] Brand Foundations · slide 14    │ approved by CEO 2 Nov│
│              │ [2] Discovery Workshop SOP v1.3 §3  │ [Open in Library]    │
│              │ 👍 👎 · Copy · Export PDF           │ [★ Bookmark]         │
│              │ ↳ What materials do I need?         │                      │
│              │ ↳ How long is the full workshop?    │                      │
│              ├─────────────────────────────────────┤                      │
│              │ Programme: Signature ▾  Stage: ▾    │                      │
│              │ [Ask a follow-up…                 ⏎]│                      │
└──────────────┴─────────────────────────────────────┴──────────────────────┘
```

### Behaviour

- **Live progress:** while working, the answer area shows plain-language
  steps from the backend's SSE events (`agent_dispatched`, `searching`,
  `citation`), e.g. "Checking Core · Signature · Discovery…". Then the answer
  streams in word by word. A **Stop** button cancels.
- **Citations:**
  - Numbered markers `[1]` in the answer; hovering shows a one-line preview.
  - Clicking opens the **side panel**:
    - **SOP:** the cited section, scrolled to and highlighted.
    - **Slide:** the slide image, its speaker notes, and ◀ ▶ to the
      neighbouring slides.
    - **PDF worksheet:** the cited page.
  - Badges on each citation: version, author, approver and approval date.
  - If a newer version is waiting for review, people who can review it see
    "*v1.4 pending review*". Others just see the current approved version.
- **Answer formatting:** steps, lists and tables are rendered properly.
  "Copy" copies the answer with its citations. "Export PDF" produces a
  one-page answer sheet with its sources.
- **Several departments:** when more than one department answers, each answer
  appears in its own section headed by the department, with its own
  citations. Nothing is merged by a model.
- **Follow-up chips:** 2–3 suggested next questions. The programme and stage
  filters carry over to the next question.
- **No-answer state:** "*No SOP you can access covers this.*" This is never
  dressed up as an answer. Three actions follow:
  - **[Request an SOP]**
  - **[Start a draft]**
  - **[Suggest an expert]**

  These feed "Gaps from your searches".
- **Outside your access:** "*That's outside what I can help with; please ask
  the delivery team ([contact]).*" This never hints that restricted content
  exists.
- **👎 reasons:** wrong · outdated · missing steps · unclear · other (free
  text). They feed gap topics and the improvement dataset (plan §5.3).
- **History:** conversations are grouped by day and searchable. Users can
  rename and **hide** a conversation. Hiding removes it from the user's view,
  but the audit copy is kept for 24 months, as the staff notice states.
- **Speed targets:**
  - progress step visible in under 0.5 s
  - first words in under 2 s on the Haiku path, under 4 s when escalated
- **Errors:** if the AI service is unreachable, the user sees "*The assistant
  is temporarily unavailable; the Library still works*", with a link to
  Library search using the same query.

## 5. Library and reading

### Browse

```
┌───────────────────┬───────────────────────────────────────────────────┐
│ View: Programme ▾ │ Signature Personal Brand Programme                │
│  (Programme/Stage/│ ┌ Discovery ┐┌ Strategy ┐┌ Content ┐┌ Delivery ┐┌ F│
│   Department)     │ │ 6 SOPs    ││ 4 SOPs   ││ 9 SOPs  ││ 7 SOPs   ││ 0│
│ ▸ Signature       │ │ 2 decks   ││ 1 deck   ││ 3 decks ││ 2 decks  ││ ⚠│
│ ▸ Exec Presence   │ └───────────┘└──────────┘└─────────┘└──────────┘└──│
│ ▸ Methodology     │ Discovery                                         │
│ ▸ Shared Templates│ ● Discovery Workshop SOP   v1.3  approved   ★     │
│ ★ Bookmarks       │ ● Intake Questionnaire     v2.0  approved         │
│                   │ ▤ Brand Foundations deck   32 slides              │
│ 🔍 Search library │ ◐ Values Card Sort         v0.4  in review        │
└───────────────────┴───────────────────────────────────────────────────┘
```

- Switch between **programme**, **stage** and **department** views.
- Status dots: approved, in review (visible to reviewers only), draft (own
  only).
- Stage columns with **0 SOPs show ⚠**, linking to the coverage map.

### Reader

- A rendered note with working `[[links]]`, plus a **backlinks** panel ("used
  in").
- A metadata strip: version, owner, author, approver, review due, programme
  and stage.
- **Version history** with a side-by-side diff of any two versions.
- Embedded decks open in the **slide viewer** (thumbnails, slide images,
  speaker notes). PDF worksheets open in the PDF viewer.
- Actions:
  - **★ Bookmark**
  - **Export PDF**
  - **Edit** (with `contribute`)
  - **Mark as read** (when the SOP is assigned as required reading)

## 6. Write

```
┌──────────────────────────────────────────────────────────────────────┐
│ Discovery Workshop SOP                     Draft · autosaved 10:42   │
│ Owner [Jane ▾] Programme [Signature ▾] Stage [Discovery ▾]           │
│ Space: Core (AI suggests: Core · internal ✓)  Review every [180 d ▾] │
├──────────────────────────────────────────────────────────────────────┤
│ H1 H2 • 1. ☐ ⊞ 🔗[[ ]] 🖼 ▤Embed deck  > [!note]  ↶ ↷               │
│                                                                      │
│ ## 3. Run the values card sort                                       │
│ Pair participants and give each pair the [[Values Card Deck]]…       │
│ ┌ ▤ Brand Foundations deck · slides 12–16 ───────────────────┐       │
│ └────────────────────────────────────────────────────────────┘       │
├──────────────────────────────────────────────────────────────────────┤
│ [Upload attachment]  [Preview]              [Save]  [Submit review]  │
└──────────────────────────────────────────────────────────────────────┘
```

- **Metadata is a form, not YAML.** Approval fields are read-only.
- **Space and sensitivity:** the AI's suggestion is shown inline. Choosing
  something *looser* than the suggestion shows "needs lead approval" (the
  one-way rule).
- **Autosave** of drafts every few seconds, saved as the author's own
  in-progress commits.
- **Templates gallery:** SOP, checklist, workshop run-sheet, client-delivery
  playbook.
- **Upload:** `.pptx`, `.pdf`, `.docx` or images, plus an "original design
  link" field (Google Slides or Canva) and the tool name.
- **Edit clash:** saving over a newer version opens a merge screen (theirs
  vs yours, choose per block).
- **Start from the template:** a new SOP opens with the SOP template's
  sections. Started from a gap, it is also pre-filled with the programme,
  stage and links to related SOPs. People write SOPs; there is no AI
  drafting.

## 7. Review

- **Tabs:** SOP changes · AI label suggestions · Unplaced notes · Governance.
- **SOP changes:**
  - a **side-by-side diff against the last approved version**
  - a short summary of what changed, generated locally on save
  - Approve · Request changes (with comment)
  - an approver option: **"Material change: require re-reading"**, which
    triggers re-acknowledgement for required-reading assignees
- **AI label suggestions:** grouped cards ("40 workshop worksheets → Core ·
  internal") showing the AI's reasoning and evidence snippets, with Approve
  all · Edit · Reject. Anything that widens access says so in plain words.
- **Unplaced notes:** routed to the author, or to the lead as a fallback.
- **Governance:** unattributed edits, notes left restricted by default
  (awaiting classification), and self-approved SOPs.

## 8. Retain

- **Gaps:**
  - **Leads:** their space's gap topics with example questions, without
    names.
  - **HR:** the anonymised cross-company view (topics shown only once at
    least 3 people are involved), with a follow-up status per topic (open →
    training planned → addressed) and a trend line showing whether
    questions drop after training.
- **Coverage map:** a programme × stage grid. Click a cell for its SOPs, or
  for "create one".
- **Handover notes:** a form following the handover template (client and
  programme, stage, done, open actions with dates, upcoming sessions, client
  preferences, files, contacts, risks). Pick the receivers, run the
  completeness check (flags missing dates or owners), then send. Receivers
  see it under "Awaiting my acknowledgement" and confirm "read and
  understood"; questions go in comments. Lists: my handovers, sent, awaiting
  acknowledgement.
- **Review due** and **bus-factor** lists.

## 9. v1 extras

### 9.1 Onboarding paths

- **Leads build a path:** an ordered list of SOPs, decks and worksheets,
  grouped into steps (e.g. *New Trainer: Week 1 / Week 2*). Each item can be
  marked required.
- **Assigning paths:** to a person or a role. HR can assign paths and see
  completion. For paths that include restricted items, HR sees **progress
  only, not item titles**.
- **For the learner:**
  - a path page with progress, a "next up" item and per-item "Done"
  - a required item is done when it's read and acknowledged (§9.2)
  - can ask the bot about the current item ("Ask about this")
- **Reports:** completion per person and path (leads and HR), which can be
  exported for audits.

### 9.2 Required reading and sign-off

- **Leads assign** SOPs as must-read for a role, programme or person, with a
  due date.
- **Staff acknowledge** "*I have read v1.3*" in the reader. The
  acknowledgement records the user, the version and the time, and is
  append-only.
- **Re-reading:** when an approver marks a new version as a *material
  change*, existing acknowledgements expire and assignees are asked to
  re-read. Minor edits don't trigger this.
- **Read-status view** for leads (who has or hasn't read, overdue), exported
  for the yearly audit.

### 9.3 PDF / print export

- **Generated by the backend** (WeasyPrint, lightweight and Python-only),
  with a clean neutral layout.
- **The header shows:** title, SOP ID, version, owner, author, approver,
  approval date and "*printed by [user] on [date]*".
- **Scope:** one SOP, one answer sheet, or a whole programme stage as a
  single PDF.
- **Restricted content:**
  - Only users with access can export it. A **watermark** carries the
    user's name, the date and "Restricted".
  - Every export is **written to the audit log**.
  - Leads can turn off export for a space entirely.
- **Print-optimised CSS** so browser printing of the reader also looks right.

### 9.4 Bookmarks and quick search

- **★ on any SOP, deck, slide or conversation.** Bookmarks appear on Home
  and in the Library sidebar.
- **Ctrl+K palette** (see §2). Bookmarks and recents rank first.

## 10. Cross-cutting rules

- **Permission-aware rendering:** never show titles, counts, badges or link
  targets for items the user can't access. Links in a note to restricted
  notes render as plain text "*(restricted note)*" with no title. All of
  this is filtered by the backend.
- **States:**
  - **Loading:** skeleton placeholders.
  - **Empty:** explains what goes here and the next action.
  - **Errors:** say what happened and what still works.
- **Accessibility:** keyboard-navigable, visible focus, WCAG AA contrast and
  labelled controls. axe checks run in CI.
- **Performance budget:** initial JS under 300 KB gzipped. Routes are
  code-split; the editor and slide viewer load only when needed.
- **Language-ready:** all UI text goes through an i18n layer (English only
  for now), matching the multilingual search index.
- **Theming:** colours, fonts, radius and logo live in `frontend/src/app/theme`
  for later branding.

## 11. Backend additions needed for the extras

| Feature | Tables | Endpoints |
|---|---|---|
| Onboarding paths | `reading_paths`, `path_steps`, `path_items`, `path_assignments`, `path_progress` | CRUD `/paths`, `POST /paths/{id}/assign`, `GET /me/paths`, `POST /path-items/{id}/done`, `GET /reports/path-completion` |
| Required reading | `reading_assignments(target: user/role/programme, document_id, due)`, `read_acknowledgements(user_id, document_id, version, at)` | `POST /reading-assignments`, `POST /documents/{id}/acknowledge`, `GET /me/required-reading`, `GET /reports/read-status` |
| Material change | `reviews.material_change` | Set on approve; expires acknowledgements |
| PDF export | `export_events` (audit) | `POST /exports` (document, answer or stage) → file |
| Bookmarks | `bookmarks(user_id, target_type, target_id)` | CRUD `/me/bookmarks` |
| Quick search | (uses existing search) | `GET /quick-search?q=` (titles/actions only, permission-filtered) |

## 12. Build order (mapped to the plan's phases)

| Phase | Frontend delivered |
|---|---|
| 0 | Project setup, theme, generated API client, layout shell, sign-in page |
| 1 | Two-factor enrolment, staff notice, Admin → users/roles/grants |
| 2 | Library (browse, reader, slide/PDF viewers, version diff), editor and round-trip test, upload, merge, **bookmarks and Ctrl+K** |
| 2b | Review → AI label suggestions, unplaced notes |
| 3 | **Ask (polish priority)**: streaming, live steps, side-panel citations, follow-ups, no-answer actions, history; ask-first Home |
| 4 | Review → SOP diffs and approval with material-change flag; **required reading and sign-off**; **PDF/print export**; notifications |
| 5 | Retain (gaps incl. HR view, coverage map, handover notes, review due, bus factor); **onboarding paths**; cost dashboard; audit log viewer |
| 6 | Playwright end-to-end suite on the deployed Mac mini; accessibility pass |
