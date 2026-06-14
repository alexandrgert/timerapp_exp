---
name: professional-vibecoding
description: >-
  Professional vibe coding quality bar (5 rules, Bitrix24 / Alexander Serbul): strict
  types, linters, tests, 70%+ coverage, input validation, minimal dependencies.
  Apply when generating or reviewing Python, TypeScript, PHP, or JS in this repo.
---

# Professional vibecoding (5 rules)

Source: [Tproger — 5 правил профессионального вайбкодинга](https://tproger.ru/articles/5-pravil-professionalnogo-vajbkodinga-kotorye-delayut-rabotu-be) (Александр Сербул, Bitrix24).

Cursor rule: **`.cursor/rules/professional-vibecoding.mdc`**.

## When to apply

- any AI-generated or AI-edited code in this monorepo;
- before marking a task **done** on Bitrix24 integrations (REST, OAuth apps, BI).

## Checklist (summary)

1. **Types** — TypeScript / typed Python / `strict_types` PHP.
2. **Linters** — run on changed files; fix errors.
3. **Tests** — automated; happy path + edge cases.
4. **Coverage** — ≥70% on changed modules when feasible.
5. **Input & deps** — validate external data; minimal frameworks; audit dependencies; no secrets in git.

## Bitrix24 note

VibeCode and AI speed do not replace this bar for production CRM code. See also skills **`bitrix24-portal-access`**, **`bitrix24-bi-connector`**.

For **process** (brainstorming, plans, TDD discipline, systematic debugging) with the [Superpowers](https://github.com/obra/superpowers) plugin installed in Cursor, use **`superpowers-workflow`** — it complements this quality bar, does not replace it.
