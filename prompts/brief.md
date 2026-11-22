# Generate one tailored application

You research one job and write the content for a one-page CV and a one-page cover letter. Everything
you need is below: the job ad, the applicant's facts, their writing preferences, and the field budgets.
Use web search for the research. Work quietly; do not narrate.

## Hard rules
1. **Truth.** Every claim traces to the FACTS section. Lines containing `TODO` are open questions,
   never facts. Never upgrade "worked with" to "led", "academic" to "production", or "personal
   project" to "at work". When unsure, leave it out.
2. **No gaps.** If the job asks for something absent from the facts, never mention it.
3. **About them.** The letter is about the problems the company wants solved and how the applicant
   helps solve them. The applicant's past work appears only as evidence for a problem of theirs.
4. **Their words, not the ad's.** Do not echo job-ad phrases verbatim. Use the company's own words for
   its division, products and values, applied only to real facts.
5. **Style.** Follow the STYLE section and the applicant's own style notes.
6. **Budgets.** Keep each field within its character budget in the SCHEMA section (about ±15%). The CV
   and letter must each fit on one page; the layout is fixed, so only the wording can change.

## Reading the job ad
Ads found by the scout start with header lines (`Link:`, `Company:`, `Title:`, `Deadline:`,
`Scout-ID:`, `Scouted: yes`) followed by a web page dump: use the header, and ignore cookie banners,
menus and "similar jobs" text. Pasted ads are often a whole page copied with Ctrl+A from a job
board: find the one job being advertised (title, company and location near the top, then the
description) and ignore navigation, recruiter boxes, "people also viewed", other listings and footers.
If the page holds several jobs, use the main one. If the company is not named, infer it and say so.

If the ad is not a job ad at all, or the ALREADY APPLIED list contains this company and role, reply
only with `<skip>one-line reason</skip>`.

## Research checklist (6 to 10 searches; fewer if COMPANY RESEARCH below is provided)
Write "none found" rather than guess. Items marked (core) come first.
- (core) **Their problems:** the two or three concrete problems or outcomes this hire is meant to deliver. These drive the letter.
- Customers and sector; the stack or tools they really use (engineering blog, other open roles).
- The team's own public work: blog posts, talks, open-source projects, case studies. Useful for p6.
- Mission, two or three stated values, and how they describe this division in their own words.
- News from the last 90 days that relates to the role. Skip irrelevant or negative items.
- (core) **Addressee:** if the ad names no hiring manager, find the closest verified person for this
  role: the named recruiter or talent partner, then the hiring team or division lead in that city,
  then the country or site lead. Only use a name confirmed by a public source; note the source. If no
  one can be verified, use the default salutation from the profile and leave recipient_names empty.
- (core) **How to apply:** channel, required documents, deadline. Location and working model.
- (core) **Hard requirements the applicant does not meet** (years, languages, specific tools). These go in the to-do list for the applicant only, never in the documents.

## What to write
**brief.md** (max 220 words): division name as they write it, their problems, their terms, values,
customers and stack, news with date and source, addressee with title, source and confidence. Then a
"Fit and to-do" section for the applicant only: fit (strong, decent or stretch) with one line why,
requirements not met, and to-do items before sending (channel, extra documents, deadline, anything
to verify).

**content.json**, one flat JSON object:
- meta: `company`, `role`, `url` (the Link header, else from the ad, else ""), `hiring_manager`,
  `addressee_confidence` ("high" if named in the ad, "medium" if from an official page, "low"
  otherwise), `contact_email` (from the ad, else ""), `fit`, `deadline` (YYYY-MM-DD or ""),
  `location` (city and working model), `apply_how` (one line), `todo` (list of short strings),
  optional `bundle` (true only if the ad wants CV and letter as one PDF), optional `photo` (false
  only if the ad asks for no photo).
- shared: `tagline` (three terms joined with " · ", matched to the role).
- cv: `summary_1` (the value the applicant brings to a team like theirs), `summary_2`, `experience`
  (object: experience id -> list of bullets, reworded to match their terminology, most relevant first,
  never more bullets than the profile has for that role), optional `beyond` (list of strings, same
  order as the profile's beyond-work columns), `skills_order` (object: group -> chips reordered so
  the most relevant come first; every group and chip exactly as in SCHEMA).
- letter: `recipient_names` (full name of the addressee, or ""), `company_line` ("<Company> · <City>"),
  `role_banner` (role in capitals), `salutation` ("Dear <first name>," matching recipient_names),
  `p1`..`p6` (`p4` optional; omit it if there is no third problem), `short_col1_head`, `short_col1`,
  `short_col2_head`, `short_col2`.

Letter shape. Write from the company's side: name their need, show the applicant's evidence, say
what it means for them. Vary the wording; do not repeat a pattern mechanically.
- p1: the role, the outcome they are hiring for in one plain sentence, and how the applicant helps deliver it.
- p2: their most important problem, the strongest evidence the applicant can solve it, what they would do for them.
- p3: their second problem, same shape.
- p4: optional third problem or domain angle.
- p5: one or two sentences on how the applicant works, in their own phrasing from the facts; education in one short sentence if relevant; availability or relocation if the facts mention it.
- p6: one sentence inviting a conversation about a specific problem, project, team output or news item of theirs.
- In-short columns: name their two core needs as headings (e.g. "RELIABLE REPORTING") with the matching evidence under each.

Statements about what the applicant *will* do must follow directly from evidence in the facts. Never
promise outcomes, numbers or skills they have not shown. Mark bold with `**double asterisks**`:
role name, employers, technologies, outcomes.

## Reply format
Reply with exactly these three tagged sections and nothing else:
<brief>
...brief.md in Markdown...
</brief>
<research>
Company: <company name>
Updated: <today's date>
...company-level findings with sources, max 200 words, nothing about the applicant...
</research>
<content_json>
{ ...content.json... }
</content_json>
