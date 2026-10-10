# paper-sift

A Claude Code plugin that builds a reading list for learning a research area.

You name the topic. Claude works out a search plan with you, then runs a deterministic pipeline:

1. **Collect** candidates from the Semantic Scholar citation graph around a few seed papers, plus
   recommendations and keyword search: up to 800 papers by default.
2. **Screen** every candidate with [TypeSafe's Jev](https://docs.typesafe.ai/) on its full abstract.
   Jev answers yes/no questions ("is this mainly about the area?", "which subtopic?"), and a rule in the
   survey's spec decides which papers pass.
3. **Read** the full text of the most promising open-access papers and ask whether each one teaches the
   area well.
4. **Report** a ranked reading list ("Start here", then one section per subtopic) that says why each
   paper is on it, with `.bib` and `.csv` exports.

The main Claude session never reads abstracts or PDFs: they go to Jev. Claude works from titles,
metadata and scores.

## Install

```bash
claude plugin marketplace add lucasddmc/paper-sift
claude plugin install paper-sift@paper-sift
```

You need Python 3.9+ and a [TypeSafe API key](https://console.typesafe.ai/). A free
[Semantic Scholar API key](https://www.semanticscholar.org/product/api) is strongly recommended: without
one, Semantic Scholar often rate-limits requests (HTTP 429) for many minutes. It is saved the same way
as the TypeSafe key (below), with `setup_key.py s2`.

## Keys

On the first survey Claude checks for the key. If it is missing, Claude shows a command to run **in your
own terminal**, along the lines of:

```bash
python3 ~/.claude/plugins/cache/.../scripts/setup_key.py typesafe
```

It reads the key without echoing it and saves it to `~/.config/typesafe/key` with mode 600. Setting
`TYPESAFE_API_KEY` works too. Do not paste keys into the chat: Claude will refuse them, and they would
stay in the conversation history.

## Use

```
/paper-sift:survey diffusion models for image generation
```

Claude asks what you already know, which papers you trust and how many papers to screen; proposes seeds
and questions with a cost estimate; and runs each stage after you approve. Claude Code will ask
permission for the plugin's `survey.py` commands: choose "Yes, and don't ask again" for the project and
the later steps run without prompts. Results go to `./paper-sift/<date>-<slug>/`:

| file | contents |
|---|---|
| `report.md` | funnel, reading list, papers to check by hand, cost |
| `reading-list.bib` | the list as BibTeX |
| `scored.csv` | every screened paper with Jev's probabilities |
| `spec.json` | the survey's definition; ranking changes re-run for free (see the skill) |

## How it decides

The model answers facts; code applies the policy. Each question returns the probability of "yes", and
the spec's policy combines them:

```json
"policy": {"gate": "topic", "priority": "p.topic * importance", "final_rank": "p.didactic"}
```

`importance` is a paper's citation percentile among papers of the same year, so recent work is not
buried under older, more-cited papers. Changing the policy re-ranks without new inference.

Abstracts are sent whole. In a 56-paper test, cutting them at 600 characters dropped recall of the
relevant papers from 7/7 to 3/7, and lowering the threshold did not help: the deciding sentence was
not in the input. Small sample, clear mechanism.

## Optional blind check

After screening, Claude offers a blind check of the gate: a separate, read-only subagent labels about
45 abstracts (30 the gate rejected, 15 it accepted) without seeing any score. You get the agreement, an
upper bound on the share of rejected papers that were relevant, and the disagreements to judge
yourself. It costs about 20k Claude tokens, so it runs only if you say yes. The labels are Claude's,
not ground truth; a sample this size catches gross failures, not small losses.

## Cost and time

Measured on a real 100-paper survey (5 highly cited seeds, no Semantic Scholar key, 2026-10-10):
collection took 8.7 minutes (about 35 Semantic Scholar requests, most of the time spent waiting out
rate limits), screening 96 abstracts took 4 seconds, and reading 17 open-access PDFs took about
1.5 minutes. Jev cost about US$ 0.02.

At Jev's published price (US$ 0.042 per million input tokens), an 800-paper survey with ~40 full texts
should cost around US$ 0.10. Collection time grows with how often the seeds are cited and with
Semantic Scholar's rate limits, which is where a key helps most.

## What leaves your machine

- To TypeSafe: the area description (written from your topic and background), titles, abstracts, and
  the full text of open-access papers.
- To Semantic Scholar, OpenAlex and arXiv: search queries, paper IDs and titles.
- Open-access PDFs are downloaded from whatever host Semantic Scholar links to (besides arXiv).
- On the first full-text run, `pypdf` is installed into the plugin's data directory from PyPI.
- Nothing else from your files.

## Limitations

- One recipe for now: learning an area. Novelty checks and property searches are planned.
- Only open-access full text is read; the report lists the rest for you.
- Jev reads English best, so questions are always written in English.
- Papers without an abstract on Semantic Scholar or OpenAlex are not screened; the report lists every
  such seed and the best-connected of the others (found by two or more sources, up to 15).

## Development

```bash
python3 -m unittest discover -s tests -v
claude plugin validate .
claude plugin validate --strict .claude-plugin/plugin.json
```

The design is in [docs/design.md](docs/design.md).

## Terms

Each user calls TypeSafe with their own key, under TypeSafe's terms. Its Master Customer Agreement
(last updated 2026-09-23) was checked on 2026-10-08.

Not affiliated with TypeSafe AI, Semantic Scholar or OpenAlex.

## License

[MIT](LICENSE)
