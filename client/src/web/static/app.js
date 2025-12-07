/**
 * BSDS Web Interface JavaScript
 */

document.addEventListener('DOMContentLoaded', () => {
    initDataSource();
    initStopSearch();
    initSettings();
    initPreview();
    loadStatus();
});

// Data Source Configuration
function initDataSource() {
    // Radio button toggle
    document.querySelectorAll('input[name="data-mode"]').forEach(radio => {
        radio.addEventListener('change', (e) => {
            const mode = e.target.value;
            document.getElementById('gtfs-options').style.display =
                mode === 'gtfs' ? 'block' : 'none';
            document.getElementById('mint-options').style.display =
                mode === 'mint' ? 'block' : 'none';
        });
    });

    // Save data source button
    document.getElementById('save-data-source').addEventListener('click', saveDataSource);

    // Download GTFS button
    document.getElementById('download-gtfs').addEventListener('click', downloadGtfs);

    // Load initial GTFS status
    loadGtfsStatus();
}

async function saveDataSource() {
    const mode = document.querySelector('input[name="data-mode"]:checked').value;

    const data = { mode };

    if (mode === 'gtfs') {
        data.gtfs_url = document.getElementById('gtfs-url').value;
        data.gtfs_rt_url = document.getElementById('gtfs-rt-url').value;
    } else {
        data.mint_api_url = document.getElementById('mint-api-url').value;
        data.mint_system_id = document.getElementById('mint-system-id').value;
    }

    try {
        const response = await fetch('/api/config/data-source', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (response.ok) {
            showToast('Data source saved', 'success');
            // Clear current stop display since we switched modes
            document.getElementById('current-stop').innerHTML = '<em>No stop selected</em>';
            loadStatus();
            loadGtfsStatus();
        } else {
            const result = await response.json();
            showToast(result.error || 'Failed to save', 'error');
        }
    } catch (error) {
        console.error('Failed to save data source:', error);
        showToast('Failed to save data source', 'error');
    }
}

async function downloadGtfs() {
    const gtfsUrl = document.getElementById('gtfs-url').value;
    if (!gtfsUrl) {
        showToast('Please enter a GTFS URL first', 'error');
        return;
    }

    // Save the URL first
    await saveDataSource();

    const btn = document.getElementById('download-gtfs');
    const originalText = btn.textContent;
    btn.textContent = '⏳ Downloading...';
    btn.disabled = true;

    try {
        const response = await fetch('/api/gtfs/refresh', { method: 'POST' });
        const result = await response.json();

        if (result.success) {
            showToast('GTFS downloaded successfully!', 'success');
            loadGtfsStatus();
            refreshPreview();
        } else {
            showToast(result.error || 'Download failed', 'error');
        }
    } catch (error) {
        console.error('GTFS download failed:', error);
        showToast('Failed to download GTFS', 'error');
    } finally {
        btn.textContent = originalText;
        btn.disabled = false;
    }
}

async function loadGtfsStatus() {
    try {
        const response = await fetch('/api/gtfs/status');
        const status = await response.json();

        const statusText = document.getElementById('gtfs-status-text');
        if (status.mode === 'gtfs') {
            if (status.loaded) {
                statusText.textContent = `GTFS: ${status.stops_count} stops, ${status.routes_count} routes`;
                statusText.className = 'status-ok';
            } else {
                statusText.textContent = 'GTFS: Not loaded';
                statusText.className = 'status-warning';
            }
        }
    } catch (error) {
        console.error('Failed to load GTFS status:', error);
    }
}

// Stop Search
function initStopSearch() {
    const searchInput = document.getElementById('stop-search');
    const resultsDiv = document.getElementById('search-results');
    let debounceTimer;

    searchInput.addEventListener('input', (e) => {
        clearTimeout(debounceTimer);
        const query = e.target.value.trim();

        if (query.length < 2) {
            resultsDiv.classList.remove('visible');
            return;
        }

        debounceTimer = setTimeout(async () => {
            try {
                const response = await fetch(`/api/stops/search?q=${encodeURIComponent(query)}`);
                const data = await response.json();

                // Check for error
                if (data.error) {
                    resultsDiv.innerHTML = `<div class="search-result"><em>${data.error}</em></div>`;
                    resultsDiv.classList.add('visible');
                    return;
                }

                const stops = data;
                if (stops.length > 0) {
                    resultsDiv.innerHTML = stops.map(stop => `
                        <div class="search-result" data-id="${stop.id}" 
                             data-name="${stop.stop_name}" data-code="${stop.stop_code || stop.id}">
                            <div class="stop-name">${stop.stop_name}</div>
                            <div class="stop-code">${stop.stop_code || stop.id}</div>
                        </div>
                    `).join('');
                    resultsDiv.classList.add('visible');

                    // Add click handlers
                    resultsDiv.querySelectorAll('.search-result').forEach(el => {
                        el.addEventListener('click', () => selectStop(el));
                    });
                } else {
                    resultsDiv.innerHTML = '<div class="search-result"><em>No stops found</em></div>';
                    resultsDiv.classList.add('visible');
                }
            } catch (error) {
                console.error('Search failed:', error);
                showToast('Search failed', 'error');
            }
        }, 300);
    });

    // Hide results when clicking outside
    document.addEventListener('click', (e) => {
        if (!searchInput.contains(e.target) && !resultsDiv.contains(e.target)) {
            resultsDiv.classList.remove('visible');
        }
    });
}

async function selectStop(el) {
    const stopId = el.dataset.id;
    const stopName = el.dataset.name;
    const stopCode = el.dataset.code;

    try {
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                stop_id: stopId,  // String now
                stop_name: stopName
            })
        });

        if (response.ok) {
            // Update UI
            document.getElementById('current-stop').innerHTML = `
                <strong>${stopName}</strong>
                <span class="stop-code">(${stopCode})</span>
            `;
            document.getElementById('search-results').classList.remove('visible');
            document.getElementById('stop-search').value = '';

            // Refresh preview
            refreshPreview();
            showToast('Stop updated successfully', 'success');
        }
    } catch (error) {
        console.error('Failed to select stop:', error);
        showToast('Failed to update stop', 'error');
    }
}

// Settings
function initSettings() {
    document.getElementById('save-settings').addEventListener('click', saveSettings);
}

async function saveSettings() {
    const refreshInterval = document.getElementById('refresh-interval').value;
    const quietStart = document.getElementById('quiet-start').value;
    const quietEnd = document.getElementById('quiet-end').value;

    try {
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                refresh_interval_seconds: parseInt(refreshInterval),
                quiet_hours_start: quietStart || null,
                quiet_hours_end: quietEnd || null
            })
        });

        if (response.ok) {
            showToast('Settings saved', 'success');
            loadStatus();
        }
    } catch (error) {
        console.error('Failed to save settings:', error);
        showToast('Failed to save settings', 'error');
    }
}

// Preview
function initPreview() {
    document.getElementById('refresh-preview').addEventListener('click', refreshPreview);
    document.getElementById('update-display').addEventListener('click', updateDisplay);
}

function refreshPreview() {
    const img = document.getElementById('preview');
    img.src = `/api/preview?t=${Date.now()}`;
}

async function updateDisplay() {
    try {
        const response = await fetch('/api/refresh', { method: 'POST' });
        const result = await response.json();

        if (result.success) {
            showToast(`Display updated - ${result.arrivals_count} arrivals`, 'success');
            refreshPreview();
        } else {
            showToast(result.error || 'Update failed', 'error');
        }
    } catch (error) {
        console.error('Display update failed:', error);
        showToast('Failed to update display', 'error');
    }
}

// Status
async function loadStatus() {
    try {
        const response = await fetch('/api/status');
        const status = await response.json();

        document.getElementById('data-source-status').textContent =
            status.data_source_mode === 'gtfs' ? 'GTFS (Standalone)' : 'MINT API';
        document.getElementById('provider-status').textContent =
            status.provider_ready ? 'Ready' : 'Not loaded';
        document.getElementById('refresh-rate').textContent = status.refresh_interval;
    } catch (error) {
        console.error('Failed to load status:', error);
    }
}

// Toast Notifications
function showToast(message, type = 'info') {
    // Remove existing toast
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    // Show
    requestAnimationFrame(() => {
        toast.classList.add('visible');
    });

    // Hide after 3 seconds
    setTimeout(() => {
        toast.classList.remove('visible');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}
