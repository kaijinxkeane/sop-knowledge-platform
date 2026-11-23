import { useState } from "react";
import { useNavigate } from "react-router";
import { Input } from "@/components/ui/input";
import { t } from "@/i18n";
import { BookmarkList } from "@/pages/library/Bookmarks";

/** Ask-first Home (frontend spec §3): the question opens the Ask screen. */
export function Home() {
  const [question, setQuestion] = useState("");
  const navigate = useNavigate();
  return (
    <section className="mx-auto max-w-2xl px-6 pt-24 text-center">
      <h1 className="text-2xl font-semibold">{t("home.title")}</h1>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (question.trim().length >= 2) navigate(`/ask?q=${encodeURIComponent(question.trim())}`);
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
      <p className="mt-3 text-sm text-muted-foreground">{t("home.askHint")}</p>
      <div className="mx-auto mt-12 max-w-md text-left">
        <BookmarkList />
      </div>
    </section>
  );
}
