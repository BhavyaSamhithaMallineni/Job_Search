"""
resume_tailor.py
Uses Ollama (local, free) to tailor resume for each job.
Falls back to Anthropic (cheapest model) only if Ollama is unavailable.
"""

import os
import requests
from pathlib import Path
from rich.console import Console
from dotenv import load_dotenv

load_dotenv()
console = Console()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")


def call_llm(prompt: str, max_tokens: int = 2000) -> str:
    """Call Ollama locally. Falls back to Anthropic if unavailable."""
    # 1. Try Ollama (free, local)
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
                  "options": {"num_predict": max_tokens, "temperature": 0.3}},
            timeout=120
        )
        if r.status_code == 200:
            return r.json().get("response", "").strip()
    except requests.ConnectionError:
        console.print("  [yellow]Ollama not running. Start it with: ollama serve[/yellow]")
    except Exception as e:
        console.print(f"  [yellow]Ollama error: {e}[/yellow]")

    # 2. Fallback: Anthropic cheapest model (haiku)
    key = os.getenv("ANTHROPIC_API_KEY")
    if key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=key)
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}]
            )
            return msg.content[0].text.strip()
        except Exception as e:
            console.print(f"  [red]Anthropic fallback failed: {e}[/red]")

    return ""


class ResumeTailor:
    def __init__(self, config: dict):
        self.config = config
        self.base_resume_path = Path(config["resume"]["base_file"])

    def load_base_resume(self) -> str:
        if not self.base_resume_path.exists():
            raise FileNotFoundError(f"Base resume not found at {self.base_resume_path}")
        return self.base_resume_path.read_text(encoding="utf-8")

    def tailor(self, job: dict) -> dict:
        base_resume = self.load_base_resume()
        jd = job.get("description", "")
        title = job.get("title", "")
        company = job.get("company", "")

        ats_before = self._ats_score(base_resume, jd)

        if not jd or len(jd) < 100:
            console.print(f"  [yellow]No JD for {company} — using base resume[/yellow]")
            return {"tailored_resume": base_resume, "ats_before": ats_before,
                    "ats_after": ats_before, "changes_made": []}

        console.print(f"  [cyan]Tailoring resume for {company} using {OLLAMA_MODEL}...[/cyan]")

        prompt = f"""You are an ATS resume expert. Tailor this resume for the job below.

STRICT RULES:
1. Never add skills or experiences NOT in the original resume
2. Reorder bullets — most relevant first
3. Rephrase bullets using exact keywords from the JD
4. List most relevant skills first
5. Never change numbers, dates, company names, education
6. Output ONLY the resume text, nothing else, no explanation

JOB: {title} at {company}
JOB DESCRIPTION:
{jd[:2500]}

RESUME:
{base_resume}

TAILORED RESUME:"""

        tailored = call_llm(prompt)

        if not tailored:
            return {"tailored_resume": base_resume, "ats_before": ats_before,
                    "ats_after": ats_before, "changes_made": ["LLM unavailable"]}

        ats_after = self._ats_score(tailored, jd)
        console.print(f"  [green]ATS score: {ats_before['score']}% → {ats_after['score']}%[/green]")

        return {"tailored_resume": tailored, "ats_before": ats_before,
                "ats_after": ats_after, "changes_made": [f"+{ats_after['score']-ats_before['score']}% ATS"]}

    def _ats_score(self, resume: str, jd: str) -> dict:
        if not jd:
            return {"score": 0, "matched": [], "missing": [], "matched_count": 0, "total_keywords": 0}

        stop_words = {
            "the","a","an","and","or","but","in","on","at","to","for","of","with","by",
            "from","is","are","was","were","be","been","have","has","had","do","does",
            "did","will","would","could","should","may","might","must","can","this",
            "that","these","those","we","you","they","our","your","their","experience",
            "work","working","team","role","years","skills","ability","strong","looking",
            "seeking","required","preferred","including","across","within","through","using","based"
        }
        jd_words = set(
            w.lower().strip(".,()-/") for w in jd.split()
            if len(w) >= 4 and w.lower().strip(".,()-/") not in stop_words
        )
        resume_lower = resume.lower()
        matched = [w for w in jd_words if w in resume_lower]
        missing = [w for w in jd_words if w not in resume_lower]

        for term in ["dbt","snowflake","airflow","python","sql","bigquery","spark",
                     "mlops","langchain","vertex ai","power bi","tableau","a/b testing",
                     "bayesian","machine learning","data modeling","streamlit","mode"]:
            if term in jd.lower():
                if term in resume_lower and term not in matched: matched.append(term)
                elif term not in resume_lower and term not in missing: missing.append(term)

        score = min(int((len(matched) / max(len(jd_words), 1)) * 100), 98)
        return {"score": score, "matched_count": len(matched), "total_keywords": len(jd_words),
                "matched": sorted(matched)[:20], "missing": sorted(missing)[:15]}

    def save(self, result: dict, output_dir: Path, job: dict):
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "resume_tailored.txt").write_text(result["tailored_resume"], encoding="utf-8")
        before, after = result["ats_before"], result["ats_after"]
        report = f"""ATS SCORE REPORT
================
Company: {job.get('company')} | Role: {job.get('title')}
Before: {before['score']}% ({before['matched_count']}/{before['total_keywords']} keywords)
After:  {after['score']}% ({after['matched_count']}/{after['total_keywords']} keywords)
Gain:   +{after['score'] - before['score']}%

MATCHED: {', '.join(after.get('matched', [])[:15])}
MISSING: {', '.join(after.get('missing', [])[:10])}
"""
        (output_dir / "ats_score.txt").write_text(report, encoding="utf-8")
        console.print(f"  [green]✓ resume_tailored.txt saved[/green]")
