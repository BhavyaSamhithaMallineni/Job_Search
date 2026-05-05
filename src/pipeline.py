"""
pipeline.py
Main orchestrator for Bhavya's agentic job application pipeline.

Usage:
  python src/pipeline.py                          # full pipeline
  python src/pipeline.py --mode search            # search + filter only
  python src/pipeline.py --mode tailor --jd x.txt # tailor for one JD
  python src/pipeline.py --mode linkedin --company "Capital One"
"""

import os
import sys
import json
import yaml
import argparse
import webbrowser
from datetime import datetime
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from job_searcher import JobSearcher
from job_filter import JobFilter
from h1b_checker import H1BChecker
from resume_tailor import ResumeTailor
from linkedin_finder import LinkedInFinder

load_dotenv()
console = Console()


def load_config() -> dict:
    config_path = Path("config.yaml")
    if not config_path.exists():
        console.print("[red]config.yaml not found. Run from the project root.[/red]")
        sys.exit(1)
    with open(config_path) as f:
        return yaml.safe_load(f)


def check_env():
    """Check required environment variables."""
    issues = []
    if not os.getenv("ANTHROPIC_API_KEY"):
        issues.append("ANTHROPIC_API_KEY not set (resume tailoring will be skipped)")
    if not os.getenv("RAPIDAPI_KEY") and not os.getenv("SCRAPER_API_KEY"):
        issues.append("Neither RAPIDAPI_KEY nor SCRAPER_API_KEY set — cannot search jobs")
    return issues


def make_output_dir(base: str, job: dict) -> Path:
    date_str = datetime.now().strftime("%Y-%m-%d")
    company = job.get("company", "unknown").replace(" ", "_").replace("/", "-")
    title = job.get("title", "role").replace(" ", "_").replace("/", "-")[:30]
    dir_path = Path(base) / date_str / f"{company}_{title}"
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def run_full_pipeline(config: dict):
    """Run the complete end-to-end pipeline."""
    console.print(Panel.fit(
        "[bold cyan]Bhavya's Agentic Job Pipeline[/bold cyan]\n"
        "[dim]Search → Filter → H-1B Check → Tailor Resume → LinkedIn Outreach[/dim]",
        border_style="cyan"
    ))

    # ── STEP 1: Search ──────────────────────────────────────
    console.print("\n[bold]Step 1/5 — Searching for jobs[/bold]")
    searcher = JobSearcher(config)
    raw_jobs = searcher.search_all()

    # ── STEP 2: Filter ──────────────────────────────────────
    console.print("\n[bold]Step 2/5 — Filtering jobs[/bold]")
    filterer = JobFilter(config)
    filtered_jobs, filter_stats = filterer.filter_all(raw_jobs)
    filterer.print_stats(filter_stats)

    if not filtered_jobs:
        console.print("\n[yellow]No jobs passed filters. Try adjusting config.yaml (e.g., relax max_age_hours)[/yellow]")
        return

    # ── STEP 3: H-1B check ──────────────────────────────────
    console.print(f"\n[bold]Step 3/5 — Checking H-1B history for {len(filtered_jobs)} jobs[/bold]")
    h1b_checker = H1BChecker(config)

    qualified_jobs = []
    for job in filtered_jobs:
        result = h1b_checker.check(job["company"])
        job["h1b_result"] = result
        status = h1b_checker.format_result(result)
        console.print(f"  {job['company']}: {status}")

        if result["passes"]:
            qualified_jobs.append(job)
        else:
            console.print(f"  [dim]  → Skipping {job['company']} (weak H-1B history)[/dim]")

    if not qualified_jobs:
        console.print("\n[yellow]No jobs passed H-1B filter. The local database may not have these companies.[/yellow]")
        console.print("[dim]Tip: Manually verify unknown companies at h1bdata.info[/dim]")
        qualified_jobs = filtered_jobs  # fall through with all for review

    console.print(f"\n  [green]{len(qualified_jobs)} jobs passed all filters[/green]")

    # ── STEP 4: Resume tailoring + LinkedIn search ──────────
    console.print(f"\n[bold]Step 4/5 — Tailoring resume + finding LinkedIn posters[/bold]")

    tailor = ResumeTailor(config)
    linkedin = LinkedInFinder(config)

    apply_packages = []

    for i, job in enumerate(qualified_jobs, 1):
        console.print(f"\n  [{i}/{len(qualified_jobs)}] [bold]{job['title']}[/bold] @ {job['company']}")

        output_dir = make_output_dir(config["output"]["base_dir"], job)

        # Save full job details
        job_path = output_dir / "job_details.json"
        job_path.write_text(json.dumps({
            k: str(v) if not isinstance(v, (str, int, float, bool, list, dict, type(None))) else v
            for k, v in job.items()
        }, indent=2))

        # Tailor resume
        tailor_result = tailor.tailor(job)
        tailor.save(tailor_result, output_dir, job)

        # Save apply URL
        apply_url = job.get("apply_url", "")
        if apply_url:
            (output_dir / "apply_url.txt").write_text(
                f"Apply URL: {apply_url}\n\n"
                f"Instructions:\n"
                f"1. Open the URL above\n"
                f"2. Use the tailored resume in: resume_tailored.txt\n"
                f"3. You click submit — the pipeline does everything else\n"
            )

        # Find LinkedIn hiring posts
        posters = linkedin.find_hiring_posts(job["company"], job["title"])
        outreach_drafts = [linkedin.draft_outreach(p, job) for p in posters]
        linkedin.save(posters, outreach_drafts, output_dir, job)

        apply_packages.append({
            "job": job,
            "output_dir": str(output_dir),
            "ats_score": tailor_result["ats_after"]["score"],
            "apply_url": apply_url,
            "posters_found": len(posters)
        })

    # ── STEP 5: Summary + launch ────────────────────────────
    console.print(f"\n[bold]Step 5/5 — Your apply packages[/bold]")
    _print_summary(apply_packages)

    if config["output"].get("open_browser_on_complete"):
        for pkg in apply_packages[:3]:  # open top 3
            if pkg["apply_url"]:
                console.print(f"  [cyan]Opening:[/cyan] {pkg['apply_url']}")
                webbrowser.open(pkg["apply_url"])


def _print_summary(packages: list[dict]):
    """Print a formatted summary table of all apply packages."""
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("Company", style="bold")
    table.add_column("Role", max_width=28)
    table.add_column("ATS %", justify="center")
    table.add_column("LinkedIn posts", justify="center")
    table.add_column("Output folder")

    for pkg in packages:
        job = pkg["job"]
        ats = pkg["ats_score"]
        ats_str = f"[green]{ats}%[/green]" if ats >= 70 else f"[yellow]{ats}%[/yellow]"
        posts = str(pkg["posters_found"])
        folder = Path(pkg["output_dir"]).name

        table.add_row(
            job.get("company", "?"),
            job.get("title", "?"),
            ats_str,
            posts,
            folder
        )

    console.print(table)
    console.print(f"\n  [dim]All output saved to: output/[date]/[company_role]/[/dim]")
    console.print(f"  [dim]Each folder contains: resume_tailored.txt, ats_score.txt, linkedin_outreach.txt, apply_url.txt[/dim]")
    console.print(f"\n  [bold green]Your action:[/bold green] Open each apply_url.txt, use the tailored resume, and click submit.")
    console.print(f"  [bold green]For LinkedIn:[/bold green] Open linkedin_outreach.txt, copy the message, paste and send.\n")


def run_tailor_only(config: dict, jd_path: str):
    """Tailor resume for a single JD file."""
    jd_file = Path(jd_path)
    if not jd_file.exists():
        console.print(f"[red]JD file not found: {jd_path}[/red]")
        sys.exit(1)

    job = {"title": "Target Role", "company": "Target Company", "description": jd_file.read_text()}
    tailor = ResumeTailor(config)
    result = tailor.tailor(job)
    output_dir = Path("output") / "manual_tailor"
    tailor.save(result, output_dir, job)
    console.print(f"\n[green]Done! Check output/manual_tailor/[/green]")


def run_linkedin_only(config: dict, company: str):
    """Find LinkedIn hiring posts for a specific company."""
    finder = LinkedInFinder(config)
    job = {"company": company, "title": "Senior Analytics Engineer"}
    posters = finder.find_hiring_posts(company, "Senior Analytics Engineer")
    drafts = [finder.draft_outreach(p, job) for p in posters]
    output_dir = Path("output") / "linkedin_search"
    finder.save(posters, drafts, output_dir, job)
    console.print(f"\n[green]Done! Check output/linkedin_search/[/green]")


def main():
    parser = argparse.ArgumentParser(description="Bhavya's Job Pipeline")
    parser.add_argument("--mode", choices=["full", "search", "tailor", "linkedin"], default="full")
    parser.add_argument("--jd", help="Path to JD text file (for --mode tailor)")
    parser.add_argument("--company", help="Company name (for --mode linkedin)")
    args = parser.parse_args()

    config = load_config()

    # Warn about missing env vars
    issues = check_env()
    for issue in issues:
        console.print(f"[yellow]⚠ {issue}[/yellow]")

    if args.mode == "full":
        run_full_pipeline(config)
    elif args.mode == "search":
        searcher = JobSearcher(config)
        filterer = JobFilter(config)
        jobs = searcher.search_all()
        passed, stats = filterer.filter_all(jobs)
        filterer.print_stats(stats)
        console.print(json.dumps(passed[:5], indent=2, default=str))
    elif args.mode == "tailor":
        if not args.jd:
            console.print("[red]--jd required for tailor mode[/red]")
            sys.exit(1)
        run_tailor_only(config, args.jd)
    elif args.mode == "linkedin":
        if not args.company:
            console.print("[red]--company required for linkedin mode[/red]")
            sys.exit(1)
        run_linkedin_only(config, args.company)


if __name__ == "__main__":
    main()
