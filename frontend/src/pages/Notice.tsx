import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import Markdown from "react-markdown";
import { api, unwrap } from "@/api/client";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";

/**
 * The staff notice (plan §11). `gate` is the first-sign-in version: the app
 * stays closed until it is acknowledged. The markdown is rendered without raw
 * HTML, and links open in a new tab without a referrer.
 */
export default function Notice({ gate = false }: { gate?: boolean }) {
  const queryClient = useQueryClient();
  const [changed, setChanged] = useState(false);
  const notice = useQuery({
    queryKey: ["notice"],
    queryFn: () => unwrap(api.GET("/api/v1/notice")),
  });
  const ack = useMutation({
    mutationFn: async (version: string) => {
      const { response } = await api.POST("/api/v1/notice/acknowledge", { body: { version } });
      if (response.status === 409) return "changed" as const;
      if (!response.ok) throw new Error("acknowledge failed");
      return "ok" as const;
    },
    onSuccess: async (result) => {
      if (result === "changed") {
        setChanged(true);
        await queryClient.invalidateQueries({ queryKey: ["notice"] });
        return;
      }
      setChanged(false);
      await queryClient.invalidateQueries({ queryKey: ["notice"] });
      await queryClient.invalidateQueries({ queryKey: ["me"] });
    },
  });

  if (notice.isPending) return <p className="p-6 text-sm text-muted-foreground">{t("app.loading")}</p>;
  if (notice.isError) return <p className="p-6 text-sm" role="alert">{t("error.generic")}</p>;

  return (
    <section className="mx-auto max-w-2xl px-6 py-10">
      <h1 className="text-xl font-semibold">{t("notice.title")}</h1>
      {gate && <p className="mt-2 text-sm text-muted-foreground">{t("notice.mustRead")}</p>}
      {changed && <Alert className="mt-4">{t("notice.changed")}</Alert>}
      <div className="mt-6 space-y-3 text-sm leading-relaxed [&_a]:underline [&_ul]:list-disc [&_ul]:pl-5">
        <Markdown
          skipHtml
          components={{
            a: ({ href, children }) => (
              <a href={href} target="_blank" rel="noopener noreferrer">
                {children}
              </a>
            ),
          }}
        >
          {notice.data.markdown}
        </Markdown>
      </div>
      <div className="mt-8">
        {notice.data.acknowledged ? (
          <p className="text-sm text-muted-foreground" role="status">
            {t("notice.acknowledged")}
          </p>
        ) : (
          <Button onClick={() => ack.mutate(notice.data.version)} disabled={ack.isPending}>
            {t("notice.acknowledge")}
          </Button>
        )}
        {ack.isError && <Alert className="mt-4">{t("error.generic")}</Alert>}
      </div>
    </section>
  );
}
