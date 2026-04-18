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
                # 2. Query arxiv with top keywords
                results = self._safe_arxiv_search(query)
                
                if not results:
                    continue
                    
                # 3. Embed paragraph + abstracts locally
                para_embedding = model.encode(text)
                abstracts = [r.summary for r in results]
                abstract_embeddings = model.encode(abstracts)
                
                # 4. Cosine similarity ranking
                # cosine_similarity expects 2D arrays: (1, 384) and (N, 384)
                similarities = cosine_similarity([para_embedding], abstract_embeddings)[0]
                
                # 5. Return matches above threshold
                best_match_idx = np.argmax(similarities)
                best_sim = similarities[best_match_idx]
                
                if best_sim >= self.similarity_threshold:
                    best_paper = results[best_match_idx]
                    source_matches.append({
                        "paragraph_id": para.get("id") or para.get("paragraph_index"),
                        "similarity_score": round(float(best_sim), 4),
                        "source": {
                            "title": best_paper.title,
                            "authors": [a.name for a in best_paper.authors],
                            "year": best_paper.published.year,
                            "url": best_paper.pdf_url or best_paper.entry_id,
                            "abstract": best_paper.summary
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
