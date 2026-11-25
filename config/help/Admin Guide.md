---
doc_type: guide
sop_id: HELP-010
title: "Admin Guide"
version: 1.0
status: published
sensitivity: public
tags: [help, admin]
---

# Admin Guide

The **Admin** page is for administrators. What you see depends on your role.

## Users

- **Invite** a new person: they receive a link to choose a password and set up two-factor sign-in. Invite links expire.
- Give people **roles**; roles decide which spaces and sensitivity levels they can reach.
- **Unlock** an account after too many failed sign-ins, or **reset two-factor** if someone lost their phone.
- For safety, administrators can't give extra roles to themselves; another administrator must do it.

## Departments

The CEO's admin role and HR's lead can create a department under **Departments**, for example when a new marketing team needs its own SOPs. Give it a name, what it covers (the assistant uses this to route questions) and who to contact.

The new department comes with two roles, `<name>-staff` and `<name>-lead`, and a folder of its own. Every member of staff can read its public documents. Nobody gets the new roles automatically: give them to people under **Users**.

## Roles

Each role lists, per space, the highest sensitivity level its members can read and what they can do there: ask, contribute, review, approve or administer. Role cards start collapsed: select one to see and change its grants, or use **Expand all**.

## Audit log

The audit log records sign-ins, changes, approvals, exports and admin actions in plain words. It holds ids and outcomes only, never the text of documents, questions or answers.

- Filter by action, date or target, and **Export CSV** for a spreadsheet.
- **Verify the chain** checks that no event was changed or removed.
- Viewing the log is itself recorded.

## Cost and usage

Shows how often each AI model was used per day. Every model runs on the company's own computer, so calls cost nothing; no questions or names are stored.
