# 🎯 Bhavya's Agentic Job Pipeline

An end-to-end automated job hunting system that finds, filters, scores, tailors your resume, and preps your outreach — all from your terminal.

## What it does

```
Search Jobs → Filter → Score H-1B → Check Salary/Location/Age
     → Screen Description → Tailor Resume → Find LinkedIn Posters
          → Generate Outreach Message → Output Apply Package
```

### Step by step
| Step | What happens | Automated? |
|------|-------------|------------|
| 1. Search | Finds jobs matching your title on LinkedIn + Indeed via scraper | ✅ Full |
| 2. Location filter | Keeps Austin TX, Remote, or configurable list | ✅ Full |
| 3. Age filter | Drops anything posted > 48 hours ago | ✅ Full |
| 4. Salary filter | Keeps roles $120k+ (estimated if not listed) | ✅ Full |
| 5. H-1B check | Checks H1BData.info for filing history, drops weak sponsors | ✅ Full |
| 6. Sponsorship screen | Scans JD for "will not sponsor", "citizens only" etc | ✅ Full |
| 7. Resume tailoring | Claude rewrites your resume bullets to match JD keywords | ✅ Full |
| 8. ATS score | Scores tailored resume against JD before saving | ✅ Full |
| 9. LinkedIn hiring posts | Finds people posting "we're hiring" for this role/company | ✅ Full |
| 10. Outreach message | Claude drafts a personalised DM for each poster | ✅ Full |
| 11. Apply | Opens apply page in browser — you click submit (1 click) | 🖱️ You |
| 12. Send DM | Opens LinkedIn profile — you paste & send the drafted message | 🖱️ You |

## Setup

### 1. Clone & install
```bash
git clone https://github.com/YOUR_USERNAME/job-pipeline.git
cd job-pipeline
pip install -r requirements.txt
```

### 2. Add your credentials
```bash
cp .env.example .env
# Edit .env with your API keys
```

### 3. Add your resume
```bash
# Put your resume text in resume/base_resume.txt
# (plain text version of your resume)
```

### 4. Run
```bash
# Full pipeline
python src/pipeline.py

# Just search + filter (no resume tailoring)
python src/pipeline.py --mode search

# Just tailor resume for a specific JD
python src/pipeline.py --mode tailor --jd "path/to/jd.txt"

# Find LinkedIn hiring posters for a company
python src/pipeline.py --mode linkedin --company "Capital One"
```

## Output

Each run creates a folder in `output/YYYY-MM-DD/` containing:
```
output/
  2026-05-04/
    jobs_found.json          # all jobs after filtering
    Capital_One_Senior_AE/
      job_details.json       # full JD + scores
      resume_tailored.txt    # your resume edited for this JD
      ats_score.json         # ATS keyword match score
      linkedin_posters.json  # people posting about hiring
      outreach_drafts.txt    # Claude-drafted DMs for each poster
      apply_url.txt          # direct apply link
```

## Configuration (config.yaml)
```yaml
search:
  titles:
    - "Senior Analytics Engineer"
    - "Senior Data Engineer"
    - "Analytics Engineer"
  locations:
    - "Austin, TX"
    - "Remote"
  max_age_hours: 48
  min_salary: 120000

h1b:
  min_filings: 50          # minimum H-1B filings in past 3 years
  min_approval_rate: 0.85  # minimum approval rate

screening:
  reject_phrases:
    - "will not sponsor"
    - "sponsorship not available"
    - "us citizen only"
    - "no visa sponsorship"
    - "must be authorized"
    - "no opt"
    - "no cpt"
```

## API Keys needed
| Key | Where to get | Cost |
|-----|-------------|------|
| `ANTHROPIC_API_KEY` | console.anthropic.com | Pay per use (~$0.01/resume) |
| `RAPIDAPI_KEY` | rapidapi.com → LinkedIn Jobs API | Free tier: 100 calls/month |
| `SCRAPER_API_KEY` | scraperapi.com | Free tier: 1000 calls/month |

No LinkedIn login required. No risk of account ban.

## Privacy
- Nothing is submitted automatically
- Your resume stays local
- No data sent anywhere except Anthropic API (for tailoring) and ScraperAPI (for job search)
