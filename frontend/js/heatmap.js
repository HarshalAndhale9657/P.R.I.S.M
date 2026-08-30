/**
 * P.R.I.S.M. — Authorship Heatmap Renderer
 * ═══════════════════════════════════════════════════════════
 * Renders color-coded paragraph blocks grouped by HDBSCAN cluster assignment.
 *
 * Data flow (matches /api/analyze response):
 *   data.paragraphs[]            → { text, cluster_id, is_anomaly, is_boundary }
 *   data.features.profiles[]     → name-keyed stylometric dicts, one per paragraph
 *   data.features.feature_names  → ordered feature-name list
 *   data.reasoning               → { available, boundary_explanations{}, anomaly_profiles{} }
 */

const HeatmapRenderer = (() => {
    let legendContainer = null;
    let gridContainer = null;
    let expandedBlock = null;

    // Curated, human-readable subset of the 27-dim feature vector.
    const CORE_FEATURES = [
        'avg_sentence_length',
        'avg_word_length',
        'pronoun_ratio',
        'preposition_ratio',
        'conjunction_ratio',
        'passive_voice_pct',
        'yules_k',
        'burstiness_coefficient',
    ];

    // ─── Light-theme cluster palette (readable on white) ───
    function generateClusterPalette(clusterLabels) {
        const unique = [...new Set(clusterLabels)].filter(c => c !== -1).sort((a, b) => a - b);
        const total = unique.length;
        const palette = {};

        unique.forEach((label, i) => {
            const hue = (i * (360 / Math.max(total, 1)) + 210) % 360;
            palette[label] = {
                bg: `hsla(${hue}, 68%, 55%, 0.10)`,
                bgHover: `hsla(${hue}, 68%, 55%, 0.16)`,
                border: `hsl(${hue}, 62%, 48%)`,
                text: `hsl(${hue}, 55%, 36%)`,
                label: `Cluster ${label}`,
                hue: hue,
            };
        });

        palette[-1] = {
            bg: 'rgba(239, 68, 68, 0.06)',
            bgHover: 'rgba(239, 68, 68, 0.12)',
            border: '#ef4444',
            text: '#b91c1c',
            label: 'Anomaly (Cluster −1)',
            hue: 0,
        };

        return palette;
    }

    // ─── Legend + stats ───
    function renderLegend(palette, clusterSizes, meta) {
        legendContainer.innerHTML = '';

        const statsEl = document.createElement('div');
        statsEl.className = 'heatmap-stats';
        const realClusters = Object.keys(clusterSizes).filter(k => parseInt(k) !== -1).length;
        statsEl.innerHTML = `
            <div class="stat-chip">
                <span class="stat-value">${meta.estimatedAuthors}</span>
                <span class="stat-label">Est. Authors</span>
            </div>
            <div class="stat-chip">
                <span class="stat-value">${realClusters}</span>
                <span class="stat-label">Clusters</span>
            </div>
            <div class="stat-chip anomaly-chip">
                <span class="stat-value">${clusterSizes[-1] || 0}</span>
                <span class="stat-label">Anomalies</span>
            </div>
            <div class="stat-chip">
                <span class="stat-value">${meta.noisePct}%</span>
                <span class="stat-label">Noise</span>
            </div>
        `;
        legendContainer.appendChild(statsEl);

        const swatchContainer = document.createElement('div');
        swatchContainer.className = 'legend-swatches';

        Object.entries(palette).forEach(([label, colors]) => {
            const item = document.createElement('div');
            item.className = 'legend-item';
            item.dataset.cluster = label;
            if (parseInt(label) === -1) item.classList.add('anomaly');

            item.innerHTML = `
                <span class="legend-swatch" style="background:${colors.border}"></span>
                <span>${colors.label}</span>
                <span class="legend-count">${clusterSizes[label] || 0}</span>
            `;

            item.addEventListener('click', () => {
                toggleClusterFilter(parseInt(label));
            });

            swatchContainer.appendChild(item);
        });

        legendContainer.appendChild(swatchContainer);
    }

    // ─── Cluster filter ───
    let activeFilter = null;

    function toggleClusterFilter(clusterId) {
        const blocks = gridContainer.querySelectorAll('.heatmap-block');
        const legendItems = legendContainer.querySelectorAll('.legend-item');

        if (activeFilter === clusterId) {
            activeFilter = null;
            blocks.forEach(b => (b.style.opacity = '1'));
            legendItems.forEach(li => li.classList.remove('filter-active'));
        } else {
            activeFilter = clusterId;
            blocks.forEach(b => {
                const blockCluster = parseInt(b.dataset.cluster);
                b.style.opacity = blockCluster === clusterId ? '1' : '0.25';
            });
            legendItems.forEach(li => {
                li.classList.toggle('filter-active', parseInt(li.dataset.cluster) === clusterId);
            });
        }
    }

    // ─── Grid ───
    function renderGrid(paragraphs, palette, profiles, featureNames, reasoning, featureMax) {
        gridContainer.innerHTML = '';

        paragraphs.forEach((para, index) => {
            const cluster = getCluster(para);
            const colors = palette[cluster] || palette[0] || palette[-1];
            const isAnomaly = cluster === -1 || para.is_anomaly === true;

            const block = document.createElement('div');
            block.className = `heatmap-block${isAnomaly ? ' anomaly' : ''}`;
            block.dataset.cluster = cluster;
            block.dataset.index = index;
            block.style.borderLeftColor = colors.border;
            block.style.background = colors.bg;

            const indexEl = document.createElement('div');
            indexEl.className = 'para-index';
            const tag = isAnomaly
                ? `<span style="color:#b91c1c;font-weight:600;">— FLAGGED</span>`
                : `<span style="color:${colors.text};font-weight:600;">— ${colors.label}</span>`;
            indexEl.innerHTML = `¶ ${index + 1} ${tag}`;

            const textEl = document.createElement('div');
            textEl.className = 'para-text';
            textEl.textContent = (para && para.text) ? para.text : (typeof para === 'string' ? para : '');

            let badgeEl = null;
            if (isAnomaly) {
                badgeEl = document.createElement('span');
                badgeEl.className = 'anomaly-badge';
                badgeEl.textContent = '🚩 Anomaly';
            }

            const detailEl = document.createElement('div');
            detailEl.className = 'heatmap-detail';
            detailEl.style.display = 'none';

            // Stylometric feature bars (curated + normalized per feature)
            const profile = profiles ? profiles[index] : null;
            if (profile) {
                const names = (featureNames && featureNames.length)
                    ? CORE_FEATURES.filter(f => featureNames.includes(f))
                    : CORE_FEATURES;
                const featuresHtml = names.map(name => {
                    const val = typeof profile[name] === 'number' ? profile[name] : 0;
                    const max = featureMax[name] || 1;
                    const pct = Math.max(2, Math.min(Math.abs(val) / max * 100, 100));
                    return `
                        <div class="feature-row">
                            <span class="feature-name">${formatFeatureName(name)}</span>
                            <div class="feature-bar-track">
                                <div class="feature-bar-fill" style="width:${pct}%;background:${colors.border};"></div>
                            </div>
                            <span class="feature-value">${val.toFixed(3)}</span>
                        </div>
                    `;
                }).join('');

                detailEl.innerHTML += `
                    <div class="detail-section">
                        <h4>📐 Stylometric Features</h4>
                        <div class="features-list">${featuresHtml}</div>
                    </div>
                `;
            }

            // AI reasoning for flagged paragraphs
            const paraReasoning = findReasoningForParagraph(reasoning, index);
            if (paraReasoning) {
                detailEl.innerHTML += `
                    <div class="detail-section reasoning-section">
                        <h4>🤖 AI Reasoning</h4>
                        <p class="reasoning-text">${escapeHtml(paraReasoning)}</p>
                    </div>
                `;
            }

            block.appendChild(indexEl);
            block.appendChild(textEl);
            if (badgeEl) block.appendChild(badgeEl);
            if (detailEl.innerHTML.trim()) block.appendChild(detailEl);

            if (detailEl.innerHTML.trim()) {
                block.style.cursor = 'pointer';
                block.addEventListener('click', () => {
                    if (expandedBlock === block) {
                        detailEl.style.display = 'none';
                        block.classList.remove('expanded');
                        expandedBlock = null;
                    } else {
                        if (expandedBlock) {
                            const prev = expandedBlock.querySelector('.heatmap-detail');
                            if (prev) prev.style.display = 'none';
                            expandedBlock.classList.remove('expanded');
                        }
                        detailEl.style.display = 'block';
                        block.classList.add('expanded');
                        expandedBlock = block;
                    }
                });
            }

            gridContainer.appendChild(block);
        });
    }

    // ─── AI reasoning lookup (matches backend shape) ───
    function findReasoningForParagraph(reasoning, paraIndex) {
        if (!reasoning || reasoning.available === false) return null;

        // Anomaly profiles are keyed by paragraph index as a string.
        const profiles = reasoning.anomaly_profiles || {};
        if (profiles[paraIndex] != null) return profiles[paraIndex];
        if (profiles[String(paraIndex)] != null) return profiles[String(paraIndex)];

        // Boundary explanations are keyed "a_to_b".
        const boundaries = reasoning.boundary_explanations || {};
        for (const key of Object.keys(boundaries)) {
            const [a, b] = key.split('_to_').map(n => parseInt(n, 10));
            if (a === paraIndex || b === paraIndex) return boundaries[key];
        }
        return null;
    }

    function formatFeatureName(name) {
        return name
            .replace(/_/g, ' ')
            .replace(/\bpct\b/i, '%')
            .replace(/\byules k\b/i, "Yule's K")
            .replace(/\bavg\b/i, 'Avg.')
            .replace(/\b\w/g, c => c.toUpperCase());
    }

    function getCluster(p) {
        if (p && p.cluster_id !== undefined && p.cluster_id !== null) return p.cluster_id;
        if (p && p.cluster !== undefined && p.cluster !== null) return p.cluster;
        return 0;
    }

    function computeClusterSizes(paragraphs) {
        const sizes = {};
        paragraphs.forEach(p => {
            const c = getCluster(p);
            sizes[c] = (sizes[c] || 0) + 1;
        });
        return sizes;
    }

    function computeFeatureMax(profiles, names) {
        const max = {};
        names.forEach(n => (max[n] = 0));
        (profiles || []).forEach(p => {
            if (!p) return;
            names.forEach(n => {
                const v = Math.abs(typeof p[n] === 'number' ? p[n] : 0);
                if (v > max[n]) max[n] = v;
            });
        });
        return max;
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str == null ? '' : String(str);
        return div.innerHTML;
    }

    // ─── Main render ───
    function render(data) {
        legendContainer = document.getElementById('heatmap-legend');
        gridContainer = document.getElementById('heatmap-grid');
        if (!legendContainer || !gridContainer) return;

        const paragraphs = data.paragraphs || [];
        const features = data.features || {};
        const profiles = features.profiles || data.profiles || null;
        const featureNames = features.feature_names || data.feature_names || CORE_FEATURES;
        const reasoning = data.reasoning || null;
        const clustering = data.clustering || {};

        const clusterLabels = paragraphs.map(getCluster);
        const palette = generateClusterPalette(clusterLabels);
        const clusterSizes = computeClusterSizes(paragraphs);
        const featureMax = computeFeatureMax(profiles, CORE_FEATURES);

        const meta = {
            estimatedAuthors: clustering.estimated_authors != null ? clustering.estimated_authors : Object.keys(clusterSizes).filter(k => parseInt(k) !== -1).length,
            noisePct: clustering.noise_percentage != null ? Number(clustering.noise_percentage).toFixed(0) : '0',
        };

        renderLegend(palette, clusterSizes, meta);
        renderGrid(paragraphs, palette, profiles, featureNames, reasoning, featureMax);

        activeFilter = null;
        expandedBlock = null;
    }

    return { render };
})();
