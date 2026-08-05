# Reference Compression

Python tool to aggressively compress BibTeX files in terrible formatting requirements that limit the number of bibliography pages. It reduces the footprint of your bibliography by stripping unnecessary fields, shortening author names, and abbreviating conference/journal venues using interactive fuzzy matching.

⚠️ **Warning:** This tool (including this README) was *vibecoded in 5 minutes*! Double check the compiled PDF references to make sure no critical information was overzealously stripped out. 

## Features

- **Field Stripping**: drops fields like `abstract`, `keywords`, `url`, `doi`, `isbn`, `issn`, `month`, `address`, `location`, `publisher`, `numpages`, `issue_date`, `series`, `pages`, `volume`, `number`, `issue`, `articleno`, `editor`, `organization`.
  - Option to retain ACM Reference Format required fields (like `doi`, `publisher`, `pages`, `volume`, etc.) via the `--strict-acm` flag.
  - `--minimal` keeps *only* what a reader needs to find the paper again: **author, title, year, venue, and `url`/`doi`**. 
- **Author Minimization**:
  - Automatically abbreviates first names (`Santosh Nagarakatte` → `S. Nagarakatte`). Toggleable via `--firstname-initials`.
  - Automatically truncates author lists to 1 author (`FirstAuthor and others`) by default. Override the count via `--keep-authors N`.
  - Disable minimization completely by using `--strict-acm` (unless explicitly overridden by the flags above).
- **Venue Abbreviation**: 
  - Can map standard journal/conference strings into tight acronyms via `--venues` (JSON map) or `--venues-bib` (`@string` definitions).
  - Interactive fuzzy matching powered by `thefuzz`: if a venue looks like an abbreviation target from your `venues.bib` file but isn't exact, the terminal will dynamically ask you if you want to replace it.
  - Anything it *can't* map is handed back to you, so you can type the acronym yourself:
    ```
    [No Match]
    Original venue: 'Proceedings of the Thirteenth EuroSys Conference'
    Best effort:    'Proc. Thirteenth EuroSys Conference'
    Acronym? [type one / Enter to keep best effort / ! to stop asking] > EuroSys
    ```
    Acronyms you type are saved and are also fed back into the fuzzy matcher, so close matches
    ("*14th* EuroSys Conference") are offered your acronym right away. Press `!` to stop being asked
    for the rest of the run, or pass `--no-interactive` to never be asked at all.
  - Generates a `fuzzy_cache.json` memory file so it remembers decisions on future runs!

## Setup

```bash
pip install bibtexparser thefuzz
```

## Usage

Compress the file, optionally using a `venues.bib` file (with `@string` acronym mappings) to guide the fuzzy finder:

```bash
python3 compress-bib.py your-references.bib -o compressed.bib # --venues-bib venues.bib 
```

### Advanced Usage

You can fine-tune the strictness and style rules:

```bash
# Keep up to 3 authors, force first-name initials, and avoid deleting ACM-required fields
python3 compress-bib.py your-references.bib \
    --strict-acm \
    --firstname-initials \
    --keep-authors 3 \
    -o compressed.bib
```

Arguments _after_ `--strict-acm` will override that flag. 

### Options

| Flag | Meaning |
| --- | --- |
| `input` | Input `.bib` file. |
| `-o`, `--output` | Output `.bib` file. Defaults to `compressed_<input>`. |
| `-v`, `--venues` | JSON file of exact `{"full venue name": "ACRONYM"}` replacements. Checked before everything else. A trailing `  # comment` in a value is ignored, so you can annotate the map. |
| `--venues-bib` | An optional `.bib` file of `@string{acm-ccs = "..."}` definitions. The key becomes the acronym (`acm-ccs` → `ACM CCS`), the value is the venue name to match against. |
| `--fuzzy-cache` | Where to store your interactive decisions. Defaults to `fuzzy_cache.json`. |
| `--no-interactive` | Never prompt. Unmatched venues keep their best-effort shortening. |
| `--strict-acm` | Keep the fields the ACM Reference Format requires, and leave author lists alone. |
| `--minimal` | Keep only author, title, year, venue and `url`/`doi`; drop every other field. |
| `--firstname-initials` | Shorten first names to initials. |
| `--keep-authors N` | Keep `N` authors and replace the rest with `and others`. |
