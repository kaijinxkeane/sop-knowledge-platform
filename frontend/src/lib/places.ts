/**
 * Where you were in each section (tab, folder, search, selected item), so
 * leaving a document or switching sections brings you back to the same place.
 *
 * Kept in memory only, never in browser storage: a search or a title must not
 * stay on the device (same rule as the access token). Cleared on sign-out.
 */

export type Place = { section: string; to: string };

const bySection = new Map<string, string>();
let lastOutsideDocument: Place | null = null;

const sectionOf = (pathname: string) => pathname.split("/")[1] ?? "";

/** A document (or one of its versions) in the Library: back links skip these. */
export const isDocumentPage = (pathname: string) => /^\/library\/[^/]+/.test(pathname);

/** A section's landing page: `/library`, `/review`, … and each `/admin/<tab>`. */
export function isLandingPage(pathname: string): boolean {
  const parts = pathname.split("/").filter(Boolean);
  return parts.length === 1 || (parts[0] === "admin" && parts.length === 2);
}

export function recordPlace(pathname: string, search: string): void {
  const to = pathname + search;
  const section = sectionOf(pathname);
  if (section && isLandingPage(pathname)) bySection.set(section, to);
  if (!isDocumentPage(pathname)) lastOutsideDocument = { section, to };
}

/** The last place in a section, or its plain landing page. */
export const placeFor = (section: string, fallback: string) => bySection.get(section) ?? fallback;

/** Where a document's back link goes: wherever you opened it from. */
export const backFromDocument = (): Place =>
  lastOutsideDocument ?? { section: "library", to: placeFor("library", "/library") };

export function forgetPlaces(): void {
  bySection.clear();
  lastOutsideDocument = null;
}
