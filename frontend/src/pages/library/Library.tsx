import { Search } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { t } from "@/i18n";
import { plainName } from "@/lib/obsidian";
import { cn } from "@/lib/utils";
import { useDocuments, useSearch, useStages, type Doc } from "./api";
import { BookmarkList } from "./Bookmarks";
import { StatusDot } from "./StatusDot";

type View = "programme" | "stage" | "department";
const OTHER = "__other__";

const isSop = (d: Doc) => d.kind === "note" && ["sop", "checklist"].includes(d.doc_type);
const isDeck = (d: Doc) => d.kind === "attachment" && d.vault_path.toLowerCase().endsWith(".pptx");
const spacesOf = (d: Doc) => [...new Set(d.access.map((a) => a.space))];

function groupsFor(view: View, docs: Doc[], stages: string[]): string[] {
  const values = new Set<string>();
  for (const d of docs) {
    if (view === "programme") values.add(plainName(d.programme) ?? OTHER);
    else if (view === "stage") values.add(d.stage ?? OTHER);
    else spacesOf(d).forEach((s) => values.add(s));
  }
  const named = [...values].filter((v) => v !== OTHER);
  const order =
    view === "stage"
      ? named.sort((a, b) => (stages.indexOf(a) + 1 || 99) - (stages.indexOf(b) + 1 || 99))
      : named.sort((a, b) => a.localeCompare(b));
  return values.has(OTHER) ? [...order, OTHER] : order;
}

function inGroup(view: View, group: string, d: Doc): boolean {
  if (view === "programme") return (plainName(d.programme) ?? OTHER) === group;
  if (view === "stage") return (d.stage ?? OTHER) === group;
  return spacesOf(d).includes(group);
}

function groupLabel(view: View, group: string): string {
  if (group !== OTHER) return group;
  return view === "stage" ? t("library.noStage") : t("library.other");
}

function DocRow({ doc }: { doc: Doc }) {
  return (
    <li className="flex items-center gap-3 py-2">
      <StatusDot doc={doc} />
      <Link to={`/library/${doc.id}`} className="font-medium hover:underline">
        {doc.title}
      </Link>
      <span className="text-xs text-muted-foreground">{doc.doc_type}</span>
      {doc.review_due && (
        <span className="ml-auto text-xs text-muted-foreground">
          {t("doc.reviewDue")} {doc.review_due}
        </span>
      )}
    </li>
  );
}

/** Programme view: one column per stage, with ⚠ where there are no SOPs yet. */
function StageColumns({ docs, stages }: { docs: Doc[]; stages: string[] }) {
  return (
    <div className="grid grid-cols-5 gap-3">
      {stages.map((stage) => {
        const here = docs.filter((d) => d.stage === stage);
        const sops = here.filter(isSop).length;
        const decks = here.filter(isDeck).length;
        return (
          <div key={stage} className={cn("rounded-md border p-3", !sops && "border-amber-300 bg-amber-50")}>
            <div className="text-sm font-medium capitalize">{stage}</div>
            <div className="mt-1 text-xs text-muted-foreground">
              {sops ? t("library.sops", { count: sops }) : `⚠ ${t("library.noSops")}`}
            </div>
            {decks > 0 && (
              <div className="text-xs text-muted-foreground">{t("library.decks", { count: decks })}</div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function Browse({ view, group, docs, stages }: { view: View; group: string; docs: Doc[]; stages: string[] }) {
  const here = docs.filter((d) => inGroup(view, group, d));
  // Inside a programme or department, list by stage; inside a stage, by programme.
  const sub = (d: Doc) => (view === "stage" ? (plainName(d.programme) ?? OTHER) : (d.stage ?? OTHER));
  const subGroups = groupsFor(view === "stage" ? "programme" : "stage", here, stages);
  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold">{groupLabel(view, group)}</h2>
      {view === "programme" && group !== OTHER && <StageColumns docs={here} stages={stages} />}
      {here.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("library.empty")}</p>
      ) : (
        subGroups.map((g) => {
          const items = here.filter((d) => sub(d) === g);
          if (!items.length) return null;
          return (
            <section key={g}>
              <h3 className="text-sm font-medium capitalize text-muted-foreground">
                {groupLabel(view === "stage" ? "programme" : "stage", g)}
              </h3>
              <ul className="divide-y">{items.map((d) => <DocRow key={d.id} doc={d} />)}</ul>
            </section>
          );
        })
      )}
    </div>
  );
}

function Results({ q }: { q: string }) {
  const search = useSearch(q);
  const [answered, setAnswered] = useState(false);
  const opened = useRef(0);
  const searchId = search.data?.search_id ?? null;

  // Counts only (plan §7): how many results were opened, and whether any helped.
  const report = (used: boolean) => {
    if (!searchId) return;
    void api.POST("/api/v1/search/{search_id}/outcome", {
      params: { path: { search_id: searchId } },
      body: { opened: opened.current, used },
    });
  };
  // Leaving the results after opening some, without saying: counts as not helped.
  const answeredRef = useRef(false);
  useEffect(() => {
    answeredRef.current = answered;
  }, [answered]);
  useEffect(() => {
    const ref = opened;
    return () => {
      if (searchId && ref.current > 0 && !answeredRef.current) {
        void api.POST("/api/v1/search/{search_id}/outcome", {
          params: { path: { search_id: searchId } },
          body: { opened: ref.current, used: false },
        });
      }
    };
  }, [searchId]);

  const failed = search.isError;
  const data = search.data
    ? { semantic: search.data.semantic, hits: search.data.results }
    : null;
  if (failed) return <p className="text-sm" role="alert">{t("error.generic")}</p>;
  if (!data) return <p className="text-sm text-muted-foreground">{t("app.loading")}</p>;
  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">{t("library.searchResults", { q })}</h2>
      {!data.semantic && <p className="text-xs text-muted-foreground">{t("library.searchKeywordOnly")}</p>}
      {data.hits.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("library.searchNone")}</p>
      ) : (
        <ol className="space-y-4">
          {data.hits.map((h, i) => {
            const where =
              h.part === "slide" ? `?slide=${h.part_number}` : h.part === "page" ? `?page=${h.part_number}` : "";
            return (
              <li key={`${h.document_id}-${i}`}>
                <Link
                  to={`/library/${h.document_id}${where}`}
                  onClick={() => (opened.current += 1)}
                  className="font-medium hover:underline"
                >
                  {h.title}
                </Link>
                <span className="ml-2 text-xs text-muted-foreground">
                  {[
                    h.heading,
                    h.part === "slide" && t("library.slide", { n: h.part_number ?? 0 }),
                    h.part === "page" && t("library.page", { n: h.part_number ?? 0 }),
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
                <p className="mt-1 text-sm text-muted-foreground">{h.snippet}</p>
              </li>
            );
          })}
        </ol>
      )}
      {data.hits.length > 0 && (
        <div className="flex items-center gap-2 border-t pt-3 text-sm">
          {answered ? (
            <span role="status">{t("library.thanks")}</span>
          ) : (
            <>
              <span>{t("library.foundIt")}</span>
              {[true, false].map((used) => (
                <Button
                  key={String(used)}
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    report(used);
                    setAnswered(true);
                  }}
                >
                  {used ? t("library.yes") : t("library.no")}
                </Button>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default function Library() {
  const docs = useDocuments();
  const stagesQ = useStages();
  const [params, setParams] = useSearchParams();
  const view = (["programme", "stage", "department"].includes(params.get("view") ?? "")
    ? params.get("view")
    : "programme") as View;
  const q = params.get("q") ?? "";
  const [draft, setDraft] = useState(q);
  const stages = stagesQ.data ?? [];
  const all = docs.data ?? [];
  const groups = groupsFor(view, all, stages);
  const group = params.get("group") ?? groups[0] ?? null;

  const set = (changes: Record<string, string | null>) =>
    setParams((p) => {
      for (const [k, v] of Object.entries(changes)) {
        if (v === null) p.delete(k);
        else p.set(k, v);
      }
      return p;
    });

  function submit(e: FormEvent) {
    e.preventDefault();
    const text = draft.trim();
    if (text.length >= 2) set({ q: text });
  }

  return (
    <div className="mx-auto grid max-w-6xl grid-cols-[15rem_1fr] gap-8 px-6 py-6">
      <aside className="space-y-4">
        <h1 className="text-xl font-semibold">{t("library.title")}</h1>
        <form onSubmit={submit} role="search" className="flex gap-1">
          <Input
            aria-label={t("library.search")}
            placeholder={t("library.search")}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <Button type="submit" size="icon" variant="outline" aria-label={t("library.searchButton")}>
            <Search />
          </Button>
        </form>
        <div className="space-y-1">
          <label htmlFor="library-view" className="text-xs text-muted-foreground">
            {t("library.view")}
          </label>
          <Select
            id="library-view"
            value={view}
            onChange={(e) => set({ view: e.target.value, group: null, q: null })}
          >
            <option value="programme">{t("library.byProgramme")}</option>
            <option value="stage">{t("library.byStage")}</option>
            <option value="department">{t("library.byDepartment")}</option>
          </Select>
        </div>
        <BookmarkList limit={8} />
        <nav aria-label={t("library.groups")}>
          <ul className="space-y-0.5 text-sm">
            {groups.map((g) => (
              <li key={g}>
                <button
                  type="button"
                  onClick={() => set({ group: g, q: null })}
                  aria-current={!q && g === group ? "true" : undefined}
                  className={cn(
                    "w-full rounded px-2 py-1 text-left capitalize hover:bg-accent",
                    !q && g === group && "bg-accent font-medium",
                  )}
                >
                  {groupLabel(view, g)}
                </button>
              </li>
            ))}
          </ul>
        </nav>
      </aside>
      <section className="min-w-0">
        {q ? (
          <>
            <Button
              variant="link"
              className="mb-2 px-0"
              onClick={() => {
                setDraft("");
                set({ q: null });
              }}
            >
              {t("library.clearSearch")}
            </Button>
            <Results key={q} q={q} />
          </>
        ) : docs.isPending || stagesQ.isPending ? (
          <p className="text-sm text-muted-foreground">{t("app.loading")}</p>
        ) : docs.isError ? (
          <p className="text-sm" role="alert">{t("error.generic")}</p>
        ) : group ? (
          <Browse view={view} group={group} docs={all} stages={stages} />
        ) : (
          <p className="text-sm text-muted-foreground">{t("library.empty")}</p>
        )}
      </section>
    </div>
  );
}
