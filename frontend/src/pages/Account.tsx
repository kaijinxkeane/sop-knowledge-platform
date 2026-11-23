import { Link } from "react-router";
import { useMe } from "@/auth/hooks";
import { Badge } from "@/components/ui/badge";
import { t } from "@/i18n";

export function Account() {
  const me = useMe();
  if (!me.data) return null;
  const rows: [string, React.ReactNode][] = [
    [t("account.email"), me.data.email],
    [
      t("account.roles"),
      <span className="flex flex-wrap gap-1">
        {me.data.roles.map((r) => (
          <Badge key={r}>{r}</Badge>
        ))}
      </span>,
    ],
    [t("account.twoFactor"), t("account.twoFactorOn")],
  ];
  return (
    <section className="mx-auto max-w-2xl px-6 py-10">
      <h1 className="text-xl font-semibold">{me.data.display_name}</h1>
      <dl className="mt-6 divide-y rounded-lg border">
        {rows.map(([label, value]) => (
          <div key={label} className="grid grid-cols-3 gap-4 px-4 py-3 text-sm">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="col-span-2">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 text-xs text-muted-foreground">{t("account.twoFactorHelp")}</p>
      <Link to="/notice" className="mt-6 inline-block text-sm underline">
        {t("account.readNotice")}
      </Link>
    </section>
  );
}
