#!/usr/bin/env python3
"""
PubMed Publication Updater for Jong Seung Kim's Homepage
Fetches publications from PubMed and updates the homepage statistics.
"""

import requests
import json
import re
from datetime import datetime
from pathlib import Path

# PubMed API configuration
PUBMED_SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_FETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# Search query for Jong Seung Kim at Jeonbuk
SEARCH_QUERY = "jong seung kim[Author] AND jeonbuk[Affiliation]"

def get_pubmed_count():
    """Get total publication count from PubMed."""
    params = {
        "db": "pubmed",
        "term": SEARCH_QUERY,
        "retmode": "json",
        "retmax": 0
    }

    try:
        response = requests.get(PUBMED_SEARCH_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        count = int(data.get("esearchresult", {}).get("count", 0))
        print(f"Found {count} publications on PubMed")
        return count
    except Exception as e:
        print(f"Error fetching PubMed data: {e}")
        return None

def get_recent_publications(max_results=10):
    """Get recent publications from PubMed."""
    # First, get the PMIDs
    search_params = {
        "db": "pubmed",
        "term": SEARCH_QUERY,
        "retmode": "json",
        "retmax": max_results,
        "sort": "date"
    }

    try:
        response = requests.get(PUBMED_SEARCH_URL, params=search_params, timeout=30)
        response.raise_for_status()
        data = response.json()
        pmids = data.get("esearchresult", {}).get("idlist", [])

        if not pmids:
            return []

        # Fetch details for these PMIDs
        fetch_params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
            "rettype": "abstract"
        }

        response = requests.get(PUBMED_FETCH_URL, params=fetch_params, timeout=30)
        response.raise_for_status()

        return pmids
    except Exception as e:
        print(f"Error fetching recent publications: {e}")
        return []

def update_html_stats(html_path, pub_count):
    """Update publication statistics in HTML file."""
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()

        original_content = content

        # Update the "110+" stat to actual count (rounded down to nearest 10)
        rounded_count = (pub_count // 10) * 10
        stat_text = f"{rounded_count}+"

        # Pattern to find and update SCI Publications stat
        # Looking for pattern like: <div class="stat-number">110+</div>
        pattern = r'(<div class="stat-number">)\d+\+?(</div>\s*<div class="stat-label">SCI Publications)'
        replacement = rf'\g<1>{stat_text}\g<2>'
        content = re.sub(pattern, replacement, content)

        # Also update the "With over X SCI-indexed publications" text
        pattern2 = r'With over \d+ SCI-indexed publications'
        replacement2 = f'With over {rounded_count} SCI-indexed publications'
        content = re.sub(pattern2, replacement2, content)

        if content != original_content:
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Updated HTML with publication count: {stat_text}")
            return True
        else:
            print("No changes needed in HTML")
            return False

    except Exception as e:
        print(f"Error updating HTML: {e}")
        return False

def save_publication_log(pub_count, pmids):
    """Save publication update log."""
    log_path = Path(__file__).parent.parent / "publication_log.json"

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "total_count": pub_count,
        "recent_pmids": pmids[:10] if pmids else []
    }

    try:
        if log_path.exists():
            with open(log_path, 'r', encoding='utf-8') as f:
                log_data = json.load(f)
        else:
            log_data = {"updates": []}

        log_data["updates"].append(log_entry)
        # Keep only last 100 entries
        log_data["updates"] = log_data["updates"][-100:]

        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)

        print(f"Saved publication log")
    except Exception as e:
        print(f"Error saving log: {e}")

def main():
    print(f"=== PubMed Publication Update - {datetime.now().isoformat()} ===")

    # Get publication count
    pub_count = get_pubmed_count()
    if pub_count is None:
        print("Failed to get publication count, exiting")
        return False

    # Get recent publications
    recent_pmids = get_recent_publications()

    # Update HTML file
    html_path = Path(__file__).parent.parent / "index.html"
    updated = update_html_stats(html_path, pub_count)

    # Save log
    save_publication_log(pub_count, recent_pmids)

    print(f"=== Update complete ===")
    return updated

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
