"""
P.R.I.S.M. — Citation Forensics Engine

Deterministic citation extraction and temporal anomaly detection.
Uses battle-tested regex patterns to extract APA/MLA/Harvard inline
citations, then performs statistical temporal analysis to flag paragraphs
whose citation year distributions diverge from the document baseline.

Pipeline:
  1. Regex extraction of inline citations per paragraph
  2. Year parsing → median citation year per paragraph (temporal anchor)
  3. Core cluster baseline vs noise cluster comparison
  4. Flag if |median_core - median_noise| > threshold (default 10 years)

Zero API calls — fully deterministic. GPT reasoning is optional overlay.
"""

import re
import logging
import statistics
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter

from models import PipelineContext, WarningCode, WarningSeverity

logger = logging.getLogger(__name__)


# ─── Citation Regex Patterns ─────────────────────────────────────────────────
# Battle-tested regex for APA/MLA/Harvard inline citations.
# Matches patterns like:
#   (Smith, 2019)
#   (Smith & Jones, 2020)
#   (Smith et al., 2018)
#   (Smith, 2019; Jones, 2020)
#   Smith (2019)
#   Smith and Jones (2020)

# Pattern 1: Parenthetical citations — (Author, Year) or (Author & Author, Year)
PARENTHETICAL_REGEX = re.compile(
    r'\('
    r'(?:[A-Z][A-Za-z\'\u2019`\-]+)'                       # First author surname
    r'(?:\s+(?:and|&)\s+[A-Z][A-Za-z\'\u2019`\-]+)?'        # Optional second author
    r'(?:\s+et\s+al\.?)?'                                    # Optional et al.
    r'(?:\s*,\s*(?:19|20)\d{2})'                             # , Year
    r'(?:\s*;\s*'                                             # Optional semicolon for multi-citations
    r'(?:[A-Z][A-Za-z\'\u2019`\-]+)'
    r'(?:\s+(?:and|&)\s+[A-Z][A-Za-z\'\u2019`\-]+)?'
    r'(?:\s+et\s+al\.?)?'
    r'(?:\s*,\s*(?:19|20)\d{2}))*'                           # Repeat for chained citations
    r'\)',
    re.UNICODE
)

# Pattern 2: Narrative citations — Author (Year) or Author and Author (Year)
NARRATIVE_REGEX = re.compile(
    r'(?<![(\w])'                                             # Not preceded by ( or word char
    r'(?:[A-Z][A-Za-z\'\u2019`\-]+)'                         # Author surname
    r'(?:\s+(?:and|&)\s+[A-Z][A-Za-z\'\u2019`\-]+)?'        # Optional second author
    r'(?:\s+et\s+al\.?)?'                                    # Optional et al.
    r'\s*\((?:19|20)\d{2}\)',                                 # (Year)
    re.UNICODE
)

# Pattern 3: Simple year extraction from any citation match
YEAR_REGEX = re.compile(r'(?:19|20)\d{2}')

# Pattern 4: IEEE-style numerical bracket citations — [1], [1, 2], [1]-[3]
IEEE_REGEX = re.compile(r'\[\s*\d+\s*(?:(?:,|-|–|—)\s*\d+\s*)*\](?:(?:\s*,\s*|(?:\s*(?:-|–|—)\s*))\[\s*\d+\s*(?:(?:,|-|–|—)\s*\d+\s*)*\])*', re.UNICODE)

# Words that look like author names but aren't — filter these out
FALSE_POSITIVE_WORDS = {
    'although', 'also', 'however', 'therefore', 'furthermore',
    'moreover', 'nevertheless', 'consequently', 'subsequently',
    'additionally', 'according', 'based', 'compared', 'during',
    'including', 'following', 'regarding', 'within', 'between',
    'through', 'after', 'before', 'since', 'until', 'while',
    'table', 'figure', 'section', 'chapter', 'appendix',
    'equation', 'page', 'volume', 'issue', 'part',
}


class CitationForensics:
    """
    Extracts inline citations from paragraphs using deterministic regex,
    computes temporal anchors (median citation year per paragraph), and
    detects temporal anomalies by comparing noise cluster paragraphs
    against the core cluster baseline.
    """

    def __init__(self, temporal_threshold: int = 10):
        """
        Args:
            temporal_threshold: Year difference above which a paragraph's
                                citation era is flagged as anomalous.
                                Default: 10 years.
        """
        self.temporal_threshold = temporal_threshold

    # ─── Public API ──────────────────────────────────────────────────────────

    def analyze(
        self,
        paragraphs: List[Dict[str, Any]],
        references: List[Dict[str, Any]],
        cluster_result: Dict[str, Any],
        ctx: Optional[PipelineContext] = None,
    ) -> Dict[str, Any]:
        """
        Run the full citation forensics pipeline.

        Args:
            paragraphs: List of paragraph dicts with "text" key.
            references: Bibliography entries from PDF parser.
            cluster_result: Output from AuthorshipClustering.cluster().
            ctx: Optional PipelineContext for warning accumulation.

        Returns:
            Dict with per-paragraph citations, temporal anchors,
            anomaly flags, and aggregate statistics.
        """
        if ctx is None:
            ctx = PipelineContext()

        clusters = cluster_result.get("clusters", [])
        anomaly_indices = cluster_result.get("anomaly_indices", [])

        # ── Step 1: Extract citations per paragraph ──────────────────────────
        per_paragraph = []
        all_years = []
        bib_map = self._build_bib_map(references)

        for i, para in enumerate(paragraphs):
            text = para.get("text", "")
            citations = self._extract_citations(text)
            years = self._extract_years(citations, bib_map)
            all_years.extend(years)

            median_year = (
                round(statistics.median(years)) if years else None
            )

            per_paragraph.append({
                "paragraph_index": i,
                "citations": citations,
                "citation_count": len(citations),
                "years": years,
                "median_year": median_year,
                "cluster_id": clusters[i] if i < len(clusters) else 0,
            })

        # ── Step 2: Compute core vs noise temporal baselines ─────────────────
        core_years = []
        noise_years = []

        for entry in per_paragraph:
            if entry["cluster_id"] == -1:
                noise_years.extend(entry["years"])
            else:
                core_years.extend(entry["years"])

        core_median = (
            round(statistics.median(core_years)) if core_years else None
        )
        noise_median = (
            round(statistics.median(noise_years)) if noise_years else None
        )

        # ── Step 3: Detect temporal anomalies ────────────────────────────────
        temporal_anomalies = []

        if core_median is not None:
            for entry in per_paragraph:
                if entry["median_year"] is not None:
                    diff = abs(entry["median_year"] - core_median)
                    if diff > self.temporal_threshold:
                        temporal_anomalies.append({
                            "paragraph_index": entry["paragraph_index"],
                            "paragraph_median_year": entry["median_year"],
                            "core_baseline_year": core_median,
                            "year_difference": diff,
                            "cluster_id": entry["cluster_id"],
                            "is_noise_cluster": entry["cluster_id"] == -1,
                            "severity": self._severity(diff),
                        })

        # ── Step 4: Citation density analysis ────────────────────────────────
        core_densities = []
        noise_densities = []

        for entry in per_paragraph:
            text = paragraphs[entry["paragraph_index"]].get("text", "")
            word_count = len(text.split())
            density = (
                entry["citation_count"] / max(word_count, 1)
            ) * 100  # citations per 100 words

            entry["citation_density"] = round(density, 4)

            if entry["cluster_id"] == -1:
                noise_densities.append(density)
            else:
                core_densities.append(density)

        avg_core_density = (
            round(statistics.mean(core_densities), 4)
            if core_densities else 0.0
        )
        avg_noise_density = (
            round(statistics.mean(noise_densities), 4)
            if noise_densities else 0.0
        )

        # ── Step 5: Reference cross-check ────────────────────────────────────
        # Extract years from bibliography for comparison
        bib_years = self._extract_bibliography_years(references)
        bib_median = (
            round(statistics.median(bib_years)) if bib_years else None
        )

        # ── Build result ─────────────────────────────────────────────────────
        year_difference = (
            abs(core_median - noise_median)
            if core_median is not None and noise_median is not None
            else None
        )

        result = {
            "per_paragraph": per_paragraph,
            "total_citations_found": sum(
                e["citation_count"] for e in per_paragraph
            ),
            "unique_years": sorted(set(all_years)),
            "temporal_baseline": {
                "core_median_year": core_median,
                "noise_median_year": noise_median,
                "year_difference": year_difference,
                "threshold": self.temporal_threshold,
                "is_anomalous": (
                    year_difference is not None
                    and year_difference > self.temporal_threshold
                ),
            },
            "temporal_anomalies": temporal_anomalies,
            "temporal_anomaly_count": len(temporal_anomalies),
            "density_analysis": {
                "avg_core_density": avg_core_density,
                "avg_noise_density": avg_noise_density,
                "density_ratio": (
                    round(avg_noise_density / max(avg_core_density, 0.001), 2)
                    if avg_core_density > 0 else None
                ),
            },
            "bibliography": {
                "total_references": len(references),
                "bibliography_median_year": bib_median,
                "bibliography_years": bib_years,
            },
        }

        logger.info(
            f"[P.R.I.S.M.] Citation forensics complete: "
            f"{result['total_citations_found']} citations found, "
            f"{len(temporal_anomalies)} temporal anomalies flagged, "
            f"core median={core_median}, noise median={noise_median}"
        )

        # ── Edge Case: No citations found ────────────────────────────────────
        if result["total_citations_found"] == 0:
            ctx.add_warning(
                WarningCode.CITATION_NONE_FOUND, WarningSeverity.INFO, "citation_forensics",
                "No inline citations were detected in this document. "
                "Temporal analysis could not be performed. This is normal "
                "for non-academic documents or documents with footnote-style citations.",
            )

        # ── Edge Case: Citations found but no parseable years ────────────────
        elif not all_years:
            ctx.add_warning(
                WarningCode.CITATION_NO_YEARS, WarningSeverity.INFO, "citation_forensics",
                "Citations were detected but no valid years could be extracted. "
                "Temporal anomaly analysis was skipped.",
                {"citation_count": result["total_citations_found"]},
            )

        return result

    def extract_inline_citations(
        self, paragraphs: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Standalone citation extraction (no cluster analysis).
        Returns per-paragraph citation data.
        """
        results = []
        for i, para in enumerate(paragraphs):
            text = para.get("text", "")
            citations = self._extract_citations(text)
            years = self._extract_years(citations)
            results.append({
                "paragraph_index": i,
                "citations": citations,
                "citation_count": len(citations),
                "years": years,
                "median_year": (
                    round(statistics.median(years)) if years else None
                ),
            })
        return results

    def calculate_temporal_anchors(
        self, paragraphs: List[Dict[str, Any]]
    ) -> List[Optional[int]]:
        """
        Calculate median citation year per paragraph.

        Returns:
            List of median years (None if no citations in paragraph).
        """
        anchors = []
        for para in paragraphs:
            text = para.get("text", "")
            citations = self._extract_citations(text)
            years = self._extract_years(citations)
            anchors.append(
                round(statistics.median(years)) if years else None
            )
        return anchors

    def detect_temporal_anomalies(
        self,
        paragraphs: List[Dict[str, Any]],
        clusters: List[int],
    ) -> List[Dict[str, Any]]:
        """
        Compare noise cluster median year vs core cluster baseline.
        Flag if |difference| > threshold.

        Args:
            paragraphs: List of paragraph dicts.
            clusters: List of cluster IDs per paragraph.

        Returns:
            List of anomaly dicts with paragraph index, years, and severity.
        """
        # Get all years for core vs noise
        core_years = []
        per_para_years = []

        for i, para in enumerate(paragraphs):
            text = para.get("text", "")
            citations = self._extract_citations(text)
            years = self._extract_years(citations)
            per_para_years.append(years)

            cluster_id = clusters[i] if i < len(clusters) else 0
            if cluster_id != -1:
                core_years.extend(years)

        if not core_years:
            return []

        core_baseline = round(statistics.median(core_years))

        anomalies = []
        for i, years in enumerate(per_para_years):
            if not years:
                continue
            median_year = round(statistics.median(years))
            diff = abs(median_year - core_baseline)
            if diff > self.temporal_threshold:
                anomalies.append({
                    "paragraph_index": i,
                    "paragraph_median_year": median_year,
                    "core_baseline_year": core_baseline,
                    "year_difference": diff,
                    "cluster_id": clusters[i] if i < len(clusters) else 0,
                    "severity": self._severity(diff),
                })

        return anomalies

    # ─── Private Helpers ─────────────────────────────────────────────────────

    def _extract_citations(self, text: str) -> List[str]:
        """
        Extract inline citations using multiple regex patterns.
        Combines parenthetical and narrative citation matches.
        Filters out false positives (common words that look like author names).
        """
        citations = []

        # Parenthetical: (Author, Year) style
        for match in PARENTHETICAL_REGEX.finditer(text):
            citation = match.group(0)
            if not self._is_false_positive(citation):
                citations.append(citation)

        # Narrative: Author (Year) style
        for match in NARRATIVE_REGEX.finditer(text):
            citation = match.group(0)
            if not self._is_false_positive(citation):
                # Avoid duplicates if the same citation was already
                # captured parenthetically
                if citation not in citations:
                    citations.append(citation)

        # IEEE-style: [1], [1, 2]
        for match in IEEE_REGEX.finditer(text):
            citation = match.group(0)
            if citation not in citations:
                citations.append(citation)

        return citations

    def _extract_years(self, citations: List[str], bib_map: Optional[Dict[int, int]] = None) -> List[int]:
        """
        Extract all 4-digit years from a list of citation strings.
        Maps IEEE numerical citations to bibliography years.
        Filters to a reasonable academic range (1900–2030).
        """
        years = []
        for citation in citations:
            matched_year = False
            for match in YEAR_REGEX.finditer(citation):
                year = int(match.group(0))
                if 1900 <= year <= 2030:
                    years.append(year)
                    matched_year = True
            
            # IEEE [N] citation mapping
            if not matched_year and bib_map and IEEE_REGEX.fullmatch(citation.strip()):
                nums = re.findall(r'\d+', citation)
                for num_str in nums:
                    mapped_year = bib_map.get(int(num_str))
                    if mapped_year:
                        years.append(mapped_year)
        return years

    def _build_bib_map(self, references: List[Any]) -> Dict[int, int]:
        """
        Map IEEE numerical citations [N] to the year in the bibliography entry.
        """
        bib_map = {}
        for ref in references:
            text = ref if isinstance(ref, str) else ref.get("text", "")
            m = re.search(r'^\s*\[?(\d+)\]?\.?\s', text)
            if m:
                num = int(m.group(1))
                ym = re.search(r'(?:19|20)\d{2}', text)
                if ym:
                    bib_map[num] = int(ym.group(0))
        return bib_map

    def _is_false_positive(self, citation: str) -> bool:
        """
        Check if a citation match is actually a common English word
        or phrase that happens to match the regex pattern.
        """
        # Extract the first word and check against false positives
        words_in_citation = re.findall(r'[A-Za-z]+', citation)
        if words_in_citation:
            first_word = words_in_citation[0].lower()
            if first_word in FALSE_POSITIVE_WORDS:
                return True
        return False

    def _extract_bibliography_years(
        self, references: List[Dict[str, Any]]
    ) -> List[int]:
        """
        Extract years from bibliography/reference entries.
        """
        years = []
        for ref in references:
            text = ref if isinstance(ref, str) else ref.get("text", "")
            for match in YEAR_REGEX.finditer(text):
                year = int(match.group(0))
                if 1900 <= year <= 2030:
                    years.append(year)
        return years

    @staticmethod
    def _severity(year_diff: int) -> str:
        """
        Classify the severity of a temporal anomaly based on year difference.
        """
        if year_diff > 20:
            return "high"
        elif year_diff > 10:
            return "medium"
        else:
            return "low"
