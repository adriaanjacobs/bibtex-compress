import argparse
import re
import sys
import os
import json
import bibtexparser
from bibtexparser.bwriter import BibTexWriter
from thefuzz import process, fuzz

def get_initial(name_part):
    name_part = name_part.lstrip(" '\"`")
    if not name_part:
        return ""
    # To handle LaTeX like {\'U} or \v{S}
    if name_part.startswith('{'):
        idx = name_part.find('}')
        if idx != -1:
            return name_part[:idx+1] + '.'
    if name_part.startswith('\\'):
        m = re.match(r'(\\[a-zA-Z]+\{[^}]*\})', name_part)
        if m:
            return m.group(1) + '.'
    
    # Otherwise find the first alphabetical character
    for c in name_part:
        if c.isalpha():
            return c.upper() + '.'
    return name_part[0].upper() + '.'

def shorten_author(author_name):
    # Handle "Last, First" or "Last, Jr, First"
    if ',' in author_name:
        parts = [p.strip() for p in author_name.split(',')]
        last = parts[0]
        first = parts[-1]
        first_initials = ' '.join(get_initial(p) for p in first.split() if p)
        return f"{first_initials} {last}".strip()
    else:
        parts = author_name.split()
        if len(parts) > 1:
            last = parts[-1]
            firsts = parts[:-1]
            first_initials = ' '.join(get_initial(f) for f in firsts if f)
            return f"{first_initials} {last}"
        return author_name

def compress_authors(author_str, firstname_initials=True, keep_authors=1):
    """
    Summarize author string to save space.
    e.g. 'A. B. Last and C. D. Second and E. F. Third' -> 'A. B. Last et al.'
    """
    # Clean up outer braces if any
    author_clean = author_str.replace('\n', ' ').strip('{}')
    authors = [a.strip() for a in author_clean.split(' and ')]
    
    if firstname_initials:
        authors = [shorten_author(a) for a in authors]
        
    if keep_authors is not None and len(authors) > keep_authors:
        return ' and '.join(authors[:keep_authors]) + ' and others'
    return ' and '.join(authors)

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

# Venues at most this long are assumed to be acronyms already, so we don't
# bother asking the user to shorten them ('PLDI', 'ACM CCS', 'USENIX Security', ...)
ABBREV_MAX_LEN = 20

def looks_abbreviated(venue):
    text = re.sub(r'[{}\\]', '', venue).strip()
    return len(text) <= ABBREV_MAX_LEN

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

# --minimal keeps only what a reader needs to identify and find the work again.
MINIMAL_FIELDS = {'author', 'title', 'year',
                  'doi', 'url', 'howpublished', 'eprint', 'eprinttype'}

# ...plus whatever field happens to name the venue for that kind of entry, so a
# @techreport keeps its institution and a @phdthesis keeps its school. Anything
# else (publisher, address, location, series, pages, ...) is dropped.
MINIMAL_VENUE_FIELDS = {
    'article': {'journal'},
    'inproceedings': {'booktitle'},
    'conference': {'booktitle'},
    'incollection': {'booktitle'},
    'inbook': {'booktitle'},
    'proceedings': {'booktitle'},
    'book': {'publisher'},
    'booklet': set(),
    'techreport': {'institution'},
    'phdthesis': {'school'},
    'mastersthesis': {'school'},
    'manual': {'organization'},
    # @misc has no venue field of its own, so a publisher there is the venue --
    # unlike on @inproceedings, where the booktitle already says where it appeared
    # and the publisher is just 'USENIX Association' taking up space.
    'misc': {'publisher'},
    'unpublished': set(),
}

# Entry types we don't know about keep any plausible venue field, so an unusual
# type never silently loses the only thing saying where it was published.
MINIMAL_VENUE_FALLBACK = {'journal', 'booktitle', 'institution', 'school',
                          'publisher', 'organization'}

def minimal_fields_for(entry_type):
    venue_fields = MINIMAL_VENUE_FIELDS.get(entry_type.lower(), MINIMAL_VENUE_FALLBACK)
    return MINIMAL_FIELDS | venue_fields

def remember(state, venue, abbrev, persist=False):
    """
    Remember a decision for the rest of this run, and optionally on disk.
    """
    state['decisions'][venue] = abbrev
    if persist:
        state['persistent'][venue] = abbrev
        if state['cache_file']:
            with open(state['cache_file'], 'w', encoding='utf-8') as f:
                json.dump(state['persistent'], f, indent=4)

def prompt(state, question):
    """
    Ask the user something, returning None if we cannot (or should not) prompt.
    """
    if not state['interactive']:
        return None
    try:
        return input(question).strip()
    except EOFError:
        # No one is listening (piped stdin): stop asking and take the defaults
        state['interactive'] = False
        return None

def fuzzy_match_and_ask(venue, known_venues, state):
    """
    Fuzzy match against known_venues {full_name: abbreviation}, confirming with
    the user. Returns None if nothing matched or the user rejected the match.
    """
    if not known_venues:
        return None # nothing to match against without --venues-bib

    if not state['interactive']:
        return None # a fuzzy match is only ever applied once confirmed

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
            ans = prompt(state, f"Replace with '{mapped_abbr}'? [y/n/a(lways)] > ")
            if ans is None:
                return None
            ans = ans.lower()
            if ans in ('y', 'a', 'yes', 'always'):
                # 'always' also survives future runs
                remember(state, venue, mapped_abbr, persist=ans in ('a', 'always'))
                return mapped_abbr
            elif ans in ('n', 'no'):
                return None
            else:
                print("Please answer 'y' (once), 'n' (no), or 'a' (always).")

    return None

def ask_for_abbreviation(venue, suggestion, state):
    """
    Last resort: we could not map this venue ourselves, so let the user type an
    acronym for it. Typed acronyms are remembered on disk for future runs.
    """
    print(f"\n[No Match]")
    print(f"Original venue: '{venue}'")
    if suggestion != venue:
        print(f"Best effort:    '{suggestion}'")

    ans = prompt(state, "Acronym? [type one / Enter to keep best effort / ! to stop asking] > ")
    if ans is None or ans == '!':
        if ans == '!':
            state['interactive'] = False
        return suggestion
    if not ans:
        # remember that we passed on this one so it doesn't ask again this run
        remember(state, venue, suggestion)
        return suggestion

    remember(state, venue, ans, persist=True)
    return ans

def resolve_venue(venue, venue_map, known_venues, state):
    """
    Map a booktitle/journal onto its acronym, asking the user when we can't.
    """
    # Custom exact replacements from --venues win over everything
    if venue in venue_map:
        return venue_map[venue]

    # Decisions from earlier runs, or from an earlier entry in this run
    if venue in state['decisions']:
        return state['decisions'][venue]

    # Exact hit in venues.bib (also covers the case where venues.bib changed)
    if venue in known_venues:
        return known_venues[venue]

    matched = fuzzy_match_and_ask(venue, known_venues, state)
    if matched is not None:
        return matched

    # Nothing matched. Anything already short is presumably an acronym already.
    if looks_abbreviated(venue):
        remember(state, venue, venue)
        return venue

    suggestion = compress_booktitle(venue)
    if not state['interactive']:
        return suggestion

    abbrev = ask_for_abbreviation(venue, suggestion, state)
    # Let later, similar venues fuzzy match against what the user just taught us
    if abbrev != venue and abbrev != suggestion:
        known_venues[venue] = abbrev
    return abbrev

def main():
    parser = argparse.ArgumentParser(description="Compress a BibTeX file for strict space constraints.")
    parser.add_argument("input", help="Input .bib file")
    parser.add_argument("-o", "--output", help="Output .bib file (default: compressed_<input>)", default=None)
    parser.add_argument("-v", "--venues", help="Custom JSON map of venues.", default=None)
    parser.add_argument("--venues-bib", help="venues.bib containing @string mappings", default=None)
    parser.add_argument("--fuzzy-cache", help="JSON file to store interactive fuzzy match memory", default="fuzzy_cache.json")
    parser.add_argument("--no-interactive", action="store_true", help="Never prompt; keep the best effort abbreviation for unmatched venues")
    parser.add_argument("--strict-acm", action="store_true", help="Ensure strict compliance with ACM Reference Format")
    parser.add_argument("--minimal", action="store_true", help="Keep only author, title, year, venue and url/doi; drop every other field")
    parser.add_argument("--firstname-initials", action="store_true", help="Use initials for first names")
    parser.add_argument("--keep-authors", type=int, default=None, help="Keep N authors and replace the rest with et al")
    args = parser.parse_args()

    firstname_initials = not args.strict_acm
    keep_authors = None if args.strict_acm else 1
    
    strict_acm_idx = max([i for i, arg in enumerate(sys.argv) if arg == '--strict-acm'], default=-1)
    fn_idx = max([i for i, arg in enumerate(sys.argv) if arg == '--firstname-initials'], default=-1)
    
    # Check if --keep-authors was passed (it could be passed as --keep-authors=2 or --keep-authors 2)
    ka_idx = max([i for i, arg in enumerate(sys.argv) if arg.startswith('--keep-authors')], default=-1)
    
    if strict_acm_idx != -1:
        if fn_idx != -1:
            firstname_initials = fn_idx > strict_acm_idx
        if ka_idx != -1 and ka_idx > strict_acm_idx:
            keep_authors = args.keep_authors
    else:
        if fn_idx != -1 or ka_idx != -1:
            firstname_initials = fn_idx != -1
            if ka_idx != -1:
                keep_authors = args.keep_authors
            else:
                keep_authors = None

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

    # 'persistent' is what ends up in the cache file, 'decisions' additionally
    # holds the venues we passed on, so we only get asked about them once a run.
    state = {
        'interactive': not args.no_interactive and sys.stdin.isatty(),
        'cache_file': args.fuzzy_cache,
        'persistent': fuzzy_cache,
        'decisions': dict(fuzzy_cache),
    }

    with open(input_file, 'r', encoding='utf-8') as f:
        bib_database = bibtexparser.load(f)
    
    # Fields to strip to save maximum space while keeping ACM compatibility
    # ACM technically requires some fields but for tight constraints, many are dropped.
    DROP_FIELDS = {'abstract', 'keywords', 'url', 'doi', 'isbn', 'issn', 
                   'month', 'address', 'location', 'publisher', 'numpages', 
                   'issue_date', 'series', 'pages', 'volume', 'number', 
                   'issue', 'articleno', 'editor', 'organization'}
                   
    if args.strict_acm:
        acm_required = {'doi', 'address', 'location', 'publisher', 'pages', 'articleno', 'volume', 'number', 'issue', 'numpages'}
        DROP_FIELDS = DROP_FIELDS - acm_required

    for entry in bib_database.entries:
        # Collect keys to remove. --minimal flips this around: instead of a list
        # of fields we know we don't want, we keep a list of the ones we do.
        if args.minimal:
            keep = minimal_fields_for(entry.get('ENTRYTYPE', ''))
            keys_to_remove = [k for k in entry
                              if k not in ('ENTRYTYPE', 'ID') and k.lower() not in keep]
        else:
            keys_to_remove = [k for k in entry if k.lower() in DROP_FIELDS]
        for k in keys_to_remove:
            del entry[k]
            
        # Compress fields if they exist
        if 'author' in entry:
            if firstname_initials or keep_authors is not None:
                entry['author'] = compress_authors(entry['author'], firstname_initials, keep_authors)
        
        # apply abbreviations:
        for field in ('booktitle', 'journal'):
            if field in entry:
                orig = entry[field].replace('\n', ' ')
                entry[field] = resolve_venue(orig, venue_map, venues_bib_mappings, state)

    # Write the modified database back using BibTexWriter
    writer = BibTexWriter()
    with open(output_file, 'w', encoding='utf-8') as f:
        bibtexparser.dump(bib_database, f, writer)
        
    print(f"Successfully compressed {len(bib_database.entries)} references.")
    print(f"Saved to {output_file}.")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        # Acronyms typed so far are already saved in the cache file
        print("\nAborted.")
        sys.exit(130)
