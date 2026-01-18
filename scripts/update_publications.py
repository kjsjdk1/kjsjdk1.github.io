#!/usr/bin/env python3
"""
PubMed Publication Updater for Jong Seung Kim's Homepage
Fetches publications from PubMed, updates journal statistics and Impact Factors.
JCR IF data is maintained in a separate JSON file (manual update required).
"""

import requests
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from collections import defaultdict

# PubMed API configuration
PUBMED_SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_FETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# Search query for Jong Seung Kim at Jeonbuk (Otorhinolaryngology/Medical Informatics)
# Excludes chemistry-related papers from different Jong Seung Kim at Korea University
SEARCH_QUERY = "jong seung kim[Author] AND jeonbuk[Affiliation] NOT (calixarene OR perovskite OR diketopyrrolopyrrole OR fluorescent sensing)"


def load_jcr_data():
    """Load JCR Impact Factor data from JSON file."""
    jcr_path = Path(__file__).parent / "jcr_impact_factors.json"
    try:
        with open(jcr_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("journals", {})
    except Exception as e:
        print(f"Warning: Could not load JCR data: {e}")
        return {}


def get_pubmed_ids():
    """Get all PMID list from PubMed."""
    params = {
        "db": "pubmed",
        "term": SEARCH_QUERY,
        "retmode": "json",
        "retmax": 500  # Get up to 500 publications
    }

    try:
        response = requests.get(PUBMED_SEARCH_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        pmids = data.get("esearchresult", {}).get("idlist", [])
        count = int(data.get("esearchresult", {}).get("count", 0))
        print(f"Found {count} publications on PubMed, fetched {len(pmids)} PMIDs")
        return pmids, count
    except Exception as e:
        print(f"Error fetching PubMed IDs: {e}")
        return [], 0


def fetch_publication_details(pmids):
    """Fetch detailed publication information from PubMed."""
    if not pmids:
        return []

    publications = []

    # Fetch in batches of 100
    batch_size = 100
    for i in range(0, len(pmids), batch_size):
        batch = pmids[i:i+batch_size]

        fetch_params = {
            "db": "pubmed",
            "id": ",".join(batch),
            "retmode": "xml",
            "rettype": "abstract"
        }

        try:
            response = requests.get(PUBMED_FETCH_URL, params=fetch_params, timeout=60)
            response.raise_for_status()

            # Parse XML
            root = ET.fromstring(response.content)

            for article in root.findall('.//PubmedArticle'):
                pub_info = parse_article(article)
                if pub_info:
                    publications.append(pub_info)

        except Exception as e:
            print(f"Error fetching batch {i}-{i+batch_size}: {e}")
            continue

    print(f"Successfully parsed {len(publications)} publications")
    return publications


def parse_article(article):
    """Parse a single PubMed article XML element."""
    try:
        medline = article.find('.//MedlineCitation')
        if medline is None:
            return None

        pmid = medline.findtext('.//PMID', '')

        # Article title
        title = medline.findtext('.//ArticleTitle', '')

        # Journal info
        journal = medline.find('.//Journal')
        journal_title = ""
        journal_abbrev = ""
        pub_year = ""

        if journal is not None:
            journal_title = journal.findtext('.//Title', '')
            journal_abbrev = journal.findtext('.//ISOAbbreviation', '')

            # Publication date
            pub_date = journal.find('.//JournalIssue/PubDate')
            if pub_date is not None:
                pub_year = pub_date.findtext('Year', '')
                if not pub_year:
                    medline_date = pub_date.findtext('MedlineDate', '')
                    if medline_date:
                        # Extract year from MedlineDate (e.g., "2024 Jan-Feb")
                        year_match = re.search(r'(\d{4})', medline_date)
                        if year_match:
                            pub_year = year_match.group(1)

        return {
            'pmid': pmid,
            'title': title,
            'journal_title': journal_title,
            'journal_abbrev': journal_abbrev,
            'year': pub_year
        }

    except Exception as e:
        print(f"Error parsing article: {e}")
        return None


def normalize_journal_name(name):
    """Normalize journal name for matching with JCR data."""
    if not name:
        return ""
    # Remove punctuation and extra spaces, convert to lowercase
    normalized = re.sub(r'[^\w\s]', '', name.lower())
    normalized = ' '.join(normalized.split())
    return normalized


def match_journal_to_jcr(journal_abbrev, journal_title, jcr_data):
    """Match a journal to JCR data and return IF info."""
    # Try exact match first with abbreviation
    if journal_abbrev in jcr_data:
        return jcr_data[journal_abbrev]

    # Try normalized matching
    normalized_abbrev = normalize_journal_name(journal_abbrev)
    normalized_title = normalize_journal_name(journal_title)

    for jcr_key, jcr_info in jcr_data.items():
        jcr_normalized = normalize_journal_name(jcr_key)
        jcr_full_normalized = normalize_journal_name(jcr_info.get('full_name', ''))

        if (jcr_normalized == normalized_abbrev or
            jcr_normalized == normalized_title or
            jcr_full_normalized == normalized_abbrev or
            jcr_full_normalized == normalized_title):
            return jcr_info

    return None


def analyze_publications(publications, jcr_data):
    """Analyze publications and compute statistics."""
    journal_stats = defaultdict(lambda: {'count': 0, 'if': 0, 'quartile': '', 'years': []})
    year_stats = defaultdict(lambda: {'count': 0, 'total_if': 0})
    unmatched_journals = set()

    for pub in publications:
        journal_abbrev = pub.get('journal_abbrev', '')
        journal_title = pub.get('journal_title', '')
        year = pub.get('year', '')

        # Match to JCR
        jcr_match = match_journal_to_jcr(journal_abbrev, journal_title, jcr_data)

        # Use abbreviation as key, fallback to title
        journal_key = journal_abbrev if journal_abbrev else journal_title

        if jcr_match:
            journal_stats[journal_key]['if'] = jcr_match['if']
            journal_stats[journal_key]['quartile'] = jcr_match.get('quartile', '')
        else:
            if journal_key:
                unmatched_journals.add(journal_key)

        journal_stats[journal_key]['count'] += 1
        if year:
            journal_stats[journal_key]['years'].append(year)

        # Year statistics
        if year:
            year_stats[year]['count'] += 1
            if jcr_match:
                year_stats[year]['total_if'] += jcr_match['if']

    # Print unmatched journals for manual JCR update
    if unmatched_journals:
        print(f"\nUnmatched journals (need to add to jcr_impact_factors.json):")
        for j in sorted(unmatched_journals):
            print(f"  - {j}")

    return dict(journal_stats), dict(year_stats)


def update_html_stats(html_path, pub_count, journal_stats, year_stats):
    """Update publication statistics in HTML file."""
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()

        original_content = content

        # Update the stat-number for SCI Publications
        rounded_count = (pub_count // 10) * 10
        stat_text = f"{rounded_count}+"

        # Update "110+" stat to actual count
        pattern = r'(<div class="stat-number">)\d+\+?(</div>\s*<div class="stat-label">SCI Publications)'
        replacement = rf'\g<1>{stat_text}\g<2>'
        content = re.sub(pattern, replacement, content)

        # Update "With over X SCI-indexed publications" text
        pattern2 = r'With over \d+ SCI-indexed publications'
        replacement2 = f'With over {rounded_count} SCI-indexed publications'
        content = re.sub(pattern2, replacement2, content)

        # Calculate total IF
        total_if = sum(js.get('if', 0) * js.get('count', 0) for js in journal_stats.values())

        # Update Total IF stat
        pattern_if = r'(<div class="stat-number">)[\d.]+</div>\s*<div class="stat-label">Total Impact Factor'
        replacement_if = rf'\g<1>{total_if:.1f}</div>\n                    <div class="stat-label">Total Impact Factor'
        content = re.sub(pattern_if, replacement_if, content)

        # Update Total Publications in statistics section
        pattern_total = r'(<div class="stat-number">)\d+</div>\s*<div class="stat-label">Total Publications'
        replacement_total = rf'\g<1>{pub_count}</div>\n                    <div class="stat-label">Total Publications'
        content = re.sub(pattern_total, replacement_total, content)

        # Calculate average IF
        avg_if = total_if / pub_count if pub_count > 0 else 0
        pattern_avg = r'(<div class="stat-number">)[\d.]+</div>\s*<div class="stat-label">Average Impact Factor'
        replacement_avg = rf'\g<1>{avg_if:.2f}</div>\n                    <div class="stat-label">Average Impact Factor'
        content = re.sub(pattern_avg, replacement_avg, content)

        # Update number of different journals
        num_journals = len(journal_stats)
        pattern_journals = r'(<div class="stat-number">)\d+</div>\s*<div class="stat-label">Different Journals'
        replacement_journals = rf'\g<1>{num_journals}</div>\n                    <div class="stat-label">Different Journals'
        content = re.sub(pattern_journals, replacement_journals, content)

        # Update Total IF Sum
        pattern_if_sum = r'(<div class="stat-number">)[\d.]+</div>\s*<div class="stat-label">Total IF Sum'
        replacement_if_sum = rf'\g<1>{total_if:.1f}</div>\n                    <div class="stat-label">Total IF Sum'
        content = re.sub(pattern_if_sum, replacement_if_sum, content)

        # Update last updated date
        today = datetime.now().strftime("%B %Y")
        pattern_updated = r'Last updated: \w+ \d{4}'
        replacement_updated = f'Last updated: {today}'
        content = re.sub(pattern_updated, replacement_updated, content)

        if content != original_content:
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Updated HTML with publication count: {stat_text}, Total IF: {total_if:.1f}")
            return True
        else:
            print("No changes needed in HTML")
            return False

    except Exception as e:
        print(f"Error updating HTML: {e}")
        return False


def save_publication_data(pub_count, journal_stats, year_stats, publications):
    """Save detailed publication data to JSON file."""
    data_path = Path(__file__).parent.parent / "publication_data.json"

    # Sort journals by IF (descending)
    sorted_journals = sorted(
        journal_stats.items(),
        key=lambda x: (-x[1].get('if', 0), -x[1].get('count', 0))
    )

    data = {
        "last_updated": datetime.now().isoformat(),
        "total_publications": pub_count,
        "total_if": sum(js.get('if', 0) * js.get('count', 0) for js in journal_stats.values()),
        "journals": [
            {
                "name": name,
                "count": stats['count'],
                "impact_factor": stats.get('if', 0),
                "quartile": stats.get('quartile', ''),
                "years": sorted(set(stats.get('years', [])), reverse=True)
            }
            for name, stats in sorted_journals
        ],
        "by_year": [
            {
                "year": year,
                "count": stats['count'],
                "total_if": round(stats['total_if'], 1)
            }
            for year, stats in sorted(year_stats.items(), reverse=True)
        ],
        "recent_publications": publications[:20]  # Save 20 most recent
    }

    try:
        with open(data_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Saved publication data to {data_path}")
    except Exception as e:
        print(f"Error saving publication data: {e}")


def save_publication_log(pub_count, journal_stats):
    """Save publication update log."""
    log_path = Path(__file__).parent.parent / "publication_log.json"

    total_if = sum(js.get('if', 0) * js.get('count', 0) for js in journal_stats.values())

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "total_count": pub_count,
        "total_if": round(total_if, 1),
        "journal_count": len(journal_stats)
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

    # Load JCR Impact Factor data
    jcr_data = load_jcr_data()
    print(f"Loaded {len(jcr_data)} journals from JCR data")

    # Get publication IDs
    pmids, pub_count = get_pubmed_ids()
    if not pmids:
        print("Failed to get publication IDs, exiting")
        return False

    # Fetch detailed publication information
    publications = fetch_publication_details(pmids)

    # Analyze publications
    journal_stats, year_stats = analyze_publications(publications, jcr_data)

    # Print summary
    print(f"\n=== Summary ===")
    print(f"Total publications: {pub_count}")
    print(f"Unique journals: {len(journal_stats)}")
    total_if = sum(js.get('if', 0) * js.get('count', 0) for js in journal_stats.values())
    print(f"Total Impact Factor: {total_if:.1f}")

    # Top 10 journals by IF
    print(f"\nTop 10 Journals by IF:")
    sorted_by_if = sorted(journal_stats.items(), key=lambda x: -x[1].get('if', 0))[:10]
    for name, stats in sorted_by_if:
        print(f"  {name}: IF={stats.get('if', 0)}, Count={stats['count']}")

    # Update HTML file
    html_path = Path(__file__).parent.parent / "index.html"
    updated = update_html_stats(html_path, pub_count, journal_stats, year_stats)

    # Save detailed data
    save_publication_data(pub_count, journal_stats, year_stats, publications)

    # Save log
    save_publication_log(pub_count, journal_stats)

    print(f"\n=== Update complete ===")
    return updated


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
