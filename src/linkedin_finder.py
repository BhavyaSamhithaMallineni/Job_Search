"""
linkedin_finder.py
Finds LinkedIn hiring posts and drafts outreach messages using Ollama (free, local).
Falls back to Anthropic if Ollama unavailable.
"""

import os
import re
import requests
from bs4 import BeautifulSoup
from rich.console import Console
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
console = Console()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")


def call_llm(prompt: str, max_tokens: int = 300) -> str:
    """Call Ollama. Falls back to Anthropic haiku if unavailable."""
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
                  "options": {"num_predict": max_tokens, "temperature": 0.5}},
            timeout=60
        )
        if r.status_code == 200:
            return r.json().get("response", "").strip()
    except Exception:
        pass

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
        except Exception:
            pass
    return ""


PROFILE = """
Bhavya Samhitha Mallineni — Analytics Engineer, 4+ years
Skills: dbt, Snowflake, GCP, Python, SQL, LangChain, A/B Testing, MLOps
Education: USC Master's EE | Currently: FloSports Austin TX
"""


class LinkedInFinder:
    def __init__(self, config: dict):
        self.config = config
        self.scraper_key = os.getenv("SCRAPER_API_KEY", "")
        self.max_posters = config.get("linkedin", {}).get("max_posters", 5)

    def find_hiring_posts(self, company: str, title: str) -> list[dict]:
        console.print(f"  [cyan]Searching LinkedIn hiring posts for {company}...[/cyan]")

        queries = [
            f'site:linkedin.com/posts "my team is hiring" "{company}"',
            f'site:linkedin.com/posts "we are hiring" "{company}" data engineer',
            f'site:linkedin.com/posts "join our team" "{company}" analytics',
        ]

        posters, seen = [], set()
        for query in queries:
            for p in self._google_search(query):
                if p["url"] not in seen:
                    seen.add(p["url"])
                    posters.append(p)
            if len(posters) >= self.max_posters:
                break

        console.print(f"  [green]Found {len(posters)} hiring posts[/green]")
        return posters[:self.max_posters]

    def _google_search(self, query: str) -> list[dict]:
        if not self.scraper_key:
            return []
        try:
            url = f"http://api.scraperapi.com?api_key={self.scraper_key}&url={requests.utils.quote('https://www.google.com/search?q='+query+'&num=5', safe='')}"
            r = requests.get(url, timeout=20)
            return self._parse_google(r.text)
        except Exception:
            return []

    def _parse_google(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        results = []
        for g in soup.find_all("div", {"class": "g"}):
            try:
                link = g.find("a")
                h3 = g.find("h3")
                snippet_el = g.find("div", {"class": re.compile("VwiC3b|s3v9rd")})
                if not link or not h3: continue
                url = link.get("href", "")
                if "linkedin.com" not in url: continue
                name_match = re.match(r"^([A-Z][a-z]+ [A-Z][a-z]+)", h3.get_text(strip=True))
                results.append({
                    "name": name_match.group(1) if name_match else "LinkedIn Member",
                    "url": url,
                    "post_snippet": snippet_el.get_text(strip=True)[:200] if snippet_el else ""
                })
            except Exception:
                continue
        return results

    def draft_outreach(self, poster: dict, job: dict) -> str:
        first_name = poster.get("name", "Hi").split()[0]
        prompt = f"""Write a LinkedIn connection request message. Under 300 characters. Sound human not templated.

Sender: Analytics Engineer with dbt, Snowflake, GCP, 4+ years experience
Recipient: {poster.get('name')} at {job.get('company')}
Their post: {poster.get('post_snippet', 'posted about hiring')}
Role I am applying for: {job.get('title')}

Rules: mention 1 skill, reference their post, no visa mention, no emojis, end with "would love to connect"
Output message only:"""

        result = call_llm(prompt, max_tokens=150)

        if not result:
            return (
                f"Hi {first_name}, saw your post about the {job.get('title')} role at "
                f"{job.get('company')}. I'm an analytics engineer with dbt and Snowflake "
                f"experience — would love to connect."
            )
        return result

    def save(self, posters: list, drafts: list, output_dir: Path, job: dict):
        output_dir.mkdir(parents=True, exist_ok=True)
        content = f"""LINKEDIN OUTREACH
=================
Company: {job.get('company')} | Role: {job.get('title')}
Posters found: {len(posters)}

"""
        for i, (poster, draft) in enumerate(zip(posters, drafts), 1):
            content += f"""─────────────────────────
#{i} {poster.get('name')}
URL: {poster.get('url')}
Post: {poster.get('post_snippet','N/A')[:150]}

YOUR MESSAGE (copy & paste into LinkedIn → Connect → Add a note):
"{draft}"

"""
        if not posters:
            content += f'No posts found. Try manually: site:linkedin.com "{job.get("company")}" "hiring" "{job.get("title")}"\n'

        (output_dir / "linkedin_outreach.txt").write_text(content, encoding="utf-8")
        console.print(f"  [green]✓ linkedin_outreach.txt saved[/green]")
