import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, authFetch, unwrap, type Schemas } from "@/api/client";
import { ServerError, call } from "@/api/errors";

export type Source = Schemas["SourceOut"];
export type Saved = Schemas["SavedOut"];

const note = (id: string) => ({ params: { path: { note_id: id } } });

/** Never cached: an editor must start from what is saved now. */
export const useSource = (id: string) =>
  useQuery({
    queryKey: ["note", id, "source"],
    queryFn: () => getSource(id),
    gcTime: 0,
    staleTime: 0,
    refetchOnWindowFocus: false,
  });

export const getSource = (id: string) => unwrap(api.GET("/api/v1/notes/{note_id}/source", note(id)));

/** Thrown when someone else saved first; `current` is what is saved now. */
export class Clash extends Error {
  constructor() {
    super("edit clash");
  }
}

export async function saveNote(id: string, baseVersion: string, content: string): Promise<Saved> {
  const res = await api.PUT("/api/v1/notes/{note_id}", {
    ...note(id),
    body: { base_version: baseVersion, content },
  });
  if (res.response.status === 409) throw new Clash();
  return call(Promise.resolve(res));
}

export const createNote = (body: Schemas["NoteCreateIn"]) => call(api.POST("/api/v1/notes", { body }));

export const submitNote = (id: string) => call(api.POST("/api/v1/notes/{note_id}/submit", note(id)));

export async function uploadAttachment(
  id: string,
  file: File,
  tool: string,
  link: string,
): Promise<Saved> {
  const form = new FormData();
  form.append("file", file);
  if (tool.trim()) form.append("source_tool", tool.trim());
  if (link.trim()) form.append("original_link", link.trim());
  const res = await authFetch(
    new Request(`${window.location.origin}/api/v1/notes/${encodeURIComponent(id)}/attachments`, {
      method: "POST",
      body: form,
      credentials: "same-origin",
    }),
  );
  if (res.ok) return (await res.json()) as Saved;
  const detail = await res
    .json()
    .then((b: { detail?: unknown }) => b.detail)
    .catch(() => null);
  throw new ServerError(res.status, typeof detail === "string" && detail.length <= 200 ? detail : null);
}

/** After a save, the reader and lists must show the new state. */
export function useAfterSave() {
  const qc = useQueryClient();
  return (id: string) => {
    void qc.invalidateQueries({ queryKey: ["documents"] });
    void qc.invalidateQueries({ queryKey: ["document", id] });
  };
}
