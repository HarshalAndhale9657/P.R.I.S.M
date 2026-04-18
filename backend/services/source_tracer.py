import spacy
from sentence_transformers import SentenceTransformer
from tenacity import retry, wait_exponential, stop_after_attempt
import arxiv
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

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
    def __init__(self, similarity_threshold=0.75):
        self.similarity_threshold = similarity_threshold
        # Note: We must use a different arxiv client approach as per arxiv>=2.0.0
        self.client = arxiv.Client()
        
    def _extract_keywords(self, text: str, top_n: int = 3) -> list[str]:
        """Extract main nouns/keywords from the text to form an arxiv search query."""
        doc = nlp(text)
        
        # Simple extraction based on nouns and adjectives
        keywords = [token.lemma_ for token in doc if token.pos_ in ["NOUN", "ADJ"] and not token.is_stop and token.is_alpha]
        
        # Get unique keywords, prioritizing longer ones
        unique_keywords = list(set(keywords))
        unique_keywords.sort(key=len, reverse=True)
        
        return unique_keywords[:top_n]

    @retry(wait=wait_exponential(multiplier=2, min=2, max=10), stop=stop_after_attempt(4))
    def _safe_arxiv_search(self, query: str, max_results: int = 5) -> list:
        """Exponential backoff for arxiv rate limits."""
        if not query.strip():
            return []
            
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance
        )
        return list(self.client.results(search))

    def trace(self, anomalous_paragraphs: list[dict]) -> list[dict]:
        """
        Trace the source of anomalous paragraphs.
        anomalous_paragraphs should be a list of dicts, e.g. [{"id": 0, "text": "..."}]
        """
        source_matches = []
        
        for para in anomalous_paragraphs:
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
                        "paragraph_id": para.get("id"),
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
                print(f"Error tracing source for paragraph {para.get('id')}: {e}")
                
        return source_matches

# Singleton instance
tracer = SourceTracer()
