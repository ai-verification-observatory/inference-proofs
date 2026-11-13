# Depth: the site is an iceberg

Read this before you add a line to a page. RFC-0018 SI-8 is the rule; this file is its map.

The site is read from the top down. The top shows the result. Each step down shows more of how the result was taken, to a reader who has chosen to look. A reader at the surface knows nothing about the method and should not need to. A reader three steps down already knows where they are and what the site does, and wants the exact thing.

So a line is placed by one question: how deep is the reader who needs it? What a figure is belongs high. How, when and on how many runs it was taken belongs lower. Nothing is deleted to make a page lighter: it moves to its depth and stays one step from where it was.

## The depths

| Depth | Where | The reader already knows | The question they are asking |
|---|---|---|---|
| 0. Glance | share cards, link previews, page titles and descriptions | nothing | What is this, and where does this system stand? |
| 1. Surface | the ladder (home), the Scale page | that this is a table of systems that prove a model's reply | Can it be proved, on what size of model, did it pass, at what cost? |
| 2. System, top | a system's page: its band and its Figures row | one system on one model, and its result | What did this system get, and what holds it back? |
| 3. System, body | a system's page: Glyph, Checks, Cost, Fidelity, Sessions | the result and the words for it | How was each state and figure taken, and on which record? |
| 4. Rules | Checks, Mandate, the glossary | what was measured | What does the rule say, who set it, who runs this? |
| 5. Records | the repository: board file, run records, level file, RFCs | the rule | Can I recompute it? |

Two things sit beside the depths, not in them:

- **Learn** is a way in for a reader who wants the subject explained. It is not a step between the ladder and a system. Its pages follow their own order (a policy track, an engineering track), and a figure there is printed with its labels, since the page is read alone.
- **The footer** is the same on every page. It holds names only (the level, the release with its date, the licence, who builds the site), each a link: the level to the mandate's line on it, the release to its board file, the licence to its text in the repository. It carries no date of a rule and no hash.

## Three laws

1. **Down, never out.** Content moves to its depth; it is not removed. Each depth links to the next: a ladder row to its system's page, a word to its definition, a state to its evidence, an evidence line to its record.
2. **A bad result never moves down.** "Failed", "undecided", "not passed yet", "not measured", "not run" stay at the surface, in words, beside the system they concern. Only the explanation of the result moves down.
3. **A hover title is a shaft, not a home.** A figure's title carries its labels (scope, n, grade, tier, record) at any depth. It is never the only place they are: a phone and a keyboard have no hover, so the same labels are printed in visible text one step down.

## What goes where

The shallowest depth where each kind of content may be printed, and its form there. Deeper, it may appear in full.

| Content | Shallowest depth | Form there |
|---|---|---|
| system and model names, model size | 0 | words |
| standing, and the checks not held | 0 | words ("not passed yet: Model check undecided") |
| the headline figure (cost vs serving) | 0 | figure with its unit |
| its two parts (generation, commit and proving) | 0, with the headline | figures with their units (see Exceptions) |
| the glyph | 0 | drawn, with its petals' names; each petal's step in words at 2; reason and quotes at 3 |
| cost, verify time | 0 | figure with its unit |
| proof size | 1 (Scale), 2 | figure with its unit |
| a unit | wherever its figure is | beside the figure, always |
| fidelity | 1 | the check's state, one word ("held") |
| the fidelity metrics (matched leading tokens, the bar, p, the controls, KL) | 3 | the Fidelity table; in the surface word's title above that |
| serving, the figure every multiple is over | 1 | figure with its unit, in the model's head |
| how the model was served (engine, GPUs, concurrency) | 3 | one line under Cost |
| what was counted (scope: "whole sessions of N replies", steady, verify) | 2 | once, under the band's figure; at 3 once for the Cost block, and under a figure whose scope differs |
| sample size (n) | 2 | once, beside the scope; at 3 beside the Cost block's scope, and under the system's own Fidelity figure (in replies) |
| pass thresholds, petal steps | 3 as the bar's row; 4 as rules | |
| the request (prompt and reply tokens, decoding) | 4 | the line that opens the six checks |
| the level's name | footer | a link to the mandate |
| the level's freeze date, its file and digest | 4 | the mandate's line on the level |
| the release | 0 (a card's stamp), footer | "Release v1.0, 2026-11-12": a card is a snapshot, and its date says of when |
| publisher quotes | 3 | behind each petal's disclosure |
| run records, failed runs | 3 | counts and links under Checks and Sessions |
| definitions | 4 | the checks page and the glossary; a head at 1 or 2 links to its definition |
| method prose | 4, Learn | prose |
| rule ids, file names, hashes, run directories | 5 | a link's target or title above that, never visible text at 0 to 2 |
| who builds the site | footer | names, linked |
| conflicts of interest | 4 | the mandate |

## Words follow depth

- **The surface names the property; deeper names the measure.** Depths 0 to 2 say "Fidelity", "Cost", "Verify time". The exact metric ("leading tokens matching the original, mean", "KL to the original weights") first appears at depth 3, as a column head. The surface word links to it.
- **The head says what, the unit says per what.** "Cost" beside USD/reply, never "Cost per reply" beside USD/reply. `FIGURE_HEAD` in `draw/words.py` holds the heads; `beside_unit` trims a longer name where a unit follows it. A name printed with no unit (a definition's title, a sentence) keeps its full form.
- **Once per block.** What a block's figures share (scope, n, a model, a date) is said once for the block, not on each figure. A figure that differs from its block says so.
- **No bare fraction.** A figure is not framed "of N" unless N is what it is judged against. The mean matched prefix is judged against the model's bar, not against the reply's length, so it is printed with the bar or not at all.
- **A state keeps its word at every depth.** held, failed, undecided; in full, in part, in lesser part. An abstraction never softens a state.
- **No visible id above depth 3.** A rule id, a file name or a control's id is a link's title there.

## The test

Ask in this order; the first yes decides.

1. Would placing it deeper hide a failure, an undecided state, an unmeasured figure or a missing run? Then it stays at depth 0 or 1, as a word.
2. Does a reader who knows only that the benchmark exists need it to read which system passed on which model, and at what cost? Depth 0 or 1.
3. Does it say what one system got, or what holds it back? Depth 2.
4. Does it say how, when or on how many runs something was taken, or quote a source? Depth 3, and the figure's title above that.
5. Is it true of every system (a rule, a threshold, a definition, who and why)? Depth 4, linked from where it applies. Is it an id, a path or a hash? Depth 5, as a link.

Then, before printing it: does a head, a unit, the glyph or another block of the same page already say it? If so, link to that instead.

## Exceptions, each deliberate

- **The two parts of the multiple are on the ladder**, a depth above where the test puts them. Where a system generates its reply in a phase of its own, most of its multiple can be generation, not proving, and the headline read alone is taken for the cost of proving (RFC-0018 CO-7, Decision Q15). The parts change how the headline reads, so they travel with it.
- **A share card carries the release and its date.** A card outlives the page it was made from; the date says which figures it shows.

## Known gaps

Places that do not yet follow the map, found by reading the built pages on 2026-11-13. Fix them as the pages are next touched.

- A ladder figure's head links to its definition (depth 4) and the figure itself links nowhere; the figure should lead to its section of the system's page (depth 3).
- The "Systems not run" reasons on the ladder ("no configuration at the request", "a different statement") use the method's words. RFC-0018 SI-4 fixes the list and its place, so moving it needs that rule amended.
