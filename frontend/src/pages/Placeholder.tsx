import { t, type MessageKey } from "@/i18n";

export function Placeholder({ title }: { title: MessageKey }) {
  return (
    <section className="px-6 py-8">
      <h1 className="text-xl font-semibold">{t(title)}</h1>
      <p className="mt-2 text-sm text-muted-foreground">{t("page.comingSoon")}</p>
    </section>
  );
}
