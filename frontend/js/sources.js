/**
 * P.R.I.S.M. — Sources Renderer
 * Renders potential source matches (arXiv / OpenAlex) for anomalous paragraphs.
 *
 * Backend schema (/api/analyze -> sources): a flat list of match objects:
 *   [{ paragraph_id, similarity_score, source: { title, authors[], year, url, abstract } }]
 */

const SourcesRenderer = (() => {
    function simClass(score) {
        if (score > 0.85) return 'sim-high';
        if (score > 0.7) return 'sim-med';
        return 'sim-low';
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str == null ? '' : String(str);
        return div.innerHTML;
    }

    function render(analysisData) {
        if (!analysisData) return;
        const container = document.getElementById('sources-content');
        if (!container) return;

        const sourcesList = analysisData.sources;
        const threshold = analysisData._sourceThreshold || 75;

        if (!sourcesList || !Array.isArray(sourcesList) || sourcesList.length === 0) {
            container.innerHTML = `
                <div class="no-sources">
                    <span class="success-icon">✅</span>
                    <p class="empty-title">No external source matches found</p>
                    <p>No paragraph flagged as anomalous had a high-similarity match
                       (≥ ${threshold}%) against papers on arXiv or OpenAlex.</p>
                </div>
            `;
            return;
        }

        const highest = Math.max(...sourcesList.map(s => (s.similarity_score || 0) * 100));

        let html = `
            <div class="citation-overview">
                <div class="overview-stat">
                    <span class="stat-value">${sourcesList.length}</span>
                    <span class="stat-label">Source Matches</span>
                </div>
                <div class="overview-stat">
                    <span class="stat-value">${highest.toFixed(1)}%</span>
                    <span class="stat-label">Highest Match</span>
                </div>
            </div>
            <div class="sources-list">
        `;

        sourcesList.forEach(entry => {
            const src = entry.source || {};
            const score = entry.similarity_score || 0;
            const simPct = (score * 100).toFixed(1);
            const cls = simClass(score);
            const paraId = entry.paragraph_id;
            const authors = (src.authors && src.authors.length) ? src.authors.join(', ') : 'Unknown';
            const url = src.url || '#';

            html += `
                <div class="source-card">
                    <div class="source-header">
                        <div class="source-titleblock">
                            <h4><a href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(src.title || 'Unknown Paper')}</a></h4>
                            <p class="source-matched">Matched against
                                <strong>Paragraph ${paraId != null ? paraId + 1 : '?'}</strong> (anomalous section)</p>
                        </div>
                        <span class="source-similarity ${cls}">${simPct}% Match</span>
                    </div>
                    <div class="source-meta">
                        <span>Authors: ${escapeHtml(authors)}</span>
                        <span class="dot">•</span>
                        <span>Published: ${escapeHtml(String(src.year || 'N/A'))}</span>
                    </div>
                    <div class="similarity-bar-bg">
                        <div class="similarity-bar-fill ${cls}" style="width:${simPct}%;"></div>
                    </div>
                    <p class="source-abstract-snippet">
                        ${src.abstract ? escapeHtml(src.abstract.substring(0, 300)) + '…' : 'No abstract available.'}
                    </p>
                    <a class="source-link" href="${escapeHtml(url)}" target="_blank" rel="noopener">Read Full Paper →</a>
                </div>
            `;
        });

        html += `</div>`;
        container.innerHTML = html;
    }

    return { render };
})();
