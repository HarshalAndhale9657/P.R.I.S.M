/**
 * P.R.I.S.M. — Charts Renderer
 * Visualizes stylometric features using Chart.js
 * Reads data from the /api/analyze response structure.
 */

const ChartsRenderer = (() => {
    // Shared chart options for dark theme
    const commonOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                labels: { color: '#e6edf3', font: { family: 'Inter' } }
            },
            tooltip: {
                backgroundColor: 'rgba(22, 27, 34, 0.9)',
                titleColor: '#e6edf3',
                bodyColor: '#c9d1d9',
                borderColor: '#30363d',
                borderWidth: 1,
            }
        },
        scales: {
            x: {
                ticks: { color: '#8b949e' },
                grid: { color: '#21262d' }
            },
            y: {
                ticks: { color: '#8b949e' },
                grid: { color: '#21262d' }
            }
        }
    };

    let featureChart = null;
    let ratioChart = null;
    let clusterChart = null;

    function render(analysisData) {
        if (!analysisData || !analysisData.paragraphs) return;

        // Support both nested (from /api/analyze) and flat structures
        const features = analysisData.features || {};
        const profiles = features.profiles || analysisData.profiles || [];
        const featureNames = features.feature_names || analysisData.feature_names || [
            "avg_sentence_length", "avg_word_length", "pronoun_ratio", 
            "preposition_ratio", "conjunction_ratio", "passive_voice_pct", "yules_k"
        ];
        const clustering = analysisData.clustering || {};
        const estimatedAuthors = clustering.estimated_authors || analysisData.estimated_authors || 1;

        if (!profiles || profiles.length === 0) return;

        const paragraphs = analysisData.paragraphs;

        const yulesKIdx = featureNames.indexOf("yules_k");
        const sentLenIdx = featureNames.indexOf("avg_sentence_length");
        
        const labels = paragraphs.map((_, i) => `¶ ${i + 1}`);
        const clusters = paragraphs.map(p => p.cluster_id != null ? p.cluster_id : 0);
        
        // Colors mapping
        const pointColors = clusters.map(c => PRISM.getClusterColor(c, estimatedAuthors).border);

        renderFeatureChart(labels, profiles, featureNames, yulesKIdx, sentLenIdx, pointColors);
        renderRatioChart(labels, profiles, featureNames);
        renderClusterChart(paragraphs, profiles, featureNames, yulesKIdx, sentLenIdx, pointColors);
    }

    function renderFeatureChart(labels, profiles, featureNames, yulesKIdx, sentLenIdx, pointColors) {
        const ctx = document.getElementById('chart-features');
        if (!ctx) return;
        
        if (featureChart) featureChart.destroy();
        
        // If indices invalid, fallback to 0 and 1
        const id1 = yulesKIdx >= 0 ? yulesKIdx : 0;
        const id2 = sentLenIdx >= 0 ? sentLenIdx : 1;
        const key1 = featureNames ? featureNames[id1] : null;
        const key2 = featureNames ? featureNames[id2] : null;

        const data1 = profiles.map(p => Array.isArray(p) ? p[id1] : (key1 ? p[key1] : 0));
        const data2 = profiles.map(p => Array.isArray(p) ? p[id2] : (key2 ? p[key2] : 0));

        featureChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Lexical Richness (Yule\'s K)',
                        data: data1,
                        borderColor: '#7c3aed',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        tension: 0.3,
                        pointBackgroundColor: pointColors,
                        pointBorderColor: pointColors,
                        pointRadius: 4,
                        yAxisID: 'y'
                    },
                    {
                        label: 'Sentence Length',
                        data: data2,
                        borderColor: '#06b6d4',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        borderDash: [5, 5],
                        tension: 0.3,
                        pointBackgroundColor: pointColors,
                        pointBorderColor: pointColors,
                        pointRadius: 4,
                        yAxisID: 'y1'
                    }
                ]
            },
            options: {
                ...commonOptions,
                scales: {
                    x: commonOptions.scales.x,
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        ticks: { color: '#8b949e' },
                        grid: { color: '#21262d' }
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        ticks: { color: '#8b949e' },
                        grid: { drawOnChartArea: false }
                    }
                }
            }
        });
    }

    function renderRatioChart(labels, profiles, featureNames) {
        const ctx = document.getElementById('chart-ratios');
        if (!ctx) return;
        
        if (ratioChart) ratioChart.destroy();

        const proIdx = featureNames.indexOf("pronoun_ratio");
        const prepIdx = featureNames.indexOf("preposition_ratio");
        const conjIdx = featureNames.indexOf("conjunction_ratio");
        
        const keyPro = featureNames[proIdx >= 0 ? proIdx : 2];
        const keyPrep = featureNames[prepIdx >= 0 ? prepIdx : 3];
        const keyConj = featureNames[conjIdx >= 0 ? conjIdx : 4];

        const dataPro = profiles.map(p => Array.isArray(p) ? p[proIdx >= 0 ? proIdx : 2] : p[keyPro] || 0);
        const dataPrep = profiles.map(p => Array.isArray(p) ? p[prepIdx >= 0 ? prepIdx : 3] : p[keyPrep] || 0);
        const dataConj = profiles.map(p => Array.isArray(p) ? p[conjIdx >= 0 ? conjIdx : 4] : p[keyConj] || 0);

        ratioChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Pronouns',
                        data: dataPro,
                        backgroundColor: 'rgba(124, 58, 237, 0.7)',
                    },
                    {
                        label: 'Prepositions',
                        data: dataPrep,
                        backgroundColor: 'rgba(6, 182, 212, 0.7)',
                    },
                    {
                        label: 'Conjunctions',
                        data: dataConj,
                        backgroundColor: 'rgba(167, 139, 250, 0.7)',
                    }
                ]
            },
            options: {
                ...commonOptions,
                scales: {
                    x: { stacked: true, ...commonOptions.scales.x },
                    y: { stacked: true, ...commonOptions.scales.y }
                }
            }
        });
    }

    function renderClusterChart(paragraphs, profiles, featureNames, yulesKIdx, sentLenIdx, pointColors) {
        const ctx = document.getElementById('chart-clusters');
        if (!ctx) return;
        
        if (clusterChart) clusterChart.destroy();

        const id1 = yulesKIdx >= 0 ? yulesKIdx : 0;
        const id2 = sentLenIdx >= 0 ? sentLenIdx : 1;
        const key1 = featureNames ? featureNames[id1] : null;
        const key2 = featureNames ? featureNames[id2] : null;

        const scatterData = paragraphs.map((p, i) => {
            const profile = profiles[i];
            const xVal = profile ? (Array.isArray(profile) ? profile[id1] : (key1 ? profile[key1] : 0)) : 0;
            const yVal = profile ? (Array.isArray(profile) ? profile[id2] : (key2 ? profile[key2] : 0)) : 0;
            return {
                x: xVal,
                y: yVal,
                label: `¶ ${i + 1}`,
                cluster: p.cluster_id != null ? p.cluster_id : 0
            };
        });

        clusterChart = new Chart(ctx, {
            type: 'scatter',
            data: {
                datasets: [{
                    label: 'Paragraphs',
                    data: scatterData,
                    backgroundColor: pointColors,
                    borderColor: pointColors,
                    pointRadius: paragraphs.map(p => (p.cluster_id === -1) ? 8 : 6),
                    pointHoverRadius: 10,
                }]
            },
            options: {
                ...commonOptions,
                plugins: {
                    ...commonOptions.plugins,
                    tooltip: {
                        ...commonOptions.plugins.tooltip,
                        callbacks: {
                            label: (context) => {
                                const pt = context.raw;
                                const clusterName = pt.cluster === -1 ? 'ANOMALY' : `Cluster ${pt.cluster}`;
                                return `${pt.label} (${clusterName}) - x: ${pt.x.toFixed(2)}, y: ${pt.y.toFixed(2)}`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        ...commonOptions.scales.x,
                        title: { display: true, text: 'Lexical Richness', color: '#8b949e' }
                    },
                    y: {
                        ...commonOptions.scales.y,
                        title: { display: true, text: 'Sentence Length', color: '#8b949e' }
                    }
                }
            }
        });
    }

    return { render };
})();
