# Reference Compression

Python tool to aggressively compress BibTeX files in terrible formatting requirements that limit the number of bibliography pages. It reduces the footprint of your bibliography by stripping unnecessary fields, shortening author names, and abbreviating conference/journal venues using interactive fuzzy matching.

⚠️ **Warning:** This tool (including this README) was *vibecoded in 5 minutes*! Double check the compiled PDF references to make sure no critical information was overzealously stripped out. 

## Features

- **Field Stripping**: Deletes space-consuming, non-essential fields (`pages`, `volume`, `number`, `url`, `doi`, `isbn`, `issn`, `abstract`, `address`, `publisher`, `month`, etc.).
- **Author Minimization**: 
  - Automatically abbreviates first names (`Santosh Nagarakatte` → `S. Nagarakatte`).
  - Automatically truncates papers with more than 2 authors to `FirstAuthor and others`.
- **Venue Abbreviation**: 
  - Can map standard journal/conference strings into tight acronyms.
  - Interactive fuzzy matching powered by `thefuzz`: if a venue looks like an abbreviation target from your `venues.bib` file but isn't exact, the terminal will dynamically ask you if you want to replace it.
  - Generates a `fuzzy_cache.json` memory file so it remembers your "yes / always" decisions on future runs!

## Setup

```bash
pip install bibtexparser thefuzz
```

## Usage

Compress the file, using your `venues.bib` file (with `@string` acronym mappings) to guide the fuzzy finder.

```bash
python compress-bib.py your-references.bib --venues-bib venues.bib -o compressed.bib
```

Whenever it spots a near-match, it will prompt you. If you choose `a` (always), it saves the rule to `fuzzy_cache.json`.
