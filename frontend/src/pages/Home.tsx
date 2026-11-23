import { Input } from "@/components/ui/input";
import { t } from "@/i18n";

/** Ask-first Home (frontend spec §3). The ask box goes live with the Ask screen. */
export function Home() {
  return (
    <section className="mx-auto max-w-2xl px-6 pt-24 text-center">
      <h1 className="text-2xl font-semibold">{t("home.title")}</h1>
      <Input
        className="mt-6 h-12 text-base"
        placeholder={t("home.askPlaceholder")}
        aria-label={t("home.askPlaceholder")}
        disabled
      />
      <p className="mt-3 text-sm text-muted-foreground">{t("home.askSoon")}</p>
    </section>
  );
}
