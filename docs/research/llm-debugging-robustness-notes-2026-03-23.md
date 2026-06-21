# Research Note — LLM Debugging Robustness Claims

Date: 2026-03-23
Trigger: social post claiming large-scale evidence that LLM debugging breaks under superficial code changes.

## What was investigated

Claim bundle included:
- 750,000 debugging experiments across 10 models
- severe sensitivity to variable renaming/comments
- dead-code confusion
- positional bias (top-of-file preference)
- function reordering causing major drops
- minimal gains in recent model versions
- recommendation to provide runtime evidence and reduce dead code before AI debugging

## Verification status

I could not yet find the exact paper matching all quoted numbers and affiliations (Virginia Tech + CMU) from accessible indexed sources in this pass.

Status: PARTIALLY VERIFIED (directionally), NOT FULLY VERIFIED (exact figures/source paper).

## Related evidence found

1) DePro: Understanding the Role of LLMs in Debugging Competitive Programming Code
- arXiv: https://arxiv.org/abs/2603.19399
- Signal: test-case-driven and iterative refinement improves debugging outcomes vs baseline zero-shot settings.
- Relevance: supports the claim that raw one-shot code reading is insufficient; runtime/test feedback matters.

2) Improved Bug Localization with AI Agents Leveraging Hypothesis and Dynamic Cognition (CogniGent)
- arXiv: https://arxiv.org/abs/2601.12522
- Signal: strong gains by adding hypothesis testing, call-graph context, and context engineering over non-agentic baselines.
- Relevance: supports the idea that structured debugging process/context outperforms plain code-only prompting.

3) Broader arXiv query trend
- Search: https://arxiv.org/search/?query=LLM+bug+localization+debugging&searchtype=all
- Signal: many 2025–2026 works push toward agentic workflows, dynamic context, and benchmarked bug localization, indicating plain prompt-only debugging remains brittle.

## Practical takeaways (high confidence)

1. Provide execution context
- Always include failing test logs, stack traces, and repro steps.

2. Localize and bound context
- Avoid huge monolithic files.
- Feed function-level slices and dependency-relevant snippets.

3. Reduce distractors before prompting
- Remove or isolate dead/commented-out branches where possible.

4. Use multi-pass debugging
- Pass A: bug localization candidates
- Pass B: hypothesis + minimal patch
- Pass C: rerun tests and verify

5. Enforce evidence gates
- No patch accepted without:
  - failing test before
  - passing test after
  - explanation tied to concrete lines and runtime symptoms

## Open follow-up

- Locate and ingest the exact VT+CMU paper (or preprint) that reports the quoted percentages.
- Once found, add precise citation, experiment design summary, and reproducibility notes.
