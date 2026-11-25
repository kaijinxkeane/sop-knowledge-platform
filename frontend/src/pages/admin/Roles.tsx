import { ChevronDown, ChevronRight } from "lucide-react";
import { useState, type FormEvent } from "react";
import { messageOf } from "@/api/errors";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { t, type MessageKey } from "@/i18n";
import {
  useCreateRole,
  useOptions,
  useRemoveGrant,
  useRoleActions,
  useRoles,
  type Grant,
  type GrantIn,
  type Options,
  type Role,
} from "./api";

const COMPANY = "__company__";
const actionLabel = (a: string) => t(`action.${a}` as MessageKey);
const sensitivityLabel = (s: string) => t(`sensitivity.${s}` as MessageKey);

function GrantRow({ role, grant, options }: { role: Role; grant: Grant; options: Options }) {
  const remove = useRemoveGrant();
  const space = options.spaces.find((s) => s.name === grant.space);
  return (
    <tr>
      <td className="py-2">{grant.space ? (space?.title ?? grant.space) : t("roles.companyWide")}</td>
      <td className="py-2">{grant.space ? sensitivityLabel(grant.max_sensitivity ?? "public") : "—"}</td>
      <td className="py-2">
        <span className="flex flex-wrap gap-1">
          {grant.actions.map((a) => (
            <Badge key={a} variant="outline">
              {actionLabel(a)}
            </Badge>
          ))}
        </span>
      </td>
      <td className="py-2 text-right">
        <ConfirmDialog
          label={t("roles.removeGrant")}
          variant="ghost"
          title={t("roles.removeGrant")}
          body={t("roles.removeGrantConfirm", { role: role.name })}
          onConfirm={() => remove.mutateAsync(grant.id)}
        />
      </td>
    </tr>
  );
}

function AddGrant({ role, options }: { role: Role; options: Options }) {
  const { addGrant } = useRoleActions(role.id);
  const [scope, setScope] = useState(options.spaces[0]?.name ?? COMPANY);
  const [level, setLevel] = useState<GrantIn["max_sensitivity"]>("public");
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [missing, setMissing] = useState(false);
  const companyWide = scope === COMPANY;
  const available = companyWide ? options.global_actions : options.space_actions;

  async function submit(e: FormEvent) {
    e.preventDefault();
    const actions = available.filter((a) => chosen.has(a));
    if (!actions.length) return setMissing(true);
    setMissing(false);
    await addGrant.mutateAsync({
      space: companyWide ? null : scope,
      // Company-wide grants read no content; the backend stores them as public.
      max_sensitivity: companyWide ? "public" : level,
      actions,
    });
    setChosen(new Set());
  }

  const id = `grant-${role.id}`;
  return (
    <form
      className="space-y-3 rounded-md border bg-muted/40 p-4"
      onSubmit={(e) => void submit(e).catch(() => {})}
      noValidate
      aria-label={`${t("roles.addGrant")}: ${role.name}`}
    >
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor={`${id}-scope`}>{t("roles.scope")}</Label>
          <Select
            id={`${id}-scope`}
            value={scope}
            onChange={(e) => {
              setScope(e.target.value);
              setChosen(new Set());
            }}
          >
            {options.spaces.map((s) => (
              <option key={s.name} value={s.name}>
                {s.title}
              </option>
            ))}
            <option value={COMPANY}>{t("roles.companyWide")}</option>
          </Select>
        </div>
        {!companyWide && (
          <div className="space-y-2">
            <Label htmlFor={`${id}-level`}>{t("roles.maxSensitivity")}</Label>
            <Select
              id={`${id}-level`}
              value={level}
              onChange={(e) => setLevel(e.target.value as GrantIn["max_sensitivity"])}
            >
              {options.sensitivities.map((s) => (
                <option key={s} value={s}>
                  {sensitivityLabel(s)}
                </option>
              ))}
            </Select>
          </div>
        )}
      </div>
      {companyWide && <p className="text-xs text-muted-foreground">{t("roles.companyWideHelp")}</p>}
      <fieldset>
        <legend className="mb-2 text-sm font-medium">{t("roles.actions")}</legend>
        <div className="flex flex-wrap gap-4">
          {available.map((a) => (
            <Checkbox
              key={a}
              label={actionLabel(a)}
              checked={chosen.has(a)}
              onChange={(e) => {
                const next = new Set(chosen);
                if (e.target.checked) next.add(a);
                else next.delete(a);
                setChosen(next);
              }}
            />
          ))}
        </div>
      </fieldset>
      {missing && <Alert>{t("roles.pickAction")}</Alert>}
      {addGrant.isError && <Alert>{messageOf(addGrant.error)}</Alert>}
      <Button type="submit" size="sm" disabled={addGrant.isPending}>
        {t("roles.addGrant")}
      </Button>
    </form>
  );
}

function EditDescription({ role }: { role: Role }) {
  const { updateDescription } = useRoleActions(role.id);
  const [open, setOpen] = useState(false);
  const [text, setText] = useState(role.description);
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (o) setText(role.description);
      }}
    >
      <Button variant="ghost" size="sm" onClick={() => setOpen(true)}>
        {t("roles.editDescription")}
      </Button>
      <DialogContent>
        <DialogTitle>{role.name}</DialogTitle>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            void updateDescription.mutateAsync(text).then(() => setOpen(false), () => {});
          }}
        >
          <div className="space-y-2">
            <Label htmlFor={`desc-${role.id}`}>{t("roles.description")}</Label>
            <Input id={`desc-${role.id}`} value={text} onChange={(e) => setText(e.target.value)} />
          </div>
          {updateDescription.isError && <Alert>{messageOf(updateDescription.error)}</Alert>}
          <DialogFooter>
            <Button type="submit" disabled={updateDescription.isPending}>
              {t("common.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function RoleCard({
  role,
  options,
  open,
  onToggle,
}: {
  role: Role;
  options: Options;
  open: boolean;
  onToggle: () => void;
}) {
  const { remove } = useRoleActions(role.id);
  const body = `role-${role.id}`;
  const scopes = [...new Set(role.grants.map((g) => (g.space ? (options.spaces.find((s) => s.name === g.space)?.title ?? g.space) : t("roles.companyWide"))))];
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-4 space-y-0">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          aria-controls={body}
          className="flex flex-1 items-start gap-2 text-left"
        >
          {open ? <ChevronDown className="mt-0.5 size-4 shrink-0" aria-hidden /> : <ChevronRight className="mt-0.5 size-4 shrink-0" aria-hidden />}
          <span>
            <span className="block font-semibold">{role.name}</span>
            <span className="block text-sm text-muted-foreground">{role.description}</span>
            <span className="mt-1 block text-xs text-muted-foreground">
              {t("roles.users", { count: role.user_count })}
              {" · "}
              {t("roles.grantCount", { count: role.grants.length })}
              {scopes.length > 0 && ` · ${scopes.join(", ")}`}
            </span>
          </span>
        </button>
        <div className="flex gap-1">
          <EditDescription role={role} />
          <ConfirmDialog
            label={t("roles.delete")}
            variant="ghost"
            title={t("roles.delete")}
            body={t("roles.deleteConfirm", { role: role.name, count: role.user_count })}
            onConfirm={() => remove.mutateAsync()}
          />
        </div>
      </CardHeader>
      {open && (
      <CardContent id={body} className="space-y-4">
        {role.grants.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("roles.noGrants")}</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="border-b text-left text-muted-foreground">
              <tr>
                <th className="py-2 font-medium">{t("roles.scope")}</th>
                <th className="py-2 font-medium">{t("roles.maxSensitivity")}</th>
                <th className="py-2 font-medium">{t("roles.actions")}</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {role.grants.map((g) => (
                <GrantRow key={g.id} role={role} grant={g} options={options} />
              ))}
            </tbody>
          </table>
        )}
        <AddGrant role={role} options={options} />
      </CardContent>
      )}
    </Card>
  );
}

function CreateRole({ onCreated }: { onCreated: (id: string) => void }) {
  const create = useCreateRole();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    const out = await create.mutateAsync({ name: name.trim(), description: description.trim(), grants: [] });
    onCreated(out.id);
    setOpen(false);
    setName("");
    setDescription("");
    create.reset();
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) create.reset();
      }}
    >
      <Button onClick={() => setOpen(true)}>{t("roles.create")}</Button>
      <DialogContent>
        <DialogTitle>{t("roles.createTitle")}</DialogTitle>
        <DialogDescription>{t("roles.nameHelp")}</DialogDescription>
        <form className="space-y-4" onSubmit={(e) => void submit(e).catch(() => {})} noValidate>
          <div className="space-y-2">
            <Label htmlFor="role-name">{t("roles.name")}</Label>
            <Input id="role-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="role-description">{t("roles.description")}</Label>
            <Input
              id="role-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          {create.isError && <Alert>{messageOf(create.error)}</Alert>}
          <DialogFooter>
            <Button type="submit" disabled={create.isPending || !name.trim()}>
              {t("roles.createSubmit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default function Roles() {
  const roles = useRoles();
  const options = useOptions();
  const [open, setOpen] = useState<Set<string>>(new Set());
  const toggle = (id: string) =>
    setOpen((o) => {
      const next = new Set(o);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  if (roles.isPending || options.isPending) {
    return <p className="text-sm text-muted-foreground">{t("app.loading")}</p>;
  }
  if (roles.isError) return <Alert>{messageOf(roles.error)}</Alert>;
  if (options.isError) return <Alert>{messageOf(options.error)}</Alert>;
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">{t("admin.roles")}</h2>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => setOpen(new Set(roles.data.map((r) => r.id)))}>
            {t("roles.expandAll")}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setOpen(new Set())}>
            {t("roles.collapseAll")}
          </Button>
          <CreateRole onCreated={(id) => setOpen((o) => new Set(o).add(id))} />
        </div>
      </div>
      {roles.data.map((r) => (
        <RoleCard key={r.id} role={r} options={options.data} open={open.has(r.id)} onToggle={() => toggle(r.id)} />
      ))}
    </div>
  );
}
