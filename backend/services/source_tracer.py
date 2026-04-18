"""
P.R.I.S.M. — Semantic Source Tracer
Tracing anomalous paragraphs back to potential source papers via arxiv.
With edge-case handling for rate limits (429) via tenacity.
"""
import spacy
from sentence_transformers import SentenceTransformer
from tenacity import retry, wait_exponential, stop_after_attempt
import arxiv
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import logging
import requests
from typing import List, Dict, Any, Optional
from models import PipelineContext, WarningCode, WarningSeverity

logger = logging.getLogger(__name__)

# Load NLP model for keyword extraction
try:
    nlp = spacy.load("en_core_web_sm", disable=["ner", "parser"])
except OSError:
    # Handle case where model might not be downloaded yet, though install script covers it
    import spacy.cli
    spacy.cli.download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm", disable=["ner", "parser"])

# Load local embeddings model
model = SentenceTransformer('all-MiniLM-L6-v2')

class SourceTracer:
    """
    Traces anomalous cluster paragraphs back to potential arxiv sources.
    Handles rate-limiting API errors gracefully with exponential backoff.
    """
    def __init__(self, similarity_threshold=0.75):
        self.similarity_threshold = similarity_threshold
        # Note: We must use a different arxiv client approach as per arxiv>=2.0.0
        self.client = arxiv.Client()
        
    def _extract_keywords(self, text: str, top_n: int = 3) -> List[str]:
        """Extract main nouns/keywords from the text to form an arxiv search query."""
        doc = nlp(text)
        
        # Simple extraction based on nouns and adjectives
        keywords = [token.lemma_ for token in doc if token.pos_ in ["NOUN", "ADJ"] and not token.is_stop and token.is_alpha]
        
        # Get unique keywords, prioritizing longer ones
        unique_keywords = list(set(keywords))
        unique_keywords.sort(key=len, reverse=True)
        
        return unique_keywords[:top_n]

    @retry(wait=wait_exponential(multiplier=2, min=2, max=10), stop=stop_after_attempt(4), reraise=True)
    def _safe_arxiv_search(self, query: str, max_results: int = 5) -> list:
        """Exponential backoff for arxiv rate limits."""
        if not query.strip():
            return []
            
        logger.info(f"[P.R.I.S.M.] Searching arxiv for: {query}")
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance
        )
        return list(self.client.results(search))

    @retry(wait=wait_exponential(multiplier=2, min=2, max=10), stop=stop_after_attempt(3), reraise=False)
    def _safe_openalex_search(self, query: str, max_results: int = 3) -> list:
        if not query.strip():
            return []
        logger.info(f"[P.R.I.S.M.] Searching OpenAlex for: {query}")
        url = f"https://api.openalex.org/works?search={query}&per-page={max_results}"
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        return res.json().get("results", [])

    def trace(self, anomalous_paragraphs: List[Dict[str, Any]], ctx: Optional[PipelineContext] = None) -> List[Dict[str, Any]]:
        """
        Trace the source of anomalous paragraphs.
        anomalous_paragraphs should be a list of dicts.
        """
        if ctx is None:
            ctx = PipelineContext()

        if ctx.skip_source_tracing:
            return []

        source_matches = []
        
        for para in anomalous_paragraphs[:3]:
            text = para.get("text", "")
            if len(text.split()) < 10:
                continue # Text too short to trace reliably
                
            # 1. Extract keywords via spaCy
            keywords = self._extract_keywords(text)
            if not keywords:
                continue
                
            query = " AND ".join(keywords)
            
            try:
                # 2. Query global databases
                arxiv_results = self._safe_arxiv_search(query, max_results=3)
                openalex_results = self._safe_openalex_search(query, max_results=3)
                
                abstracts = []
                aggregated_docs = []

                # Format arXiv
                if arxiv_results:
                    for r in arxiv_results:
                        abstracts.append(r.summary)
                        aggregated_docs.append({
                            "title": r.title,
                            "authors": [a.name for a in r.authors],
                            "year": r.published.year,
                            "url": r.pdf_url or r.entry_id,
                            "abstract": r.summary,
                            "origin": "arXiv"
                        })

                # Format OpenAlex
                if openalex_results:
                    for r in openalex_results:
                        # OpenAlex uses inverted index for abstracts, or sometimes just string depending on endpoint, 
                        # but normally we construct it or fallback to title if abstract is deep nested.
                        # We'll use title + context as fallback if abstract processing is complex.
                        # Wait, we can just use the title for embedding if abstract isn't readily available as plaintext.
                        raw_idx = r.get("abstract_inverted_index")
                        abstract_text = ""
                        if raw_idx:
                            # Reconstruct text from inverted index 
                            words = max([max(pos) for pos in raw_idx.values()]) + 1
                            text_arr = [""] * words
                            for word, positions in raw_idx.items():
                                for pos in positions:
                                    text_arr[pos] = word
                            abstract_text = " ".join(text_arr)
                        else:
                            abstract_text = r.get("title", "")
                        
                        abstracts.append(abstract_text)
                        
                        authors = [auth.get("author", {}).get("display_name", "Unknown") for auth in r.get("authorships", [])]
                        
                        aggregated_docs.append({
                            "title": r.get("title", "Unknown Title"),
                            "authors": authors,
                            "year": r.get("publication_year", 0),
                            "url": r.get("id"),
                            "abstract": abstract_text,
                            "origin": "OpenAlex"
                        })
                
                if not aggregated_docs:
                    continue
                    
                # 3. Embed paragraph + combined abstracts locally
                para_embedding = model.encode(text)
                abstract_embeddings = model.encode(abstracts)
                
                # 4. Cosine similarity ranking
                # cosine_similarity expects 2D arrays: (1, 384) and (N, 384)
                similarities = cosine_similarity([para_embedding], abstract_embeddings)[0]
                
                # 5. Return matches above threshold or exact text matches
                best_match_idx = np.argmax(similarities)
                best_sim = similarities[best_match_idx]
                best_paper = aggregated_docs[best_match_idx]
                
                # Simple heuristic
                text_lower = text.lower().strip()
                match_abstract = best_paper["abstract"].lower()
                is_exact = text_lower in match_abstract or text_lower in best_paper["title"].lower()
                
                if best_sim >= self.similarity_threshold or is_exact:
                    source_matches.append({
                        "paragraph_id": para.get("id") or para.get("paragraph_index"),
                        "similarity_score": round(float(best_sim), 4),
                        "source": {
                            "title": best_paper["title"],
                            "authors": best_paper["authors"],
                            "year": best_paper["year"],
                            "url": best_paper["url"],
                            "origin": best_paper["origin"],
                            "abstract": best_paper["abstract"]
                        }
                    })
                    
            except Exception as e:
                logger.error(f"[P.R.I.S.M.] Error tracing source for paragraph: {e}")
                ctx.add_warning(
                    WarningCode.SOURCE_ARXIV_TIMEOUT, WarningSeverity.WARNING, "source_tracer",
                    f"Arxiv search failed limit handling for query: '{query}'",
                    {"error": str(e)}
                )
                
        return source_matches

# Singleton instance
tracer = SourceTracer()
