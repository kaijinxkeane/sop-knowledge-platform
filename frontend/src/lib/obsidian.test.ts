import { describe, expect, it } from "vitest";
import { CALLOUT, EMBED, LINK, MARK, TAG, calloutTone, makeResolver, plainName, splitFrontmatter, toMarkdown } from "./obsidian";

describe("obsidian markdown", () => {
  it("splits frontmatter from the body", () => {
    const { frontmatter, body } = splitFrontmatter("---\ntitle: X\n---\n# Hello\n");
    expect(frontmatter).toBe("title: X");
    expect(body).toBe("# Hello\n");
    expect(splitFrontmatter("no frontmatter").body).toBe("no frontmatter");
  });

  it("turns links, aliases, headings and embeds into private links", () => {
    expect(toMarkdown("See [[Leave Policy]].")).toBe(`See [Leave Policy](${LINK}Leave%20Policy).`);
    expect(toMarkdown("Bring ==spare markers== today")).toBe(`Bring [spare markers](${MARK}) today`);
    expect(toMarkdown("```\na ==b== c\n```")).toBe("```\na ==b== c\n```");
    expect(toMarkdown("[[Leave Policy|leave]]")).toBe(`[leave](${LINK}Leave%20Policy)`);
    expect(toMarkdown("[[Leave Policy#Carry over]]")).toBe(`[Leave Policy](${LINK}Leave%20Policy%23Carry%20over)`);
    expect(toMarkdown("![[Brand Foundations.pptx]]")).toBe(
      `[Brand Foundations.pptx](${EMBED}Brand%20Foundations.pptx)`,
    );
  });

  it("marks tags but leaves headings alone", () => {
    expect(toMarkdown("# Heading\nTagged #deck here")).toBe(`# Heading\nTagged [#deck](${TAG}deck) here`);
  });

  it("turns callouts into a bold label", () => {
    expect(toMarkdown("> [!warning] Check the date\n> body")).toBe(`> [Warning: Check the date](${CALLOUT}warning)\n> body`);
    expect(toMarkdown("> [!TIP]-")).toBe(`> [Tip](${CALLOUT}tip)`);
    expect([calloutTone("warning"), calloutTone("Caution"), calloutTone("bug"), calloutTone("odd")]).toEqual(["amber", "amber", "red", "blue"]);
  });

  it("never touches fenced code", () => {
    const code = "```\n[[Not a link]] #nottag\n```";
    expect(toMarkdown(`before [[A]]\n${code}\nafter`)).toContain(code);
  });

  it("escapes brackets in link text", () => {
    // Obsidian links can't hold "]", but "[" in an alias must not break the markdown.
    expect(toMarkdown("[[Note|a [b c]]")).toBe(`[a \\[b c](${LINK}Note)`);
  });

  it("resolves by file name, stem, path or title, and returns null otherwise", () => {
    const docs = [
      { id: "1", title: "Brand Foundations", vault_path: "Training Content/Attachments/Brand Foundations.pptx", kind: "attachment" },
      { id: "2", title: "Leave policy (2026)", vault_path: "HR/Leave Policy.md", kind: "note" },
    ];
    const resolve = makeResolver(docs);
    expect(resolve("Brand Foundations.pptx")?.id).toBe("1");
    expect(resolve("leave policy")?.id).toBe("2");
    expect(resolve("HR/Leave Policy")?.id).toBe("2");
    expect(resolve("Leave policy (2026)")?.id).toBe("2");
    expect(resolve("Leave Policy#Carry over")?.id).toBe("2");
    expect(resolve("Rate Card 2026")).toBeNull();
  });

  it("shows frontmatter links as plain names", () => {
    expect(plainName("[[Signature Personal Brand Programme]]")).toBe("Signature Personal Brand Programme");
    expect(plainName("[[Avery Tan|Avery]]")).toBe("Avery");
    expect(plainName(null)).toBeNull();
  });
});
