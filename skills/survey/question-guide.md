# Writing the questions

Jev answers each question with the probability that the answer is yes. It reads literally, judges one
thing at a time, and sees only the spec's `area` and one paper. These rules come from TypeSafe's
guidance (https://docs.typesafe.ai/) and from what failed in practice.

## Rules

1. **One judgment per question.** "Is it about X and does it propose Y?" is two questions; combine them
   in the policy.
2. **Say exactly what counts.** The `true` and `false` criteria must agree with the instruction; edge
   cases go there.
3. **Name the look-alikes that do not count.** When a neighboring field uses the same words, say so in
   `false`, for example: "adversarial training of GANs does NOT count as adversarial robustness".
4. **Point at the inputs by name:** `paper` (title and abstract, or full text) and `area`.
5. **No double negatives** and no questions about properties of properties.
6. **Never gate on a holistic question** such as "is this relevant to our project?" or "is this close to
   the area?". It accepts too much: one such question let through every paper that used a common
   baseline technique. Gate on what the paper is mainly about.
7. **Plain English**, with no abbreviation that `area` does not define.

## Abstract questions

- `topic` (required; the gate). Instructions: "Is `paper` mainly about <the area in a few words>, in the
  sense described in `area`?" True: "The main subject is <...>: <the kinds of contribution that count>".
  False: "The paper only uses <...> as a tool for another goal, or is about <look-alike>".
- `survey`. Instructions: "Is `paper` a survey, tutorial, taxonomy or position paper?" True: "It
  surveys, systematizes or teaches a research area rather than presenting one new method". False: "It
  presents a new method, dataset or empirical study".
- 4–8 subtopics named `sub_<name>`, each with a short `label`. Instructions: "Is `paper` about
  <subtopic>?" True: "<subtopic> is a main contribution". False: "<subtopic> is not a main
  contribution". Together they should cover the area as `area` describes it, with little overlap.

## Full-text questions (defaults; adapt the wording to the area)

| name | instructions | true | false |
|---|---|---|---|
| `didactic` | Reading the full text of `paper`: could a newcomer with the background described in `area` learn the core concepts of the area from it? | It explains its problem, background and method clearly and self-containedly; a newcomer could follow it without prior reading in the area | It assumes the reader already knows the area, or it is narrow and incremental |
| `map` | Does `paper` give the reader a map of the area described in `area`: a taxonomy, a systematic comparison of many methods, or a synthesis of what works and what does not? | A reader comes out with an overview of many methods | It covers one method or one setting |
| `formulation` | Does `paper` state its problem precisely: explicit assumptions, inputs and outputs, and a definition of success or an evaluation criterion? | The setting and the success criterion are explicit | The setting or the success criterion is left implicit |
| `limitations` | Does `paper` explicitly discuss its limitations or open problems? | Yes | No |
| `code` | Does `paper` state that its code, models or data are publicly available? | Yes | No |

With these, use `start_here` = `(survey or map) and didactic` and `final_rank` = `p.didactic`.
