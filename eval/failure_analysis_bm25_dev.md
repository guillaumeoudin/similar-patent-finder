# Preliminary failure analysis: keyword baseline, development set

This is not the final analysis. The final one will be done on the real pipeline after the test run.

Setup: BM25 keyword search, 20 development queries, 86 expected references in the corpus. 47 of them were not in the top 10 (55 percent). 15 of those 47 were drawn at random (fixed seed) and read by hand. One reader, so the classification is a judgment call.

| Cause | Cases | What it looks like |
|---|---|---|
| Different wording for the same idea | 7 | "cloth" against "fabric", "non-contact" against "wireless", "power feeding" against "wireless power transmission", "position measurement" against "coil alignment" |
| Reference only loosely related | 6 | The examiner cited a patent from the same field that deals with another aspect (a boosting circuit against a self-tuning resonator, a mechanical shim assembly against coil selection) |
| Different sub-technology | 1 | Far-field radio transmission cited against an inductive charging query |
| Query focuses on another aspect | 1 | The query is mostly about a manufacturing process, the reference only matches its coil layer |

Notes:

- One of the wording cases is a spelling issue: "mousepad" in the query and "mouse pad" in the reference. A tokenizer that splits words differently would not find it, and a meaning based search probably would.
- Missed references often rank far down (ranks 12 to 420 among 500 patents). Only one of the 15 was a near miss (rank 12).
- Document length did not stand out as a cause. The longest reference in the sample had 30 claims, but it was also only loosely related.

What this suggests, before any measurement of the hybrid search:

- About half of the sampled misses (7 of 15) look like cases where search on meaning could help.
- About 6 of 15 are references that no similarity search should be expected to find. They set a ceiling on recall for this evaluation, not a defect of the keyword method.

These two statements are hypotheses. They are tested when the vector search runs.
