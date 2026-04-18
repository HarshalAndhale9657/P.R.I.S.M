/**
 * P.R.I.S.M. — Authorship Heatmap Renderer
 * Color-coded paragraph blocks per HDBSCAN cluster.
 * Cluster -1 = red border + anomaly badge.
 * Click paragraph → show style features + GPT reasoning.
 * Dynamic HSL color generation with YIQ contrast.
 */

const HeatmapRenderer = (() => {
    // ─── DOM Cache ───
    let legendContainer = null;
    let gridContainer = null;
    let expandedBlock = null; // currently expanded paragraph

    // ─── Dynamic HSL Color Palette ───
    function generateClusterPalette(clusterLabels) {
        const unique = [...new Set(clusterLabels)].filter(c => c !== -1).sort((a, b) => a - b);
        const total = unique.length;
        const palette = {};

        unique.forEach((label, i) => {
            const hue = (i * (360 / Math.max(total, 1)) + 220) % 360; // Start from blue range
            palette[label] = {
                bg: `hsla(${hue}, 60%, 55%, 0.10)`,
                bgHover: `hsla(${hue}, 60%, 55%, 0.18)`,
                border: `hsl(${hue}, 60%, 55%)`,
                text: `hsl(${hue}, 50%, 75%)`,
                label: `Cluster ${label}`,
                hue: hue,
            };
        });

        // Anomaly cluster (-1)
        palette[-1] = {
            bg: 'rgba(248, 113, 113, 0.08)',
            bgHover: 'rgba(248, 113, 113, 0.15)',
            border: '#f87171',
            text: '#fca5a5',
            label: 'Anomaly (Cluster -1)',
            hue: 0,
        };

        return palette;
    }

    // ─── YIQ Contrast ───
    function getTextColor(hue, saturation, lightness) {
        // Convert HSL to RGB to determine contrast
        const h = hue / 360;
        const s = saturation / 100;
        const l = lightness / 100;

        let r, g, b;
        if (s === 0) {
            r = g = b = l;
        } else {
            const hue2rgb = (p, q, t) => {
                if (t < 0) t += 1;
                if (t > 1) t -= 1;
                if (t < 1/6) return p + (q - p) * 6 * t;
                if (t < 1/2) return q;
                if (t < 2/3) return p + (q - p) * (2/3 - t) * 6;
                return p;
            };
            const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
            const p = 2 * l - q;
            r = hue2rgb(p, q, h + 1/3);
            g = hue2rgb(p, q, h);
            b = hue2rgb(p, q, h - 1/3);
        }

        // YIQ formula
        const yiq = (r * 255 * 299 + g * 255 * 587 + b * 255 * 114) / 1000;
        return yiq >= 128 ? '#0d1117' : '#e6edf3';
    }

    // ─── Build Legend ───
    function renderLegend(palette, clusterSizes) {
        legendContainer.innerHTML = '';

        // Summary stats
        const statsEl = document.createElement('div');
        statsEl.className = 'heatmap-stats';
        statsEl.innerHTML = `
            <div class="stat-chip">
                <span class="stat-value">${Object.keys(clusterSizes).length}</span>
                <span class="stat-label">Clusters</span>
            </div>
            <div class="stat-chip anomaly-chip">
                <span class="stat-value">${clusterSizes[-1] || 0}</span>
                <span class="stat-label">Anomalies</span>
            </div>
        `;
        legendContainer.appendChild(statsEl);

        // Color swatches
        const swatchContainer = document.createElement('div');
        swatchContainer.className = 'legend-swatches';

        Object.entries(palette).forEach(([label, colors]) => {
            const item = document.createElement('div');
            item.className = 'legend-item';
            if (parseInt(label) === -1) item.classList.add('anomaly');

            item.innerHTML = `
                <span class="legend-swatch" style="background:${colors.border}"></span>
                <span>${colors.label}</span>
                <span class="legend-count">${clusterSizes[label] || 0}</span>
            `;

            // Click to filter
            item.addEventListener('click', () => {
                toggleClusterFilter(parseInt(label));
                item.classList.toggle('filter-active');
            });

            swatchContainer.appendChild(item);
        });

        legendContainer.appendChild(swatchContainer);
    }

    // ─── Filter by Cluster ───
    let activeFilter = null;

    function toggleClusterFilter(clusterId) {
        const blocks = gridContainer.querySelectorAll('.heatmap-block');

        if (activeFilter === clusterId) {
            // Remove filter
            activeFilter = null;
            blocks.forEach(b => b.style.opacity = '1');
            legendContainer.querySelectorAll('.legend-item').forEach(li => li.classList.remove('filter-active'));
        } else {
            activeFilter = clusterId;
            blocks.forEach(b => {
                const blockCluster = parseInt(b.dataset.cluster);
                b.style.opacity = blockCluster === clusterId ? '1' : '0.2';
            });
        }
    }

    // ─── Build Heatmap Grid ───
    function renderGrid(paragraphs, palette, profiles, featureNames, reasoning) {
        gridContainer.innerHTML = '';

        paragraphs.forEach((para, index) => {
            const cluster = para.cluster !== undefined ? para.cluster : 0;
            const colors = palette[cluster] || palette[0];
            const isAnomaly = cluster === -1;

            // Block container
            const block = document.createElement('div');
            block.className = `heatmap-block${isAnomaly ? ' anomaly' : ''}`;
            block.dataset.cluster = cluster;
            block.dataset.index = index;
            block.style.borderLeftColor = colors.border;
            block.style.background = colors.bg;

            // Paragraph index
            const indexEl = document.createElement('div');
            indexEl.className = 'para-index';
            indexEl.textContent = `¶ ${index + 1}`;
            if (isAnomaly) {
                indexEl.innerHTML += ` <span style="color:#f87171;font-weight:600;">— FLAGGED</span>`;
            } else {
                indexEl.innerHTML += ` <span style="color:${colors.text};">— ${colors.label}</span>`;
            }

            // Paragraph text preview
            const textEl = document.createElement('div');
            textEl.className = 'para-text';
            textEl.textContent = para.text || para;

            // Anomaly badge
            let badgeEl = null;
            if (isAnomaly) {
                badgeEl = document.createElement('span');
                badgeEl.className = 'anomaly-badge';
                badgeEl.textContent = '🚨 Anomaly';
            }

            // Expandable detail section
            const detailEl = document.createElement('div');
            detailEl.className = 'heatmap-detail';
            detailEl.style.display = 'none';

            // Feature profile
            const profile = profiles ? profiles[index] : null;
            if (profile && featureNames) {
                const featuresHtml = featureNames.map((name, fi) => {
                    const val = profile.features ? profile.features[fi] : (profile[fi] || 0);
                    const formatted = typeof val === 'number' ? val.toFixed(3) : val;
                    return `
                        <div class="feature-row">
                            <span class="feature-name">${formatFeatureName(name)}</span>
                            <div class="feature-bar-track">
                                <div class="feature-bar-fill" style="width:${Math.min(Math.abs(val) * 100, 100)}%;background:${colors.border};"></div>
                            </div>
                            <span class="feature-value">${formatted}</span>
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

            // GPT Reasoning (if available for this paragraph)
            if (reasoning && isAnomaly) {
                const paraReasoning = findReasoningForParagraph(reasoning, index);
                if (paraReasoning) {
                    detailEl.innerHTML += `
                        <div class="detail-section reasoning-section">
                            <h4>🤖 AI Reasoning</h4>
                            <p class="reasoning-text">${paraReasoning}</p>
                        </div>
                    `;
                }
            }

            // Assemble block
            block.appendChild(indexEl);
            block.appendChild(textEl);
            if (badgeEl) block.appendChild(badgeEl);
            block.appendChild(detailEl);

            // Click to expand
            block.addEventListener('click', () => {
                if (expandedBlock === block) {
                    // Collapse
                    detailEl.style.display = 'none';
                    block.classList.remove('expanded');
                    expandedBlock = null;
                } else {
                    // Collapse previous
                    if (expandedBlock) {
                        expandedBlock.querySelector('.heatmap-detail').style.display = 'none';
                        expandedBlock.classList.remove('expanded');
                    }
                    // Expand this
                    detailEl.style.display = 'block';
                    block.classList.add('expanded');
                    expandedBlock = block;
                }
            });

            gridContainer.appendChild(block);
        });
    }

    // ─── Find GPT Reasoning ───
    function findReasoningForParagraph(reasoning, paraIndex) {
        if (!reasoning) return null;

        // Check style_profiles
        if (reasoning.style_profiles) {
            const profile = reasoning.style_profiles.find(p =>
                p.paragraph_index === paraIndex || p.index === paraIndex
            );
            if (profile) return profile.explanation || profile.style_summary || JSON.stringify(profile);
        }

        // Check boundary_analyses
        if (reasoning.boundary_analyses) {
            const boundary = reasoning.boundary_analyses.find(b =>
                b.paragraph_a === paraIndex || b.paragraph_b === paraIndex ||
                b.index_a === paraIndex || b.index_b === paraIndex
            );
            if (boundary) return boundary.explanation || boundary.reasoning || JSON.stringify(boundary);
        }

        // Check if reasoning is an array
        if (Array.isArray(reasoning)) {
            const item = reasoning.find(r => r.paragraph_index === paraIndex || r.index === paraIndex);
            if (item) return item.explanation || item.reasoning || JSON.stringify(item);
        }

        return null;
    }

    // ─── Format Feature Names ───
    function formatFeatureName(name) {
        return name
            .replace(/_/g, ' ')
            .replace(/\b\w/g, c => c.toUpperCase())
            .replace('Pct', '%')
            .replace('Avg', 'Avg.');
    }

    // ─── Compute Cluster Sizes ───
    function computeClusterSizes(paragraphs) {
        const sizes = {};
        paragraphs.forEach(p => {
            const c = p.cluster !== undefined ? p.cluster : 0;
            sizes[c] = (sizes[c] || 0) + 1;
        });
        return sizes;
    }

    // ─── Main Render ───
    function render(data) {
        legendContainer = document.getElementById('heatmap-legend');
        gridContainer = document.getElementById('heatmap-grid');

        if (!legendContainer || !gridContainer) return;

        const paragraphs = data.paragraphs || [];
        const profiles = data.profiles || null;
        const featureNames = data.feature_names || [];
        const reasoning = data.reasoning || null;

        // Extract cluster labels
        const clusterLabels = paragraphs.map(p => p.cluster !== undefined ? p.cluster : 0);

        // Generate palette
        const palette = generateClusterPalette(clusterLabels);

        // Cluster sizes
        const clusterSizes = computeClusterSizes(paragraphs);

        // Render
        renderLegend(palette, clusterSizes);
        renderGrid(paragraphs, palette, profiles, featureNames, reasoning);

        // Reset filter state
        activeFilter = null;
        expandedBlock = null;
    }

    // ─── Public API ───
    return { render };
})();
