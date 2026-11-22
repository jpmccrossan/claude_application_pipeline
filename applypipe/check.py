"""Mechanical rule checks on a job's content.json. render.py runs these before rendering.

Usage: python -m applypipe.check data/output/<day>/<job>
Errors: banned phrases, em or en dashes, exclamation marks, a technology that is not in facts.md
(outside p6), a salutation that does not match the addressee. Warnings: another job's company named here.
"""
import json
import re
import sys
from pathlib import Path

from . import profile as profiles
from .jobfiles import read_content
from .paths import OUTPUT

# Puffery, clichés, gap admissions and self-deprecation. Add your own in profile.json "banned_phrases".
BANNED = [
    "haven't used", "have not used", "haven't worked with", "fast learner", "quick learner",
    "passionate", "rockstar", "ninja", "world-class", "perfect fit", "perfect candidate", "dream job",
    "thrilled", "incredibly excited", "hit the ground running", "move the needle",
    "low-hanging fruit", "wear many hats", "leverage", "leveraging", "synergies", "cutting-edge",
    "best-in-class", "game-changing", "game changer", "revolutionise", "revolutionize", "spearhead",
    "results-driven", "proven track record", "go-getter", "think outside the box",
    "better than me", "still learning", "not an expert", "limited experience", "relatively new to",
    "although i lack", "despite my lack", "i hope to", "i believe i could", "i may not",
]

# Technologies that turn up in job ads. Any of these in content.json must also appear in facts.md.
TECH = [
    "Python", "SQL", "PostgreSQL", "MySQL", "SQL Server", "Oracle", "MongoDB", "Redis", "Supabase",
    "Snowflake", "Databricks", "BigQuery", "Spark", "PySpark", "Kafka", "Airflow", "dbt", "Dask",
    "Fabric", "Azure Data Factory", "Synapse", "Power BI", "Tableau", "Looker", "Plotly", "Excel",
    "Pandas", "NumPy", "Scikit-learn", "XGBoost", "TensorFlow", "PyTorch", "Keras", "Hugging Face",
    "MLflow", "LangChain", "LangGraph", "LlamaIndex", "Ollama", "OpenAI", "Bedrock", "Vertex",
    "Copilot Studio", "Power Automate", "SharePoint", "Salesforce", "SAP", "HubSpot", "Figma",
    "FAISS", "Pinecone", "Chroma", "pgvector", "OpenSearch", "Elasticsearch",
    "FastAPI", "Flask", "Django", "Node.js", "Next.js", "React", "Angular", "Vue", "Svelte",
    "TypeScript", "JavaScript", "Java", "Kotlin", "Swift", "Scala", "C++", "C#", ".NET", "Go", "Rust",
    "Ruby", "PHP", "Docker", "Kubernetes", "Helm", "Terraform", "Ansible", "GitHub Actions", "GitLab",
    "Jenkins", "AWS", "Azure", "GCP", "Google Cloud", "Nginx", "Cloudflare", "Linux", "Bash",
    "Prometheus", "Grafana", "Streamlit", "Unity", "Unreal",
]
META = {"company", "role", "location", "apply_how", "hiring_manager", "deadline", "fit",
        "addressee_confidence", "company_line", "recipient_names", "salutation"}


def facts_text(example: bool = False) -> str:
    """facts.md without open TODO questions and without the 'Not used' section."""
    text = "\n".join(l for l in profiles.facts(example).splitlines() if "TODO" not in l)
    return re.sub(r"## Not used.*?(?=\n## |\Z)", "", text, flags=re.S)


# Tech names that are also ordinary words: only their exact capitalisation counts as a claim.
WORDLIKE = {"Go", "Rust", "Swift", "Ruby", "Spark", "Unity", "Excel", "Chroma", "Fabric", "Vertex", "Helm",
            "Bash", "Looker", "Airflow", "Ansible", "Unreal", "Figma"}


def has(term: str, text: str, exact_case: bool = False) -> bool:
    flags = 0 if exact_case else re.I
    return re.search(rf"(?<![\w.+#]){re.escape(term)}(?![\w+#])", text, flags) is not None


def text_fields(content: dict) -> dict[str, str]:
    """Every piece of prose in content.json, keyed by a readable name."""
    fields = {k: v for k, v in content.items() if isinstance(v, str) and k not in ("url", "accent_hex", "contact_email")}
    for job_id, bullets in (content.get("experience") or {}).items():
        for i, b in enumerate(bullets or []):
            fields[f"experience.{job_id}[{i}]"] = str(b)
    for i, b in enumerate(content.get("beyond") or []):
        fields[f"beyond[{i}]"] = str(b)
    return fields


def check(job: Path, example: bool = False) -> tuple[list[str], list[str]]:
    content = read_content(job)
    profile = profiles.load(example)
    fields = text_fields(content)
    prose = {k: v for k, v in fields.items() if k not in META}
    facts = facts_text(example)
    errors, warnings = [], []

    banned = BANNED + [p.lower() for p in profile.get("banned_phrases", [])]
    for phrase in banned:
        for key, value in prose.items():
            if has(phrase, value):
                errors.append(f"{key}: banned phrase '{phrase}'")
    for key, value in prose.items():
        if "—" in value or "–" in value:
            errors.append(f"{key}: em or en dash (use a comma, colon or full stop)")
        if "!" in value:
            errors.append(f"{key}: exclamation mark")

    company = content.get("company", "")
    # p6 talks about the company's own work (its tools, partners, news), not the applicant's skills.
    claims = "\n".join(v for k, v in prose.items() if k != "p6")
    for term in TECH:
        if has(term, claims, exact_case=term in WORDLIKE) and not has(term, facts) and not has(term, company):
            errors.append(f"'{term}' is not in facts.md, so it cannot be claimed")

    known = {j["id"] for j in profile.get("experience", [])}
    for job_id in (content.get("experience") or {}):
        if job_id not in known:
            errors.append(f"experience.{job_id}: no such experience id in profile.json (use one of {sorted(known)})")

    salutation = content.get("salutation", "")
    recipient = content.get("recipient_names", "")
    first = salutation.removeprefix("Dear ").rstrip(",").strip()
    if recipient and (not first or not recipient.startswith(first)):
        errors.append(f"salutation '{salutation}' does not match recipient_names '{recipient}'")

    own = company.split(",")[0].split()[0].lower() if company.split() else ""
    for other in OUTPUT.glob("*/*/source/content.json"):
        if other.parent.parent.resolve() == Path(job).resolve():
            continue
        try:
            name = json.loads(other.read_text()).get("company", "").split(",")[0]
        except (json.JSONDecodeError, OSError):
            continue
        if name and name.split()[0].lower() != own and has(name, "\n".join(prose.values())):
            warnings.append(f"mentions '{name}' (another job's company)")
    return errors, sorted(set(warnings))


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    errors, warnings = check(Path(sys.argv[1]))
    for w in warnings:
        print(f"check warning: {w}")
    for e in errors:
        print(f"check error: {e}")
    if errors:
        sys.exit(1)
    print("check: ok")


if __name__ == "__main__":
    main()
