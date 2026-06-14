/**
 * Home Page - Strategy Selection
 *
 * Loads available strategies from API and renders cards for user selection.
 * Handles navigation to scanner with strategy preset.
 */

const API_BASE = '/api';
const MODAL_ID = 'strategy-modal';

/**
 * Initialize home page on DOM load
 */
document.addEventListener('DOMContentLoaded', () => {
    console.log('Home page loaded');
    loadAndRenderStrategies();
});

/**
 * Load strategies from API and render cards
 */
async function loadAndRenderStrategies() {
    try {
        const response = await fetch(`${API_BASE}/strategies`);
        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }

        const data = await response.json();
        const strategies = data.strategies || [];

        if (!strategies || strategies.length === 0) {
            renderEmptyState();
            return;
        }

        renderStrategyCards(strategies);
    } catch (error) {
        console.error('Error loading strategies:', error);
        renderError(error.message);
    }
}

/**
 * Render strategy cards in grid
 * @param {Array} strategies - Array of strategy metadata objects
 */
function renderStrategyCards(strategies) {
    const grid = document.getElementById('strategies-grid');
    if (!grid) return;

    grid.innerHTML = ''; // Clear loading spinner

    strategies.forEach(strategy => {
        const card = createStrategyCard(strategy);
        grid.appendChild(card);
    });
}

/**
 * Create a single strategy card element
 * @param {Object} strategy - Strategy metadata
 * @returns {HTMLElement} Card element
 */
function createStrategyCard(strategy) {
    const card = document.createElement('div');
    card.className = 'strategy-card';
    card.setAttribute('data-strategy-id', strategy.id);

    const typeLabel = strategy.type === 'income' ? '💰 Income' :
                      strategy.type === 'directional' ? '📈 Directional' :
                      strategy.type === 'volatility' ? '⚡ Volatility' :
                      'Strategy';

    const colorStyle = strategy.color_hex ? `border-left: 4px solid ${strategy.color_hex};` : '';

    card.innerHTML = `
        <div class="strategy-card-header" style="${colorStyle}">
            <span class="icon">${strategy.icon}</span>
            <h3>${escapeHtml(strategy.name)}</h3>
        </div>
        <p class="description">${escapeHtml(strategy.description)}</p>
        <div class="specs">
            <span><strong>Type:</strong> ${typeLabel}</span>
            <span><strong>DTE:</strong> ${strategy.recommended_dte_min}-${strategy.recommended_dte_max} days</span>
            <span><strong>Delta:</strong> ${strategy.recommended_delta_min.toFixed(2)} to ${strategy.recommended_delta_max.toFixed(2)}</span>
            <span><strong>Position:</strong> ${capitalizeFirst(strategy.position_type)}</span>
        </div>
        <div class="actions">
            <button class="btn btn-select" onclick="selectStrategy('${strategy.id}')">
                Start Scanning
            </button>
            <button class="btn btn-learn" onclick="openResourceLink('${strategy.learn_url}')">
                Learn More
            </button>
        </div>
    `;

    return card;
}

/**
 * Select a strategy and navigate to scanner
 * @param {string} strategyId - Strategy ID (e.g., "CSP", "WHEEL")
 */
function selectStrategy(strategyId) {
    if (!strategyId) {
        console.error('Invalid strategy ID');
        return;
    }

    // Store selected strategy in session storage for scanner to read
    sessionStorage.setItem('selectedStrategy', strategyId);

    // Navigate to scanner
    window.location.href = `/scanner?strategy=${encodeURIComponent(strategyId)}`;
}

/**
 * Open educational resource link
 * @param {string} url - Resource URL
 */
function openResourceLink(url) {
    if (!url) {
        console.warn('No resource URL provided');
        return;
    }

    // Open in new tab
    window.open(url, '_blank');
}

/**
 * Render empty state when no strategies available
 */
function renderEmptyState() {
    const grid = document.getElementById('strategies-grid');
    if (!grid) return;

    grid.innerHTML = `
        <div class="loading-spinner">
            <p>No strategies available at this time.</p>
        </div>
    `;
}

/**
 * Render error state
 * @param {string} message - Error message
 */
function renderError(message) {
    const grid = document.getElementById('strategies-grid');
    if (!grid) return;

    grid.innerHTML = `
        <div class="loading-spinner" style="color: var(--danger);">
            <p>❌ Error loading strategies</p>
            <p style="font-size: 0.875rem; margin-top: 0.5rem;">${escapeHtml(message)}</p>
        </div>
    `;
}

/**
 * Close strategy detail modal
 */
function closeStrategyModal() {
    const modal = document.getElementById(MODAL_ID);
    if (modal) {
        modal.classList.add('hidden');
    }
}

/**
 * Escape HTML special characters for safe display
 * @param {string} text - Text to escape
 * @returns {string} Escaped text
 */
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
}

/**
 * Capitalize first letter of string
 * @param {string} str - String to capitalize
 * @returns {string} Capitalized string
 */
function capitalizeFirst(str) {
    if (!str) return '';
    return str.charAt(0).toUpperCase() + str.slice(1);
}

// Allow ESC key to close modal
document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
        closeStrategyModal();
    }
});
