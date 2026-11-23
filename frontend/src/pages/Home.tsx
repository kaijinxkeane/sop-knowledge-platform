import { useState } from "react";
import { useNavigate } from "react-router";
import { Input } from "@/components/ui/input";
import { t } from "@/i18n";
import type { Filters } from "@/pages/ask/api";
import { FilterBar, filterQuery } from "@/pages/ask/FilterBar";
import { HomeCards } from "@/pages/home/Cards";

/** Ask-first Home (frontend spec §3): the question opens the Ask screen. */
export function Home() {
  const [question, setQuestion] = useState("");
  const [filters, setFilters] = useState<Filters>({ programme: null, stage: null });
  const navigate = useNavigate();
  return (
    <div className="px-6 pb-16">
      <section className="mx-auto max-w-2xl pt-24 text-center">
        <h1 className="text-2xl font-semibold">{t("home.title")}</h1>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (question.trim().length >= 2)
              navigate(`/ask?q=${encodeURIComponent(question.trim())}${filterQuery(filters)}`);
          }}
        >
          <Input
            className="mt-6 h-12 text-base"
            placeholder={t("home.askPlaceholder")}
            aria-label={t("home.askPlaceholder")}
            maxLength={2000}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
        </form>
        <div className="mt-3 flex justify-center">
          <FilterBar value={filters} onChange={setFilters} />
        </div>
        <p className="mt-3 text-sm text-muted-foreground">{t("home.askHint")}</p>
      </section>
      <HomeCards />
    </div>
  );
}
