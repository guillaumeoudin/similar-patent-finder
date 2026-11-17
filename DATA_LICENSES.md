# Data sources and licenses

## PatentsView (USPTO)

- Source: PatentsView granted patent tables, distributed through the USPTO Open Data Portal (data.uspto.gov).
- Tables used: `g_patent`, `g_patent_abstract`, `g_cpc_current`, `g_us_patent_citation`, `g_claims_<year>`.
- Date of access: 2026-11-17.
- Stated license: Creative Commons Attribution 4.0 International (CC BY 4.0), as announced in the PatentsView API documentation (search.patentsview.org/docs).
- Status of verification: the Open Data Portal pages read on the date of access do not display a license or terms of reuse for the bulk files. The CC BY 4.0 statement comes from the PatentsView API documentation only.
- Attribution: data derived from PatentsView. This project is not endorsed by, or affiliated with, PatentsView or the USPTO.

## What this repository contains

- No raw data. A script downloads and prepares the files (raw files are ignored by Git).
- `eval/dataset/split.json`: patent numbers only.
- Short excerpts of patent text may appear in the README and in evaluation outputs, always with the patent number.

## Changes made to the data

- Filtered to CPC group H02J50 and grant years 2015 to 2025.
- Sampled a corpus of 500 patents (fixed seed) for the evaluation.
- A second, illustration only collection of random patents from CPC group A47J31 (coffee and beverage machines), granted 2015 to 2025, is used by the web demo. It comes from the same PatentsView tables, with the same statements above, and `corpora/coffee_ids.json` lists its patent numbers only.
- Abstract and claims are split into chunks; no other transformation of the text.
- The description sections are not used in V1.

## Not legal advice

This file records what was checked. It is not a legal opinion.
