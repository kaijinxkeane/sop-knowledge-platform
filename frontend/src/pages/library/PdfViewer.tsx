import { useSearchParams } from "react-router";
import { t } from "@/i18n";
import { useFileUrl, type Doc } from "./api";

/** The browser's own PDF viewer, on a blob: URL; ?page=N opens that page. */
export function PdfViewer({ doc }: { doc: Doc }) {
  const { url, failed } = useFileUrl(doc);
  const [params] = useSearchParams();
  const page = Number(params.get("page") ?? "");
  if (failed) return <p className="text-sm text-muted-foreground">{t("doc.loadFailed")}</p>;
  if (!url) return <p className="text-sm text-muted-foreground">{t("app.loading")}</p>;
  return (
    <iframe
      title={t("doc.pdfTitle", { title: doc.title })}
      src={page > 0 ? `${url}#page=${page}` : url}
      className="h-[80vh] w-full rounded-lg border"
    />
  );
}
