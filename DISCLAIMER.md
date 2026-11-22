# Disclaimer and responsible use

Please read this before using the Application Pipeline. By using it you accept these terms.

## No liability
This software is provided "as is", without warranty of any kind, under the PolyForm Noncommercial License 1.0.0. The authors and
contributors are **not responsible** for how you use it, for any consequences of that use, or for any
loss, damage, account suspension, legal claim or other harm that results. You use it entirely at your
own risk and you are solely responsible for complying with all laws, regulations and terms of service
that apply to you.

## Web scraping and job sites
The "Find jobs" feature can collect job listings from websites you configure. Whether automated access
to a website is allowed depends on that website's terms of service, its robots.txt, and the law where
you and the website are located (for example computer misuse, copyright, database rights and data
protection law). These differ between countries and change over time.

- **Check each site's terms before you add it.** Many job boards prohibit scraping or automated access.
  If a site's terms forbid it, do not add that site. Paste its job ads by hand instead.
- **Prefer official channels.** Company boards on Greenhouse, Lever and Ashby, and RSS feeds, are public
  interfaces published for this kind of use. Prefer them over scraping web pages.
- **Keep volumes low.** The tool checks robots.txt, spaces out its requests, and identifies itself.
  Do not remove these safeguards, run it in parallel against the same site, or run it more often than
  you need (once a day or once a week is plenty for a personal job search).
- **Personal use only.** Do not use this tool to build datasets, resell listings, monitor competitors,
  or collect information about people.
- **No logins.** Do not configure it to access pages that require you to be logged in, or to get around
  paywalls, CAPTCHAs, rate limits or other access controls.

## Personal data
Job ads can contain names and contact details of recruiters and hiring managers, and the research step
looks up the right person to address. Treat that information with care, use it only to apply for the
job in question, and follow the data protection law that applies to you (such as the GDPR). Your own
CV, facts and job ads are sent to Anthropic when Claude researches and writes; see Anthropic's terms and
privacy policy. Everything else stays on your computer in the `data/` folder.

## AI-generated content
Claude writes the CVs and cover letters. The tool is built to use only facts from your own profile and
runs automatic checks, but **AI can still make mistakes**: wrong claims, wrong names, wrong details
about a company. **Read and check every document before you send it.** You are responsible for
everything you submit to an employer. Never submit anything that is not true.

## Costs
Generating applications uses your Claude Code plan or your Claude API account, and may cost money.
You are responsible for any charges.

## Not legal advice
This disclaimer is a general notice, not legal advice. If you are unsure whether a use is lawful
where you live, ask a qualified lawyer.
