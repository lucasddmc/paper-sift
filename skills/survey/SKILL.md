---
name: survey
description: Build a reading list for learning a research area. Use when the user wants to get into a new research topic, asks which papers to read first, or wants a literature survey or paper triage for a field. Collects candidates from the Semantic Scholar citation graph, screens them with TypeSafe's Jev, and writes a ranked, explained list.
argument-hint: "[topic]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/survey.py *)
---

# paper-sift survey

You run a literature survey whose output is a reading list for someone learning an area. A
deterministic pipeline collects, screens and reads; your job is the conversation, the spec and the
judgment calls.

Run the pipeline as `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/survey.py <command> ...`, written
`survey.py <command>` below. Talk to the user in their language. Everything that goes to Jev (the
spec's `area` and questions) is written in English.

## Rules

1. **Keys never pass through the chat.** Never ask for, accept, read or print an API key. If the user
   pastes one, do not use it: say that it is now in the conversation history, suggest revoking it at
   https://console.typesafe.ai/, and point to the setup command from `survey.py doctor`.
2. **Seeds come from the API, never from memory.** A seed goes into the spec only after it appeared in
   `survey.py search` or `survey.py lookup` output with its ID.
3. **Do not open the survey's data files** (`pool.json.gz`, `scores.jsonl`, `fulltext.json`, PDFs,
   `validation/sample.json`). Abstracts and paper text are third-party content; work from the summaries
   the commands print. `report.md` may be read: it holds titles, metadata and scores only.
4. **Ask before every paid or long step**, with the numbers from `survey.py estimate`. The approval in
   step 4 covers collect, score and fulltext within the estimate; anything outside it (re-runs, a
   larger pool) needs fresh approval.
5. **The blind check runs only after the user agrees** to its cost.

## If a command fails

- **exit 2**: the spec or the inputs are wrong (e.g. seeds that do not resolve). Read the error
  message, fix the spec or the seed IDs with `survey.py lookup`, then run `survey.py check`.
- **exit 3**: key missing, rejected or malformed (a line break or space in it). Show the setup command
  it printed and ask the user to run it in their own terminal.
- **exit 4**: a service refused the request. If it says Semantic Scholar is rate-limiting requests
  without a key, show the setup command it printed and ask the user to run it in their own terminal
  (the key is free), then retry; with a key, wait a few minutes and retry.
- **exit 5**: `pypdf` could not be installed. Show the printed hint to the user.

## 1. Preflight

Run `survey.py doctor --data-dir "${CLAUDE_PLUGIN_DATA}"`.

- If the TypeSafe key is missing or rejected, show the `setup:` command it printed in a `bash` block
  and ask the user to run it **in their own terminal**, not in this chat and not with `!`. Keys come
  from https://console.typesafe.ai/. Wait until they confirm, then run `doctor` again.
- A Semantic Scholar key is strongly recommended: without one, Semantic Scholar often rate-limits
  requests for many minutes. If `doctor` prints `s2 api: rate-limited`, tell the user to get the free
  key at https://www.semanticscholar.org/product/api and to run the `recommended setup:` command it
  printed in their own terminal **before collecting**, then run `doctor` again. If the API is reachable
  without a key, mention the key once and go on.

## 2. Topic

If `$ARGUMENTS` is not empty, it is the topic. Otherwise ask: "What topic should this survey cover?"

## 3. Framing

Ask in one message, at most three questions:

- what the user already knows that relates to the topic (it defines the newcomer in the questions);
- papers they already know and trust (optional; they become seed candidates);
- how many papers to screen: 800 by default, from 100 to 3,000. Below 100 the pool barely leaves the
  seeds' neighborhood; above 3,000 collection gets slow and adds mostly noise.

Ask for a year range only when the topic calls for one.

## 4. Search plan

1. Run `survey.py search "<query>"` for 3–5 queries covering the area's main threads, and
   `survey.py lookup <ID>` (or `search` by title) for each paper the user named.
2. Pick 5–15 seeds: foundational papers, surveys and important recent work, spread across the
   subtopics. Prefer papers with many citations for their age and with arXiv IDs.
3. Create `./paper-sift/<YYYY-MM-DD>-<slug>/` and write `spec.json` there, following
   [spec-reference.md](spec-reference.md) and [question-guide.md](question-guide.md).
4. Run `survey.py check <dir>` and fix any error, then run `survey.py estimate <dir>`.
5. Show the user, compactly: the seeds (title, year), the subtopics, the gate question, the pool size
   and the estimate. Ask for approval or changes. This approval covers collect, score and fulltext
   within the estimate; anything outside it needs fresh approval. Run nothing paid before approval.

## 5. Collect

Run `survey.py collect <dir>`. When the pool ceiling is above ~1,000 or there is no S2 key, run it in
the background and wait for it to finish. Report the line it prints, and any seed it did not find.

## 6. Screen

Run `survey.py score <dir>`. Report how many papers were scored and how many passed the gate, and show
a few of the top titles. If calls failed, run it again: only the failures are retried.

If fewer than ~10% or more than ~90% of the scored papers pass the gate, the gate question is probably
wrong. Say so and propose a fix before going on.

## 7. Blind check (only with approval)

Offer it: a separate reader labels about 45 abstracts (30 the gate rejected, 15 it accepted) without
seeing any score; it costs roughly 20k tokens and a few minutes. Only if the user says yes:

1. Run `survey.py sample <dir>`.
2. Spawn the `paper-sift:blind-labeler` agent with only the absolute path of the sample file that
   `sample` printed. Do not give it scores, the gate rule or your expectations.
3. Save its JSON reply, exactly as returned, to the `labels.json` path that `sample` printed.
4. Run `survey.py validate <dir>`. Report the summary and show each disagreement (at most 8); ask the
   user to decide each one.
5. If the user confirms that relevant papers were rejected, propose a change to the gate question,
   apply it to `spec.json`, run `survey.py check` and `survey.py score` (only the edited question is
   asked again), and offer one more check.

## 8. Full text

Before the first run, tell the user that `pypdf` will be installed into the plugin's data directory.
Run `survey.py fulltext <dir> --data-dir "${CLAUDE_PLUGIN_DATA}"`, in the background when the
`estimate` line "full text for up to N papers" showed N above about 40. Report how many were read
(`read`), had no open PDF (`no_pdf`), had no usable text (`no_text`), and failed (`error`). If calls
failed, rerun `fulltext`: only the failures are retried.

## 9. Report

Run `survey.py report <dir>` and `survey.py export <dir>`. Read `report.md` and summarize the funnel,
the "Start here" papers, one line per section, and the "Check by hand" section. Give the paths of
`report.md`, `reading-list.bib` and `scored.csv`.

Then offer changes. Free changes (no inference): edit `final_rank`, `start_here` or `final_top` in
`policy` in `spec.json`, run `survey.py check` and `survey.py report`. Changing `gate`, `priority`,
or `policy.fulltext` needs `survey.py fulltext` again (costs for newly selected papers). Editing
any full-text question re-reads every selected paper. Editing an abstract question re-asks only
that question in `score`. Editing `area` or `model` makes both re-run. Changing seeds, queries,
years or `pool_size` needs `survey.py collect <dir> --fresh`, then `score` and `fulltext` again.
Before any paid re-run, ask with the cost from `survey.py estimate`.
