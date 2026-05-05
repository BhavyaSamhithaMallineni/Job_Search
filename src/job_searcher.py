"""
job_searcher.py
Searches LinkedIn Jobs and Indeed for relevant roles.
Uses RapidAPI's LinkedIn Jobs endpoint (free tier: 100 calls/month).
Falls back to direct scraping if no API key provided.
"""

import os
import time
import requests
from datetime import datetime, timedelta
from typing import Optional
from rich.console import Console
from dotenv import load_dotenv

load_dotenv()
console = Console()


class JobSearcher:
    def __init__(self, config: dict):
        self.config = config
        self.rapidapi_key = os.getenv("RAPIDAPI_KEY", "")
        self.scraper_api_key = os.getenv("SCRAPER_API_KEY", "")
        self.max_age_hours = config["search"].get("max_age_hours", 48)
        self.max_results = config["search"].get("max_results_per_title", 25)

    def search_all(self) -> list[dict]:
        """Run search for all configured titles and locations."""
        all_jobs = []
        seen_ids = set()

        titles = self.config["search"]["titles"]
        locations = self.config["search"]["locations"]

        for title in titles:
            for location in locations:
                console.print(f"  [cyan]Searching:[/cyan] '{title}' in '{location}'")
                jobs = self._search(title, location)
                for job in jobs:
                    job_id = job.get("id") or f"{job['company']}_{job['title']}"
                    if job_id not in seen_ids:
                        seen_ids.add(job_id)
                        all_jobs.append(job)
                time.sleep(1.2)  # be polite to APIs

        console.print(f"  [green]Found {len(all_jobs)} unique jobs before filtering[/green]")
        return all_jobs

    def _search(self, title: str, location: str) -> list[dict]:
        """Search jobs via RapidAPI LinkedIn Jobs endpoint."""
        if self.rapidapi_key:
            return self._search_via_rapidapi(title, location)
        else:
            console.print("  [yellow]No RAPIDAPI_KEY found — using fallback scraper[/yellow]")
            return self._search_via_scraper(title, location)

    def _search_via_rapidapi(self, title: str, location: str) -> list[dict]:
        """
        LinkedIn Jobs Search via RapidAPI.
        Endpoint: https://rapidapi.com/jaypat87/api/linkedin-jobs-search
        Free tier: 100 requests/month
        """
        url = "https://linkedin-jobs-search.p.rapidapi.com/"
        headers = {
            "content-type": "application/json",
            "X-RapidAPI-Key": self.rapidapi_key,
            "X-RapidAPI-Host": "linkedin-jobs-search.p.rapidapi.com"
        }
        payload = {
            "search_terms": title,
            "location": location,
            "page": "1",
            "fetchJobContent": "true"
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            return self._parse_rapidapi_response(data)
        except requests.RequestException as e:
            console.print(f"  [red]RapidAPI error: {e}[/red]")
            return []

    def _parse_rapidapi_response(self, data: list) -> list[dict]:
        """Parse RapidAPI LinkedIn response into standard format."""
        jobs = []
        for item in data:
            try:
                posted_at = self._parse_posted_time(item.get("posted_date", ""))
                jobs.append({
                    "id": item.get("job_id", ""),
                    "title": item.get("job_title", ""),
                    "company": item.get("company_name", ""),
                    "location": item.get("job_location", ""),
                    "description": item.get("job_description", ""),
                    "apply_url": item.get("linkedin_job_url_cleaned", ""),
                    "posted_at": posted_at,
                    "posted_str": item.get("posted_date", ""),
                    "salary_str": item.get("salary", ""),
                    "salary_min": self._extract_salary_min(item.get("salary", "")),
                    "salary_max": self._extract_salary_max(item.get("salary", "")),
                    "remote": self._is_remote(item.get("job_location", "")),
                    "source": "linkedin_rapidapi"
                })
            except Exception:
                continue
        return jobs

    def _search_via_scraper(self, title: str, location: str) -> list[dict]:
        """
        Fallback: scrape LinkedIn Jobs public search page via ScraperAPI.
        No login required. ScraperAPI handles rotating proxies + JS rendering.
        """
        if not self.scraper_api_key:
            console.print("  [red]No SCRAPER_API_KEY — cannot search without API keys.[/red]")
            console.print("  [dim]Get a free key at scraperapi.com (1000 calls/month free)[/dim]")
            return []

        # LinkedIn public job search URL (no login needed)
        title_encoded = title.replace(" ", "%20")
        location_encoded = location.replace(" ", "%20").replace(",", "%2C")
        # f=TPT&... filters for jobs posted in past 24h
        target_url = (
            f"https://www.linkedin.com/jobs/search/"
            f"?keywords={title_encoded}&location={location_encoded}"
            f"&f_TPR=r86400&sortBy=DD"  # past 24h, sorted by date
        )

        scraper_url = (
            f"http://api.scraperapi.com"
            f"?api_key={self.scraper_api_key}"
            f"&url={requests.utils.quote(target_url, safe='')}"
            f"&render=true"
        )

        try:
            response = requests.get(scraper_url, timeout=30)
            response.raise_for_status()
            return self._parse_linkedin_html(response.text)
        except requests.RequestException as e:
            console.print(f"  [red]Scraper error: {e}[/red]")
            return []

    def _parse_linkedin_html(self, html: str) -> list[dict]:
        """Parse LinkedIn jobs search results HTML."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        jobs = []

        job_cards = soup.find_all("div", {"class": lambda c: c and "job-search-card" in c})

        for card in job_cards[:self.max_results]:
            try:
                title_el = card.find("h3", {"class": "base-search-card__title"})
                company_el = card.find("h4", {"class": "base-search-card__subtitle"})
                location_el = card.find("span", {"class": "job-search-card__location"})
                time_el = card.find("time")
                link_el = card.find("a", {"class": "base-card__full-link"})

                title = title_el.get_text(strip=True) if title_el else ""
                company = company_el.get_text(strip=True) if company_el else ""
                location = location_el.get_text(strip=True) if location_el else ""
                posted_str = time_el.get("datetime", "") if time_el else ""
                apply_url = link_el.get("href", "") if link_el else ""

                posted_at = datetime.fromisoformat(posted_str) if posted_str else datetime.now()

                jobs.append({
                    "id": apply_url.split("?")[0].split("/")[-1],
                    "title": title,
                    "company": company,
                    "location": location,
                    "description": "",  # fetched separately if needed
                    "apply_url": apply_url,
                    "posted_at": posted_at,
                    "posted_str": posted_str,
                    "salary_str": "",
                    "salary_min": None,
                    "salary_max": None,
                    "remote": self._is_remote(location),
                    "source": "linkedin_scrape"
                })
            except Exception:
                continue

        return jobs

    def _parse_posted_time(self, posted_str: str) -> datetime:
        """Convert various posted time strings to datetime."""
        now = datetime.now()
        if not posted_str:
            return now

        s = posted_str.lower().strip()
        try:
            # ISO format
            return datetime.fromisoformat(s)
        except ValueError:
            pass

        # "2 hours ago", "1 day ago", "3 days ago"
        if "hour" in s:
            n = int(''.join(filter(str.isdigit, s)) or "1")
            return now - timedelta(hours=n)
        elif "day" in s:
            n = int(''.join(filter(str.isdigit, s)) or "1")
            return now - timedelta(days=n)
        elif "week" in s:
            n = int(''.join(filter(str.isdigit, s)) or "1")
            return now - timedelta(weeks=n)
        elif "minute" in s:
            n = int(''.join(filter(str.isdigit, s)) or "1")
            return now - timedelta(minutes=n)
        elif "just now" in s or "moment" in s:
            return now
        return now

    def _extract_salary_min(self, salary_str: str) -> Optional[int]:
        """Extract minimum salary from string like '$130K - $160K' or '$145,000/yr'"""
        import re
        if not salary_str:
            return None
        nums = re.findall(r'[\$]?(\d[\d,\.]+)[kK]?', salary_str.replace(",", ""))
        if nums:
            val = float(nums[0])
            if val < 1000:
                val *= 1000  # it's in thousands (130K → 130000)
            return int(val)
        return None

    def _extract_salary_max(self, salary_str: str) -> Optional[int]:
        """Extract maximum salary from range string."""
        import re
        if not salary_str:
            return None
        nums = re.findall(r'[\$]?(\d[\d,\.]+)[kK]?', salary_str.replace(",", ""))
        if len(nums) >= 2:
            val = float(nums[1])
            if val < 1000:
                val *= 1000
            return int(val)
        elif len(nums) == 1:
            val = float(nums[0])
            if val < 1000:
                val *= 1000
            return int(val)
        return None

    def _is_remote(self, location: str) -> bool:
        loc = location.lower()
        return any(w in loc for w in ["remote", "anywhere", "distributed", "work from home", "wfh"])
