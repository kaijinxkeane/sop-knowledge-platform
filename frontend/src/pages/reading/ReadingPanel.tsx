import { useState } from "react";
import { messageOf } from "@/api/errors";
import { PeoplePicker } from "@/components/PeoplePicker";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { t } from "@/i18n";
import type { Colleague } from "@/pages/handovers/api";
import { shortDate, useAssignableRoles, useReadingActions, useReadingStatus } from "./api";

/**
 * Required reading in the reader (frontend spec §9.2): "I have read version N".
 * Shown only for approved notes, and only on the live version.
 */
export function ReadingBanner({ docId }: { docId: string }) {
  const status = useReadingStatus(docId);
  const { acknowledge } = useReadingActions();
  const [error, setError] = useState<string | null>(null);
  const s = status.data;
  if (!s || s.current_version == null) return null;
  const read = s.acknowledged_version != null;
  // Not assigned and never read: nothing to ask.
  if (!s.required && !read) return null;
  return (
    <div
      role="region"
      aria-label={t("reading.title")}
      className={
        read
          ? "mt-4 rounded-md border bg-muted/30 px-4 py-3 text-sm"
          : "mt-4 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
      }
    >
      {read ? (
        <p>
          {t("reading.done", { version: s.acknowledged_version!, date: shortDate(s.acknowledged_at!) })}
          {s.acknowledged_version !== s.current_version && ` ${t("reading.minorSince")}`}
        </p>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p>
            {s.reread ? t("reading.reread") : t("reading.required")}
            {s.due_on && ` ${t(s.overdue ? "reading.overdue" : "reading.due", { date: shortDate(s.due_on) })}`}
          </p>
          <Button
            size="sm"
            disabled={acknowledge.isPending}
            onClick={() => {
              setError(null);
              acknowledge.mutateAsync(docId).catch((e) => setError(messageOf(e)));
            }}
          >
            {t("reading.acknowledge", { version: s.current_version })}
          </Button>
        </div>
      )}
      {error && <Alert className="mt-2">{error}</Alert>}
    </div>
  );
}

/** A space lead marks this SOP as must-read for people or roles, with a due date. */
export function AssignReading({ docId, onDone }: { docId: string; onDone: () => void }) {
  const roles = useAssignableRoles(true);
  const { assign } = useReadingActions();
  const [people, setPeople] = useState<Colleague[]>([]);
  const [picked, setPicked] = useState<string[]>([]);
  const [due, setDue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  if (done) {
    return (
      <p role="status" className="mt-4 rounded-md border bg-muted/30 px-4 py-3 text-sm">
        {t("reading.assigned")}{" "}
        <button type="button" className="underline" onClick={onDone}>{t("common.close")}</button>
      </p>
    );
  }
  return (
    <form
      className="mt-4 space-y-3 rounded-md border bg-muted/30 p-4"
      aria-label={t("reading.assign")}
      onSubmit={async (e) => {
        e.preventDefault();
        setError(null);
        if (!people.length && !picked.length) return setError(t("reading.chooseSomeone"));
        try {
          await assign.mutateAsync({
            document_id: docId,
            user_ids: people.map((p) => p.id),
            roles: picked,
            due_on: due || null,
          });
          setDone(true);
        } catch (err) {
          setError(messageOf(err));
        }
      }}
    >
      <h2 className="font-medium">{t("reading.assign")}</h2>
      <PeoplePicker id="reading-people" label={t("reading.people")} value={people} onChange={setPeople} />
      <fieldset className="space-y-1">
        <legend className="text-sm font-medium">{t("reading.roles")}</legend>
        <div className="flex flex-wrap gap-2">
          {(roles.data ?? []).map((r) => (
            <label key={r.name} title={r.description} className="flex items-center gap-1 rounded-full border px-2 py-0.5 text-sm">
              <input
                type="checkbox"
                checked={picked.includes(r.name)}
                onChange={(e) => setPicked(e.target.checked ? [...picked, r.name] : picked.filter((x) => x !== r.name))}
              />
              {r.name}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="max-w-xs space-y-1">
        <Label htmlFor="reading-due">{t("reading.dueOn")}</Label>
        <Input id="reading-due" type="date" value={due} onChange={(e) => setDue(e.target.value)} />
      </div>
      <p className="text-xs text-muted-foreground">{t("reading.assignHint")}</p>
      {error && <Alert>{error}</Alert>}
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={assign.isPending}>{t("reading.assignButton")}</Button>
        <Button type="button" size="sm" variant="ghost" onClick={onDone}>{t("common.cancel")}</Button>
      </div>
    </form>
  );
}
