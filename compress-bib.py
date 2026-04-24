import argparse
import re
import sys
import os
import json
import bibtexparser
from bibtexparser.bwriter import BibTexWriter
try:
    from thefuzz import process, fuzz
except ImportError:
    process = None
    fuzz = None

def shorten_author(author_name):
    # Handle "Last, First" or "Last, Jr, First"
    if ',' in author_name:
        parts = [p.strip() for p in author_name.split(',')]
        last = parts[0]
        first = parts[-1]
        first_initials = ' '.join(p[0].upper() + '.' for p in first.split() if p)
        return f"{first_initials} {last}".strip()
    else:
        parts = author_name.split()
        if len(parts) > 1:
            last = parts[-1]
            firsts = parts[:-1]
            first_initials = ' '.join(f[0].upper() + '.' for f in firsts if f)
            return f"{first_initials} {last}"
        return author_name

def compress_authors(author_str):
    """
    Summarize author string to save space.
    e.g. 'A. B. Last and C. D. Second and E. F. Third' -> 'A. B. Last et al.'
    """
    # Clean up outer braces if any
    author_clean = author_str.replace('\n', ' ').strip('{}')
    authors = [a.strip() for a in author_clean.split(' and ')]
    
    if len(authors) > 2:
        first_author = shorten_author(authors[0])
        return first_author + ' and others'
    return ' and '.join(shorten_author(a) for a in authors)

def compress_booktitle(title_str):
    """
    Shorten proceedings/journals to acronyms if possible to save space.
    """
    t = title_str.replace('\n', ' ')
    t = re.sub(r'Proceedings of the\s+', 'Proc. ', t, flags=re.IGNORECASE)
    t = re.sub(r'Conference on\s+', 'Conf. ', t, flags=re.IGNORECASE)
    t = re.sub(r'Symposium on\s+', 'Symp. ', t, flags=re.IGNORECASE)
    t = re.sub(r'International\s+', 'Intl. ', t, flags=re.IGNORECASE)
    return t

def format_venue_abbr(abbrev):
    # e.g., 'acm-ccs' -> 'ACM CCS'
    # e.g., 'USENIX-Security' -> 'USENIX Security'
    parts = abbrev.split('-')
    formatted_parts = []
    for p in parts:
        if p.islower():
            formatted_parts.append(p.upper())
        else:
            formatted_parts.append(p)
    return ' '.join(formatted_parts)

def load_venue_strings(venues_bib_path):
    if not venues_bib_path or not os.path.exists(venues_bib_path):
        return {}
    
    # We parse manually instead of using bibtexparser.load for values 
    # because bibtexparser arbitrarily lowercases all @string keys!
    mapping = {}
    
    # We ignore standard bibtex months and common short words that often cause false positive fuzzy matches
    IGNORE_STRINGS = {
        'jan', 'feb', 'mar', 'apr', 'may', 'jun', 
        'jul', 'aug', 'sep', 'oct', 'nov', 'dec',
        'january', 'february', 'march', 'april', 'may', 'june',
        'july', 'august', 'september', 'october', 'november', 'december'
    }
    
    with open(venues_bib_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    string_pattern = re.compile(r'@string\s*\{\s*([^=\s]+)\s*=\s*(["{])(.*?)\2\s*\}', re.IGNORECASE | re.DOTALL)
    for match in string_pattern.finditer(content):
        key = match.group(1)
        val = match.group(3)
        
        if key.lower() in IGNORE_STRINGS or val.lower() in IGNORE_STRINGS:
            continue
        mapping[val] = format_venue_abbr(key)
        
    return mapping

def fuzzy_match_and_ask(venue, known_venues, saved_mappings, saved_mappings_file):
    # known_venues is a dict: {full_name: abbreviation}
    # saved_mappings is a dict: {exact_venue_in_bib: abbreviation}
    # check exact match first:
    if venue in saved_mappings:
        return saved_mappings[venue]

    if not process:
        return venue # gracefully degrade if thefuzz is not installed

    # see if any known_venues perfectly match (in case `venues.bib` changed):
    if venue in known_venues:
        return known_venues[venue]

    # Clean the venue string a bit to avoid fuzzy matching on years/dates/cities
    # e.g., 'Proceedings of the 12th USENIX...' -> 'Proceedings of the USENIX...'
    clean_venue = re.sub(r'\b(19|20)\d{2}\b', '', venue)  # remove years
    clean_venue = re.sub(r'\d+(st|nd|rd|th)\b', '', clean_venue) # remove 12th, 1st
    
    # else fuzzy match against known_venues keys
    best_match, score = process.extractOne(clean_venue, list(known_venues.keys()), scorer=fuzz.token_set_ratio)
    
    if score > 80: # configurable threshold
        mapped_abbr = known_venues[best_match]
        print(f"\n[Fuzzy Match]")
        print(f"Original venue: '{venue}'")
        print(f"Matched with:   '{best_match}' (score: {score})")
        
        while True:
            ans = input(f"Replace with '{mapped_abbr}'? [y/n/a(lways)] > ").strip().lower()
            if ans in ('y', 'a', 'yes', 'always'):
                if ans in ('a', 'always'):
                    # Save it for future queries
                    saved_mappings[venue] = mapped_abbr
                    with open(saved_mappings_file, 'w', encoding='utf-8') as f:
                        json.dump(saved_mappings, f, indent=4)
                return mapped_abbr
            elif ans in ('n', 'no'):
                # remember that we said 'no' so it doesn't ask again this run
                saved_mappings[venue] = venue
                return venue
    
    return venue

def main():
    parser = argparse.ArgumentParser(description="Compress a BibTeX file for strict space constraints.")
    parser.add_argument("input", help="Input .bib file")
    parser.add_argument("-o", "--output", help="Output .bib file (default: compressed_<input>)", default=None)
    parser.add_argument("-v", "--venues", help="Custom JSON map of venues.", default=None)
    parser.add_argument("--venues-bib", help="venues.bib containing @string mappings", default=None)
    parser.add_argument("--fuzzy-cache", help="JSON file to store interactive fuzzy match memory", default="fuzzy_cache.json")
    args = parser.parse_args()

    input_file = args.input
    output_file = args.output if args.output else f"compressed_{input_file}"

    venue_map = {}
    if args.venues:
        with open(args.venues, 'r', encoding='utf-8') as f:
            raw_map = json.load(f)
            # Remove the " # Appears N times" comment from unedited values
            for k, v in raw_map.items():
                venue_map[k] = v.split("  #")[0].strip()

    venues_bib_mappings = load_venue_strings(args.venues_bib)
    
    fuzzy_cache = {}
    if os.path.exists(args.fuzzy_cache):
        with open(args.fuzzy_cache, 'r', encoding='utf-8') as f:
            fuzzy_cache = json.load(f)

    with open(input_file, 'r', encoding='utf-8') as f:
        bib_database = bibtexparser.load(f)
    
    # Fields to strip to save maximum space while keeping ACM compatibility
    # ACM technically requires some fields but for tight constraints, many are dropped.
    DROP_FIELDS = {'abstract', 'keywords', 'url', 'doi', 'isbn', 'issn', 
                   'month', 'address', 'location', 'publisher', 'numpages', 
                   'issue_date', 'series', 'pages', 'volume', 'number', 
                   'issue', 'articleno', 'editor', 'organization'}
                   
    for entry in bib_database.entries:
        # Collect keys to remove
        keys_to_remove = [k for k in entry if k.lower() in DROP_FIELDS]
        for k in keys_to_remove:
            del entry[k]
            
        # Compress fields if they exist
        if 'author' in entry:
            entry['author'] = compress_authors(entry['author'])
        
        # apply abbreviations:
        for field in ('booktitle', 'journal'):
            if field in entry:
                orig = entry[field].replace('\n', ' ')
                
                # Check custom exact replacements first
                if orig in venue_map:
                    entry[field] = venue_map[orig]
                elif orig in fuzzy_cache:
                    entry[field] = fuzzy_cache[orig]
                # Then fuzzy process:
                elif len(venues_bib_mappings) > 0:
                    entry[field] = fuzzy_match_and_ask(orig, venues_bib_mappings, fuzzy_cache, args.fuzzy_cache)
                else:
                    entry[field] = compress_booktitle(orig)

    # Write the modified database back using BibTexWriter
    writer = BibTexWriter()
    with open(output_file, 'w', encoding='utf-8') as f:
        bibtexparser.dump(bib_database, f, writer)
        
    print(f"Successfully compressed {len(bib_database.entries)} references.")
    print(f"Saved to {output_file}.")

if __name__ == '__main__':
    main()
