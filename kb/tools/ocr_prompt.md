You are transcribing ONE scanned sheet of a Soviet technical document (typewritten Russian on a ГОСТ 2.106-68 form).
This is sheet «{sheet}» of {doc}. Previous sheet: «{prev}». Next sheet: «{next}».

Read the image file `{image}` with the Read tool. Then reply with ONLY the format below — no preamble, no code fences.

Rules:
- Transcribe the body text verbatim, in reading order. Do not correct, summarize, translate or complete anything.
- Copy characters as printed: the typewriter uses the letter I for the digit 1 (e.g. 6.II.I, МI02) — keep it; a script normalizes later.
- Skip the form frame entirely: margin columns (Инв. № подл., Подп. и дата, Взам. инв. №, Инв. № дубл.), the header «Ф5а ГОСТ 2.106-68», the footer «Копировал / Формат 11», and the whole title block — change row (Изм., Лист, № докум., Подп., Дата), signatures, surnames, dates, inventory numbers. Never mention any of these in TEXT, MARKS or UNCERTAIN.
- From the title block read only the document designation (e.g. «М181-600-000 ИЭ») and the sheet number in the «Лист» cell. If either differs from «{doc}» / «{sheet}», add an UNCERTAIN line `лист: напечатано «<designation> л.<number>», ожидалось «{doc} л.{sheet}»`. If they match, say nothing.
- Handwritten corrections: when printed text is struck through and replaced by hand, put the NEW text in TEXT, and right after that paragraph add `<!-- изм. N: было «old text» -->` (N = circled number, if any). Also add one MARKS line describing it.
- Handwritten additions (formulas, symbols, inserted words) go into TEXT where they belong, plus a MARKS line.
- Anything you cannot read: write [неразборчиво]. Never guess a digit.
- Numbered section headings (e.g. «6.11. Проверка …») become `## ` headings; numbered items stay plain paragraphs starting with their number.
- Tables become Markdown tables, one row per table row.
- Figures and drawings: do NOT draw or describe the drawing. Write the caption in bold, then one line listing the labels/dimensions printed on it.
- Wiring diagrams (Схема электрическая соединений): do NOT transcribe the wiring. List only the connectors named on the sheet, the printed notes and the drawing title, then end TEXT with `<!-- wiring is NOT transcribed by design — open the scan -->`.
- If the sheet starts in the middle of a sentence, begin TEXT with `<!-- начало на листе {prev} -->`.
  If it ends in the middle of a sentence, end TEXT with `<!-- продолжение на листе {next} -->`.

- In UNCERTAIN list every value, word or table cell whose reading you are not sure of (exactly as you wrote it in TEXT), with the reason. Be honest: this list decides whether a stronger model re-reads the sheet.
  Do NOT list doubts that only concern look-alike characters (I/1, О/0, З/3, Latin vs Cyrillic letters): a script normalizes those.
- Write MARKS and UNCERTAIN lines in Russian.

Format — always write all five headers in exactly this order, even when MARKS or UNCERTAIN has no lines; after TEXT comes only the body:
KIND: <one of: title, toc, text, table, figure, diagram, changelog, insert>
SECTION: <number and title of the section this sheet belongs to, if visible; else empty>
MARKS:
- <one line per handwritten mark in the body; no lines if none>
UNCERTAIN:
- <exact reading> — <why unsure>; no lines if none
TEXT:
<markdown body>
