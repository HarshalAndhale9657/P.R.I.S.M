/**
 * P.R.I.S.M. — Sources Renderer
 * Renders potential source matches from arXiv for anomalous paragraphs.
 * 
 * Backend schema (from /api/analyze -> sources):
 *   sources is a flat list of match objects:
 *   [
 *     {
 *       paragraph_id: int,
 *       similarity_score: float,
 *       source: {
 *         title: str,
 *         authors: [str],
 *         year: int,
 *         url: str,
 *         abstract: str
 *       }
 *     },
 *     ...
 *   ]
 */

const SourcesRenderer = (() => {
    function render(analysisData) {
        if (!analysisData) return;
        
        const container = document.getElementById('sources-content');
        if (!container) return;

        const sourcesList = analysisData.sources;
        
        // Handle null, undefined, or empty array
        if (!sourcesList || !Array.isArray(sourcesList) || sourcesList.length === 0) {
            container.innerHTML = `
                <div class="no-sources">
                    <span class="success-icon">✅</span>
                    <p>No external source matches found for any anomalous sections.</p>
                    <p style="color:#8b949e; font-size:0.9em; margin-top:8px;">
                        This means no paragraphs flagged as anomalous had a high similarity match 
                        (≥${analysisData._sourceThreshold || 75}%) against papers on arXiv.
                    </p>
                </div>
            `;
            return;
        }

        let html = `
            <div class="citation-overview" style="margin-bottom: 1.5rem;">
                <div class="overview-stat">
                    <span class="stat-value">${sourcesList.length}</span>
                    <span class="stat-label">Source Matches Found</span>
                </div>
                <div class="overview-stat">
                    <span class="stat-value">${Math.max(...sourcesList.map(s => s.similarity_score * 100)).toFixed(1)}%</span>
                    <span class="stat-label">Highest Match</span>
                </div>
            </div>
        `;
        
        html += `<div class="sources-list">`;

        sourcesList.forEach(entry => {
            const src = entry.source || {};
            const simPct = ((entry.similarity_score || 0) * 100).toFixed(1);
            const simColor = entry.similarity_score > 0.85 ? '#f85149' : (entry.similarity_score > 0.7 ? '#d29922' : '#3fb950');
            const paraId = entry.paragraph_id;
            
            html += `
                <div class="source-card" style="background: rgba(22, 27, 34, 0.5); border: 1px solid #30363d; border-radius: 6px; padding: 16px; margin-bottom: 1rem;">
                    <div class="source-header" style="display: flex; justify-content: space-between; align-items: flex-start; gap: 12px;">
                        <div>
                            <h4 style="margin: 0;">
                                <a href="${src.url || '#'}" target="_blank" style="color: #58a6ff; text-decoration: none;">${src.title || 'Unknown Paper'}</a>
                            </h4>
                            <p style="color:#8b949e; font-size:0.85em; margin:4px 0 0 0;">
                                Matched against <strong>Paragraph ${paraId != null ? paraId + 1 : '?'}</strong> (anomalous section)
                            </p>
                        </div>
                        <span class="source-similarity" style="color: ${simColor}; font-weight: bold; background: rgba(0,0,0,0.2); padding: 4px 10px; border-radius: 4px; white-space: nowrap; font-size: 0.95em;">${simPct}% Match</span>
                    </div>
                    <div class="source-meta" style="margin-top: 10px; color: #8b949e; font-size: 0.9em;">
                        <span>Authors: ${(src.authors && src.authors.length) ? src.authors.join(', ') : 'Unknown'}</span> | 
                        <span>Published: ${src.year || 'N/A'}</span>
                    </div>
                    <div class="similarity-bar-bg" style="width: 100%; height: 6px; background: #21262d; border-radius: 3px; margin-top: 12px; overflow: hidden;">
                        <div class="similarity-bar-fill" style="width: ${simPct}%; height: 100%; background: ${simColor}; border-radius: 3px;"></div>
                    </div>
                    <p class="source-abstract-snippet" style="margin-top: 12px; color: #c9d1d9; font-size: 0.95em; line-height: 1.5;">
                        ${src.abstract ? src.abstract.substring(0, 300) + '...' : 'No abstract available.'}
                    </p>
                    <a href="${src.url || '#'}" target="_blank" style="display: inline-block; margin-top: 8px; color: #58a6ff; font-size: 0.9em; text-decoration: underline;">Read Full Paper →</a>
                </div>
            `;
        });
        
        html += `</div>`;
        
        container.innerHTML = html;
    }

    return { render };
})();
