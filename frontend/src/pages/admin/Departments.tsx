import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { api, type Schemas } from "@/api/client";
import { call, messageOf } from "@/api/errors";
import { useMe } from "@/auth/hooks";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { t } from "@/i18n";

type Department = Schemas["DepartmentOut"];
type DepartmentIn = Schemas["DepartmentIn"];

const KEY = ["admin", "departments"];
const suggest = (title: string) => title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 31);

function useDepartments() {
  return useQuery({ queryKey: KEY, queryFn: () => call(api.GET("/api/v1/admin/departments")) });
}

function useCreateDepartment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: DepartmentIn) => call(api.POST("/api/v1/admin/departments", { body })),
    onSettled: () =>
      Promise.all(
        [KEY, ["admin", "roles"], ["admin", "options"], ["me"], ["documents"]].map((queryKey) =>
          qc.invalidateQueries({ queryKey }),
        ),
      ),
  });
}

function NewDepartment({ onDone }: { onDone: (d: Department) => void }) {
  const create = useCreateDepartment();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [contact, setContact] = useState("");
  const [name, setName] = useState<string | null>(null); // null = follow the title
  const [folder, setFolder] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const shortName = name ?? suggest(title);
  const folderName = folder ?? title.trim();

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      onDone(
        await create.mutateAsync({
          title: title.trim(),
          description: description.trim(),
          contact: contact.trim(),
          name: shortName,
          folder: folderName,
        }),
      );
    } catch (err) {
      setError(messageOf(err));
    }
  }

  return (
    <form aria-label={t("departments.new")} className="space-y-4 rounded-md border bg-muted/40 p-4" onSubmit={(e) => void submit(e)}>
      <h3 className="font-semibold">{t("departments.new")}</h3>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="dep-title">{t("departments.title")}</Label>
          <Input id="dep-title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Marketing" required maxLength={80} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="dep-contact">{t("departments.contact")}</Label>
          <Input id="dep-contact" value={contact} onChange={(e) => setContact(e.target.value)} placeholder={t("departments.contactHint")} maxLength={200} />
        </div>
      </div>
      <div className="space-y-1">
        <Label htmlFor="dep-description">{t("departments.description")}</Label>
        <textarea
          id="dep-description"
          className="min-h-20 w-full rounded-md border bg-background px-3 py-2 text-sm"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder={t("departments.descriptionHint")}
          required
          minLength={10}
          maxLength={1000}
        />
        <p className="text-xs text-muted-foreground">{t("departments.descriptionHelp")}</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="dep-name">{t("departments.shortName")}</Label>
          <Input id="dep-name" value={shortName} onChange={(e) => setName(e.target.value)} pattern="[a-z][a-z0-9-]{1,30}" />
          <p className="text-xs text-muted-foreground">{t("departments.shortNameHelp", { name: shortName || "marketing" })}</p>
        </div>
        <div className="space-y-1">
          <Label htmlFor="dep-folder">{t("departments.folder")}</Label>
          <Input id="dep-folder" value={folderName} onChange={(e) => setFolder(e.target.value)} maxLength={60} />
          <p className="text-xs text-muted-foreground">{t("departments.folderHelp")}</p>
        </div>
      </div>
      {error && <Alert>{error}</Alert>}
      <Button type="submit" disabled={create.isPending || !title.trim() || description.trim().length < 10}>
        {t("departments.create")}
      </Button>
    </form>
  );
}

/** Admin → Departments (manage_spaces: the CEO and HR's lead). */
export default function Departments() {
  const list = useDepartments();
  const canAssign = !!useMe().data?.global_actions.includes("manage_users");
  const [adding, setAdding] = useState(false);
  const [created, setCreated] = useState<Department | null>(null);
  if (list.isPending) return <p className="text-sm text-muted-foreground">{t("app.loading")}</p>;
  if (list.isError) return <Alert>{messageOf(list.error)}</Alert>;
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">{t("admin.departments")}</h2>
          <p className="text-sm text-muted-foreground">{t("departments.intro")}</p>
        </div>
        {!adding && <Button onClick={() => { setAdding(true); setCreated(null); }}>{t("departments.new")}</Button>}
      </div>
      {created && (
        <p role="status" className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-900">
          {t("departments.created", { title: created.title, staff: `${created.name}-staff`, lead: `${created.name}-lead` })}{" "}
          {canAssign ? (
            <Link to="/admin/users" className="underline">{t("departments.assignInUsers")}</Link>
          ) : (
            t("departments.askAdmin")
          )}
        </p>
      )}
      {adding && <NewDepartment onDone={(d) => { setCreated(d); setAdding(false); }} />}
      <div className="grid gap-3 sm:grid-cols-2">
        {list.data.map((d) => (
          <Card key={d.name}>
            <CardHeader className="space-y-1">
              <div className="flex items-center gap-2">
                <h3 className="font-semibold">{d.title}</h3>
                <Badge variant="outline">{d.created_in_app ? t("departments.inApp") : t("departments.configured")}</Badge>
              </div>
              <p className="text-sm text-muted-foreground">{d.description}</p>
            </CardHeader>
            <CardContent className="space-y-1 text-xs text-muted-foreground">
              <p>{t("departments.shortName")}: <code>{d.name}</code>{d.folders.length > 0 && <> · {t("departments.folders")}: {d.folders.map((f) => `${f}/`).join(", ")}</>}</p>
              {d.roles.length > 0 && <p>{t("departments.roles")}: {d.roles.join(", ")}</p>}
              {d.contact && <p>{d.contact}</p>}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
