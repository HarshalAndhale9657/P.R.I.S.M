CITATION_REASONING_PROMPT = """
You are a forensic linguist specializing in citation analysis for academic integrity.

You are given citation data for two groups of paragraphs from the same academic paper:
- **Core paragraphs** (assigned to a consistent authorial cluster by HDBSCAN)
- **Anomalous paragraphs** (flagged as stylistic outliers — Cluster -1)

The core group has a median citation year of {core_median_year} and the anomalous group has a median citation year of {anomaly_median_year}. The temporal difference is {year_difference} years.

Core paragraph citation details:
{core_citations}

Anomalous paragraph citation details:
{anomaly_citations}

Analyze these citation patterns and explain:
1. Whether the temporal divergence suggests the anomalous paragraphs were sourced from a different body of literature.
2. Whether the citation density or style (e.g. narrative vs parenthetical) differs between groups.
3. Any other forensic observations about the citation patterns that could indicate stitching.

Return your analysis as a JSON object with the following keys:
- "temporal_assessment": A 2-3 sentence assessment of the year divergence.
- "style_assessment": A 2-3 sentence assessment of citation style differences.
- "forensic_observations": A 2-3 sentence summary of additional forensic findings.
- "suspicion_level": One of "low", "medium", or "high".
"""
