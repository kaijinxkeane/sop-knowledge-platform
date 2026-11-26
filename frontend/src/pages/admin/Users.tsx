import { useState, type FormEvent } from "react";
import { messageOf } from "@/api/errors";
import { useMe } from "@/auth/hooks";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import { t } from "@/i18n";
import {
  inviteLink,
  useInviteUser,
  useOptions,
  useRoles,
  useUpdateUser,
  useUserAction,
  useUsers,
  type Invite,
  type Role,
  type User,
  type UserUpdate,
} from "./api";
import { TIME_ZONE } from "@/lib/dates";

function StatusBadges({ user }: { user: User }) {
  const badges: [string, "default" | "warning" | "danger" | "outline"][] = [];
  if (!user.is_active) badges.push([t("users.statusInactive"), "danger"]);
  else if (user.locked) badges.push([t("users.statusLocked"), "danger"]);
  if (user.is_active && user.invite_pending) badges.push([t("users.statusInvite"), "warning"]);
  else if (user.is_active && !user.totp_enabled) badges.push([t("users.statusNoTotp"), "warning"]);
  if (user.leaving_on) badges.push([t("users.statusLeaving", { date: user.leaving_on }), "outline"]);
  if (!badges.length) badges.push([t("users.statusActive"), "default"]);
  return (
    <span className="flex flex-wrap gap-1">
      {badges.map(([text, variant]) => (
        <Badge key={text} variant={variant}>
          {text}
        </Badge>
      ))}
    </span>
  );
}

function formatDate(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleDateString([], { timeZone: TIME_ZONE }) : t("users.never");
}

/** Shows a sign-in link once. Closing the dialog is the only way out: it isn't stored anywhere. */
function LinkDialog({ invite, onClose }: { invite: Invite; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const link = inviteLink(invite.invite_token);
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogTitle>{t("users.linkTitle", { name: invite.user.display_name })}</DialogTitle>
        <DialogDescription>
          {t("users.linkBody", { hours: invite.expires_in_hours })}
        </DialogDescription>
        <code className="block select-all break-all rounded bg-muted px-3 py-2 text-sm">{link}</code>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => void navigator.clipboard?.writeText(link).then(() => setCopied(true))}
          >
            {copied ? t("common.copied") : t("common.copy")}
          </Button>
          <Button onClick={onClose}>{t("common.close")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RoleChoices({
  roles,
  chosen,
  setChosen,
  lockedIn,
}: {
  roles: Role[];
  chosen: Set<string>;
  setChosen: (s: Set<string>) => void;
  /** Roles that can't be added (two-person rule when editing yourself). */
  lockedIn?: Set<string> | null;
}) {
  return (
    <fieldset className="space-y-2">
      <legend className="mb-2 text-sm font-medium">{t("users.roles")}</legend>
      {lockedIn && <p className="text-xs text-muted-foreground">{t("users.selfRolesHint")}</p>}
      <div className="grid grid-cols-2 gap-2">
        {roles.map((r) => (
          <Checkbox
            key={r.id}
            label={r.name}
            hint={r.description}
            checked={chosen.has(r.name)}
            disabled={!!lockedIn && !lockedIn.has(r.name)}
            onChange={(e) => {
              const next = new Set(chosen);
              if (e.target.checked) next.add(r.name);
              else next.delete(r.name);
              setChosen(next);
            }}
          />
        ))}
      </div>
    </fieldset>
  );
}

function SpaceSelect({ id, value, onChange }: { id: string; value: string; onChange: (v: string) => void }) {
  const options = useOptions();
  return (
    <Select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{t("common.none")}</option>
      {options.data?.spaces.map((s) => (
        <option key={s.name} value={s.name}>
          {s.title}
        </option>
      ))}
    </Select>
  );
}

function InviteDialog({ onInvited }: { onInvited: (i: Invite) => void }) {
  const roles = useRoles();
  const invite = useInviteUser();
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [home, setHome] = useState("");
  const [chosen, setChosen] = useState<Set<string>>(new Set(["employee"]));

  async function submit(e: FormEvent) {
    e.preventDefault();
    const result = await invite.mutateAsync({
      email: email.trim(),
      display_name: name.trim(),
      roles: [...chosen],
      home_space: home || null,
    });
    setOpen(false);
    setEmail("");
    setName("");
    setHome("");
    setChosen(new Set(["employee"]));
    invite.reset();
    onInvited(result);
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) invite.reset();
      }}
    >
      <Button onClick={() => setOpen(true)}>{t("users.invite")}</Button>
      <DialogContent>
        <DialogTitle>{t("users.inviteTitle")}</DialogTitle>
        <DialogDescription>{t("users.inviteBody")}</DialogDescription>
        <form className="space-y-4" onSubmit={(e) => void submit(e).catch(() => {})} noValidate>
          <div className="space-y-2">
            <Label htmlFor="invite-name">{t("users.name")}</Label>
            <Input id="invite-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="invite-email">{t("users.email")}</Label>
            <Input
              id="invite-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="invite-home">{t("users.homeSpace")}</Label>
            <SpaceSelect id="invite-home" value={home} onChange={setHome} />
          </div>
          {roles.data && <RoleChoices roles={roles.data} chosen={chosen} setChosen={setChosen} />}
          {invite.isError && <Alert>{messageOf(invite.error)}</Alert>}
          <DialogFooter>
            <Button type="submit" disabled={invite.isPending || !email.trim() || !name.trim()}>
              {t("users.inviteSubmit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function EditUserDialog({
  user,
  isSelf,
  onClose,
  onLink,
}: {
  user: User;
  isSelf: boolean;
  onClose: () => void;
  onLink: (i: Invite) => void;
}) {
  const roles = useRoles();
  const update = useUpdateUser(user.id);
  const actions = useUserAction(user.id);
  const [name, setName] = useState(user.display_name);
  const [home, setHome] = useState(user.home_space ?? "");
  const [chosen, setChosen] = useState(new Set(user.roles));
  const [leaving, setLeaving] = useState(user.leaving_on ?? "");
  const [active, setActive] = useState(user.is_active);

  async function save(e: FormEvent) {
    e.preventDefault();
    // Send only what changed, so the audit log records only real changes.
    const body: UserUpdate = {};
    if (name.trim() !== user.display_name) body.display_name = name.trim();
    if ((home || null) !== user.home_space) body.home_space = home || null;
    const sameRoles =
      chosen.size === user.roles.length && user.roles.every((r) => chosen.has(r));
    if (!sameRoles) body.roles = [...chosen];
    if ((leaving || null) !== (user.leaving_on ?? null)) body.leaving_on = leaving || null;
    if (active !== user.is_active) body.is_active = active;
    if (Object.keys(body).length) await update.mutateAsync(body);
    onClose();
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogTitle>{t("users.editTitle", { name: user.display_name })}</DialogTitle>
        <DialogDescription>{user.email}</DialogDescription>
        <form className="space-y-4" onSubmit={(e) => void save(e).catch(() => {})} noValidate>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="edit-name">{t("users.name")}</Label>
              <Input id="edit-name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-home">{t("users.homeSpace")}</Label>
              <SpaceSelect id="edit-home" value={home} onChange={setHome} />
            </div>
          </div>
          {roles.data && (
            <RoleChoices
              roles={roles.data}
              chosen={chosen}
              setChosen={setChosen}
              lockedIn={isSelf ? new Set(user.roles) : null}
            />
          )}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="edit-leaving">{t("users.leavingOn")}</Label>
              <Input
                id="edit-leaving"
                type="date"
                value={leaving}
                onChange={(e) => setLeaving(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">{t("users.leavingHelp")}</p>
            </div>
            <Checkbox
              className="pt-7"
              label={t("users.active")}
              hint={t("users.activeHelp")}
              checked={active}
              disabled={isSelf}
              onChange={(e) => setActive(e.target.checked)}
            />
          </div>
          {update.isError && <Alert>{messageOf(update.error)}</Alert>}
          <div className="flex flex-wrap items-center gap-2 border-t pt-4">
            <ConfirmDialog
              label={t("users.newLink")}
              title={t("users.newLink")}
              body={t("users.newLinkConfirm")}
              onConfirm={async () => onLink(await actions.reinvite.mutateAsync())}
            />
            {user.totp_enabled && (
              <ConfirmDialog
                label={t("users.resetTotp")}
                title={t("users.resetTotp")}
                body={t("users.resetTotpConfirm")}
                onConfirm={() => actions.resetTotp.mutateAsync()}
              />
            )}
            {user.locked && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => actions.unlock.mutate()}
              >
                {t("users.unlock")}
              </Button>
            )}
            <div className="ml-auto flex gap-2">
              <Button type="button" variant="outline" onClick={onClose}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" disabled={update.isPending}>
                {update.isPending ? t("common.saving") : t("common.save")}
              </Button>
            </div>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default function Users() {
  const me = useMe();
  const users = useUsers();
  const [editing, setEditing] = useState<User | null>(null);
  const [link, setLink] = useState<Invite | null>(null);

  if (users.isPending) return <p className="text-sm text-muted-foreground">{t("app.loading")}</p>;
  if (users.isError) return <Alert>{messageOf(users.error)}</Alert>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">{t("admin.users")}</h2>
        <InviteDialog onInvited={setLink} />
      </div>
      {users.data.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("users.empty")}</p>
      ) : (
        <table className="w-full text-sm">
          <thead className="border-b text-left text-muted-foreground">
            <tr>
              <th className="py-2 font-medium">{t("users.name")}</th>
              <th className="py-2 font-medium">{t("users.email")}</th>
              <th className="py-2 font-medium">{t("users.roles")}</th>
              <th className="py-2 font-medium">{t("users.status")}</th>
              <th className="py-2 font-medium">{t("users.lastSignIn")}</th>
              <th className="py-2" />
            </tr>
          </thead>
          <tbody className="divide-y">
            {users.data.map((u) => (
              <tr key={u.id}>
                <td className="py-2">
                  {u.display_name}
                  {u.id === me.data?.id && (
                    <span className="text-muted-foreground"> ({t("common.you")})</span>
                  )}
                </td>
                <td className="py-2 text-muted-foreground">{u.email}</td>
                <td className="py-2">
                  <span className="flex flex-wrap gap-1">
                    {u.roles.map((r) => (
                      <Badge key={r} variant="outline">
                        {r}
                      </Badge>
                    ))}
                  </span>
                </td>
                <td className="py-2">
                  <StatusBadges user={u} />
                </td>
                <td className="py-2 text-muted-foreground">{formatDate(u.last_login_at)}</td>
                <td className="py-2 text-right">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setEditing(u)}
                    aria-label={`${t("users.edit")} ${u.display_name}`}
                  >
                    {t("users.edit")}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {editing && (
        <EditUserDialog
          key={editing.id}
          user={editing}
          isSelf={editing.id === me.data?.id}
          onClose={() => setEditing(null)}
          onLink={(i) => {
            setEditing(null);
            setLink(i);
          }}
        />
      )}
      {link && <LinkDialog invite={link} onClose={() => setLink(null)} />}
    </div>
  );
}
