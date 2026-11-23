import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";
import { api, ApiError, unwrap, type Schemas } from "@/api/client";

export type Doc = Schemas["DocumentOut"];
export type Part = Schemas["PartOut"];
export type Version = Schemas["VersionOut"];
export type Backlink = Schemas["BacklinkOut"];
export type Hit = Schemas["HitOut"];

const path = (id: string) => ({ params: { path: { document_id: id } } });

export const useDocuments = () =>
  useQuery({ queryKey: ["documents"], queryFn: () => unwrap(api.GET("/api/v1/documents")) });

export const useStages = () =>
  useQuery({
    queryKey: ["stages"],
    queryFn: () => unwrap(api.GET("/api/v1/documents/stages")),
    staleTime: Infinity,
  });

export const useDocument = (id: string) =>
  useQuery({
    queryKey: ["document", id],
    queryFn: () => unwrap(api.GET("/api/v1/documents/{document_id}", path(id))),
  });

export const useParts = (id: string, enabled: boolean) =>
  useQuery({
    queryKey: ["document", id, "parts"],
    queryFn: () => unwrap(api.GET("/api/v1/documents/{document_id}/parts", path(id))),
    enabled,
  });

export const useVersions = (id: string) =>
  useQuery({
    queryKey: ["document", id, "versions"],
    queryFn: () => unwrap(api.GET("/api/v1/documents/{document_id}/versions", path(id))),
  });

/**
 * One search. Cached for the session, so going back to the results doesn't
 * record the same search again in the person's history.
 */
export const useSearch = (q: string) =>
  useQuery({
    queryKey: ["search", q],
    queryFn: () => unwrap(api.GET("/api/v1/search", { params: { query: { q, limit: 20 } } })),
    staleTime: Infinity,
    retry: false,
  });

export const useBacklinks = (id: string) =>
  useQuery({
    queryKey: ["document", id, "backlinks"],
    queryFn: () => unwrap(api.GET("/api/v1/documents/{document_id}/backlinks", path(id))),
  });

export async function fetchFile(id: string): Promise<Blob> {
  const { data, response } = await api.GET("/api/v1/documents/{document_id}/file", {
    ...path(id),
    parseAs: "blob",
  });
  if (!response.ok || !data) throw new ApiError(response.status);
  return data as Blob;
}

/** A note's text, as this user may read it (approved version unless they edit it). */
export const useNoteText = (id: string, enabled: boolean) =>
  useQuery({
    queryKey: ["document", id, "text"],
    queryFn: async () => (await fetchFile(id)).text(),
    enabled,
  });

const SAFE_TYPES: Record<string, string> = {
  pdf: "application/pdf",
  pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
};

/**
 * The file as a short-lived blob: URL, for viewers. Files need the bearer
 * token, so they can't be linked directly. The blob gets a fixed type from the
 * extension (never the server's guess); the URL is freed when the viewer
 * closes, and the bytes aren't kept in the cache afterwards.
 */
export function useFileUrl(doc: Doc | undefined) {
  const ext = doc?.vault_path.split(".").pop()?.toLowerCase() ?? "";
  const file = useQuery({
    queryKey: ["document", doc?.id, "file"],
    queryFn: () => fetchFile(doc!.id),
    enabled: !!doc,
    gcTime: 0,
  });
  const url = useMemo(
    () =>
      file.data
        ? URL.createObjectURL(new Blob([file.data], { type: SAFE_TYPES[ext] ?? "application/octet-stream" }))
        : null,
    [file.data, ext],
  );
  useEffect(() => () => void (url && URL.revokeObjectURL(url)), [url]);
  return { url, failed: file.isError };
}

export const fileName = (doc: Doc) => doc.vault_path.split("/").pop() ?? doc.title;

/** Fetch on click and hand the file to the browser as a download. */
export async function downloadFile(doc: Doc): Promise<void> {
  const ext = doc.vault_path.split(".").pop()?.toLowerCase() ?? "";
  const blob = new Blob([await fetchFile(doc.id)], {
    type: SAFE_TYPES[ext] ?? "application/octet-stream",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName(doc);
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

export type VersionText = Schemas["VersionContentOut"];
export type Bookmark = Schemas["BookmarkOut"];
export type Quick = Schemas["QuickOut"];

/** One version's text: only versions this reader may see (approved, or theirs to edit). */
export const useVersion = (id: string, commit: string | null) =>
  useQuery({
    queryKey: ["document", id, "version", commit],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/documents/{document_id}/versions/{commit}", {
          params: { path: { document_id: id, commit: commit! } },
        }),
      ),
    enabled: !!commit,
    staleTime: Infinity, // a commit never changes
  });

export const useBookmarks = () =>
  useQuery({ queryKey: ["bookmarks"], queryFn: () => unwrap(api.GET("/api/v1/me/bookmarks")) });

export function useBookmarkToggle() {
  const qc = useQueryClient();
  const done = () => void qc.invalidateQueries({ queryKey: ["bookmarks"] });
  return {
    add: (body: Schemas["BookmarkIn"]) => unwrap(api.POST("/api/v1/me/bookmarks", { body })).then(done),
    remove: (id: string) =>
      api
        .DELETE("/api/v1/me/bookmarks/{bookmark_id}", { params: { path: { bookmark_id: id } } })
        .then(done),
  };
}

/** Ctrl+K: titles only, permission-filtered by the backend; kept in memory briefly. */
export const useQuickSearch = (q: string) =>
  useQuery({
    queryKey: ["quick", q],
    queryFn: () => unwrap(api.GET("/api/v1/quick-search", { params: { query: { q } } })),
    enabled: q.length > 0,
    staleTime: 30_000,
    gcTime: 60_000,
    placeholderData: (prev) => prev,
  });

/** Where a bookmark opens. */
export function bookmarkHref(b: Bookmark): string {
  if (b.target_type === "conversation") return `/ask?conversation=${b.target_id}`;
  // Deck and PDF viewers each read their own parameter and ignore the other.
  return `/library/${b.target_id}${b.part ? `?slide=${b.part}&page=${b.part}` : ""}`;
}
