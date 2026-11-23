import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";

export function NotFound() {
  return (
    <section className="px-6 py-16 text-center">
      <h1 className="text-xl font-semibold">{t("page.notFound")}</h1>
      <p className="mt-2 text-sm text-muted-foreground">{t("page.notFoundBody")}</p>
      <Button asChild variant="outline" className="mt-6">
        <Link to="/">{t("page.backHome")}</Link>
      </Button>
    </section>
  );
}
