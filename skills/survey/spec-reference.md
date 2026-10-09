# spec.json reference

```json
{
  "slug": "diffusion-models",
  "area": "We are building the reading list of a newcomer to diffusion models for image generation. The area covers denoising diffusion and score-based models, samplers, guidance and conditioning, latent diffusion, evaluation, and image editing. The reader knows deep learning, VAEs and GANs, but not score-based models.",
  "seeds": [{"id": "arXiv:2006.11239", "title": "Denoising Diffusion Probabilistic Models", "why": "foundational"}],
  "queries": ["diffusion models image generation", "score-based generative models"],
  "pool_size": 800,
  "questions": {
    "topic": {"instructions": "Is `paper` mainly about diffusion or score-based generative models, in the sense described in `area`?", "true": "The main subject is a diffusion or score-based model: its theory, training, sampling, conditioning, evaluation, or an application where the diffusion model is the contribution", "false": "The paper only uses a diffusion model as a tool for another goal, or is about another kind of generative model"},
    "survey": {"instructions": "Is `paper` a survey, tutorial, taxonomy or position paper?", "true": "It surveys, systematizes or teaches a research area rather than presenting one new method", "false": "It presents a new method, dataset or empirical study"},
    "sub_sampling": {"label": "Sampling", "instructions": "Is `paper` about sampling from diffusion models faster or better, such as new samplers, ODE/SDE solvers, or distillation of the sampling process?", "true": "Sampling speed or quality is a main contribution", "false": "Sampling is not a main contribution"}
  },
  "fulltext_questions": {
    "didactic": {"instructions": "Reading the full text of `paper`: could a newcomer with the background described in `area` learn the core concepts of the area from it?", "true": "It explains its problem, background and method clearly and self-containedly; a newcomer could follow it without prior reading in the area", "false": "It assumes the reader already knows the area, or it is narrow and incremental"}
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

(The `start_here` above assumes a `map` full-text question; see question-guide.md.)

| field | meaning |
|---|---|
| `slug` | lowercase words joined by `-`; also the end of the directory name |
| `area` | 3–6 sentences in English: what the area covers (name the subtopics) and who the reader is (what they already know). Every Jev call sees it |
| `seeds` | `[{id, title, why}]`, with `id` as printed by `search` or `lookup` (`arXiv:…`, `DOI:…` or an S2 paperId) |
| `queries` | 0–5 keyword queries; their top results join the pool |
| `sources` | optional: `citations`, `references`, `recommendations` (booleans, default true), `search_per_query` (0–100, default 100) |
| `years` | optional: `null` or `[first, last]`; seeds are never filtered out |
| `pool_size` | ceiling on papers screened: 100–3,000, default 800 |
| `model` | optional: Jev model, default `jev-1.13.0` |
| `tau` | optional: probability at which a fact counts as true, default 0.5 |
| `questions` | abstract questions; must include `topic` (the gate); subtopics are named `sub_*` and have a short `label` |
| `fulltext_questions` | questions asked of the full text |
| `policy.gate` | which papers pass the abstract stage; normally `topic` |
| `policy.priority` | order for full-text selection; normally `p.topic * importance` |
| `policy.fulltext` | `top` (best by priority), `per_subtopic`, `include_seeds` |
| `policy.start_here` | papers that open the list |
| `policy.final_rank` | order inside each section; normally `p.didactic` |
| `policy.final_top` | papers in the list, all sections together; default 20 |

## Expressions

- A bare question name is true when its probability is at least `tau`: `topic and not sub_hardware`.
- `p.<name>` is the probability itself: `p.topic * importance`.
- `importance` is the paper's citation percentile among papers of the same year (0–1); `year` and
  `citations` are also available.
- Allowed: `and`, `or`, `not`, comparisons, `+ - * /`, numbers, parentheses. Nothing else.
- `gate` and `priority` may use abstract questions only; `start_here` and `final_rank` may use both sets.
