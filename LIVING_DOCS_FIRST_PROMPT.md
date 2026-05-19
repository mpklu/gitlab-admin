# Bootstrap prompt — first 3 thin articles (greenfield)

> Paste the section below into Claude (Claude Code, claude.ai, or any
> Claude-powered tool) running in your project's root directory. Claude
> will ask you a few questions about the project's intent, then write
> three thin "north star" articles capturing the planned shape.

---

This repository just adopted the living-documentation methodology and is at the **greenfield** stage — most of the code hasn't been written yet, so there's nothing to scan. Read these files first to understand the rules:

- `LIVING_DOCS_OVERVIEW.md` (or fetch from
  https://github.com/mpklu/living-doc/blob/main/LIVING_DOCS_OVERVIEW.md)
- `CLAUDE.md` (in this repo's root — the same-task rule applies to this work too)
- `schemas/article-frontmatter.schema.json` (the contract for article frontmatter)

## Your task

Write **exactly three** thin concept articles in `knowledge/concepts/` capturing the project's *planned* shape — its purpose, the key decisions already made, and the abstractions that will anchor the codebase. Each ~150–250 words. These are "north star" articles: they describe intent before code exists. As code lands, the same-task rule keeps them honest.

## Step 1 — ask me, don't invent

Before writing anything, ask me 3–5 short questions to anchor the articles. Suggested topics (pick the ones that matter most for *this* project — don't ask all of them):

- What is this project? (one-sentence purpose)
- Who's the user, and what's the primary thing they do with it?
- What are the 2–3 biggest constraints shaping the design? (latency, cost, regulatory, deploy target, language interop, etc.)
- What's already been decided that's hard to undo? (tech stack, hosting, data model, API style)
- What's deliberately *out of scope*?
- What's the riskiest unknown — the part most likely to force a rewrite if we get it wrong?

Wait for my answers. Don't speculate.

## Step 2 — pick three seams

From my answers, identify the three concepts that most need a durable explanation *before* the code exists. Good candidates:

- **The core abstraction.** The thing other code will be built around (the document model, the request lifecycle, the agent loop, the catalog format).
- **The boundary that's expensive to move.** Wire format, persistence schema, public API contract.
- **The decision a future contributor would otherwise re-litigate.** Stack choice, sync vs. async, monolith vs. service split, build system.

If you're unsure which three, propose four or five and ask me to pick.

## Step 3 — write each article

YAML frontmatter (validated against `schemas/article-frontmatter.schema.json`):

```yaml
---
title: <human-readable, ~6-10 words>
type: concept
area: <project-defined grouping>
updated: <today's date as YYYY-MM-DD>
status: thin
# affects: leave empty for now — code doesn't exist yet.
# Add a glob once the matching files land.
load_bearing: true
---
```

Body, ~200 words:

- **What this is, in one paragraph.** Plain language, no jargon. Should be understandable to someone joining the project two months from now with no other context.
- **Why this shape, not the alternatives.** State the decision and what was ruled out. If the decision is *open* ("we're trying X but might switch to Y"), say so explicitly. Open decisions are valid living-docs content.
- **What would invalidate this article.** The change that triggers a rewrite — the contract that, if broken, means this article is wrong.
- **First commitments.** Two or three concrete things that will be true once the first code lands (file names, module boundaries, function signatures). These let the same-task rule attach `affects:` globs as code arrives.

Place each at `knowledge/concepts/{area}/{topic}.md`. Create the area subdirectory if it doesn't exist.

## Constraints

- **Don't write code.** This step is articles-first. If a piece of code would help, *suggest* it; let me decide whether to write it or scaffold it next.
- **Don't fill `affects:` with speculative globs.** The whole point of `affects:` is that the matching code change triggers a same-task review. Globs pointing at non-existent files quietly do nothing. Leave `affects:` empty until the files exist.
- **Capture intent, not implementation.** "We use a hash-based cache key because requests are idempotent" is good. "The function signature is `f(req: Request) -> Response`" is not — code documents that.
- **Open decisions are valid.** If the answer to "why this way?" is "we're not sure yet, but we're trying X first" — write that. The article gets updated when the decision crystallizes.

## After writing

1. Append one entry to `knowledge/log.md` (newest at top) listing the three articles, the questions you asked me, and any decisions still pending.
2. Update `knowledge/index.md` so the new articles are reachable.
3. Run `scripts/validate-articles` (if present) to verify frontmatter — should print `✅ All N article(s) have valid frontmatter.`
4. Suggest a single commit: `git add -A && git commit -m 'living-docs: seed first 3 articles'` — but don't run it; let me review.

Then briefly summarize: the three seams, what's still uncertain, and what the first code-bearing PR should look like.
