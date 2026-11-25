import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { session } from "@/auth/session";
import { json, makeMe, mockFetch, renderApp, type Handler } from "@/test/utils";
import { widens } from "./api";

const lead = makeMe({ space_actions: { core: ["ask", "contribute", "review", "approve"], hr: ["ask"], it: ["ask"] } });
const author = makeMe({ space_actions: { core: ["ask", "contribute"], hr: ["ask"], it: ["ask"] } });

const REVIEW = {
  id: "r1",
  document_id: "n1",
  title: "Discovery Workshop",
  vault_path: "Programmes/Discovery Workshop.md",
  space: "core",
  status: "open",
  requested_by: "Avery Tan",
  requested_at: "2026-11-24T09:00:00Z",
  self_review: false,
  stale: false,
  git_commit: "bbbbbbb",
  base_commit: "aaaaaaa",
  summary: "Room booking moved to the week before.",
  summary_pending: false,
  comment: "",
  decided_by: null,
  decided_at: null,
  flags: [],
};

const proposal = (over: Record<string, unknown>) => ({
  id: "p1",
  document_id: "d1",
  title: "Values Worksheet",
  vault_path: "Training Content/Values Worksheet.md",
  proposed: { space: "core", sensitivity: "internal", shared_with: [] },
  current: { space: "core", sensitivity: "restricted", shared_with: [] },
  confidence: 0.91,
  rationale: "A workshop handout used in delivery.",
  evidence: ["Hand this out at the start."],
  names: [],
  safeguards: [],
  decision: "proposed",
  needs: "review",
  stale: false,
  ...over,
});

const QUEUE = [
  {
    group_key: "Training Content|core|internal",
    folder: "Training Content",
    proposed_space: "core",
    proposed_sensitivity: "internal",
    items: [
      proposal({}),
      proposal({ id: "p2", document_id: "d2", title: "Story Prompts", vault_path: "Training Content/Story Prompts.md" }),
    ],
  },
  {
    group_key: "Inbox|core|restricted",
    folder: "Inbox",
    proposed_space: "core",
    proposed_sensitivity: "restricted",
    items: [proposal({ id: "p3", document_id: "d3", title: "Call notes", vault_path: "Inbox/Call notes.md", current: null, proposed: { space: "core", sensitivity: "restricted", shared_with: [] } })],
  },
];

function reviewApi(me = lead, extra: Record<string, Handler> = {}) {
  session.signIn("t");
  return mockFetch({
    "GET /api/v1/me": () => json(me),
    "GET /api/v1/notifications": () => json([]),
    "GET /api/v1/reviews": () => json([REVIEW]),
    "GET /api/v1/classifications/queue": () => json(QUEUE),
    "GET /api/v1/documents/n1/versions/aaaaaaa": () => json({ commit: "aaaaaaa", content: "# Discovery\n\nBook the room.\n" }),
    "GET /api/v1/documents/n1/versions/bbbbbbb": () => json({ commit: "bbbbbbb", content: "# Discovery\n\nBook the room a week before.\n" }),
    ...extra,
  });
}

beforeEach(() => session.signOut());

describe("Review → SOP changes", () => {
  it("shows the submitted version against the approved one and approves with a comment", async () => {
    let body: unknown = null;
    const { calls } = reviewApi(lead, {
      "POST /api/v1/reviews/r1/approve": async (req) => ((body = await req.json()), json({ approval: "review" })),
    });
    renderApp("/review?tab=changes&id=r1");
    expect(await screen.findByRole("heading", { name: "Discovery Workshop" })).toBeInTheDocument();
    expect(screen.getByText("Room booking moved to the week before.")).toBeInTheDocument();
    expect(await screen.findByText("Book the room a week before.")).toBeInTheDocument();
    expect(screen.getByText("Book the room.")).toBeInTheDocument();
    // Exactly the submitted version and its base, nothing else.
    const versionCalls = calls.map((c) => new URL(c.url).pathname).filter((p) => p.includes("/versions/"));
    expect(new Set(versionCalls)).toEqual(new Set(["/api/v1/documents/n1/versions/aaaaaaa", "/api/v1/documents/n1/versions/bbbbbbb"]));

    await userEvent.type(screen.getByLabelText("Comment (sent to the author)"), "Looks right");
    await userEvent.click(screen.getByRole("button", { name: "Approve this version" }));
    expect(await screen.findByText(/Approved\. Answers can now cite/)).toBeInTheDocument();
    expect(body).toEqual({ comment: "Looks right", material_change: false });
  });

  it("can mark an approval as a material change, so people read it again", async () => {
    let body: unknown = null;
    reviewApi(lead, {
      "POST /api/v1/reviews/r1/approve": async (req) => ((body = await req.json()), json({ approval: "review" })),
    });
    renderApp("/review?tab=changes&id=r1");
    await userEvent.click(await screen.findByLabelText(/^Material change/));
    await userEvent.click(screen.getByRole("button", { name: "Approve this version" }));
    await screen.findByText(/Approved\. Answers can now cite/);
    expect(body).toEqual({ comment: "", material_change: true });
  });

  it("asks for a comment before requesting changes", async () => {
    reviewApi();
    renderApp("/review?tab=changes&id=r1");
    await userEvent.click(await screen.findByRole("button", { name: "Request changes" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Say what needs to change.");
  });

  it("refuses to approve a change that moved on since it was sent", async () => {
    reviewApi(lead, { "GET /api/v1/reviews": () => json([{ ...REVIEW, stale: true }]) });
    renderApp("/review?tab=changes&id=r1");
    expect(await screen.findByRole("button", { name: "Approve this version" })).toBeDisabled();
  });

  it("gives an author no approve button and no governance tab", async () => {
    reviewApi(author, { "GET /api/v1/reviews": () => json([{ ...REVIEW, self_review: true }]) });
    renderApp("/review?tab=governance&id=r1");
    expect(await screen.findByRole("button", { name: "Withdraw" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve this version" })).toBeNull();
    expect(screen.queryByRole("tab", { name: /Governance/ })).toBeNull();
  });

  it("is a 404 for someone with no review, approve or contribute rights", async () => {
    reviewApi(makeMe());
    renderApp("/review");
    expect(await screen.findByText("Page not found")).toBeInTheDocument();
  });
});

describe("Review → AI label suggestions", () => {
  it("groups placed notes, shows reasoning, and approves a group in one go", async () => {
    let ids: unknown = null;
    reviewApi(lead, {
      "POST /api/v1/classifications/bulk-approve": async (req) => {
        ids = ((await req.json()) as { ids: string[] }).ids;
        return json([{ id: "p1", ok: true }, { id: "p2", ok: false, error: "this decision needs the space lead" }]);
      },
    });
    renderApp("/review?tab=labels");
    const group = (await screen.findByRole("heading", { name: "2 in Training Content" })).closest("div.rounded-lg") as HTMLElement;
    expect(within(group).queryByText("Call notes")).toBeNull(); // unplaced notes have their own tab
    expect(within(group).getAllByText("Approving this lets more people read the note.")).toHaveLength(2);
    await userEvent.click(within(group).getByRole("button", { name: /Approve all as suggested/ }));
    expect(await within(group).findByText("1 approved, 1 not approved.")).toBeInTheDocument();
    expect(within(group).getByText("Story Prompts: this decision needs the space lead")).toBeInTheDocument();
    expect(ids).toEqual(["p1", "p2"]);
  });

  it("lets a reviewer edit the labels, never looser than restricted when personal data was found", async () => {
    reviewApi(lead, {
      "GET /api/v1/classifications/queue": () => json([{ ...QUEUE[0], items: [proposal({ safeguards: ["phone"] })] }]),
      "GET /api/v1/spaces": () => json([{ name: "core", title: "Core", access: "restricted", actions: [] }]),
    });
    renderApp("/review?tab=labels");
    await userEvent.click(await screen.findByRole("button", { name: "Edit" }));
    const level = screen.getByLabelText("Level") as HTMLSelectElement;
    const enabled = [...level.options].filter((o) => !o.disabled).map((o) => o.value);
    expect(enabled).toEqual(["restricted"]);
  });
});

describe("Review → Unplaced notes", () => {
  it("lists only notes nobody can read yet and rejects one", async () => {
    let rejected = false;
    reviewApi(lead, { "POST /api/v1/classifications/p3/reject": () => ((rejected = true), new Response(null, { status: 204 })) });
    renderApp("/review?tab=unplaced");
    expect(await screen.findByText("Call notes")).toBeInTheDocument();
    expect(screen.queryByText("Values Worksheet")).toBeNull();
    expect(screen.getByText("Now: nobody can read it", { exact: false })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reject" }));
    await waitFor(() => expect(rejected).toBe(true));
  });
});

describe("Review → Governance", () => {
  it("shows titles only for documents the reader can open", async () => {
    const empty = { unattributed_edits: [], changes_awaiting_review: [], never_approved: [], published_outside_platform: [], self_approved: [], review_overdue: [], possible_instructions: [], access_changes: [] };
    reviewApi(lead, {
      "GET /api/v1/reports/governance": () =>
        json({
          ...empty,
          spaces: ["core"],
          review_overdue: [
            { document_id: "d1", title: "Values Worksheet", space: "core", detail: { due: "2026-10-01" } },
            { document_id: "d9", title: null, space: "core", detail: { due: "2026-10-02" } },
          ],
        }),
    });
    renderApp("/review?tab=governance");
    expect(await screen.findByRole("link", { name: "Values Worksheet" })).toHaveAttribute("href", "/library/d1");
    expect(screen.getByText("A document you can't open")).toBeInTheDocument();
  });
});

describe("widens", () => {
  const l = (space: string, sensitivity: string, shared_with: { space: string; sensitivity: string }[] = []) => ({ space, sensitivity, shared_with });
  it("treats placing, loosening, moving and new shares as widening", () => {
    expect(widens(null, l("core", "restricted"))).toBe(true);
    expect(widens(l("core", "restricted"), l("core", "internal"))).toBe(true);
    expect(widens(l("core", "internal"), l("hr", "internal"))).toBe(true);
    expect(widens(l("core", "internal"), l("core", "internal", [l("hr", "public")]))).toBe(true);
    expect(widens(l("core", "internal"), l("core", "restricted"))).toBe(false);
    expect(widens(l("core", "bogus"), l("core", "restricted"))).toBe(false); // unknown = restricted
  });
});
