# Postprocessor Effect Report

## 1. Goal

Improve markdown readability and retrieval recall by fixing section heading rendering issues in converted PDF output.

## 2. Reported Problem

Examples observed before optimization:

- `Duplicate message suppression` rendered as plain paragraph text
- `References` rendered inline with body content, not as a heading

These issues reduce:

- Human readability of long converted papers
- Heading-based chunking quality
- Recall for section-scoped retrieval queries

## 3. Implemented Changes

### 3.1 Heading promotion logic

- Expanded heading detection for sentence-case title/header lines.
- Kept safeguards for lowercase sentence fragments to reduce false promotion.

### 3.2 Inline heading splitter

- Added a postprocessor that detects inline section-start patterns and rewrites them as headings.
- Example transformation:
  - input: `References 1. Bolt Beranek ...`
  - output:
    - `## References`
    - `1. Bolt Beranek ...`

### 3.3 Retrieval-aware chunk split improvement

- by_title chunking now splits on markdown heading markers (`#`, `##`, ...), not only raw element type `Title`.
- This allows postprocessed headings (for example inline-promoted `References`) to form chunk boundaries.

## 4. Validation Summary

Command used:

```bash
/root/agent/.venv/bin/python -m pytest -q pdf_trans/tests
```

Result:

- 13 passed

Real sample run:

- elements: 92
- chunks: 43

Confirmed headings in output markdown:

- `## Secure transmission of data`
- `## Duplicate message suppression`
- `## Conclusions`
- `## Acknowledgements`
- `## References`

## 5. Impact

### Readability

- Major sections are now visually separable in markdown.
- Document navigation and manual QA are easier.

### Retrieval

- Section boundaries are reflected in chunk segmentation.
- Heading-specific retrieval prompts (for example references, conclusions) have better chunk targeting.

## 6. Known Limitations

- Reference entries are still partly mixed between plain lines and list items.
- No dedicated bibliography schema yet.
- Some PDF extraction line-break noise remains in long paragraphs.

## 7. Recommended Next Iteration

- Add explicit section metadata in chunks (`section_title`, `section_type`).
- Add bibliography normalizer with deterministic formatting.
- Add benchmark script comparing heading coverage and retrieval hit quality before/after postprocessing.
