You are transcribing ONE scanned sheet of a Soviet technical document (typewritten Russian on a ГОСТ 2.106-68 form).
This is sheet «{sheet}» of {doc}. Previous sheet: «{prev}». Next sheet: «{next}».

Read the image file `{image}` with the Read tool. Then reply with ONLY the format below — no preamble, no code fences.

Rules:
- Transcribe the body text verbatim, in reading order. Do not correct, summarize, translate or complete anything.
- Copy characters as printed: the typewriter uses the letter I for the digit 1 (e.g. 6.II.I, МI02) — keep it; a script normalizes later.
- Skip the form frame: margin columns (Инв. № подл., Подп. и дата, Взам. инв. №, Инв. № дубл.), the header «Ф5а ГОСТ 2.106-68», the footer «Копировал / Формат 11», and the title-block grid.
- From the title block report only the change row (Изм., Лист/Зам, № докум., дата) in MARKS, and its Изм. number in REV.
- Handwritten corrections: when printed text is struck through and replaced by hand, put the NEW text in TEXT, and right after that paragraph add `<!-- изм. N: было «old text» -->` (N = circled number, if any). Also add one MARKS line describing it.
- Handwritten additions (formulas, symbols, inserted words) go into TEXT where they belong, plus a MARKS line.
- Anything you cannot read: write [неразборчиво]. Never guess a digit.
- Numbered section headings (e.g. «6.11. Проверка …») become `## ` headings; numbered items stay plain paragraphs starting with their number.
- Tables become Markdown tables, one row per table row.
- Figures and drawings: do NOT draw or describe the drawing. Write the caption in bold, then one line listing the labels/dimensions printed on it.
- If the sheet starts in the middle of a sentence, begin TEXT with `<!-- начало на листе {prev} -->`.
  If it ends in the middle of a sentence, end TEXT with `<!-- продолжение на листе {next} -->`.

Format:
SECTION: <number and title of the section this sheet belongs to, if visible; else empty>
REV: <Изм. number from the title block change row; else empty>
MARKS:
- <one line per stamp / handwritten mark; omit the list if none>
TEXT:
<markdown body>
