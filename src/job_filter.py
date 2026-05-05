"""
job_filter.py
Filters job listings based on:
- Posted within 48 hours
- Salary >= $120k (or estimated if not listed)
- Location: Austin TX, Remote, or configured list
- No "will not sponsor" language in description
"""

from datetime import datetime, timedelta
from rich.console import Console

console = Console()


class JobFilter:
    def __init__(self, config: dict):
        self.config = config
        self.max_age_hours = config["search"].get("max_age_hours", 48)
        self.min_salary = config["search"].get("min_salary", 120000)
        self.locations = [l.lower() for l in config["search"].get("locations", [])]
        self.reject_phrases = [p.lower() for p in config["screening"].get("reject_phrases", [])]

        # Salary estimates by title when not listed (conservative estimates)
        self.salary_estimates = {
            "senior analytics engineer": 145000,
            "senior data engineer": 148000,
            "staff data engineer": 165000,
            "analytics engineer": 130000,
            "data engineer": 125000,
            "analytics engineering manager": 170000,
            "machine learning engineer": 155000,
            "data scientist": 135000,
        }

    def filter_all(self, jobs: list[dict]) -> tuple[list[dict], dict]:
        """
        Filter jobs through all criteria.
        Returns (passing_jobs, rejection_stats)
        """
        stats = {
            "total": len(jobs),
            "too_old": 0,
            "low_salary": 0,
            "wrong_location": 0,
            "no_sponsorship_phrase": 0,
            "passed": 0
        }

        passed = []

        for job in jobs:
            # 1. Age check
            if not self._check_age(job):
                stats["too_old"] += 1
                continue

            # 2. Location check
            if not self._check_location(job):
                stats["wrong_location"] += 1
                continue

            # 3. Salary check
            if not self._check_salary(job):
                stats["low_salary"] += 1
                continue

            # 4. Description screening
            rejection_phrase = self._check_description(job)
            if rejection_phrase:
                stats["no_sponsorship_phrase"] += 1
                console.print(f"  [red]✗ REJECTED:[/red] {job['company']} — contains '{rejection_phrase}'")
                continue

            stats["passed"] += 1
            passed.append(job)

        return passed, stats

    def _check_age(self, job: dict) -> bool:
        """Check if job was posted within max_age_hours."""
        posted_at = job.get("posted_at")
        if not posted_at:
            return True  # assume recent if unknown

        if isinstance(posted_at, str):
            try:
                posted_at = datetime.fromisoformat(posted_at)
            except ValueError:
                return True

        cutoff = datetime.now() - timedelta(hours=self.max_age_hours)
        return posted_at >= cutoff

    def _check_location(self, job: dict) -> bool:
        """Check if job location matches configured locations."""
        job_location = job.get("location", "").lower()

        # Always pass remote
        if job.get("remote") or "remote" in job_location:
            return True

        # Check against configured location list
        for allowed in self.locations:
            if allowed in job_location or job_location in allowed:
                return True

        # US-wide passes (could be remote not labeled)
        if job_location in ["united states", "us", "usa", "anywhere in us"]:
            return True

        return False

    def _check_salary(self, job: dict) -> bool:
        """Check if salary meets minimum. Estimates if not listed."""
        # If explicitly listed
        salary_max = job.get("salary_max")
        salary_min = job.get("salary_min")

        if salary_max and salary_max >= self.min_salary:
            return True
        if salary_min and salary_min >= self.min_salary:
            return True

        # Both listed but both low
        if salary_max and salary_max < self.min_salary * 0.85:
            return False

        # Not listed — estimate from title
        title = job.get("title", "").lower()
        for title_key, estimated_salary in self.salary_estimates.items():
            if title_key in title:
                job["salary_estimated"] = estimated_salary
                job["salary_note"] = f"Salary not listed — estimated ${estimated_salary:,} for '{title_key}'"
                return estimated_salary >= self.min_salary

        # Unknown title — assume it passes (better to over-include)
        job["salary_estimated"] = 130000
        job["salary_note"] = "Salary not listed — included for manual review"
        return True

    def _check_description(self, job: dict) -> str | None:
        """
        Scan job description for phrases indicating no sponsorship.
        Returns the offending phrase if found, None if clean.
        """
        description = (job.get("description") or "").lower()
        title_desc = (job.get("title") or "").lower() + " " + description

        for phrase in self.reject_phrases:
            if phrase in title_desc:
                return phrase

        return None

    def print_stats(self, stats: dict):
        """Print filter stats summary."""
        console.print(f"\n  [bold]Filter results:[/bold]")
        console.print(f"    Total found:          {stats['total']}")
        console.print(f"    [red]Too old (>48h):[/red]       {stats['too_old']}")
        console.print(f"    [red]Wrong location:[/red]       {stats['wrong_location']}")
        console.print(f"    [red]Salary too low:[/red]       {stats['low_salary']}")
        console.print(f"    [red]No sponsorship:[/red]       {stats['no_sponsorship_phrase']}")
        console.print(f"    [green]Passed filters:[/green]       {stats['passed']}")
