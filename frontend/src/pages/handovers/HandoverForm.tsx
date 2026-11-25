import { Trash2 } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { useNavigate, useParams } from "react-router";
import { messageOf } from "@/api/errors";
import { Loading } from "@/app/routes";
import { useMe } from "@/auth/hooks";
import { PeoplePicker } from "@/components/PeoplePicker";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { t } from "@/i18n";
import { useStages } from "@/pages/library/api";
import { NotFound } from "@/pages/NotFound";
import { emptyFields, useHandover, useHandoverActions, type Colleague, type Fields } from "./api";
import { spaceLabel } from "@/lib/spaceLabel";

const area = "w-full rounded-md border border-input bg-background px-3 py-2 text-sm";

function Field({ id, label, children }: { id: string; label: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  );
}

function Text({ name, fields, set, rows = 3 }: { name: keyof Fields; fields: Fields; set: (f: Fields) => void; rows?: number }) {
  return (
    <Field id={`ho-${name}`} label={t(`handover.${name}` as "handover.done")}>
      <textarea
        id={`ho-${name}`}
        className={area}
        rows={rows}
        maxLength={20_000}
        value={fields[name] as string}
        onChange={(e) => set({ ...fields, [name]: e.target.value })}
      />
    </Field>
  );
}

function Editor({ initial, existing }: { initial: { title: string; space: string; fields: Fields; receivers: Colleague[] }; existing?: string }) {
  const me = useMe();
  const stages = useStages();
  const navigate = useNavigate();
  const { create, update } = useHandoverActions();
  const spaces = Object.entries(me.data?.space_actions ?? {})
    .filter(([, a]) => a.includes("contribute"))
    .map(([s]) => s)
    .sort();
  const [title, setTitle] = useState(initial.title);
  const [space, setSpace] = useState(initial.space || me.data?.home_space || spaces[0] || "");
  const [fields, setFields] = useState<Fields>(initial.fields);
  const [receivers, setReceivers] = useState<Colleague[]>(initial.receivers);
  const [error, setError] = useState<string | null>(null);
  const busy = create.isPending || update.isPending;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (receivers.length === 0) return setError(t("handover.needReceiver"));
    const ids = receivers.map((r) => r.id);
    try {
      const out = existing
        ? await update.mutateAsync({ id: existing, body: { fields, receivers: ids } })
        : await create.mutateAsync({ title, space, fields, receivers: ids });
      void navigate(`/handovers/${out.id}`);
    } catch (err) {
      setError(messageOf(err));
    }
  }

  const setRow = <K extends "actions" | "sessions">(key: K, i: number, row: Fields[K][number]) =>
    setFields({ ...fields, [key]: fields[key].map((r, j) => (j === i ? row : r)) });
  const dropRow = (key: "actions" | "sessions", i: number) =>
    setFields({ ...fields, [key]: fields[key].filter((_, j) => j !== i) });

  return (
    <form onSubmit={submit} className="space-y-5">
      <div className="grid grid-cols-2 gap-4">
        <Field id="ho-title" label={t("handover.noteTitle")}>
          <Input id="ho-title" required maxLength={150} value={title} disabled={!!existing} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <Field id="ho-space" label={t("handover.space")}>
          <Select id="ho-space" value={space} disabled={!!existing} onChange={(e) => setSpace(e.target.value)}>
            {spaces.map((s) => <option key={s} value={s}>{spaceLabel(s)}</option>)}
          </Select>
        </Field>
      </div>
      <PeoplePicker id="ho-receivers" label={t("handover.receivers")} hint={t("handover.receiversHint")} value={receivers} onChange={setReceivers} />
      <div className="grid grid-cols-3 gap-4">
        <Field id="ho-client" label={t("handover.client")}>
          <Input id="ho-client" maxLength={200} value={fields.client} onChange={(e) => setFields({ ...fields, client: e.target.value })} />
        </Field>
        <Field id="ho-programme" label={t("handover.programme")}>
          <Input id="ho-programme" maxLength={200} value={fields.programme} onChange={(e) => setFields({ ...fields, programme: e.target.value })} />
        </Field>
        <Field id="ho-stage" label={t("handover.stage")}>
          <Select id="ho-stage" value={fields.stage} onChange={(e) => setFields({ ...fields, stage: e.target.value })}>
            <option value="">—</option>
            {(stages.data ?? []).map((s) => <option key={s} value={s}>{s}</option>)}
          </Select>
        </Field>
      </div>
      <Text name="done" fields={fields} set={setFields} rows={4} />

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">{t("handover.actions")}</legend>
        {fields.actions.map((a, i) => (
          <div key={i} className="grid grid-cols-[1fr_12rem_10rem_auto] items-end gap-2">
            <Field id={`ho-a${i}`} label={t("handover.action")}>
              <Input id={`ho-a${i}`} value={a.text} maxLength={2000} onChange={(e) => setRow("actions", i, { ...a, text: e.target.value })} />
            </Field>
            <Field id={`ho-ao${i}`} label={t("handover.owner")}>
              <Input id={`ho-ao${i}`} value={a.owner} maxLength={200} onChange={(e) => setRow("actions", i, { ...a, owner: e.target.value })} />
            </Field>
            <Field id={`ho-ad${i}`} label={t("handover.due")}>
              <Input id={`ho-ad${i}`} type="date" value={a.due ?? ""} onChange={(e) => setRow("actions", i, { ...a, due: e.target.value || null })} />
            </Field>
            <Button type="button" variant="ghost" size="sm" aria-label={t("handover.removeRow")} onClick={() => dropRow("actions", i)}><Trash2 /></Button>
          </div>
        ))}
        <Button type="button" variant="outline" size="sm" onClick={() => setFields({ ...fields, actions: [...fields.actions, { text: "", owner: "", due: null }] })}>
          {t("handover.addAction")}
        </Button>
      </fieldset>

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">{t("handover.sessions")}</legend>
        {fields.sessions.map((s, i) => (
          <div key={i} className="grid grid-cols-[1fr_10rem_auto] items-end gap-2">
            <Field id={`ho-s${i}`} label={t("handover.session")}>
              <Input id={`ho-s${i}`} value={s.what} maxLength={2000} onChange={(e) => setRow("sessions", i, { ...s, what: e.target.value })} />
            </Field>
            <Field id={`ho-sw${i}`} label={t("handover.when")}>
              <Input id={`ho-sw${i}`} type="date" value={s.when ?? ""} onChange={(e) => setRow("sessions", i, { ...s, when: e.target.value || null })} />
            </Field>
            <Button type="button" variant="ghost" size="sm" aria-label={t("handover.removeRow")} onClick={() => dropRow("sessions", i)}><Trash2 /></Button>
          </div>
        ))}
        <div className="flex items-center gap-4">
          <Button type="button" variant="outline" size="sm" disabled={fields.no_upcoming_sessions} onClick={() => setFields({ ...fields, sessions: [...fields.sessions, { what: "", when: null }] })}>
            {t("handover.addSession")}
          </Button>
          <Checkbox
            label={t("handover.noSessions")}
            checked={fields.no_upcoming_sessions}
            onChange={(e) => setFields({ ...fields, no_upcoming_sessions: e.target.checked })}
          />
        </div>
      </fieldset>

      <Text name="preferences" fields={fields} set={setFields} />
      <Text name="files" fields={fields} set={setFields} />
      <Text name="contacts" fields={fields} set={setFields} />
      <Text name="risks" fields={fields} set={setFields} />
      {error && <Alert>{error}</Alert>}
      <Button type="submit" disabled={busy || !title.trim() || !space}>{busy ? t("common.saving") : t("handover.saveDraft")}</Button>
    </form>
  );
}

export function NewHandover() {
  return (
    <div className="mx-auto max-w-4xl space-y-4 px-6 py-6">
      <h1 className="text-2xl font-semibold">{t("handover.new")}</h1>
      <Editor initial={{ title: "", space: "", fields: emptyFields(), receivers: [] }} />
    </div>
  );
}

export function EditHandover() {
  const { id = "" } = useParams();
  const h = useHandover(id);
  if (h.isPending) return <Loading />;
  if (h.isError || !h.data.mine) return <NotFound />;
  return (
    <div className="mx-auto max-w-4xl space-y-4 px-6 py-6">
      <h1 className="text-2xl font-semibold">{h.data.title}</h1>
      <Editor
        existing={id}
        initial={{
          title: h.data.title,
          space: h.data.space,
          fields: { ...emptyFields(), ...h.data.fields, actions: h.data.fields.actions ?? [], sessions: h.data.fields.sessions ?? [] },
          receivers: h.data.receivers.map((r) => ({ id: r.user_id, name: r.name })),
        }}
      />
    </div>
  );
}
