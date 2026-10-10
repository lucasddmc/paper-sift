# paper-sift: design

Status: draft for review · 2026-10-08 · scope: v0.1

## 1. What it is

paper-sift is a Claude Code plugin that builds a reading list for someone learning a research area.
The user names the topic and Claude turns it into a search plan together with the user. A
deterministic Python pipeline then collects candidates from the Semantic Scholar (S2) citation graph,
TypeSafe's Jev screens each candidate on its title and full abstract, and Jev reads the full text of
the most promising open-access papers. The pipeline writes a ranked reading list that says why each
paper is on it.

v0.1 ships one recipe, **learn an area**. Later recipes (checking the novelty of an idea, finding
papers with a given property) reuse the same pipeline with a different policy.

## 2. Principles

1. **The model answers facts; code applies the policy.** Jev answers atomic yes/no questions
   (Nouls) about each paper. Which papers pass, and in what order, is a rule in the survey's spec.
   Changing the rule re-runs the report without paying for inference again.
2. **Send the whole abstract.** In a 56-paper test (September 2026), cutting abstracts at 600
   characters dropped recall of the relevant papers from 7/7 to 3/7, and lowering the threshold did
   not bring them back: the deciding sentence was absent from the input. Small sample, clear mechanism.
3. **Seeds are verified, never recalled.** Every seed is resolved through the S2 API and confirmed
   by the user, with title, year and ID on screen.
4. **Nothing disappears silently.** Every stage reports its counts. Papers dropped for reasons other
   than the policy (no abstract, no open PDF) are listed for manual checking.
5. **Third-party text stays out of the main session.** Abstracts and PDFs go to Jev and, only if the
   user approves validation, to a read-only subagent. The main Claude session sees titles, metadata
   and scores. This keeps the session small and limits exposure to prompt injection.
6. **Secrets never pass through the chat.** Keys are entered in the user's own terminal.

## 3. User flow

The skill `/paper-sift:survey [topic]` drives the flow. Claude talks to the user in the user's
language; everything sent to Jev is in English, its strongest language.

1. **Preflight.** `survey.py doctor` checks Python (≥ 3.9), the TypeSafe key (present, and accepted
   by one minimal call), the S2 key (strongly recommended) and one S2 request (reachable or
   rate-limited), and the PDF dependency. If S2 is rate-limiting requests without a key, Claude asks
   for the free key before collecting. If the TypeSafe key is missing or invalid, Claude shows the
   command to run in the user's terminal (§10) and waits.
2. **Topic.** Without a topic argument, Claude asks: *"What topic should this survey cover?"*
3. **Framing.** One message, at most three follow-ups: the user's background relative to the topic,
   papers they already know (optional), and the pool size (default 800, §5). A year range is optional.
4. **Search plan.** Claude runs `survey.py search` for 3–5 queries, picks 5–15 seeds (foundational
   papers, surveys, recent work across subtopics), resolves any paper the user named, and drafts the
   spec (§4): area description, subtopics, questions and policy. It shows seeds and questions
   compactly, with cost and time from `survey.py estimate`, and runs nothing paid until the user
   approves.
5. **Collect.** `survey.py collect` builds the pool (§5).
6. **Screen.** `survey.py score` asks the abstract questions of every pool paper that has an
   abstract (§6).
7. **Validate (optional).** Claude offers the blind check (§7) and states its cost. It runs only if
   the user says yes.
8. **Read.** `survey.py fulltext` downloads open PDFs of the selected papers and asks the full-text
   questions (§8).
9. **Report.** `survey.py report` writes `report.md`; `survey.py export` writes `.bib` and `.csv`
   (§9). Claude summarizes the top of the list and offers policy changes. Ranking fields
   (`final_rank`, `start_here`, `final_top`) re-run `report` and `export` for free; other policy
   edits (`gate`, `priority`, `policy.fulltext`) need paid re-runs, asked first. Editing an abstract
   question or `tau` needs `score`, then `fulltext`. `report` and `export` refuse to run while the
   full-text stage is out of date: when the current scores and policy select other papers than it
   read, or when a full-text question changed since a paper was read.

## 4. The spec

Each survey lives in `./paper-sift/<date>-<slug>/` under the user's working directory. Claude
writes `spec.json`, and the user may edit it.

```json
{
  "version": 1,
  "recipe": "learn-area",
  "slug": "diffusion-models",
  "model": "jev-1.13.0",
  "tau": 0.5,
  "area": "We are building the reading list of a newcomer to diffusion models for image generation. The area covers denoising diffusion and score-based models, samplers, guidance and conditioning, latent diffusion, evaluation, and image editing. The reader knows deep learning, VAEs and GANs, but not score-based models.",
  "seeds": [
    {"id": "arXiv:2006.11239", "title": "Denoising Diffusion Probabilistic Models", "why": "foundational"}
  ],
  "queries": ["diffusion models image generation", "score-based generative models"],
  "sources": {"citations": true, "references": true, "recommendations": true, "search_per_query": 100},
  "years": null,
  "pool_size": 800,
  "questions": {
    "topic": {
      "instructions": "Is `paper` mainly about diffusion or score-based generative models, in the sense described in `area`?",
      "true": "The main subject is a diffusion or score-based model: its theory, training, sampling, conditioning, evaluation, or an application where the diffusion model is the contribution",
      "false": "The paper only uses a diffusion model as a tool for another goal, or is about another kind of generative model"
    },
    "survey": {
      "instructions": "Is `paper` a survey, tutorial, taxonomy or position paper?",
      "true": "It surveys, systematizes or teaches a research area rather than presenting one new method",
      "false": "It presents a new method, dataset or empirical study"
    },
    "sub_sampling": {
      "instructions": "Is `paper` about sampling from diffusion models faster or better, such as new samplers, ODE/SDE solvers, or distillation of the sampling process?",
      "true": "Sampling speed or quality is a main contribution",
      "false": "Sampling is not a main contribution"
    }
  },
  "fulltext_questions": {
    "didactic": {
      "instructions": "Reading the full text of `paper`: could a newcomer with the background described in `area` learn the core concepts from it?",
      "true": "Clear problem statement, background and method, understandable without prior reading in the area",
      "false": "Assumes the reader already knows the area, or is narrow and incremental"
    }
  },
  "policy": {
    "gate": "topic",
    "priority": "p.topic * importance",
    "fulltext": {"top": 30, "per_subtopic": 5, "include_seeds": true},
    "start_here": "(survey or map) and didactic",
    "final_rank": "p.didactic",
    "final_top": 20
  }
}
```

- **Abstract questions** are Nouls. Questions named `sub_*` are subtopics; they drive coverage, not
  exclusion. The default full-text set is `didactic`, `map` (gives an overview of many methods),
  `formulation` (explicit problem statement), `limitations` and `code`; Claude adapts the wording
  to the area.
- **How Claude writes questions** is fixed in `skills/survey/question-guide.md`: one atomic judgment
  per question; literal wording; criteria that agree with the instruction; explicit "does NOT count"
  lines for look-alikes; fields referenced by name (`paper`, `area`); no double negation; and **no
  holistic "is this relevant?" question as a gate**. (A holistic "close to our project" question once
  accepted "used as a baseline" and let every paper on a common baseline technique through.)
- **Policy expressions** go through a small whitelisted parser (Python `ast`, no `eval`). A bare fact
  name means "probability ≥ `tau`"; `p.<fact>` is the probability; `importance`, `year` and
  `citations` are available. Allowed: `and`, `or`, `not`, comparisons, `+ - * /`, numbers and
  parentheses.
- **State sent to Jev:** `{"area": ..., "paper": {"title": ..., "abstract": ...}}`, with all
  questions in one call (fan-out). The full-text stage sends `"text"` instead of `"abstract"`.

## 5. Pool: sources and size

**Sources, first hop only.** For each seed: the papers that cite it and the papers it cites (S2 pages
through up to 10,000 of each). Up to 500 S2 recommendations from the seed set. The top
`search_per_query` results of each keyword query. Each paper records what found it (`cites:<seed>`,
`cited-by:<seed>`, `recommended`, `query:<n>`), and its **connectivity** is the number of distinct
sources that found it.

**Size is a ceiling: default 800, allowed range 100–3,000.** `pool_size` caps how many papers enter
screening, so cost and time are predictable.

- If the sources find more, seeds are always kept and the rest are ranked by connectivity, then by
  importance. The trimmed tail is saved and counted in the report.
- If they find fewer, the pool is smaller and the report says so. There is no automatic second hop:
  each hop away from the seeds adds mostly noise.
- Below 100, the pool barely leaves the seeds' immediate neighborhood and the pipeline adds little
  over reading the abstracts. Above 3,000, collection can take over half an hour without an S2 key,
  and the seeds matter far more than the volume. The script rejects values outside the range, and
  Claude explains why.

**Importance** is a paper's citation percentile among the candidates published in the same year.
Raw citation counts would punish recent papers.

**Abstracts.** S2 often lacks them. After trimming, missing abstracts are looked up in OpenAlex by
title, serially (parallel requests failed in testing), and accepted only on a title similarity of
0.92 or more. A lookup that fails (an error, not a miss) is retried on the next `collect`. Papers still
without an abstract are listed, not scored.

## 6. Abstract stage

One Jev call per paper, with all `questions`. Results go to `scores.jsonl`, keyed by S2 paperId.
The stage is incremental: a re-run scores only papers without a result, so adding sources or
retrying failures costs only the new calls. Each result stores a hash of every question's text;
editing a question re-scores that question only.

## 7. Blind validation (optional, after the user approves)

Purpose: catch a gate that quietly drops relevant papers, such as a misread question or a missing
exclusion.

1. Claude states the cost (about 45 abstracts read by a subagent: roughly 20k tokens and a few
   minutes) and asks.
2. `survey.py sample` draws, with a fixed random seed, 30 papers the gate rejected and 15 it
   accepted, and writes only `id`, `title` and `abstract` to `validation/sample.json`.
3. The `paper-sift:blind-labeler` agent (tools: Read) labels each paper relevant or not relevant to
   `area` without seeing any score, and returns JSON. Claude saves it as `validation/labels.json`.
4. `survey.py validate` reports agreement, the relevant papers found in the rejected sample with a
   one-sided 95% Clopper–Pearson upper bound on the miss rate (0 of 30 gives about 10%), and
   precision on the accepted sample.
5. Up to 8 disagreements go to the user to arbitrate. If the user confirms that the gate missed
   relevant papers, Claude proposes question changes, re-scores (cheap), and may re-check on a fresh
   sample.

The report says the labels are Claude's, not ground truth, and that 30 samples detect gross failures,
not small losses of recall.

## 8. Full-text stage

**Selection:** the seeds, the top `fulltext.top` gate-passing papers by `priority`, and the top
`fulltext.per_subtopic` of each subtopic, without duplicates.

**Retrieval:** arXiv when the paper has an arXiv ID, otherwise S2's open-access link. arXiv requests
are spaced 3 s apart.

**Text:** extracted with `pypdf`, cut at the first "References" or "Bibliography" heading found after
30% of the document (which also drops appendices), and capped at 90,000 characters (about 25k tokens, inside Jev's 32k state
limit). On a size error the call is retried with half the text. The text goes only to Jev and is
never printed. Papers without an open PDF are listed in the report for manual reading.

## 9. Report and exports

`report.md` contains:

- the funnel: candidates found → kept in the pool → with abstract → passed the gate → selected for
  full text → full text read → in the list;
- the reading list: **Start here** (papers where `start_here` holds), then one section per subtopic,
  ordered by `final_rank`, up to `final_top` papers in all. Each entry shows title, year, venue, link,
  the facts that put it there, importance and provenance;
- what to check by hand: gate-passing papers without an open PDF, and highly connected papers
  without an abstract;
- validation results, if run; the model version that answered; tokens and estimated cost.

`survey.py export` writes `reading-list.bib`, built from S2 metadata, and `scored.csv`, with every
scored paper and its probabilities.

## 10. Keys

- **TypeSafe** (required): `TYPESAFE_API_KEY`, else `~/.config/typesafe/key`.
- **Semantic Scholar** (optional but strongly recommended: on 2026-10-09 the public API answered 429
  to every request without a key for over 30 minutes): `S2_API_KEY`, else
  `~/.config/semanticscholar/key`, sent as `x-api-key`.

When a key is missing, Claude shows one command for the user to run **in their own terminal**, with
the plugin path already resolved:

```bash
python3 "<plugin root>/scripts/setup_key.py" typesafe
```

The script reads the key with `getpass` (nothing is echoed), writes it with mode 600 in a directory
with mode 700, validates it with one minimal call, and prints only "OK" or the error. The skill
forbids Claude from reading key files and from accepting a key pasted in the chat. If one is pasted,
Claude does not use it, says it is now in the conversation history, and suggests revoking it in the
TypeSafe console.

Plugin `userConfig` with `sensitive: true` was considered and rejected: its values reach hooks and
MCP servers, but not the Bash commands a skill runs.

## 11. Runtime, dependencies, errors

- Python ≥ 3.9 and the standard library only, except `pypdf` (BSD) for the full-text stage. It is
  installed on first use into a venv under `${CLAUDE_PLUGIN_DATA}` (fallback `~/.cache/paper-sift`).
  PyMuPDF was avoided because it is AGPL.
- PDFs are cached in the same data directory.
- Every request sends the User-Agent `paper-sift/<version>`: TypeSafe's CDN answers 403 to the
  default urllib agent.
- 429, 5xx and 529 are retried with exponential backoff (cap 60 s). 401 and 403 stop with "invalid
  key". Any other 4xx stops the stage and prints the field the API rejected, never the reply. Failed
  per-paper calls are recorded with their HTTP status and retried on the next run; 20 failed calls in a
  row stop `score` (TypeSafe is likely down).
- S2 without a key often returns 429. `collect` retries 10 times with backoff; `search` and `lookup`
  stop after 3 retries (about 14 s) and say how to get the free key. OpenAlex is called serially.
- Every stage writes to disk as it goes and resumes when re-run. `collect` saves its progress after
  each source (`pool.partial.json.gz`, deleted once the pool is written) and every 50 OpenAlex lookups;
  `--fresh` starts over.
- The skill pre-approves only `Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*)` through
  `allowed-tools`. `collect`, `score` and `fulltext` run in the background (`run_in_background`,
  timeout above the estimate, at most 2 hours); the other commands run in the foreground.

## 12. Repository layout

```
paper-sift/
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json       # the repo is its own marketplace
├── skills/survey/
│   ├── SKILL.md               # /paper-sift:survey
│   ├── spec-reference.md
│   └── question-guide.md
├── agents/blind-labeler.md
├── scripts/
│   ├── survey.py              # doctor, search, lookup, check, estimate, collect, score, sample, validate, fulltext, report, export
│   ├── setup_key.py
│   └── paper_sift/            # net, keys, jev, s2, openalex, policy, spec, store, pool, screen, ranking,
│                              # validate, pdftext, deps, fulltext, report, estimate
├── tests/
├── docs/design.md
├── README.md
└── LICENSE
```

Install: `claude plugin marketplace add lucasddmc/paper-sift`, then
`claude plugin install paper-sift@paper-sift`.

## 13. Testing

- Offline unit tests with the standard library's `unittest`: the policy parser (including rejected
  constructs), trimming and connectivity, importance percentiles, sampling determinism, the
  Clopper–Pearson bound, cutting at the references, key precedence, spec validation, and report
  rendering from fixtures. Network clients take an injectable transport, so tests use recorded
  responses.
- `claude plugin validate --strict`.
- Before release: one live survey from a clean install (`claude plugin marketplace add ./`), on a
  neutral topic with `pool_size` 100, end to end.
- Later: `claude plugin eval` cases for the skill's behavior (asks for the topic first, refuses
  pasted keys, asks before validating).

## 14. What leaves the machine; terms

- To TypeSafe: the area description (written from the user's topic and background), titles,
  abstracts, and the full text of open-access papers. TypeSafe states that it does not train on
  customer requests.
- To S2, OpenAlex and arXiv: search queries, paper IDs and titles.
- Nothing else from the user's files.

TypeSafe's Master Customer Agreement (last updated 2026-09-23), Terms of Use (2026-09-19) and
Acceptable Use Policy (2026-09-23) were read on 2026-10-08. None restricts publishing benchmarks or
performance information; an earlier MCA version reportedly did. MCA §2.2 allows building the API into
applications, and each plugin user calls the API with their own key under their own agreement.
§2.3(b) forbids using outputs to train imitating models, which the plugin does not do. Re-check before
each release: §16.7 allows amendments on 60 days' notice.

## 15. Out of scope for v0.1

Other recipes (novelty check, property search); snowballing from the final list; an MCP server;
Zotero; marking papers the user already has (`--known refs.bib`); non-English questions to Jev;
tested Windows support.

## 16. Decisions

| Decision | By | Date |
|---|---|---|
| Name `paper-sift`, MIT license, repo `lucasddmc/paper-sift` | Lucas | 2026-10-08 |
| Repo private until the live test passes | Claude | 2026-10-08 |
| v0.1 recipe: learn an area | Lucas | 2026-10-08 |
| Blind validation runs only after the user approves it | Lucas | 2026-10-08 |
| Pool size is a ceiling: default 800, range 100–3,000, first hop only | Claude, delegated by Lucas | 2026-10-08 |
| Skill + Python CLI over Bash rather than an MCP server | proposed by Claude, no objection | 2026-10-08 |
| Keys entered in the user's terminal; `userConfig` not used | Lucas, Claude | 2026-10-08 |
| `pypdf` instead of PyMuPDF, for the license | Claude | 2026-10-08 |
