/**
 * P.R.I.S.M. — Sources Renderer
 * Renders potential source matches from arXiv for anomalous paragraphs.
 */

const SourcesRenderer = (() => {
    function render(analysisData) {
        if (!analysisData || !analysisData.sources) return;
        
        const container = document.getElementById('sources-content');
        if (!container) return;

        const sourcesList = analysisData.sources;
        
        if (!sourcesList || sourcesList.length === 0) {
            container.innerHTML = `
                <div class="no-sources">
                    <span class="success-icon">✅</span>
                    <p>No external source matches found for any sections.</p>
                </div>
            `;
            return;
        }

        let html = `<div class="sources-list">`;
        
        sourcesList.forEach(sourceEntry => {
            const matches = sourceEntry.matches || [];
            
            html += `
                <div class="source-group" style="margin-bottom: 2rem;">
                    <h3 class="source-group-title" style="border-bottom: 1px solid #30363d; padding-bottom: 8px;">Matches for Anomalous Section ${sourceEntry.paragraph_id + 1}</h3>
            `;
            
            if (matches.length === 0) {
                 html += `<p class="no-match" style="color: #8b949e; font-style: italic;">No strong matches found on arXiv.</p>`;
            } else {
                matches.forEach(m => {
                    const simPct = (m.similarity * 100).toFixed(1);
                    const simColor = m.similarity > 0.85 ? '#f85149' : (m.similarity > 0.7 ? '#d29922' : '#3fb950');
                    
                    html += `
                        <div class="source-card" style="background: rgba(22, 27, 34, 0.5); border: 1px solid #30363d; border-radius: 6px; padding: 16px; margin-top: 1rem;">
                            <div class="source-header" style="display: flex; justify-content: space-between; align-items: flex-start;">
                                <h4 class="source-title" style="margin: 0;"><a href="${m.url}" target="_blank" style="color: #58a6ff; text-decoration: none;">${m.title}</a></h4>
                                <span class="source-similarity" style="color: ${simColor}; font-weight: bold; background: rgba(0,0,0,0.2); padding: 4px 8px; border-radius: 4px;">${simPct}% Match</span>
                            </div>
                            <div class="source-meta" style="margin-top: 8px; color: #8b949e; font-size: 0.9em;">
                                <span>Authors: ${(m.authors && m.authors.length) ? m.authors.join(', ') : 'Unknown'}</span> | 
                                <span>Published: ${m.published}</span>
                            </div>
                            <div class="similarity-bar-bg" style="width: 100%; height: 6px; background: #21262d; border-radius: 3px; margin-top: 12px; overflow: hidden;">
                                <div class="similarity-bar-fill" style="width: ${simPct}%; height: 100%; background: ${simColor}; border-radius: 3px;"></div>
                            </div>
                            <p class="source-abstract-snippet" style="margin-top: 12px; color: #c9d1d9; font-size: 0.95em; line-height: 1.5;">
                                ${m.summary ? m.summary.substring(0, 300) + '...' : 'No abstract available.'}
                            </p>
                            <a href="${m.url}" target="_blank" style="display: inline-block; margin-top: 8px; color: #58a6ff; font-size: 0.9em; text-decoration: underline;">Read Full Paper</a>
                        </div>
                    `;
                });
            }
            
            html += `</div>`;
        });
        
        html += `</div>`;
        
        container.innerHTML = html;
    }

    return { render };
})();
