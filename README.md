# Reference Compression

Python tool to aggressively compress BibTeX files in terrible formatting requirements that limit the number of bibliography pages. It reduces the footprint of your bibliography by stripping unnecessary fields, shortening author names, and abbreviating conference/journal venues using interactive fuzzy matching.

⚠️ **Warning:** This tool (including this README) was *vibecoded in 5 minutes*! Double check the compiled PDF references to make sure no critical information was overzealously stripped out. 

## Features

  - Option to retain ACM Reference Format required fields (like `doi`, `publisher`, `pages`, `volume`, etc.) via the `--strict-acm` flag.
- **Author Minimization**:
  - Automatically abbreviates first names (`Santosh Nagarakatte` → `S. Nagarakatte`). Toggleable via `--firstname-initials`.
  - Automatically truncates author lists to 1 author (`FirstAuthor and others`) by default. Override the count via `--keep-authors N`.
  - Disable minimization completely by using `--strict-acm` (unless explicitly overridden by the flags above).
- **Venue Abbreviation**: 
  - Can map standard journal/conference strings into tight acronyms via `--venues` (JSON map) or `--venues-bib` (`@string` definitions).
  - Interactive fuzzy matching powered by `thefuzz`: if a venue looks like an abbreviation target from your `venues.bib` file but isn't exact, the terminal will dynamically ask you if you want to replace it.
  - Generates a `fuzzy_cache.json` memory file so it remembers your "yes / always" decisions on future runs!

## Setup

```bash
pip install bibtexparser thefuzz
```

## Usage

Compress the file, using your `venues.bib` file (with `@string` acronym mappings) to guide the fuzzy finder:

```bash
python compress-bib.py your-references.bib --venues-bib venues.bib -o compressed.bib
```

### Advanced Usage

You can fine-tune the strictness and style rules:

```bash
# Keep up to 3 authors, force first-name initials, and avoid deleting ACM-required fields
python compress-bib.py your-references.bib \
    --strict-acm \
    --firstname-initials \
    --keep-authors 3 \
    -o compressed.bib
```

Arguments _after_ `--strict-acm` will override that flag. 
