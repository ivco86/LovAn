// ============ AI Gallery Frontend Application ============

// Global State
const state = {
    images: [],
    boards: [],
    tags: [],
    currentView: 'all',
    currentBoard: null,
    currentImage: null,
    searchQuery: '',
    stats: {},
    aiStyles: {},
    externalApps: {},
    selectedStyle: 'classic',
    pendingAnalyzeImageId: null,
    uploadFiles: [],
    similarImagesCache: new Map(),

    // Selection mode
    selectionMode: false,
    selectedImages: new Set(),

    // Operation locks
    isScanning: false,
    isAnalyzing: false,
    isUploading: false,

    // Sorting
    imageSort: 'date-desc'
};

// Constants
const CONFIG = {
    MIN_IMAGE_HEIGHT: 180,
    MAX_IMAGE_HEIGHT: 450,
    BASE_HEIGHT: 250,
    SEARCH_DEBOUNCE_MS: 300,
    TOAST_DURATION_MS: 5000,
    SIMILAR_IMAGES_LIMIT: 6,
    // Performance optimizations
    RENDER_BATCH_SIZE: 50,           // Render images in batches
    INTERSECTION_ROOT_MARGIN: '200px' // Pre-load images 200px before visible
};

// Lazy loading observer for images
let _imageObserver = null;

function getImageObserver() {
    if (!_imageObserver) {
        _imageObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    if (img.dataset.src) {
                        img.src = img.dataset.src;
                        img.removeAttribute('data-src');
                        _imageObserver.unobserve(img);
                    }
                }
            });
        }, {
            rootMargin: CONFIG.INTERSECTION_ROOT_MARGIN,
            threshold: 0.01
        });
    }
    return _imageObserver;
}

// Animation visibility observer - pauses animations on off-screen cards
let _animationObserver = null;

function getAnimationObserver() {
    if (!_animationObserver) {
        _animationObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.remove('offscreen');
                } else {
                    entry.target.classList.add('offscreen');
                }
            });
        }, {
            rootMargin: '100px',
            threshold: 0
        });
    }
    return _animationObserver;
}

// Clean up images before removing from DOM to prevent memory leaks
function cleanupGridImages(grid) {
    if (!grid) return;

    // Unobserve all images from IntersectionObserver
    const observer = getImageObserver();
    const images = grid.querySelectorAll('img');
    images.forEach(img => {
        observer.unobserve(img);
        // Clear image source to release memory
        img.src = '';
        img.removeAttribute('src');
        img.removeAttribute('data-src');
    });

    // Unobserve all cards from animation observer
    const animObserver = getAnimationObserver();
    const cards = grid.querySelectorAll('.image-card');
    cards.forEach(card => animObserver.unobserve(card));

    // Also clean up any video elements
    const videos = grid.querySelectorAll('video');
    videos.forEach(video => {
        video.pause();
        video.src = '';
        video.load();
    });
}

// ============ Initialization ============

document.addEventListener('DOMContentLoaded', () => {
    initializeApp();
    attachEventListeners();

    // Recalculate grid placeholders on window resize (debounced)
    let resizeTimeout;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(addGridPlaceholders, 150);
    });
});

async function initializeApp() {
    showLoading();

    // Check system health
    await checkHealth();

    // Load initial data (exclude YouTube videos from main view)
    await Promise.all([
        loadImages({ exclude_youtube: 'true' }),
        loadBoards(),
        loadTags(),
        loadExternalApps(),
        updateStats()
    ]);

    hideLoading();

    // Update UI
    renderImages();
    renderBoards();
    renderTagCloud();
    updateCounts();
}

// ============ API Calls ============

async function apiCall(endpoint, options = {}) {
    try {
        const response = await fetch(`/api${endpoint}`, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        });

        if (!response.ok) {
            let errorMessage = 'API request failed';

            try {
                const error = await response.json();
                errorMessage = error.error || error.message || errorMessage;
            } catch (e) {
                errorMessage = `HTTP ${response.status}: ${response.statusText}`;
            }

            throw new Error(errorMessage);
        }

        return await response.json();
    } catch (error) {
        console.error('API Error:', error);
        showToast(error.message, 'error');
        throw error;
    }
}

async function checkHealth() {
    try {
        const data = await apiCall('/health');

        // Update AI status indicator
        const statusEl = document.getElementById('aiStatus');
        if (data.ai_connected) {
            statusEl.textContent = '●';
            statusEl.title = 'AI Connected';
            statusEl.classList.add('connected');
        } else {
            statusEl.textContent = '●';
            statusEl.title = 'AI Offline';
            statusEl.classList.remove('connected');
        }

        state.stats = data.stats;
    } catch (error) {
        console.error('Health check failed:', error);
    }
}

async function loadImages(filters = {}) {
    try {
        const params = new URLSearchParams(filters);
        const data = await apiCall(`/images?${params}`);
        
        // Ensure images is always an array
        if (data && Array.isArray(data.images)) {
            state.images = data.images;
        } else {
            state.images = [];
        }
        
        return state.images;
    } catch (error) {
        console.error('Failed to load images:', error);
        state.images = [];
        return [];
    }
}

async function loadBoards() {
    try {
        const data = await apiCall('/boards');
        state.boards = data.boards;
        return data.boards;
    } catch (error) {
        console.error('Failed to load boards:', error);
        return [];
    }
}

async function loadTags() {
    try {
        const data = await apiCall('/tags');
        state.tags = data.tags;
        return data.tags;
    } catch (error) {
        console.error('Failed to load tags:', error);
        return [];
    }
}

async function updateStats() {
    try {
        const data = await apiCall('/health');
        state.stats = data.stats;
        updateCounts();
    } catch (error) {
        console.error('Failed to update stats:', error);
    }
}

async function loadAIStyles() {
    try {
        const data = await apiCall('/ai/styles');
        state.aiStyles = data.styles;
        return data.styles;
    } catch (error) {
        console.error('Failed to load AI styles:', error);
        return {};
    }
}

async function loadExternalApps() {
    try {
        const data = await apiCall('/external-apps');
        state.externalApps = data.apps;
        return data.apps;
    } catch (error) {
        console.error('Failed to load external apps:', error);
        return {};
    }
}

async function scanDirectory() {
    if (state.isScanning) {
        showToast('Scan already in progress', 'warning');
        return;
    }

    state.isScanning = true;
    const scanBtn = document.getElementById('scanBtn');
    const scanBtnEmpty = document.getElementById('scanBtnEmpty');
    const originalText = scanBtn ? scanBtn.textContent : '';

    if (scanBtn) {
        scanBtn.disabled = true;
        scanBtn.textContent = 'Scanning...';
    }
    if (scanBtnEmpty) {
        scanBtnEmpty.disabled = true;
        scanBtnEmpty.textContent = 'Scanning...';
    }

    try {
        const data = await apiCall('/scan', { method: 'POST' });
        showToast(`Found ${data.found} images, ${data.new} new`, 'success');

        await loadImages();
        await updateStats();
        renderImages();
    } catch (error) {
        showToast('Scan failed: ' + error.message, 'error');
    } finally {
        state.isScanning = false;
        if (scanBtn) {
            scanBtn.disabled = false;
            scanBtn.textContent = originalText;
        }
        if (scanBtnEmpty) {
            scanBtnEmpty.disabled = false;
            scanBtnEmpty.textContent = 'Scan Directory';
        }
    }
}

function openAIStyleModal(imageId, isBatchMode = false) {
    state.pendingAnalyzeImageId = imageId;
    state.isBatchAnalyze = isBatchMode;

    if (Object.keys(state.aiStyles).length === 0) {
        loadAIStyles().then(() => {
            renderAIStylesModal();
            document.getElementById('aiStyleModal').style.display = 'block';
        });
    } else {
        renderAIStylesModal();
        document.getElementById('aiStyleModal').style.display = 'block';
    }
}

function renderAIStylesModal() {
    const container = document.getElementById('styleSelection');
    if (!container) return;

    const stylesHTML = Object.entries(state.aiStyles).map(([key, style]) => `
        <label class="style-option" for="style-${key}">
            <input
                type="radio"
                id="style-${key}"
                name="aiStyle"
                value="${key}"
                ${state.selectedStyle === key ? 'checked' : ''}
            >
            <div class="style-info">
                <div class="style-name">${style.name}</div>
                <div class="style-description">${style.description}</div>
            </div>
        </label>
    `).join('');

    container.innerHTML = stylesHTML;

    container.querySelectorAll('input[name="aiStyle"]').forEach(radio => {
        radio.addEventListener('change', (e) => {
            state.selectedStyle = e.target.value;

            const customSection = document.getElementById('customPromptSection');
            if (e.target.value === 'custom') {
                customSection.style.display = 'block';
            } else {
                customSection.style.display = 'none';
            }

            container.querySelectorAll('.style-option').forEach(opt => {
                opt.classList.remove('selected');
            });
            e.target.closest('.style-option').classList.add('selected');
        });
    });
}

async function analyzeImage(imageId, style = null, customPrompt = null) {
    try {
        showToast('Analyzing image...', 'warning');

        const analyzeStyle = style || state.selectedStyle || 'classic';
        const requestBody = { style: analyzeStyle };

        if (analyzeStyle === 'custom' && customPrompt) {
            requestBody.custom_prompt = customPrompt;
        }

        const data = await apiCall(`/images/${imageId}/analyze`, {
            method: 'POST',
            body: JSON.stringify(requestBody)
        });

        // Update image in state
        const imageIndex = state.images.findIndex(img => img.id === imageId);
        if (imageIndex !== -1) {
            state.images[imageIndex].description = data.description;
            state.images[imageIndex].tags = data.tags;
            state.images[imageIndex].analyzed_at = new Date().toISOString();

            if (data.renamed && data.new_filename) {
                state.images[imageIndex].filename = data.new_filename;
            }
        }

        if (data.renamed) {
            showToast(`Analyzed & renamed to: ${data.new_filename}`, 'success');
        } else {
            showToast('Image analyzed successfully!', 'success');
        }

        // Update UI if modal is open
        if (state.currentImage && state.currentImage.id === imageId) {
            state.currentImage.description = data.description;
            state.currentImage.tags = data.tags;
            if (data.renamed && data.new_filename) {
                state.currentImage.filename = data.new_filename;
            }
            updateModal();
        }

        await updateStats();
        renderImages();

    } catch (error) {
        showToast('Analysis failed: ' + error.message, 'error');
        throw error;
    }
}

async function batchAnalyze(limit = 10) {
    if (state.isAnalyzing) {
        showToast('Analysis already in progress', 'warning');
        return;
    }

    state.isAnalyzing = true;
    const analyzeBtn = document.getElementById('analyzeBtn');
    const originalText = analyzeBtn.textContent;

    analyzeBtn.disabled = true;
    analyzeBtn.textContent = 'Analyzing...';

    try {
        showToast(`Analyzing up to ${limit} images...`, 'warning');

        const data = await apiCall(`/analyze-batch?limit=${limit}`, { method: 'POST' });

        if (data.renamed > 0) {
            showToast(`Analyzed ${data.analyzed} images, renamed ${data.renamed} files${data.failed ? `, ${data.failed} failed` : ''}`, 'success');
        } else {
            showToast(`Analyzed ${data.analyzed} images${data.failed ? `, ${data.failed} failed` : ''}`, 'success');
        }

        await loadImages();
        await updateStats();
        renderImages();

    } catch (error) {
        showToast('Batch analysis failed: ' + error.message, 'error');
    } finally {
        state.isAnalyzing = false;
        analyzeBtn.disabled = false;
        analyzeBtn.textContent = originalText;
    }
}

async function toggleFavorite(imageId) {
    try {
        const data = await apiCall(`/images/${imageId}/favorite`, { method: 'POST' });

        const imageIndex = state.images.findIndex(img => img.id === imageId);
        if (imageIndex !== -1) {
            state.images[imageIndex].is_favorite = data.is_favorite;
        }

        if (state.currentImage && state.currentImage.id === imageId) {
            state.currentImage.is_favorite = data.is_favorite;
            updateModal();
        }

        await updateStats();
        renderImages();

    } catch (error) {
        showToast('Failed to toggle favorite: ' + error.message, 'error');
    }
}

async function renameImage(imageId, newFilename) {
    try {
        const data = await apiCall(`/images/${imageId}/rename`, {
            method: 'POST',
            body: JSON.stringify({ new_filename: newFilename })
        });

        showToast('Image renamed successfully!', 'success');

        const imageIndex = state.images.findIndex(img => img.id === imageId);
        if (imageIndex !== -1) {
            state.images[imageIndex].filename = data.new_filename;
            state.images[imageIndex].filepath = data.new_filepath;
        }

        if (state.currentImage && state.currentImage.id === imageId) {
            state.currentImage.filename = data.new_filename;
            state.currentImage.filepath = data.new_filepath;
            updateModal();
        }

        renderImages();
    } catch (error) {
        showToast('Rename failed: ' + error.message, 'error');
    }
}

async function openWithApp(imageId, appId) {
    try {
        const data = await apiCall(`/images/${imageId}/open-with`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ app_id: appId })
        });

        showToast(`Opening ${data.file} with ${data.app}`, 'success');
    } catch (error) {
        showToast('Failed to open with external app: ' + error.message, 'error');
    }
}

function showOpenWithMenu(event, imageId, mediaType) {
    const apps = state.externalApps[mediaType] || [];

    if (apps.length === 0) {
        showToast('No external applications configured', 'warning');
        return;
    }

    // Create dropdown menu
    const menu = document.createElement('div');
    menu.className = 'open-with-menu';
    menu.innerHTML = apps.map(app => `
        <div class="open-with-item" data-app-id="${app.id}">
            <span>${escapeHtml(app.name)}</span>
        </div>
    `).join('');

    // Position and show menu
    const button = event.target.closest('button');
    const rect = button.getBoundingClientRect();
    menu.style.position = 'fixed';
    menu.style.top = `${rect.bottom + 5}px`;
    menu.style.left = `${rect.left}px`;
    menu.style.zIndex = '10001';

    // Add click handlers
    menu.addEventListener('click', async (e) => {
        const item = e.target.closest('.open-with-item');
        if (item) {
            const appId = item.dataset.appId;
            await openWithApp(imageId, appId);
            document.body.removeChild(menu);
        }
    });

    // Close menu on outside click
    const closeMenu = (e) => {
        if (!menu.contains(e.target) && !button.contains(e.target)) {
            if (document.body.contains(menu)) {
                document.body.removeChild(menu);
            }
            document.removeEventListener('click', closeMenu);
        }
    };

    setTimeout(() => {
        document.addEventListener('click', closeMenu);
    }, 100);

    document.body.appendChild(menu);
}

function editImage(imageId) {
    if (!state.currentImage) return;
    openEditImageModal();
}

function openEditImageModal() {
    if (!state.currentImage) return;

    const modal = document.getElementById('editImageModal');
    const filenameInput = document.getElementById('editImageFilename');
    const descriptionInput = document.getElementById('editImageDescription');
    const tagsContainer = document.getElementById('editTagsContainer');

    // Populate current values
    filenameInput.value = state.currentImage.filename;
    descriptionInput.value = state.currentImage.description || '';

    // Store current tags in a temporary state
    state.editingTags = [...(state.currentImage.tags || [])];

    // Render tags
    renderEditTags();

    modal.style.display = 'block';
}

function closeEditImageModal() {
    closeModal('editImageModal', () => {
        state.editingTags = null;
    });
}

function renderEditTags() {
    const tagsContainer = document.getElementById('editTagsContainer');

    if (!state.editingTags || state.editingTags.length === 0) {
        tagsContainer.innerHTML = '<span style="color: var(--text-muted); font-size: 13px;">No tags yet</span>';
        return;
    }

    tagsContainer.innerHTML = state.editingTags.map(tag => `
        <span class="tag" style="display: flex; align-items: center; gap: 4px;">
            ${escapeHtml(tag)}
            <span onclick="removeEditTag('${escapeHtml(tag)}')" style="cursor: pointer; font-weight: bold;">×</span>
        </span>
    `).join('');
}

function addEditTag(tagName) {
    if (!tagName || !tagName.trim()) return;

    const trimmedTag = tagName.trim();

    // Check if tag already exists
    if (state.editingTags.includes(trimmedTag)) {
        showToast('Tag already exists', 'warning');
        return;
    }

    state.editingTags.push(trimmedTag);
    renderEditTags();

    // Clear input
    document.getElementById('editImageNewTag').value = '';
}

function removeEditTag(tagName) {
    state.editingTags = state.editingTags.filter(t => t !== tagName);
    renderEditTags();
}

async function saveImageEdit() {
    if (!state.currentImage) return;

    const imageId = state.currentImage.id;
    const newFilename = document.getElementById('editImageFilename').value.trim();
    const newDescription = document.getElementById('editImageDescription').value.trim();
    const newTags = state.editingTags || [];

    if (!newFilename) {
        showToast('Filename is required', 'error');
        return;
    }

    try {
        // Update filename if changed
        if (newFilename !== state.currentImage.filename) {
            await renameImage(imageId, newFilename);
        }

        // Update description and tags
        await apiCall(`/images/${imageId}`, {
            method: 'PATCH',
            body: JSON.stringify({
                description: newDescription,
                tags: newTags
            })
        });

        showToast('Image updated successfully!', 'success');

        // Refresh current image and reload
        await loadImages();

        // Reopen the image modal with updated data
        const updatedImage = state.images.find(img => img.id === imageId);
        if (updatedImage) {
            await openImageModal(updatedImage);
        }

        closeEditImageModal();
    } catch (error) {
        showToast('Failed to update image: ' + error.message, 'error');
    }
}

async function searchImages(query) {
    if (!query.trim()) {
        await loadImages();
        renderImages();
        updateBreadcrumb('All Images');
        return;
    }

    try {
        const useAI = document.getElementById('ai-search-toggle')?.checked || false;
        const searchInput = document.getElementById('searchInput');
        const aiToggle = document.querySelector('.ai-toggle');
        let data;

        if (useAI) {
            // Show loading state for AI search
            if (searchInput) searchInput.disabled = true;
            if (aiToggle) {
                aiToggle.classList.add('ai-searching');
                aiToggle.innerHTML = '<span class="spinner-small"></span> Searching...';
            }

            // --- НОВАТА AI ЛОГИКА ---
            console.log("Използвам AI търсене...");
            try {
                data = await apiCall('/search/semantic', {
                    method: 'POST',
                    body: JSON.stringify({
                        query: query,
                        top_k: 20
                    })
                });
            } finally {
                // Restore AI toggle state
                if (searchInput) searchInput.disabled = false;
                if (aiToggle) {
                    aiToggle.classList.remove('ai-searching');
                    aiToggle.innerHTML = '<label><input type="checkbox" id="ai-search-toggle" checked> ✨ AI</label>';
                }
            }
            // AI endpoint връща results директно
            console.log("AI търсене резултати:", data);

            // Нормализиране на данните - уверяваме се че tags е масив
            const results = (data.results || []).map(img => {
                // Ако tags е string, парсваме го
                if (typeof img.tags === 'string') {
                    try {
                        img.tags = JSON.parse(img.tags);
                    } catch (e) {
                        img.tags = [];
                    }
                }
                // Ако tags не съществува, задаваме празен масив
                if (!Array.isArray(img.tags)) {
                    img.tags = [];
                }
                return img;
            });

            state.images = results;
            if (state.images.length === 0) {
                console.warn("AI търсенето не върна резултати.");
                // Проверяваме дали има специфично съобщение от сървъра
                if (data.message) {
                    showToast(data.message, 'warning');
                } else if (data.error) {
                    showToast(data.error, 'error');
                } else {
                    // Предлагаме алтернативи
                    const suggestions = [
                        'Try a different search term',
                        'Make sure images are analyzed (embeddings generated)',
                        'Try searching in English for better results'
                    ];
                    showToast(`No results found. ${suggestions[0]}.`, 'warning');
                }
            } else {
                // Показваме similarity scores в конзолата
                const similarities = results.map(r => r.similarity || 0).filter(s => s > 0);
                if (similarities.length > 0) {
                    const maxSim = Math.max(...similarities);
                    const minSim = Math.min(...similarities);
                    console.log(`AI търсенето намери ${state.images.length} резултата (similarity: ${minSim.toFixed(3)} - ${maxSim.toFixed(3)})`);
                } else {
                    console.log(`AI търсенето намери ${state.images.length} резултата`);
                }
            }
        } else {
            // --- СТАРАТА ЛОГИКА ---
            console.log("Използвам стандартно търсене...");
            data = await apiCall(`/images/search?q=${encodeURIComponent(query)}`);
            state.images = data.results || [];
        }

        state.searchQuery = query;
        renderImages();
        updateBreadcrumb(`Search: "${query}"${useAI ? ' (AI)' : ''}`);
    } catch (error) {
        console.error('Search error:', error);
        showToast('Search failed: ' + error.message, 'error');
        // При грешка, покажи всички снимки
        await loadImages();
        renderImages();
        updateBreadcrumb('All Images');
    }
}

async function searchByTag(tag) {
    await searchImages(tag);

    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.value = tag;
    }
}

async function createBoard(name, description, parentId) {
    try {
        const data = await apiCall('/boards', {
            method: 'POST',
            body: JSON.stringify({
                name: name,
                description: description,
                parent_id: parentId || null
            })
        });

        showToast('Board created successfully!', 'success');

        await loadBoards();
        renderBoards();
        await updateStats();

        return data.board_id;
    } catch (error) {
        showToast('Failed to create board: ' + error.message, 'error');
        throw error;
    }
}

async function loadBoard(boardId) {
    try {
        const data = await apiCall(`/boards/${boardId}`);
        state.currentBoard = data;
        state.images = data.images;
        renderImages();
        updateBreadcrumb(data.name);
    } catch (error) {
        showToast('Failed to load board: ' + error.message, 'error');
    }
}

async function addImageToBoard(boardId, imageId) {
    try {
        await apiCall(`/boards/${boardId}/images`, {
            method: 'POST',
            body: JSON.stringify({ image_id: imageId })
        });
        return true;
    } catch (error) {
        console.error('Failed to add image to board:', error);
        return false;
    }
}

async function removeImageFromBoard(boardId, imageId) {
    try {
        await apiCall(`/boards/${boardId}/images`, {
            method: 'DELETE',
            body: JSON.stringify({ image_id: imageId })
        });
        return true;
    } catch (error) {
        console.error('Failed to remove image from board:', error);
        return false;
    }
}

async function renameBoard(boardId, newName, newDescription) {
    try {
        const data = await apiCall(`/boards/${boardId}`, {
            method: 'PUT',
            body: JSON.stringify({
                name: newName,
                description: newDescription
            })
        });

        showToast('Board renamed successfully!', 'success');

        await loadBoards();
        renderBoards();

        return true;
    } catch (error) {
        showToast('Failed to rename board: ' + error.message, 'error');
        return false;
    }
}

async function deleteBoard(boardId, deleteSubBoards = false) {
    try {
        const params = new URLSearchParams({ delete_sub_boards: deleteSubBoards });
        await apiCall(`/boards/${boardId}?${params}`, {
            method: 'DELETE'
        });

        showToast('Board deleted successfully!', 'success');

        await loadBoards();
        renderBoards();
        await updateStats();

        // If currently viewing the deleted board, switch to all images
        if (state.currentBoard && state.currentBoard.id === boardId) {
            switchView('all');
        }

        return true;
    } catch (error) {
        showToast('Failed to delete board: ' + error.message, 'error');
        return false;
    }
}

async function mergeBoards(sourceBoardId, targetBoardId, deleteSource = true) {
    try {
        const data = await apiCall(`/boards/${sourceBoardId}/merge`, {
            method: 'POST',
            body: JSON.stringify({
                target_board_id: targetBoardId,
                delete_source: deleteSource
            })
        });

        showToast(`Board merged successfully! Moved ${data.images_moved} images.`, 'success');

        await loadBoards();
        renderBoards();
        await updateStats();

        // If currently viewing the source board, switch to target board
        if (state.currentBoard && state.currentBoard.id === sourceBoardId) {
            switchView('board', targetBoardId);
        }

        return true;
    } catch (error) {
        showToast('Failed to merge boards: ' + error.message, 'error');
        return false;
    }
}

async function getImageDetails(imageId) {
    try {
        const data = await apiCall(`/images/${imageId}`);
        return data;
    } catch (error) {
        console.error('Failed to get image details:', error);
        return null;
    }
}

async function loadSimilarImages(imageId) {
    const container = document.getElementById('similarImages');
    if (!container) return;

    // Check cache first
    if (state.similarImagesCache.has(imageId)) {
        const cached = state.similarImagesCache.get(imageId);
        renderSimilarImagesInContainer(container, cached, imageId);
        return;
    }

    container.innerHTML = '<span class="tags-placeholder">Loading...</span>';

    try {
        const data = await apiCall(`/images/${imageId}/similar?limit=${CONFIG.SIMILAR_IMAGES_LIMIT}`);

        const similarImages = data.similar || [];
        state.similarImagesCache.set(imageId, similarImages);

        renderSimilarImagesInContainer(container, similarImages, imageId);
    } catch (error) {
        console.error('Failed to load similar images:', error);
        container.innerHTML = '<span class="tags-placeholder">Failed to load similar images</span>';
    }
}

function renderSimilarImagesInContainer(container, similarImages) {
    if (similarImages.length > 0) {
        container.innerHTML = similarImages.map(img => `
            <div class="similar-image-thumb" data-image-id="${img.id}">
                <img src="/api/images/${img.id}/thumbnail?size=400" alt="${escapeHtml(img.filename)}" loading="lazy">
            </div>
        `).join('');

        // ✅ Event delegation for similar image clicks
        container.onclick = async (e) => {
            const thumb = e.target.closest('.similar-image-thumb');
            if (thumb) {
                e.stopPropagation();
                const imageId = parseInt(thumb.dataset.imageId);
                const imageDetails = await getImageDetails(imageId);
                if (imageDetails) {
                    openImageModal(imageDetails);
                }
            }
        };
    } else {
        container.innerHTML = '<span class="tags-placeholder">No similar images found</span>';
    }
}

// ============ UI Rendering ============

function getConsistentHeight(imageId, width, height) {
    if (!width || !height) {
        const heights = [200, 250, 280, 320, 350, 400];
        return heights[imageId % heights.length];
    }

    const aspectRatio = height / width;
    let imageHeight = Math.floor(CONFIG.BASE_HEIGHT * aspectRatio);

    return Math.max(CONFIG.MIN_IMAGE_HEIGHT, Math.min(CONFIG.MAX_IMAGE_HEIGHT, imageHeight));
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function renderImages() {
    const grid = document.getElementById('imageGrid');
    const emptyState = document.getElementById('emptyState');

    if (!grid || !emptyState) {
        console.error('Image grid or empty state element not found');
        return;
    }

    if (!state.images || state.images.length === 0) {
        grid.style.display = 'none';
        emptyState.style.display = 'flex';
        return;
    }

    // Ensure grid is visible before rendering
    grid.style.display = 'block';
    emptyState.style.display = 'none';

    try {
        // Sort images before rendering
        const sortedImages = sortImages([...state.images], state.imageSort);

        // OPTIMIZED: Use DocumentFragment for faster DOM updates
        const fragment = document.createDocumentFragment();
        const tempContainer = document.createElement('div');

        // For large galleries, render in batches
        if (sortedImages.length > CONFIG.RENDER_BATCH_SIZE) {
            // IMPORTANT: Clean up old images before clearing to prevent memory leaks
            cleanupGridImages(grid);
            grid.innerHTML = '';

            // Render first batch immediately
            const firstBatch = sortedImages.slice(0, CONFIG.RENDER_BATCH_SIZE);
            tempContainer.innerHTML = firstBatch.map(image => createImageCard(image, true)).join('');
            while (tempContainer.firstChild) {
                fragment.appendChild(tempContainer.firstChild);
            }
            grid.appendChild(fragment);

            // Setup lazy loading for images
            setupLazyLoading(grid);

            // Render remaining batches asynchronously
            if (sortedImages.length > CONFIG.RENDER_BATCH_SIZE) {
                renderRemainingBatches(grid, sortedImages.slice(CONFIG.RENDER_BATCH_SIZE));
            }
        } else {
            // Small gallery - render all at once
            tempContainer.innerHTML = sortedImages.map(image => createImageCard(image, true)).join('');
            while (tempContainer.firstChild) {
                fragment.appendChild(tempContainer.firstChild);
            }
            // IMPORTANT: Clean up old images before clearing to prevent memory leaks
            cleanupGridImages(grid);
            grid.innerHTML = '';
            grid.appendChild(fragment);
            setupLazyLoading(grid);
        }

        // Add placeholders to fill empty spaces in last row
        requestAnimationFrame(() => addGridPlaceholders());
    } catch (error) {
        console.error('Error rendering images:', error);
        grid.style.display = 'none';
        emptyState.style.display = 'flex';
    }
}

function renderRemainingBatches(grid, remainingImages) {
    /**
     * Render remaining images in batches using requestIdleCallback
     * This prevents UI blocking for large galleries
     */
    let index = 0;

    function renderBatch(deadline) {
        const fragment = document.createDocumentFragment();
        const tempContainer = document.createElement('div');

        // Render as many as we can in this idle period
        while (index < remainingImages.length &&
               (deadline.timeRemaining() > 5 || deadline.didTimeout)) {
            const batchEnd = Math.min(index + 10, remainingImages.length);
            const batch = remainingImages.slice(index, batchEnd);
            tempContainer.innerHTML = batch.map(image => createImageCard(image, true)).join('');

            while (tempContainer.firstChild) {
                fragment.appendChild(tempContainer.firstChild);
            }
            index = batchEnd;
        }

        grid.appendChild(fragment);
        setupLazyLoading(grid);

        // Continue if there are more images
        if (index < remainingImages.length) {
            requestIdleCallback(renderBatch, { timeout: 100 });
        } else {
            // All batches done - add placeholders
            addGridPlaceholders();
        }
    }

    // Use requestIdleCallback if available, otherwise setTimeout
    if ('requestIdleCallback' in window) {
        requestIdleCallback(renderBatch, { timeout: 100 });
    } else {
        setTimeout(() => {
            const tempContainer = document.createElement('div');
            tempContainer.innerHTML = remainingImages.map(image => createImageCard(image, true)).join('');
            while (tempContainer.firstChild) {
                grid.appendChild(tempContainer.firstChild);
            }
            setupLazyLoading(grid);
            addGridPlaceholders(); // Add placeholders after rendering
        }, 0);
    }
}

function addGridPlaceholders() {
    /**
     * Add placeholder cards to fill empty spaces in the last row of the grid
     * This prevents layout issues when the number of items doesn't fill the row
     */
    const grid = document.getElementById('imageGrid');
    if (!grid) return;

    // Remove existing placeholders
    grid.querySelectorAll('.image-card-placeholder').forEach(p => p.remove());

    // Get the number of real image cards
    const realCards = grid.querySelectorAll('.image-card');
    if (realCards.length === 0) return;

    // Calculate how many columns fit in the grid
    const gridStyle = window.getComputedStyle(grid);
    const gridColumns = gridStyle.gridTemplateColumns.split(' ').length;

    // Calculate how many placeholders needed to fill the last row
    const remainder = realCards.length % gridColumns;
    const placeholdersNeeded = remainder === 0 ? 0 : gridColumns - remainder;

    // Add placeholder cards
    for (let i = 0; i < placeholdersNeeded; i++) {
        const placeholder = document.createElement('div');
        placeholder.className = 'image-card-placeholder';
        grid.appendChild(placeholder);
    }
}

function setupLazyLoading(container) {
    /**
     * Setup IntersectionObserver for lazy loading images
     */
    const observer = getImageObserver();
    const lazyImages = container.querySelectorAll('img[data-src]');
    lazyImages.forEach(img => observer.observe(img));

    // Also setup animation observer for image cards
    const animObserver = getAnimationObserver();
    const cards = container.querySelectorAll('.image-card');
    cards.forEach(card => animObserver.observe(card));
}

function sortImages(images, sortType) {
    const sorted = [...images];

    switch (sortType) {
        case 'date-desc':
            sorted.sort((a, b) => {
                const dateA = new Date(a.created_at || 0);
                const dateB = new Date(b.created_at || 0);
                return dateB - dateA; // Newest first
            });
            break;
        case 'date-asc':
            sorted.sort((a, b) => {
                const dateA = new Date(a.created_at || 0);
                const dateB = new Date(b.created_at || 0);
                return dateA - dateB; // Oldest first
            });
            break;
        case 'name-asc':
            sorted.sort((a, b) => a.filename.localeCompare(b.filename));
            break;
        case 'name-desc':
            sorted.sort((a, b) => b.filename.localeCompare(a.filename));
            break;
        case 'size-desc':
            sorted.sort((a, b) => (b.file_size || 0) - (a.file_size || 0));
            break;
        case 'size-asc':
            sorted.sort((a, b) => (a.file_size || 0) - (b.file_size || 0));
            break;
    }

    return sorted;
}

function createImageCard(image, useLazyLoading = false) {
    /**
     * Create HTML for an image card
     * @param {Object} image - Image data object
     * @param {boolean} useLazyLoading - Use data-src for IntersectionObserver lazy loading
     */
    const favoriteClass = image.is_favorite ? 'active' : '';
    const isVideo = image.media_type === 'video';

    // Check if image has been analyzed (has tags or description)
    const isAnalyzed = image.tags && image.tags.length > 0;
    const statusIconClass = isAnalyzed ? 'status-icon-analyzed' : 'status-icon-pending';
    const statusIcon = isAnalyzed ? '✓' : '✗';

    const description = image.description || 'No description yet';
    const tags = image.tags.slice(0, 3);

    // Check if image is selected
    const isSelected = state.selectedImages.has(image.id);
    const checkboxClass = isSelected ? 'checked' : '';
    const selectedClass = isSelected ? 'selected' : '';

    // OPTIMIZED: Use data-src for lazy loading with IntersectionObserver
    const thumbUrl = `/api/images/${image.id}/thumbnail?size=500`;
    // Add aspect-ratio to style to prevent layout shift in Masonry layout
    const styleAttr = (image.width && image.height) 
        ? `style="aspect-ratio: ${image.width}/${image.height};"` 
        : '';
        
    const imgSrcAttr = useLazyLoading
        ? `data-src="${thumbUrl}" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1 1'%3E%3C/svg%3E"`
        : `src="${thumbUrl}"`;

    return `
        <div class="image-card ${selectedClass}" data-id="${image.id}" data-media-type="${image.media_type || 'image'}"
             draggable="true">
            <div class="image-card-checkbox ${checkboxClass}" data-id="${image.id}"></div>
            <div class="image-card-status-icon ${statusIconClass}">${statusIcon}</div>
            ${isVideo ?
            `<div class="image-card-video-wrapper" data-image-id="${image.id}">
                    <img
                        class="image-card-image"
                        ${imgSrcAttr}
                        ${styleAttr}
                        alt="${escapeHtml(image.filename)}"
                        loading="lazy"
                    >
                    <div class="video-play-overlay">
                        <div class="video-play-icon">▶</div>
                        <div class="video-icon-label">VIDEO</div>
                    </div>
                </div>` :
            `<img
                    class="image-card-image"
                    ${imgSrcAttr}
                    ${styleAttr}
                    alt="${escapeHtml(image.filename)}"
                    loading="lazy"
                >`
        }
            <div class="image-card-content">
                <div class="image-card-header">
                    <div class="image-card-filename">${escapeHtml(image.filename)}</div>
                    <div class="image-card-favorite ${favoriteClass}">⭐</div>
                </div>
                <div class="image-card-description">${escapeHtml(description)}</div>
                <div class="image-card-tags">
                    ${tags.map(tag => `<span class="tag" data-tag="${escapeHtml(tag)}">${escapeHtml(tag)}</span>`).join('')}
                    ${image.tags.length > 3 ? `<span class="tag">+${image.tags.length - 3}</span>` : ''}
                    ${image.similarity !== undefined ? `<span class="tag" style="background: var(--accent-pink); color: white;" title="AI Similarity Score">${(image.similarity * 100).toFixed(0)}%</span>` : ''}
                </div>
            </div>
        </div>
    `;
}

function renderBoards() {
    const boardsList = document.getElementById('boardsList');
    const boardParentSelect = document.getElementById('boardParent');

    if (state.boards.length === 0) {
        boardsList.innerHTML = '<li style="color: var(--text-muted); padding: var(--spacing-sm);">No boards yet</li>';
        boardParentSelect.innerHTML = '<option value="">-- Top Level --</option>';
        return;
    }

    boardsList.innerHTML = state.boards.map(board => createBoardItem(board)).join('');

    boardParentSelect.innerHTML = '<option value="">-- Top Level --</option>' +
        state.boards.map(board => createBoardOption(board)).join('');
}

function renderTagCloud() {
    const tagCloud = document.getElementById('tagCloud');

    if (!state.tags || state.tags.length === 0) {
        tagCloud.innerHTML = '<span style="color: var(--text-muted); font-size: 0.75rem;">No tags yet</span>';
        return;
    }

    // Take top 20 tags
    const topTags = state.tags.slice(0, 20);

    // Find min/max counts for sizing
    const counts = topTags.map(t => t.count);
    const minCount = Math.min(...counts);
    const maxCount = Math.max(...counts);

    // Assign size class based on count
    const getTagSize = (count) => {
        if (maxCount === minCount) return 'tag-size-md';

        const ratio = (count - minCount) / (maxCount - minCount);
        if (ratio >= 0.8) return 'tag-size-xl';
        if (ratio >= 0.6) return 'tag-size-lg';
        if (ratio >= 0.4) return 'tag-size-md';
        if (ratio >= 0.2) return 'tag-size-sm';
        return 'tag-size-xs';
    };

    tagCloud.innerHTML = topTags.map(tagData => {
        const sizeClass = getTagSize(tagData.count);
        return `
            <span class="tag-cloud-item ${sizeClass}" data-tag="${escapeHtml(tagData.tag)}">
                ${escapeHtml(tagData.tag)}
                <span class="tag-cloud-count">${tagData.count}</span>
            </span>
        `;
    }).join('');

    // Add event delegation for tag cloud clicks
    // Clone to remove old listeners
    const tagCloudClone = tagCloud.cloneNode(true);
    tagCloud.parentNode.replaceChild(tagCloudClone, tagCloud);

    tagCloudClone.addEventListener('click', (e) => {
        const item = e.target.closest('.tag-cloud-item[data-tag]');
        if (item) {
            const tagValue = item.dataset.tag;
            searchByTag(tagValue);
        }
    });
}

function createBoardItem(board, isSubBoard = false) {
    const imageCount = board.image_count || 0;
    const hasSubBoards = board.sub_boards && board.sub_boards.length > 0;

    // Get gradient colors based on board name hash
    const gradients = [
        ['#ff006e', '#7b2cbf'],
        ['#00f5d4', '#7b2cbf'],
        ['#ff006e', '#00f5d4'],
        ['#7b2cbf', '#ff006e'],
        ['#c1121f', '#ff006e'],
        ['#00f5d4', '#c1121f']
    ];
    const hash = board.name.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
    const [color1, color2] = gradients[hash % gradients.length];

    let html = `
        <div class="board-pill ${hasSubBoards ? 'has-children' : ''}"
             data-board-id="${board.id}"
             data-has-children="${hasSubBoards}"
             data-drop-target="true"
             style="background: linear-gradient(135deg, ${color1}, ${color2});">
            <span class="board-pill-name">${escapeHtml(board.name)}</span>
            <span class="board-pill-count">${imageCount}</span>
            ${hasSubBoards ? '<span class="board-pill-expand">▼</span>' : ''}
        </div>
    `;

    if (hasSubBoards) {
        html += `<div class="board-sub-pills" data-parent-id="${board.id}" style="display: none;">`;
        html += board.sub_boards.map(sub => createBoardItem(sub, true)).join('');
        html += `</div>`;
    }

    return html;
}

function createBoardOption(board, prefix = '') {
    let html = `<option value="${board.id}">${prefix}${escapeHtml(board.name)}</option>`;

    if (board.sub_boards && board.sub_boards.length > 0) {
        html += board.sub_boards.map(sub => createBoardOption(sub, prefix + '  ')).join('');
    }

    return html;
}

function updateCounts() {
    const allCount = document.getElementById('allCount');
    const favCount = document.getElementById('favCount');
    const unanalyzedCount = document.getElementById('unanalyzedCount');
    const videosCount = document.getElementById('videosCount');
    const statTotal = document.getElementById('statTotal');
    const statAnalyzed = document.getElementById('statAnalyzed');
    const statBoards = document.getElementById('statBoards');

    if (allCount) allCount.textContent = state.stats.total_images || 0;
    if (favCount) favCount.textContent = state.stats.favorite_images || 0;
    if (unanalyzedCount) unanalyzedCount.textContent = state.stats.unanalyzed_images || 0;
    if (videosCount) videosCount.textContent = state.stats.video_count || 0;
    if (statTotal) statTotal.textContent = state.stats.total_images || 0;
    if (statAnalyzed) statAnalyzed.textContent = state.stats.analyzed_images || 0;
    if (statBoards) statBoards.textContent = state.stats.total_boards || 0;
}

function updateBreadcrumb(text) {
    const breadcrumb = document.getElementById('breadcrumb');
    if (breadcrumb) {
        breadcrumb.innerHTML = `<span class="breadcrumb-item">${escapeHtml(text)}</span>`;
    }
}

// ============ View Switching ============

async function switchView(view, param = null) {
    state.currentView = view;
    state.currentBoard = null;
    state.searchQuery = '';

    // Update active state for category pills
    document.querySelectorAll('.category-pill').forEach(pill => {
        pill.classList.remove('active');
    });
    
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });

    showLoading();

    try {
        switch (view) {
            case 'all':
                await loadImages({ exclude_youtube: 'true' });
                updateBreadcrumb('All Images');
                const allView = document.querySelector('[data-view="all"]');
                if (allView) allView.classList.add('active');
                break;

            case 'favorites':
                await loadImages({ favorites: 'true' });
                updateBreadcrumb('Favorites');
                const favView = document.querySelector('[data-view="favorites"]');
                if (favView) favView.classList.add('active');
                break;

            case 'unanalyzed':
                await loadImages({ analyzed: 'false' });
                updateBreadcrumb('Unanalyzed');
                const unanalyzedView = document.querySelector('[data-view="unanalyzed"]');
                if (unanalyzedView) unanalyzedView.classList.add('active');
                break;

            case 'videos':
                await loadImages({ media_type: 'video', exclude_youtube: 'true' });
                updateBreadcrumb('Videos');
                const videosView = document.querySelector('[data-view="videos"]');
                if (videosView) videosView.classList.add('active');
                break;

            case 'youtube':
                await loadImages({ media_type: 'video', youtube_only: 'true' });
                updateBreadcrumb('YouTube Videos');
                const youtubeView = document.querySelector('[data-view="youtube"]');
                if (youtubeView) youtubeView.classList.add('active');
                break;

            case 'board':
                await loadBoard(param);
                const boardItem = document.querySelector(`[data-board-id="${param}"]`);
                if (boardItem) boardItem.classList.add('active');
                break;
        }

        // Always render images, even if empty
        renderImages();
    } catch (error) {
        console.error('Error switching view:', error);
        showToast('Failed to load view: ' + error.message, 'error');
        // Ensure we show something even on error
        state.images = [];
        renderImages();
    } finally {
        hideLoading();
    }
}

// ============ Modal Management ============

async function openImageModal(image) {
    state.currentImage = image;

    const fullDetails = await getImageDetails(image.id);
    if (fullDetails) {
        state.currentImage = fullDetails;
    }

    const modal = document.getElementById('imageModal');
    modal.style.display = 'block';

    updateModal();
}

function updateModal() {
    const image = state.currentImage;
    const modal = document.getElementById('imageModal');
    const modalBody = modal.querySelector('.modal-body');

    // IMPORTANT: Clean up any existing video before replacing content to prevent memory leaks
    const existingVideo = modalBody.querySelector('video');
    if (existingVideo) {
        existingVideo.pause();
        existingVideo.removeAttribute('src');
        existingVideo.load();
        // Remove track elements
        existingVideo.querySelectorAll('track').forEach(t => t.remove());
    }

    const statusText = image.analyzed_at ? 'Analyzed' : 'Pending Analysis';
    const statusIcon = image.analyzed_at ? '✅' : '⏳';
    const isVideo = image.media_type === 'video';

    // Media viewer (image or video)
    const mediaViewer = isVideo
        ? `<video controls id="modalVideoPlayer" style="width: 100%; max-height: 86vh; object-fit: contain;">
               <source src="/api/images/${image.id}/file" type="video/mp4">
               Your browser does not support video playback.
           </video>
           <div id="subtitlePanelContainer"></div>`
        : `<img src="/api/images/${image.id}/file" alt="${escapeHtml(image.filename)}">`;

    const mediaTypeIcon = isVideo ? '🎬' : '📄';
    const mediaTypeText = isVideo ? 'Video' : 'Image';

    modalBody.innerHTML = `
        <div class="image-detail-container">
            <div class="image-main-view">
                ${mediaViewer}
            </div>

            <div class="image-info-panel">
                <div class="detail-section title-section">
                    <h2>${escapeHtml(image.title || image.filename)}</h2>
                    <span class="status-badge">
                        <span class="status-icon">${statusIcon}</span>
                        ${statusText}
                    </span>
                </div>

                <div class="detail-section description-section">
                    <h3>Description</h3>
                    <p class="${!image.description ? 'description-placeholder' : ''}">
                        ${escapeHtml(image.description || 'No description yet. Click analyze to generate.')}
                    </p>
                </div>

                <div class="detail-section tags-section">
                    <h3>Tags</h3>
                    <div class="tags-container">
                        ${image.tags && image.tags.length > 0
            ? image.tags.map(tag => `<span class="tag" data-tag="${escapeHtml(tag)}">${escapeHtml(tag)}</span>`).join('')
            : '<span class="tags-placeholder">No tags yet</span>'
        }
                    </div>
                </div>

                <div class="detail-section boards-section">
                    <h3>Boards</h3>
                    <div class="boards-container">
                        ${image.boards && image.boards.length > 0
            ? image.boards.map(board => `<span class="tag">${escapeHtml(board.name)}</span>`).join('')
            : '<div class="boards-placeholder">Not in any boards</div>'
        }
                    </div>
                </div>

                <div class="detail-section metadata-section">
                    <h3>Metadata</h3>
                    <div class="metadata-grid">
                        <div class="metadata-item">
                            <span class="metadata-label">Type</span>
                            <span class="metadata-value">${mediaTypeIcon} ${mediaTypeText}</span>
                        </div>
                        <div class="metadata-item">
                            <span class="metadata-label">Dimensions</span>
                            <span class="metadata-value">${image.width && image.height ? `${image.width} × ${image.height}` : 'N/A'}</span>
                        </div>
                        <div class="metadata-item">
                            <span class="metadata-label">File Size</span>
                            <span class="metadata-value">${formatFileSize(image.file_size)}</span>
                        </div>
                        <div class="metadata-item">
                            <span class="metadata-label">Status</span>
                            <span class="metadata-value highlight">${statusText}</span>
                        </div>
                    </div>
                </div>

                <div class="detail-section exif-section" id="exifSection">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--spacing-sm);">
                        <h3>EXIF Data</h3>
                        <button class="btn btn-sm btn-secondary" onclick="loadImageEXIF(${image.id})" style="padding: 0.25em 0.75em; font-size: 0.875em;">Load</button>
                    </div>
                    <div id="exifContent-${image.id}" style="color: var(--text-secondary); font-size: 0.9em;">
                        <span class="tags-placeholder">Click "Load" to view EXIF data</span>
                    </div>
                </div>

                <div class="image-actions">
                    <button class="action-btn primary" onclick="openAIStyleModal(${image.id})">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M12 1v6m0 6v10M1 12h6m6 0h10"/></svg>
                        Analyze
                    </button>
                    <button class="action-btn primary" onclick="openChatWithImage(${image.id})">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                        Chat
                    </button>
                </div>
                <div class="image-actions" style="margin-top: 6px;">
                    <button class="action-btn secondary" onclick="editImage(${image.id})">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                        Edit
                    </button>
                    <button class="action-btn secondary" onclick="openImageFolder(${image.id})">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                        Folder
                    </button>
                    <button class="action-btn secondary" onclick="openAddToBoardModal()">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
                        Boards
                    </button>
                    <button class="action-btn secondary" onclick="showOpenWithMenu(event, ${image.id}, '${image.media_type || 'image'}')">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                        Open With
                    </button>
                    <button class="action-btn secondary" onclick="showExportMenu(event, ${image.id})">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                        Export
                    </button>
                    <button class="action-btn secondary" onclick="syncToExif(${image.id})" title="Save description and tags to EXIF metadata">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
                        EXIF
                    </button>
                    <button class="action-btn secondary" onclick="openReverseSearchModal(${image.id})">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                        Search
                    </button>
                    <button class="action-btn secondary" onclick="openSendToTelegramModal(${image.id})">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
                        Telegram
                    </button>
                </div>
                <div class="image-actions" style="margin-top: 6px;">
                    <button class="action-btn danger full-width" onclick="confirmDeleteImage(${image.id}, '${escapeHtml(image.filename).replace(/'/g, "\\'")}')">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                        Delete
                    </button>
                </div>
            </div>

            <div class="similar-panel">
                <div class="detail-section similar-section">
                    <h3>More Like This</h3>
                    <div class="similar-images-grid" id="similarImages">
                        <span class="tags-placeholder">Loading...</span>
                    </div>
                </div>
            </div>
        </div>
    `;

    // Add event delegation for tags in modal
    // Remove old listener by cloning and replacing the node
    const tagsContainer = modalBody.querySelector('.tags-container');
    if (tagsContainer) {
        const newTagsContainer = tagsContainer.cloneNode(true);
        tagsContainer.parentNode.replaceChild(newTagsContainer, tagsContainer);

        // Add new event listener
        newTagsContainer.addEventListener('click', (e) => {
            const tag = e.target.closest('.tag[data-tag]');
            if (tag) {
                e.stopPropagation();
                e.preventDefault();
                const tagValue = tag.dataset.tag;

                // Close modal first
                closeImageModal();

                // Then search by tag
                searchByTag(tagValue);
            }
        });
    }

    loadSimilarImages(image.id);

    // Load EXIF data if available
    loadImageEXIF(image.id);

    // Load subtitles for YouTube videos
    if (isVideo) {
        loadAndInitSubtitles(image.id);
    }
}

// Load subtitles and initialize sync for YouTube videos
async function loadAndInitSubtitles(imageId) {
    // Clean up previous subtitle sync
    cleanupSubtitleSync();

    const container = document.getElementById('subtitlePanelContainer');
    const videoElement = document.getElementById('modalVideoPlayer');

    if (!container) return;

    // Show loading state
    container.innerHTML = '<div class="subtitle-panel"><div class="no-subtitles">Loading subtitles...</div></div>';

    try {
        const data = await loadSubtitlesForVideo(imageId);

        if (data && data.subtitles && data.subtitles.length > 0) {
            subtitleData.subtitles = data.subtitles;
            subtitleData.languages = data.languages;
            subtitleData.currentLang = data.languages[0];

            // Add VTT track to video player for native subtitle support
            if (videoElement) {
                addSubtitleTracksToVideo(videoElement, imageId, data.languages);
            }

            container.innerHTML = createSubtitlePanel(data.subtitles, data.languages);

            // Initialize resize functionality
            initSubtitleResize();

            // Initialize video sync for karaoke panel
            if (videoElement) {
                initSubtitleSync(videoElement);
                attachSubtitleClickHandlers();

                // Load bookmarks when video metadata is ready
                if (videoElement.readyState >= 1) {
                    // Metadata already loaded
                    await loadVideoBookmarks(imageId);
                    renderBookmarkMarkers();
                } else {
                    videoElement.addEventListener('loadedmetadata', async () => {
                        await loadVideoBookmarks(imageId);
                        renderBookmarkMarkers();
                    }, { once: true });
                }
            }
        } else {
            // No subtitles - hide the panel or show message
            container.innerHTML = '';

            // Still load bookmarks even if no subtitles
            if (videoElement) {
                if (videoElement.readyState >= 1) {
                    await loadVideoBookmarks(imageId);
                    renderBookmarkMarkers();
                } else {
                    videoElement.addEventListener('loadedmetadata', async () => {
                        await loadVideoBookmarks(imageId);
                        renderBookmarkMarkers();
                    }, { once: true });
                }
            }
        }
    } catch (error) {
        console.error('Error loading subtitles:', error);
        container.innerHTML = '';
    }
}

// Add subtitle tracks to video player for native CC support
function addSubtitleTracksToVideo(videoElement, imageId, languages) {
    // Remove existing tracks
    const existingTracks = videoElement.querySelectorAll('track');
    existingTracks.forEach(track => track.remove());

    // Add track for each language
    languages.forEach((lang, idx) => {
        const track = document.createElement('track');
        track.kind = 'subtitles';
        track.label = lang.toUpperCase();
        track.srclang = lang;
        track.src = `/api/images/${imageId}/subtitles.vtt?language=${lang}`;

        // Set first track as default
        if (idx === 0) {
            track.default = true;
        }

        videoElement.appendChild(track);
    });

    // Enable text tracks display
    if (videoElement.textTracks && videoElement.textTracks.length > 0) {
        // Show first track by default
        videoElement.textTracks[0].mode = 'showing';
    }
}

// Load and display EXIF data for an image
async function loadImageEXIF(imageId) {
    const exifContent = document.getElementById(`exifContent-${imageId}`);
    if (!exifContent) return;
    
    // Show loading
    exifContent.innerHTML = '<span class="tags-placeholder">Loading EXIF data...</span>';
    
    try {
        const response = await fetch(`/api/images/${imageId}/exif`);
        const data = await response.json();
        
        if (data.has_exif && data.formatted) {
            const formatted = data.formatted;
            let html = '<div class="exif-grid" style="display: grid; grid-template-columns: auto 1fr; gap: 0.5em 1em; align-items: start;">';
            
            if (formatted.camera) {
                html += `<div style="font-weight: 600; color: var(--text-primary);">Camera:</div><div>${escapeHtml(formatted.camera)}</div>`;
            }
            
            if (formatted.lens) {
                html += `<div style="font-weight: 600; color: var(--text-primary);">Lens:</div><div>${escapeHtml(formatted.lens)}</div>`;
            }
            
            if (formatted.settings) {
                html += `<div style="font-weight: 600; color: var(--text-primary);">Settings:</div><div>${escapeHtml(formatted.settings)}</div>`;
            }
            
            if (formatted.exposure_compensation) {
                html += `<div style="font-weight: 600; color: var(--text-primary);">Exposure:</div><div>${escapeHtml(formatted.exposure_compensation)}</div>`;
            }
            
            if (formatted.flash) {
                html += `<div style="font-weight: 600; color: var(--text-primary);">Flash:</div><div>${escapeHtml(formatted.flash)}</div>`;
            }
            
            if (formatted.date_taken) {
                html += `<div style="font-weight: 600; color: var(--text-primary);">Date Taken:</div><div>${escapeHtml(formatted.date_taken)}</div>`;
            }
            
            if (formatted.gps) {
                html += `<div style="font-weight: 600; color: var(--text-primary);">Location:</div><div><a href="${escapeHtml(formatted.gps)}" target="_blank" style="color: var(--accent-purple);">View on Map</a></div>`;
            }
            
            html += '</div>';
            exifContent.innerHTML = html;
        } else {
            // Try to extract EXIF if not available
            exifContent.innerHTML = '<span class="tags-placeholder">No EXIF data available. <button onclick="extractImageEXIF(' + imageId + ')" style="background: none; border: none; color: var(--accent-purple); cursor: pointer; text-decoration: underline;">Extract from file</button></span>';
        }
    } catch (error) {
        console.error('Failed to load EXIF data:', error);
        exifContent.innerHTML = '<span class="tags-placeholder" style="color: var(--danger);">Failed to load EXIF data</span>';
    }
}

// Extract EXIF data from image file
async function extractImageEXIF(imageId) {
    const exifContent = document.getElementById(`exifContent-${imageId}`);
    if (!exifContent) return;
    
    exifContent.innerHTML = '<span class="tags-placeholder">Extracting EXIF data...</span>';
    
    try {
        const response = await fetch(`/api/images/${imageId}/exif/extract`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success && data.formatted) {
            // Reload EXIF data
            await loadImageEXIF(imageId);
        } else {
            exifContent.innerHTML = '<span class="tags-placeholder" style="color: var(--danger);">' + (data.message || 'No EXIF data found in file') + '</span>';
        }
    } catch (error) {
        console.error('Failed to extract EXIF data:', error);
        exifContent.innerHTML = '<span class="tags-placeholder" style="color: var(--danger);">Failed to extract EXIF data</span>';
    }
}

function closeModal(modalId, resetCallback = null) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
    }

    if (resetCallback) {
        resetCallback();
    }
}

function closeImageModal() {
    // Clean up subtitle sync before closing
    cleanupSubtitleSync();

    // IMPORTANT: Clean up video element to prevent memory leaks
    const videoElement = document.getElementById('modalVideoPlayer');
    if (videoElement) {
        videoElement.pause();
        videoElement.removeAttribute('src');
        videoElement.load(); // Reset the video element

        // Remove all track elements (subtitles)
        const tracks = videoElement.querySelectorAll('track');
        tracks.forEach(track => track.remove());
    }

    closeModal('imageModal', () => {
        state.currentImage = null;
    });
}

/**
 * Navigate to next/previous image in modal
 * @param {number} direction - 1 for next, -1 for previous
 */
function navigateModal(direction) {
    if (!state.currentImage || !state.images || state.images.length === 0) return;

    // Get sorted images (same order as displayed in grid)
    const sortedImages = sortImages([...state.images], state.imageSort);
    const currentIndex = sortedImages.findIndex(img => img.id === state.currentImage.id);

    if (currentIndex === -1) return;

    const newIndex = currentIndex + direction;

    // Check bounds
    if (newIndex < 0 || newIndex >= sortedImages.length) return;

    // Open the new image
    const newImage = sortedImages[newIndex];
    openImageModal(newImage);
}

function closeAIStyleModal() {
    closeModal('aiStyleModal', () => {
        state.pendingAnalyzeImageId = null;
    });
}

function openCreateBoardModal() {
    const modal = document.getElementById('createBoardModal');
    modal.style.display = 'block';

    document.getElementById('createBoardForm').reset();
}

function closeCreateBoardModal() {
    closeModal('createBoardModal');
}

async function openAddToBoardModal(imageId = null, isBatchMode = false) {
    state.isBatchBoardAdd = isBatchMode;

    if (!isBatchMode && !state.currentImage) return;

    const modal = document.getElementById('addToBoardModal');
    const selection = document.getElementById('boardSelection');

    let imageBoardIds = [];

    if (!isBatchMode) {
        const imageBoards = state.currentImage.boards || [];
        imageBoardIds = imageBoards.map(b => b.id);
    }

    selection.innerHTML = flattenBoards(state.boards).map(board => {
        const checked = !isBatchMode && imageBoardIds.includes(board.id) ? 'checked' : '';
        return `
            <div class="board-checkbox">
                <input
                    type="checkbox"
                    id="board-${board.id}"
                    value="${board.id}"
                    ${checked}
                >
                <label for="board-${board.id}">${escapeHtml((board.prefix || '') + board.name)}</label>
            </div>
        `;
    }).join('');

    modal.style.display = 'block';
}

function closeAddToBoardModal() {
    closeModal('addToBoardModal');
}

function flattenBoards(boards, prefix = '') {
    let result = [];

    for (const board of boards) {
        result.push({ ...board, prefix });

        if (board.sub_boards && board.sub_boards.length > 0) {
            result = result.concat(flattenBoards(board.sub_boards, prefix + '  '));
        }
    }

    return result;
}

// Board Management Modals
let currentBoardAction = { boardId: null, boardName: '' };

function openRenameBoardModal(boardId) {
    const board = findBoardById(boardId, state.boards);
    if (!board) return;

    currentBoardAction.boardId = boardId;
    currentBoardAction.boardName = board.name;

    document.getElementById('renameBoardName').value = board.name;
    document.getElementById('renameBoardDescription').value = board.description || '';

    const modal = document.getElementById('renameBoardModal');
    modal.style.display = 'block';
}

function closeRenameBoardModal() {
    closeModal('renameBoardModal', () => {
        currentBoardAction = { boardId: null, boardName: '' };
    });
}

function openMergeBoardModal(boardId) {
    const board = findBoardById(boardId, state.boards);
    if (!board) return;

    currentBoardAction.boardId = boardId;
    currentBoardAction.boardName = board.name;

    document.getElementById('mergeSourceName').textContent = board.name;

    // Populate target board dropdown (exclude the source board and its sub-boards)
    const targetSelect = document.getElementById('mergeTargetBoard');
    const excludedIds = new Set([boardId, ...getAllSubBoardIds(boardId, state.boards)]);

    const availableBoards = flattenBoards(state.boards).filter(b => !excludedIds.has(b.id));

    targetSelect.innerHTML = '<option value="">-- Select Board --</option>' +
        availableBoards.map(board =>
            `<option value="${board.id}">${escapeHtml((board.prefix || '') + board.name)}</option>`
        ).join('');

    const modal = document.getElementById('mergeBoardModal');
    modal.style.display = 'block';
}

function closeMergeBoardModal() {
    closeModal('mergeBoardModal', () => {
        currentBoardAction = { boardId: null, boardName: '' };
    });
}

function openDeleteBoardModal(boardId) {
    const board = findBoardById(boardId, state.boards);
    if (!board) return;

    currentBoardAction.boardId = boardId;
    currentBoardAction.boardName = board.name;

    document.getElementById('deleteSourceName').textContent = board.name;
    document.getElementById('deleteSubBoards').checked = false;

    const modal = document.getElementById('deleteBoardModal');
    modal.style.display = 'block';
}

function closeDeleteBoardModal() {
    closeModal('deleteBoardModal', () => {
        currentBoardAction = { boardId: null, boardName: '' };
    });
}

function openSmartRulesModal(boardId) {
    const board = findBoardById(boardId, state.boards);
    if (!board) return;

    currentBoardAction.boardId = boardId;
    currentBoardAction.boardName = board.name;

    document.getElementById('smartRulesBoardName').textContent = board.name;

    // Parse existing smart rules
    const smartRules = board.smart_rules || {};
    const hasRules = smartRules && Object.keys(smartRules).length > 0;

    // Set checkbox state
    const enabledCheckbox = document.getElementById('smartRulesEnabled');
    enabledCheckbox.checked = hasRules;

    // Show/hide config section
    const configSection = document.getElementById('smartRulesConfig');
    configSection.style.display = hasRules ? 'block' : 'none';

    // Populate fields
    if (smartRules.tags_include && Array.isArray(smartRules.tags_include)) {
        document.getElementById('tagsInclude').value = smartRules.tags_include.join(', ');
    } else {
        document.getElementById('tagsInclude').value = '';
    }

    if (smartRules.tags_exclude && Array.isArray(smartRules.tags_exclude)) {
        document.getElementById('tagsExclude').value = smartRules.tags_exclude.join(', ');
    } else {
        document.getElementById('tagsExclude').value = '';
    }

    document.getElementById('descriptionContains').value = smartRules.description_contains || '';
    document.getElementById('processExisting').checked = false;

    const modal = document.getElementById('smartRulesModal');
    modal.style.display = 'block';
}

function closeSmartRulesModal() {
    closeModal('smartRulesModal', () => {
        currentBoardAction = { boardId: null, boardName: '' };
    });
}

// Helper functions for board management
function findBoardById(boardId, boards) {
    for (const board of boards) {
        if (board.id === boardId) return board;
        if (board.sub_boards && board.sub_boards.length > 0) {
            const found = findBoardById(boardId, board.sub_boards);
            if (found) return found;
        }
    }
    return null;
}

function getAllSubBoardIds(boardId, boards) {
    const board = findBoardById(boardId, boards);
    if (!board || !board.sub_boards) return [];

    let ids = [];
    for (const subBoard of board.sub_boards) {
        ids.push(subBoard.id);
        ids = ids.concat(getAllSubBoardIds(subBoard.id, boards));
    }
    return ids;
}

// Board Context Menu
function showBoardContextMenu(boardId, x, y) {
    const contextMenu = document.getElementById('boardContextMenu');
    if (!contextMenu) return;

    currentBoardAction.boardId = boardId;

    contextMenu.style.left = x + 'px';
    contextMenu.style.top = y + 'px';
    contextMenu.style.display = 'block';

    // Close context menu when clicking anywhere else
    const closeContextMenu = (e) => {
        if (!contextMenu.contains(e.target)) {
            hideBoardContextMenu();
            document.removeEventListener('click', closeContextMenu);
        }
    };

    // Delay adding the listener to avoid immediate trigger
    setTimeout(() => {
        document.addEventListener('click', closeContextMenu);
    }, 10);
}

function hideBoardContextMenu() {
    const contextMenu = document.getElementById('boardContextMenu');
    if (contextMenu) {
        contextMenu.style.display = 'none';
    }
}

// ============ Video Hover Preview ============

let videoPreviewTimeout = null;

function playVideoPreview(wrapper) {
    const imageId = wrapper.dataset.imageId;
    if (!imageId) return;

    // Wait 300ms before starting preview to avoid flickering on quick mouse moves
    videoPreviewTimeout = setTimeout(() => {
        const video = document.createElement('video');
        video.src = `/api/images/${imageId}/file`;
        video.muted = true;
        video.loop = true;
        video.playbackRate = 2.0; // 2x speed for quick preview
        video.className = 'image-card-image preview-video';
        video.style.objectFit = 'cover';
        video.style.position = 'absolute';
        video.style.top = '0';
        video.style.left = '0';
        video.style.width = '100%';
        video.style.height = '100%';
        video.play().catch(() => {}); // Ignore autoplay errors

        // Hide thumbnail and play icon
        const img = wrapper.querySelector('img');
        if (img) img.style.opacity = '0';

        const overlay = wrapper.querySelector('.video-play-overlay');
        if (overlay) overlay.style.opacity = '0';

        wrapper.appendChild(video);
    }, 300);
}

function stopVideoPreview(wrapper) {
    clearTimeout(videoPreviewTimeout);

    const video = wrapper.querySelector('video.preview-video');
    if (video) {
        video.pause();
        video.src = '';
        video.remove();
    }

    const img = wrapper.querySelector('img');
    if (img) img.style.opacity = '1';

    const overlay = wrapper.querySelector('.video-play-overlay');
    if (overlay) overlay.style.opacity = '1';
}

// ============ Drag & Drop to Boards ============

let draggedImageId = null;

function handleImageDragStart(e) {
    const card = e.target.closest('.image-card');
    if (!card) return;

    draggedImageId = parseInt(card.dataset.id);
    e.dataTransfer.effectAllowed = 'copy';
    e.dataTransfer.setData('text/plain', draggedImageId);

    // Add dragging visual effect
    card.classList.add('dragging');

    // If we're in selection mode and this image is selected, we're dragging all selected
    if (state.selectionMode && state.selectedImages.has(draggedImageId)) {
        e.dataTransfer.setData('text/plain', JSON.stringify(Array.from(state.selectedImages)));
    }
}

function handleImageDragEnd(e) {
    const card = e.target.closest('.image-card');
    if (card) card.classList.remove('dragging');
    draggedImageId = null;
}

function handleBoardDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';

    const boardPill = e.target.closest('.board-pill[data-drop-target]');
    if (boardPill) {
        boardPill.classList.add('drag-over');
    }
}

function handleBoardDragLeave(e) {
    const boardPill = e.target.closest('.board-pill[data-drop-target]');
    if (boardPill) {
        boardPill.classList.remove('drag-over');
    }
}

async function handleBoardDrop(e) {
    e.preventDefault();

    const boardPill = e.target.closest('.board-pill[data-drop-target]');
    if (!boardPill) return;

    boardPill.classList.remove('drag-over');

    const boardId = parseInt(boardPill.dataset.boardId);
    if (!boardId) return;

    // Check if we're dragging multiple selected images
    if (state.selectionMode && state.selectedImages.size > 0 && state.selectedImages.has(draggedImageId)) {
        const count = state.selectedImages.size;
        showToast(`Adding ${count} images to board...`, 'info');

        let success = 0;
        for (const imageId of state.selectedImages) {
            try {
                await addImageToBoard(boardId, imageId);
                success++;
            } catch (error) {
                console.error(`Failed to add image ${imageId} to board:`, error);
            }
        }

        showToast(`Added ${success} images to board`, 'success');
        await loadBoards();
        renderBoards();
    } else if (draggedImageId) {
        // Single image drag
        showToast('Adding image to board...', 'info');

        try {
            await addImageToBoard(boardId, draggedImageId);
            showToast('Image added to board', 'success');
            await loadBoards();
            renderBoards();
        } catch (error) {
            console.error('Failed to add image to board:', error);
            showToast('Failed to add image to board', 'error');
        }
    }

    draggedImageId = null;
}

// ============ Event Listeners ============

function attachEventListeners() {
    // Theme toggle
    const themeToggle = document.getElementById('themeToggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', toggleTheme);
    }

    // Initialize theme from localStorage or system preference
    initializeTheme();

    // Sidebar toggle
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebar = document.getElementById('sidebar');
    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', () => {
            sidebar.classList.toggle('collapsed');
        });
    }

    // Dropdown menu toggle
    const moreBtn = document.getElementById('moreBtn');
    const moreMenu = document.getElementById('moreMenu');
    if (moreBtn && moreMenu) {
        moreBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            moreMenu.classList.toggle('show');
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', () => {
            moreMenu.classList.remove('show');
        });
    }

    // Dropdown menu items
    const scanBtnMenu = document.getElementById('scanBtnMenu');
    const sortImagesBtnMenu = document.getElementById('sortImagesBtnMenu');
    const findDuplicatesBtnMenu = document.getElementById('findDuplicatesBtnMenu');
    const analyzeBtnMenu = document.getElementById('analyzeBtnMenu');
    const chatBtnMenu = document.getElementById('chatBtnMenu');
    const settingsBtnMenu = document.getElementById('settingsBtnMenu');

    if (scanBtnMenu) scanBtnMenu.addEventListener('click', scanDirectory);
    if (sortImagesBtnMenu) sortImagesBtnMenu.addEventListener('click', () => {
        const imageSortMenu = document.getElementById('imageSortMenu');
        if (imageSortMenu) {
            imageSortMenu.style.display = imageSortMenu.style.display === 'none' ? 'block' : 'none';
        }
    });
    if (findDuplicatesBtnMenu) findDuplicatesBtnMenu.addEventListener('click', findDuplicates);
    if (analyzeBtnMenu) analyzeBtnMenu.addEventListener('click', () => batchAnalyze(10));
    if (chatBtnMenu) chatBtnMenu.addEventListener('click', () => {
        if (typeof openChat === 'function') {
            openChat();
        }
    });
    if (settingsBtnMenu) settingsBtnMenu.addEventListener('click', openSettingsModal);

    // Category pills - handle clicks separately to update active state
    const categoryPills = document.querySelectorAll('.category-pill');
    categoryPills.forEach(pill => {
        pill.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation(); // Prevent other event listeners from firing
            
            // Update active state immediately
            categoryPills.forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
            
            const view = pill.dataset.view;
            if (view) {
                await switchView(view);
            }
        });
    });

    // Header buttons
    const scanBtnEmpty = document.getElementById('scanBtnEmpty');
    const uploadBtn = document.getElementById('uploadBtn');
    const selectBtn = document.getElementById('selectBtn');

    if (scanBtnEmpty) scanBtnEmpty.addEventListener('click', scanDirectory);
    if (uploadBtn) uploadBtn.addEventListener('click', openUploadModal);
    if (selectBtn) selectBtn.addEventListener('click', toggleSelectionMode);

    // Batch operations bar buttons
    const selectAllBtn = document.getElementById('selectAllBtn');
    const deselectAllBtn = document.getElementById('deselectAllBtn');
    const batchAnalyzeBtn = document.getElementById('batchAnalyzeBtn');
    const batchTagBtn = document.getElementById('batchTagBtn');
    const batchNameBtn = document.getElementById('batchNameBtn');
    const batchAddToBoardBtn = document.getElementById('batchAddToBoardBtn');
    const batchExportBtn = document.getElementById('batchExportBtn');
    const closeBatchBtn = document.getElementById('closeBatchBtn');

    if (selectAllBtn) selectAllBtn.addEventListener('click', selectAllImages);
    if (deselectAllBtn) deselectAllBtn.addEventListener('click', deselectAllImages);
    if (batchAnalyzeBtn) batchAnalyzeBtn.addEventListener('click', batchAnalyzeImages);
    if (batchTagBtn) batchTagBtn.addEventListener('click', batchTagImages);
    if (batchNameBtn) batchNameBtn.addEventListener('click', batchNameImages);
    if (batchAddToBoardBtn) batchAddToBoardBtn.addEventListener('click', batchAddImagesToBoard);
    if (batchExportBtn) batchExportBtn.addEventListener('click', showBatchExportMenu);
    if (closeBatchBtn) closeBatchBtn.addEventListener('click', () => {
        if (state.selectionMode) {
            toggleSelectionMode();
        }
    });

    // Search with debouncing
    const searchInput = document.getElementById('searchInput');
    const searchBtn = document.getElementById('searchBtn');
    let searchTimeout = null;

    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                searchImages(e.target.value);
            }, CONFIG.SEARCH_DEBOUNCE_MS);
        });

        // Search on Enter key
        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                clearTimeout(searchTimeout);
                searchImages(searchInput.value);
            }
        });
    }

    // View navigation - exclude category pills (they have their own handler)
    document.querySelectorAll('[data-view]:not(.category-pill)').forEach(item => {
        item.addEventListener('click', async (e) => {
            e.preventDefault();
            const view = item.dataset.view;
            if (view) {
                await switchView(view);
            }
        });
    });

    // ✅ Image Grid - Event delegation for image cards
    const imageGrid = document.getElementById('imageGrid');
    if (imageGrid) {
        imageGrid.addEventListener('click', (e) => {
            // Check for checkbox clicks FIRST
            const checkbox = e.target.closest('.image-card-checkbox');
            if (checkbox) {
                e.stopPropagation();
                e.preventDefault();
                const imageId = parseInt(checkbox.dataset.id);
                toggleImageSelection(imageId);
                return;
            }

            // Check for tag clicks (before card clicks)
            // This prevents opening modal when clicking on tags
            const tag = e.target.closest('.tag[data-tag]');
            if (tag) {
                e.stopPropagation();
                e.preventDefault();
                const tagValue = tag.dataset.tag;
                searchByTag(tagValue);
                return; // Stop here - don't check for card
            }

            // Check for card clicks (open modal)
            // Don't open modal if in selection mode
            if (!state.selectionMode) {
                const card = e.target.closest('.image-card');
                if (card) {
                    const imageId = parseInt(card.dataset.id);
                    const image = state.images.find(img => img.id === imageId);
                    if (image) {
                        openImageModal(image);
                    }
                }
            }
        });

        // Video hover preview events
        imageGrid.addEventListener('mouseenter', (e) => {
            const wrapper = e.target.closest('.image-card-video-wrapper');
            if (wrapper) {
                playVideoPreview(wrapper);
            }
        }, true);

        imageGrid.addEventListener('mouseleave', (e) => {
            const wrapper = e.target.closest('.image-card-video-wrapper');
            if (wrapper) {
                stopVideoPreview(wrapper);
            }
        }, true);

        // Drag & drop events for image cards
        imageGrid.addEventListener('dragstart', handleImageDragStart);
        imageGrid.addEventListener('dragend', handleImageDragEnd);
    }

    // ✅ Boards List - Event delegation with single/double click
    const boardsList = document.getElementById('boardsList');
    if (boardsList) {
        let clickTimer = null;
        let clickPrevent = false;

        boardsList.addEventListener('click', (e) => {
            const boardPill = e.target.closest('.board-pill[data-board-id]');
            if (!boardPill) return;

            e.preventDefault();
            const boardId = parseInt(boardPill.dataset.boardId);
            const hasChildren = boardPill.dataset.hasChildren === 'true';

            // Clear existing timer
            clearTimeout(clickTimer);

            // Prevent single click if double click is detected
            if (clickPrevent) {
                clickPrevent = false;
                return;
            }

            // Set timer for single click
            clickTimer = setTimeout(() => {
                // Single click - expand/collapse if has children
                if (hasChildren) {
                    const subPills = boardsList.querySelector(`.board-sub-pills[data-parent-id="${boardId}"]`);
                    const expandIcon = boardPill.querySelector('.board-pill-expand');

                    if (subPills) {
                        const isExpanded = subPills.style.display !== 'none';
                        subPills.style.display = isExpanded ? 'none' : 'flex';

                        if (expandIcon) {
                            expandIcon.textContent = isExpanded ? '▼' : '▲';
                        }
                    }
                } else {
                    // No children - open gallery
                    switchView('board', boardId);
                }
            }, 250);
        });

        boardsList.addEventListener('dblclick', (e) => {
            const boardPill = e.target.closest('.board-pill[data-board-id]');
            if (!boardPill) return;

            e.preventDefault();
            clearTimeout(clickTimer);
            clickPrevent = true;

            const boardId = parseInt(boardPill.dataset.boardId);

            // Double click - always open gallery
            switchView('board', boardId);

            // Reset prevent flag
            setTimeout(() => { clickPrevent = false; }, 300);
        });

        // Right-click context menu on boards
        boardsList.addEventListener('contextmenu', (e) => {
            const boardPill = e.target.closest('.board-pill[data-board-id]');
            if (boardPill) {
                e.preventDefault();
                const boardId = parseInt(boardPill.dataset.boardId);
                showBoardContextMenu(boardId, e.pageX, e.pageY);
            }
        });

        // Touch long-press support for context menu (touch screens)
        let touchTimer = null;
        let touchStartX = 0;
        let touchStartY = 0;
        const LONG_PRESS_DURATION = 500; // ms
        const TOUCH_MOVE_THRESHOLD = 10; // px

        boardsList.addEventListener('touchstart', (e) => {
            const boardPill = e.target.closest('.board-pill[data-board-id]');
            if (!boardPill) return;

            const touch = e.touches[0];
            touchStartX = touch.pageX;
            touchStartY = touch.pageY;

            touchTimer = setTimeout(() => {
                const boardId = parseInt(boardPill.dataset.boardId);
                showBoardContextMenu(boardId, touch.pageX, touch.pageY);
                // Prevent click event after long press
                e.preventDefault();
            }, LONG_PRESS_DURATION);
        }, { passive: false });

        boardsList.addEventListener('touchmove', (e) => {
            if (touchTimer) {
                const touch = e.touches[0];
                const deltaX = Math.abs(touch.pageX - touchStartX);
                const deltaY = Math.abs(touch.pageY - touchStartY);

                // Cancel long press if finger moved too much
                if (deltaX > TOUCH_MOVE_THRESHOLD || deltaY > TOUCH_MOVE_THRESHOLD) {
                    clearTimeout(touchTimer);
                    touchTimer = null;
                }
            }
        });

        boardsList.addEventListener('touchend', () => {
            if (touchTimer) {
                clearTimeout(touchTimer);
                touchTimer = null;
            }
        });

        boardsList.addEventListener('touchcancel', () => {
            if (touchTimer) {
                clearTimeout(touchTimer);
                touchTimer = null;
            }
        });

        // Drag & drop events for board pills (drop targets)
        boardsList.addEventListener('dragover', handleBoardDragOver);
        boardsList.addEventListener('dragleave', handleBoardDragLeave);
        boardsList.addEventListener('drop', handleBoardDrop);
    }

    // Board Context Menu
    const boardContextMenu = document.getElementById('boardContextMenu');
    if (boardContextMenu) {
        boardContextMenu.addEventListener('click', (e) => {
            const menuItem = e.target.closest('.context-menu-item');
            if (menuItem) {
                const action = menuItem.dataset.action;
                const boardId = currentBoardAction.boardId;

                hideBoardContextMenu();

                if (action === 'rename') {
                    openRenameBoardModal(boardId);
                } else if (action === 'smart-rules') {
                    openSmartRulesModal(boardId);
                } else if (action === 'move') {
                    openMoveBoardModal(boardId);
                } else if (action === 'merge') {
                    openMergeBoardModal(boardId);
                } else if (action === 'export') {
                    showBoardExportMenu(e, boardId);
                } else if (action === 'delete') {
                    openDeleteBoardModal(boardId);
                }
            }
        });
    }

    // Rename Board Modal
    const renameBoardClose = document.getElementById('renameBoardClose');
    const cancelRenameBtn = document.getElementById('cancelRenameBtn');
    const renameBoardForm = document.getElementById('renameBoardForm');

    if (renameBoardClose) renameBoardClose.addEventListener('click', closeRenameBoardModal);
    if (cancelRenameBtn) cancelRenameBtn.addEventListener('click', closeRenameBoardModal);

    if (renameBoardForm) {
        renameBoardForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            const newName = document.getElementById('renameBoardName').value.trim();
            const newDescription = document.getElementById('renameBoardDescription').value.trim();

            if (newName && currentBoardAction.boardId) {
                const success = await renameBoard(currentBoardAction.boardId, newName, newDescription);
                if (success) {
                    closeRenameBoardModal();
                }
            }
        });
    }

    // Merge Board Modal
    const mergeBoardClose = document.getElementById('mergeBoardClose');
    const cancelMergeBtn = document.getElementById('cancelMergeBtn');
    const mergeBoardForm = document.getElementById('mergeBoardForm');

    if (mergeBoardClose) mergeBoardClose.addEventListener('click', closeMergeBoardModal);
    if (cancelMergeBtn) cancelMergeBtn.addEventListener('click', closeMergeBoardModal);

    if (mergeBoardForm) {
        mergeBoardForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            const targetBoardId = parseInt(document.getElementById('mergeTargetBoard').value);
            const deleteSource = document.getElementById('mergeDeleteSource').checked;

            if (targetBoardId && currentBoardAction.boardId) {
                const success = await mergeBoards(currentBoardAction.boardId, targetBoardId, deleteSource);
                if (success) {
                    closeMergeBoardModal();
                }
            } else {
                showToast('Please select a target board', 'error');
            }
        });
    }

    // Delete Board Modal
    const deleteBoardClose = document.getElementById('deleteBoardClose');
    const cancelDeleteBtn = document.getElementById('cancelDeleteBtn');
    const deleteBoardForm = document.getElementById('deleteBoardForm');

    if (deleteBoardClose) deleteBoardClose.addEventListener('click', closeDeleteBoardModal);
    if (cancelDeleteBtn) cancelDeleteBtn.addEventListener('click', closeDeleteBoardModal);

    if (deleteBoardForm) {
        deleteBoardForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            const deleteSubBoards = document.getElementById('deleteSubBoards').checked;

            if (currentBoardAction.boardId) {
                const success = await deleteBoard(currentBoardAction.boardId, deleteSubBoards);
                if (success) {
                    closeDeleteBoardModal();
                }
            }
        });
    }

    // Smart Rules Modal
    const smartRulesClose = document.getElementById('smartRulesClose');
    const cancelSmartRulesBtn = document.getElementById('cancelSmartRulesBtn');
    const smartRulesForm = document.getElementById('smartRulesForm');
    const smartRulesEnabled = document.getElementById('smartRulesEnabled');
    const smartRulesConfig = document.getElementById('smartRulesConfig');

    if (smartRulesClose) smartRulesClose.addEventListener('click', closeSmartRulesModal);
    if (cancelSmartRulesBtn) cancelSmartRulesBtn.addEventListener('click', closeSmartRulesModal);

    // Toggle config visibility
    if (smartRulesEnabled && smartRulesConfig) {
        smartRulesEnabled.addEventListener('change', (e) => {
            smartRulesConfig.style.display = e.target.checked ? 'block' : 'none';
        });
    }

    if (smartRulesForm) {
        smartRulesForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            const boardId = currentBoardAction.boardId;
            if (!boardId) return;

            const enabled = document.getElementById('smartRulesEnabled').checked;

            let smartRules = null;

            if (enabled) {
                // Parse tags
                const tagsInclude = document.getElementById('tagsInclude').value
                    .split(',')
                    .map(t => t.trim())
                    .filter(t => t.length > 0);

                const tagsExclude = document.getElementById('tagsExclude').value
                    .split(',')
                    .map(t => t.trim())
                    .filter(t => t.length > 0);

                const descriptionContains = document.getElementById('descriptionContains').value.trim();

                // Build rules object
                smartRules = {};
                if (tagsInclude.length > 0) smartRules.tags_include = tagsInclude;
                if (tagsExclude.length > 0) smartRules.tags_exclude = tagsExclude;
                if (descriptionContains) smartRules.description_contains = descriptionContains;

                // If no rules specified, treat as disabled
                if (Object.keys(smartRules).length === 0) {
                    smartRules = null;
                }
            }

            const processExisting = document.getElementById('processExisting').checked;

            try {
                const response = await fetch(`/api/boards/${boardId}/smart-rules`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        smart_rules: smartRules,
                        process_existing: processExisting
                    })
                });

                const data = await response.json();

                if (response.ok) {
                    showToast(smartRules ? `Smart Rules saved! ${data.images_added || 0} images added.` : 'Smart Rules disabled', 'success');
                    closeSmartRulesModal();
                    await loadBoards(); // Refresh boards to get updated rules
                } else {
                    showToast(data.error || 'Failed to save Smart Rules', 'error');
                }
            } catch (error) {
                console.error('Error saving Smart Rules:', error);
                showToast('Error saving Smart Rules', 'error');
            }
        });
    }

    // Image Modal
    const modalClose = document.getElementById('modalClose');
    const modalOverlay = document.getElementById('modalOverlay');
    if (modalClose) modalClose.addEventListener('click', closeImageModal);
    if (modalOverlay) modalOverlay.addEventListener('click', closeImageModal);

    // Edit Image Modal
    const editImageClose = document.getElementById('editImageClose');
    const cancelEditImageBtn = document.getElementById('cancelEditImageBtn');
    const editImageForm = document.getElementById('editImageForm');
    const addTagBtn = document.getElementById('addTagBtn');
    const editImageNewTag = document.getElementById('editImageNewTag');

    if (editImageClose) editImageClose.addEventListener('click', closeEditImageModal);
    if (cancelEditImageBtn) cancelEditImageBtn.addEventListener('click', closeEditImageModal);

    if (editImageForm) {
        editImageForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            await saveImageEdit();
        });
    }

    if (addTagBtn) {
        addTagBtn.addEventListener('click', () => {
            const tagInput = document.getElementById('editImageNewTag');
            addEditTag(tagInput.value);
        });
    }

    if (editImageNewTag) {
        editImageNewTag.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                addEditTag(editImageNewTag.value);
            }
        });
    }

    // Create Board Modal
    const createBoardBtn = document.getElementById('createBoardBtn');
    const createBoardClose = document.getElementById('createBoardClose');
    const cancelBoardBtn = document.getElementById('cancelBoardBtn');
    const createBoardForm = document.getElementById('createBoardForm');

    if (createBoardBtn) createBoardBtn.addEventListener('click', openCreateBoardModal);
    if (createBoardClose) createBoardClose.addEventListener('click', closeCreateBoardModal);
    if (cancelBoardBtn) cancelBoardBtn.addEventListener('click', closeCreateBoardModal);

    if (createBoardForm) {
        createBoardForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            const name = document.getElementById('boardName').value.trim();
            const description = document.getElementById('boardDescription').value.trim();
            const parentId = document.getElementById('boardParent').value;

            if (name) {
                try {
                    await createBoard(name, description, parentId || null);
                    closeCreateBoardModal();
                } catch (error) {
                    // Error already shown
                }
            }
        });
    }

    // Add to Board Modal
    const addToBoardClose = document.getElementById('addToBoardClose');
    const cancelAddToBoardBtn = document.getElementById('cancelAddToBoardBtn');
    const saveAddToBoardBtn = document.getElementById('saveAddToBoardBtn');

    if (addToBoardClose) addToBoardClose.addEventListener('click', closeAddToBoardModal);
    if (cancelAddToBoardBtn) cancelAddToBoardBtn.addEventListener('click', closeAddToBoardModal);

    if (saveAddToBoardBtn) {
        saveAddToBoardBtn.addEventListener('click', async () => {
            const checkboxes = document.querySelectorAll('#boardSelection input[type="checkbox"]');
            const selectedBoards = Array.from(checkboxes)
                .filter(cb => cb.checked)
                .map(cb => parseInt(cb.value));

            if (selectedBoards.length === 0) {
                showToast('Please select at least one board', 'error');
                return;
            }

            // Batch mode: add selected images to selected boards
            if (state.isBatchBoardAdd && state.pendingBatchBoardImageIds) {
                const imageIds = state.pendingBatchBoardImageIds;
                const total = imageIds.length;
                const boardsCount = selectedBoards.length;

                showToast(`Adding ${total} images to ${boardsCount} boards...`, 'info');

                for (const imageId of imageIds) {
                    for (const boardId of selectedBoards) {
                        await addImageToBoard(boardId, imageId);
                    }
                }

                showToast(`Successfully added ${total} images to ${boardsCount} boards! 📌`, 'success');

                // Clear batch state
                state.pendingBatchBoardImageIds = null;
                deselectAllImages();
                if (state.selectionMode) {
                    toggleSelectionMode();
                }
            }
            // Single image mode
            else if (state.currentImage) {
                const currentBoards = (state.currentImage.boards || []).map(b => b.id);

                const toAdd = selectedBoards.filter(id => !currentBoards.includes(id));
                const toRemove = currentBoards.filter(id => !selectedBoards.includes(id));

                for (const boardId of toAdd) {
                    await addImageToBoard(boardId, state.currentImage.id);
                }

                for (const boardId of toRemove) {
                    await removeImageFromBoard(boardId, state.currentImage.id);
                }

                showToast('Board assignments updated!', 'success');

                const updated = await getImageDetails(state.currentImage.id);
                if (updated) {
                    state.currentImage = updated;
                    updateModal();
                }
            }

            closeAddToBoardModal();
        });
    }

    // AI Style Modal
    const aiStyleClose = document.getElementById('aiStyleClose');
    const aiStyleOverlay = document.getElementById('aiStyleOverlay');
    const cancelAIStyleBtn = document.getElementById('cancelAIStyleBtn');
    const analyzeWithStyleBtn = document.getElementById('analyzeWithStyleBtn');

    if (aiStyleClose) aiStyleClose.addEventListener('click', closeAIStyleModal);
    if (aiStyleOverlay) aiStyleOverlay.addEventListener('click', closeAIStyleModal);
    if (cancelAIStyleBtn) cancelAIStyleBtn.addEventListener('click', closeAIStyleModal);

    if (analyzeWithStyleBtn) {
        analyzeWithStyleBtn.addEventListener('click', async () => {
            const selectedStyle = state.selectedStyle || 'classic';
            let customPrompt = null;

            if (selectedStyle === 'custom') {
                customPrompt = document.getElementById('customPrompt').value.trim();
                if (!customPrompt) {
                    showToast('Please enter a custom prompt', 'error');
                    return;
                }
            }

            // ✅ CRITICAL FIX: Capture imageId BEFORE closing modal
            const imageId = state.pendingAnalyzeImageId;
            const isBatch = state.isBatchAnalyze;

            closeAIStyleModal();

            // Check if this is batch mode
            if (isBatch) {
                await performBatchAnalyze(selectedStyle, customPrompt);
            } else {
                // Уверяваме се че imageId е валидно число, не true/false
                if (!imageId || typeof imageId !== 'number') {
                    console.error('Invalid imageId for analysis:', imageId);
                    return;
                }
                await analyzeImage(imageId, selectedStyle, customPrompt);
            }
        });
    }

    // Upload Modal
    const uploadModalClose = document.getElementById('uploadModalClose');
    const selectFilesBtn = document.getElementById('selectFilesBtn');
    const fileInput = document.getElementById('fileInput');
    const cancelUploadBtn = document.getElementById('cancelUploadBtn');
    const startUploadBtn = document.getElementById('startUploadBtn');

    if (uploadModalClose) uploadModalClose.addEventListener('click', closeUploadModal);
    if (selectFilesBtn) {
        selectFilesBtn.addEventListener('click', () => {
            if (fileInput) fileInput.click();
        });
    }

    if (fileInput) fileInput.addEventListener('change', handleFileSelect);
    if (cancelUploadBtn) cancelUploadBtn.addEventListener('click', closeUploadModal);
    if (startUploadBtn) startUploadBtn.addEventListener('click', uploadFiles);

    // Board selection change handler
    const uploadBoardSelect = document.getElementById('uploadBoardSelect');
    if (uploadBoardSelect) {
        uploadBoardSelect.addEventListener('change', (e) => {
            const createSection = document.getElementById('createBoardSection');
            if (createSection) {
                if (e.target.value === '__create_new__') {
                    createSection.style.display = 'block';
                } else {
                    createSection.style.display = 'none';
                }
            }
        });
    }

    // Drag and drop for upload area
    const uploadArea = document.getElementById('uploadArea');

    if (uploadArea) {
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('dragover');
        });

        uploadArea.addEventListener('dragleave', () => {
            uploadArea.classList.remove('dragover');
        });

        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');

            const files = Array.from(e.dataTransfer.files).filter(file =>
                file.type.startsWith('image/') || file.type.startsWith('video/')
            );

            if (files.length > 0) {
                state.uploadFiles = files;
                showUploadPreview();
            }
        });

        uploadArea.addEventListener('click', () => {
            if (fileInput) fileInput.click();
        });
    }

    // Settings Modal
    const settingsBtn = document.getElementById('settingsBtn');
    const settingsClose = document.getElementById('settingsClose');
    const settingsOverlay = document.getElementById('settingsOverlay');
    const botConfigForm = document.getElementById('botConfigForm');
    const startBotBtn = document.getElementById('startBotBtn');
    const stopBotBtn = document.getElementById('stopBotBtn');
    const testBotBtn = document.getElementById('testBotBtn');
    const viewLogsBtn = document.getElementById('viewLogsBtn');
    const refreshLogsBtn = document.getElementById('refreshLogsBtn');

    if (settingsBtn) settingsBtn.addEventListener('click', openSettingsModal);
    if (settingsClose) settingsClose.addEventListener('click', closeSettingsModal);
    if (settingsOverlay) settingsOverlay.addEventListener('click', closeSettingsModal);

    if (startBotBtn) startBotBtn.addEventListener('click', startBot);
    if (stopBotBtn) stopBotBtn.addEventListener('click', stopBot);
    if (testBotBtn) testBotBtn.addEventListener('click', testBot);
    if (viewLogsBtn) viewLogsBtn.addEventListener('click', viewBotLogs);
    if (refreshLogsBtn) refreshLogsBtn.addEventListener('click', loadBotLogs);

    if (botConfigForm) {
        botConfigForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            await saveBotConfig();
        });
    }

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            // Close context menu first
            if (document.getElementById('boardContextMenu').style.display === 'block') {
                hideBoardContextMenu();
            }
            else if (document.getElementById('settingsModal').style.display === 'block') {
                closeSettingsModal();
            }
            else if (document.getElementById('renameBoardModal').style.display === 'block') {
                closeRenameBoardModal();
            }
            else if (document.getElementById('mergeBoardModal').style.display === 'block') {
                closeMergeBoardModal();
            }
            else if (document.getElementById('deleteBoardModal').style.display === 'block') {
                closeDeleteBoardModal();
            }
            else if (document.getElementById('aiStyleModal').style.display === 'block') {
                closeAIStyleModal();
            }
            else if (document.getElementById('imageModal').style.display === 'block') {
                closeImageModal();
            }
            else if (document.getElementById('createBoardModal').style.display === 'block') {
                closeCreateBoardModal();
            }
            else if (document.getElementById('addToBoardModal').style.display === 'block') {
                closeAddToBoardModal();
            }
            else if (document.getElementById('uploadModal').style.display === 'block') {
                closeUploadModal();
            }
        }

        // Modal navigation with arrow keys
        if (document.getElementById('imageModal').style.display === 'block') {
            if (e.key === 'ArrowLeft') {
                e.preventDefault();
                navigateModal(-1);
            } else if (e.key === 'ArrowRight') {
                e.preventDefault();
                navigateModal(1);
            }
        }

        // Skip shortcuts if typing in an input field
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

        // Power user shortcuts when modal is open
        if (document.getElementById('imageModal').style.display === 'block' && state.currentImage) {
            // 'F' for Favorite
            if (e.key === 'f' || e.key === 'F') {
                e.preventDefault();
                toggleFavorite(state.currentImage.id);
            }

            // 'Delete' for deleting image
            if (e.key === 'Delete') {
                e.preventDefault();
                confirmDeleteImage(state.currentImage.id, state.currentImage.filename);
            }

            // 'E' for Edit
            if (e.key === 'e' || e.key === 'E') {
                e.preventDefault();
                openEditImageModal(state.currentImage.id);
            }
        }

        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            if (searchInput) searchInput.focus();
        }
    });

    // Sorting Controls
    const sortImagesBtn = document.getElementById('sortImagesBtn');
    const imageSortMenu = document.getElementById('imageSortMenu');

    // Image sorting
    if (sortImagesBtn && imageSortMenu) {
        sortImagesBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            imageSortMenu.style.display = imageSortMenu.style.display === 'none' ? 'block' : 'none';
        });

        imageSortMenu.addEventListener('click', (e) => {
            const option = e.target.closest('.sort-option');
            if (option) {
                state.imageSort = option.dataset.sort;

                // Update active state
                imageSortMenu.querySelectorAll('.sort-option').forEach(opt => opt.classList.remove('active'));
                option.classList.add('active');

                renderImages();
                imageSortMenu.style.display = 'none';
                showToast('Images sorted!', 'success');
            }
        });
    }

    // Close sort menus on outside click
    document.addEventListener('click', () => {
        if (imageSortMenu) imageSortMenu.style.display = 'none';
    });

    // Duplicate Finder
    const findDuplicatesBtn = document.getElementById('findDuplicatesBtn');
    const duplicatesModal = document.getElementById('duplicatesModal');
    const duplicatesClose = document.getElementById('duplicatesClose');
    const duplicatesOverlay = document.getElementById('duplicatesOverlay');

    if (findDuplicatesBtn) {
        findDuplicatesBtn.addEventListener('click', findDuplicates);
    }

    if (duplicatesClose) {
        duplicatesClose.addEventListener('click', closeDuplicatesModal);
    }

    if (duplicatesOverlay) {
        duplicatesOverlay.addEventListener('click', closeDuplicatesModal);
    }
}

// ============ Helper Functions ============

function showLoading() {
    const loadingState = document.getElementById('loadingState');
    const imageGrid = document.getElementById('imageGrid');
    const emptyState = document.getElementById('emptyState');

    if (loadingState) loadingState.style.display = 'flex';
    if (imageGrid) imageGrid.style.display = 'none';
    if (emptyState) emptyState.style.display = 'none';
}

function hideLoading() {
    const loadingState = document.getElementById('loadingState');
    if (loadingState) loadingState.style.display = 'none';
}

// ============ Theme Functions ============

function initializeTheme() {
    // Check localStorage first
    const savedTheme = localStorage.getItem('theme');

    if (savedTheme) {
        document.documentElement.setAttribute('data-theme', savedTheme);
    } else {
        // Check system preference
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        const theme = prefersDark ? 'dark' : 'light';
        document.documentElement.setAttribute('data-theme', theme);
    }

    // Listen for system theme changes
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
        // Only auto-switch if user hasn't set a preference
        if (!localStorage.getItem('theme')) {
            const theme = e.matches ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', theme);
        }
    });
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';

    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);

    // Optional: Show a brief toast notification
    showToast(`Switched to ${newTheme} mode`, 'success', 2000);
}

function showToast(message, type = 'success', duration = null) {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;

    container.appendChild(toast);

    const displayDuration = duration || CONFIG.TOAST_DURATION_MS;

    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => {
            if (toast.parentNode) {
                container.removeChild(toast);
            }
        }, 300);
    }, displayDuration);
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';

    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

// ============ Upload Functions ============

function openUploadModal() {
    const modal = document.getElementById('uploadModal');
    const uploadPreview = document.getElementById('uploadPreview');
    const uploadArea = document.getElementById('uploadArea');

    if (modal) modal.style.display = 'block';
    if (uploadPreview) uploadPreview.style.display = 'none';
    if (uploadArea) uploadArea.style.display = 'block';
    state.uploadFiles = [];

    // Populate board selection dropdown
    populateUploadBoardSelect();
}

function closeUploadModal() {
    closeModal('uploadModal', () => {
        state.uploadFiles = [];
    });
}

function handleFileSelect(e) {
    const files = Array.from(e.target.files).filter(file =>
        file.type.startsWith('image/') || file.type.startsWith('video/')
    );

    if (files.length > 0) {
        state.uploadFiles = files;
        showUploadPreview();
    }
}

function showUploadPreview() {
    const preview = document.getElementById('uploadPreview');
    const fileList = document.getElementById('uploadFileList');
    const uploadArea = document.getElementById('uploadArea');

    if (uploadArea) uploadArea.style.display = 'none';
    if (preview) preview.style.display = 'block';

    if (fileList) {
        fileList.innerHTML = state.uploadFiles.map((file, index) => `
            <div class="upload-file-item">
                <span class="upload-file-name">${escapeHtml(file.name)} (${formatFileSize(file.size)})</span>
                <button class="upload-file-remove" onclick="removeUploadFile(${index})">×</button>
            </div>
        `).join('');
    }

    // Reset board selection
    const boardSelect = document.getElementById('uploadBoardSelect');
    const createSection = document.getElementById('createBoardSection');
    if (boardSelect) boardSelect.value = '';
    if (createSection) createSection.style.display = 'none';
}

function populateUploadBoardSelect() {
    const select = document.getElementById('uploadBoardSelect');
    if (!select) return;

    // Keep first two options (None and Create New)
    const firstOptions = Array.from(select.options).slice(0, 2);
    select.innerHTML = '';

    firstOptions.forEach(opt => select.add(opt));

    // Get all boards including subboards with full paths
    const allBoards = getAllBoardsFlat();

    // Add existing boards with hierarchical display
    allBoards.forEach(({ board, path, level }) => {
        const option = document.createElement('option');
        option.value = board.id;
        // Add indentation for subboards
        const indent = '  '.repeat(level);
        option.textContent = indent + (path ? path + ' / ' + board.name : board.name);
        select.add(option);
    });
}

// Helper function to get all boards in flat list with hierarchy info
function getAllBoardsFlat() {
    const result = [];

    function traverse(boards, parentPath = '', level = 0) {
        boards.forEach(board => {
            const currentPath = parentPath;
            result.push({ board, path: currentPath, level });

            if (board.sub_boards && board.sub_boards.length > 0) {
                const newPath = parentPath ? `${parentPath} / ${board.name}` : board.name;
                traverse(board.sub_boards, newPath, level + 1);
            }
        });
    }

    traverse(state.boards);
    return result;
}

function removeUploadFile(index) {
    state.uploadFiles.splice(index, 1);

    const uploadArea = document.getElementById('uploadArea');
    const uploadPreview = document.getElementById('uploadPreview');

    if (state.uploadFiles.length === 0) {
        if (uploadArea) uploadArea.style.display = 'block';
        if (uploadPreview) uploadPreview.style.display = 'none';
    } else {
        showUploadPreview();
    }
}

async function uploadFiles() {
    if (state.uploadFiles.length === 0) return;

    if (state.isUploading) {
        showToast('Upload already in progress', 'warning');
        return;
    }

    // Get selected board or create new
    const boardSelect = document.getElementById('uploadBoardSelect');
    const selectedBoardValue = boardSelect ? boardSelect.value : '';
    let targetBoardId = null;

    // Handle board selection
    if (selectedBoardValue === '__create_new__') {
        const boardName = document.getElementById('newBoardNameUpload').value.trim();
        if (!boardName) {
            showToast('Please enter a board name', 'warning');
            return;
        }

        const boardDesc = document.getElementById('newBoardDescUpload').value.trim();

        try {
            const response = await fetch('/api/boards', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: boardName, description: boardDesc })
            });

            if (response.ok) {
                const data = await response.json();
                targetBoardId = data.board_id;
                showToast(`Board "${boardName}" created`, 'success');
            } else {
                showToast('Failed to create board', 'error');
                return;
            }
        } catch (error) {
            console.error('Error creating board:', error);
            showToast('Error creating board', 'error');
            return;
        }
    } else if (selectedBoardValue) {
        targetBoardId = parseInt(selectedBoardValue);
    }

    state.isUploading = true;
    const uploadBtn = document.getElementById('startUploadBtn');
    const originalText = uploadBtn ? uploadBtn.textContent : '';

    if (uploadBtn) {
        uploadBtn.disabled = true;
        uploadBtn.textContent = 'Uploading...';
    }

    let uploaded = 0;
    let failed = 0;
    const uploadedImageIds = [];

    for (const file of state.uploadFiles) {
        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });

            if (response.ok) {
                const data = await response.json();
                if (data.image_id) {
                    uploaded++;
                    uploadedImageIds.push(data.image_id);
                } else {
                    console.error('No image_id in response:', data);
                    failed++;
                }
            } else {
                failed++;
            }
        } catch (error) {
            console.error('Upload error:', error);
            failed++;
        }
    }

    // Add uploaded images to board if selected
    if (targetBoardId && uploadedImageIds.length > 0) {
        for (const imageId of uploadedImageIds) {
            try {
                await fetch(`/api/boards/${targetBoardId}/images`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ image_id: imageId })
                });
            } catch (error) {
                console.error('Error adding image to board:', error);
            }
        }
    }

    const uploadMessage = `Uploaded ${uploaded} image${uploaded !== 1 ? 's' : ''}${failed > 0 ? `, ${failed} failed` : ''}`;
    showToast(uploadMessage, uploaded > 0 ? 'success' : 'error');

    closeUploadModal();

    await loadImages();
    await loadBoards();
    await updateStats();
    renderImages();

    if (uploadedImageIds.length > 0) {
        showToast(`Starting AI analysis for ${uploadedImageIds.length} image${uploadedImageIds.length !== 1 ? 's' : ''}...`, 'warning');

        let analyzed = 0;
        let analyzeFailed = 0;

        for (let i = 0; i < uploadedImageIds.length; i++) {
            const imageId = uploadedImageIds[i];

            try {
                console.log(`Analyzing image ${i + 1}/${uploadedImageIds.length}...`);
                await analyzeImage(imageId, 'classic', null);
                analyzed++;
            } catch (error) {
                console.error(`Failed to analyze image ${imageId}:`, error);
                analyzeFailed++;
            }
        }

        await loadImages();
        await updateStats();
        renderImages();

        const messages = [];
        if (analyzed > 0) {
            messages.push(`✨ Analyzed ${analyzed} image${analyzed !== 1 ? 's' : ''}`);
        }
        if (analyzeFailed > 0) {
            messages.push(`⚠️ ${analyzeFailed} failed`);
        }

        if (messages.length > 0) {
            showToast(messages.join(', '), analyzed > 0 ? 'success' : 'error');
        }
    }

    state.isUploading = false;
    if (uploadBtn) {
        uploadBtn.disabled = false;
        uploadBtn.textContent = originalText;
    }
}

// ============ Telegram Bot Management ============

async function loadBotStatus() {
    try {
        const data = await apiCall('/telegram/status');
        updateBotStatusUI(data);
        return data;
    } catch (error) {
        console.error('Failed to load bot status:', error);
        return null;
    }
}

function updateBotStatusUI(status) {
    const statusDot = document.getElementById('botStatusDot');
    const statusText = document.getElementById('botStatusText');
    const startBtn = document.getElementById('startBotBtn');
    const stopBtn = document.getElementById('stopBotBtn');

    if (status.running) {
        statusDot.textContent = '';
        statusText.textContent = `Bot Running (PID: ${status.pid})`;
        startBtn.disabled = true;
        stopBtn.disabled = false;
    } else if (status.configured) {
        statusDot.textContent = '';
        statusText.textContent = 'Bot Configured (Offline)';
        startBtn.disabled = false;
        stopBtn.disabled = true;
    } else {
        statusDot.textContent = '';
        statusText.textContent = 'Bot Not Configured';
        startBtn.disabled = true;
        stopBtn.disabled = true;
    }
}

async function startBot() {
    const startBtn = document.getElementById('startBotBtn');
    const originalText = startBtn.textContent;

    startBtn.disabled = true;
    startBtn.textContent = 'Starting...';

    try {
        const data = await apiCall('/telegram/start', { method: 'POST' });

        if (data.success) {
            showToast(data.message, 'success');
            await loadBotStatus();
        } else {
            showToast(data.message, 'error');
        }
    } catch (error) {
        showToast('Failed to start bot: ' + error.message, 'error');
    } finally {
        startBtn.disabled = false;
        startBtn.textContent = originalText;
    }
}

async function stopBot() {
    const stopBtn = document.getElementById('stopBotBtn');
    const originalText = stopBtn.textContent;

    stopBtn.disabled = true;
    stopBtn.textContent = 'Stopping...';

    try {
        const data = await apiCall('/telegram/stop', { method: 'POST' });

        if (data.success) {
            showToast(data.message, 'success');
            await loadBotStatus();
        } else {
            showToast(data.message, 'error');
        }
    } catch (error) {
        showToast('Failed to stop bot: ' + error.message, 'error');
    } finally {
        stopBtn.disabled = false;
        stopBtn.textContent = originalText;
    }
}

async function testBot() {
    const status = await loadBotStatus();

    if (status && status.running) {
        showToast('Bot is running! Try sending a photo to your bot on Telegram.', 'success');
    } else if (status && status.configured) {
        showToast('Bot is configured but not running. Click Start to begin.', 'warning');
    } else {
        showToast('Bot is not configured. Please add your bot token and save.', 'error');
    }
}

async function viewBotLogs() {
    const logsSection = document.getElementById('botLogsSection');
    const viewLogsBtn = document.getElementById('viewLogsBtn');

    // Toggle logs section visibility
    if (logsSection.style.display === 'none') {
        logsSection.style.display = 'block';
        viewLogsBtn.textContent = 'Hide Logs';
        await loadBotLogs();
    } else {
        logsSection.style.display = 'none';
        viewLogsBtn.textContent = 'View Logs';
    }
}

async function loadBotLogs() {
    const logsEl = document.getElementById('botLogs');

    try {
        logsEl.textContent = 'Loading logs...';

        const data = await apiCall('/telegram/logs?lines=200');

        if (data.logs) {
            logsEl.textContent = data.logs || 'No logs available';

            // Auto-scroll to bottom
            logsEl.scrollTop = logsEl.scrollHeight;
        } else {
            logsEl.textContent = data.message || 'No logs available';
        }
    } catch (error) {
        logsEl.textContent = 'Error loading logs: ' + error.message;
        console.error('Failed to load bot logs:', error);
    }
}

async function loadBotConfig() {
    try {
        const data = await apiCall('/telegram/config');
        const config = data.config;

        if (config.TELEGRAM_BOT_TOKEN) {
            document.getElementById('botToken').value = config.TELEGRAM_BOT_TOKEN;
        }

        if (config.AUTO_ANALYZE !== undefined) {
            document.getElementById('autoAnalyze').checked = config.AUTO_ANALYZE === 'true';
        }

        if (config.AI_STYLE) {
            document.getElementById('aiStyle').value = config.AI_STYLE;
        }
    } catch (error) {
        console.error('Failed to load bot config:', error);
    }
}

async function saveBotConfig() {
    const botToken = document.getElementById('botToken').value.trim();
    const autoAnalyze = document.getElementById('autoAnalyze').checked ? 'true' : 'false';
    const aiStyle = document.getElementById('aiStyle').value;

    if (!botToken) {
        showToast('Please enter a bot token', 'error');
        return;
    }

    try {
        const data = await apiCall('/telegram/config', {
            method: 'POST',
            body: JSON.stringify({
                bot_token: botToken,
                auto_analyze: autoAnalyze,
                ai_style: aiStyle
            })
        });

        if (data.success) {
            showToast('Configuration saved successfully!', 'success');
            await loadBotStatus();
        } else {
            showToast('Failed to save configuration', 'error');
        }
    } catch (error) {
        showToast('Failed to save configuration: ' + error.message, 'error');
    }
}

function openSettingsModal() {
    const modal = document.getElementById('settingsModal');
    modal.style.display = 'block';

    loadBotStatus();
    loadBotConfig();
    loadExternalAppsForSettings();
}

function closeSettingsModal() {
    closeModal('settingsModal');
}

// ============ Batch Selection Mode ============

function toggleSelectionMode() {
    state.selectionMode = !state.selectionMode;

    const imageGrid = document.getElementById('imageGrid');
    const selectBtn = document.getElementById('selectBtn');

    if (state.selectionMode) {
        imageGrid.classList.add('selection-mode');
        selectBtn.textContent = 'Cancel';
        selectBtn.classList.remove('btn-secondary');
        selectBtn.classList.add('btn-danger');
    } else {
        imageGrid.classList.remove('selection-mode');
        selectBtn.textContent = 'Select';
        selectBtn.classList.remove('btn-danger');
        selectBtn.classList.add('btn-secondary');

        // Clear selection when exiting selection mode
        deselectAllImages();
    }
}

function toggleImageSelection(imageId) {
    if (state.selectedImages.has(imageId)) {
        state.selectedImages.delete(imageId);
    } else {
        state.selectedImages.add(imageId);
    }

    updateSelectionUI();
}

function selectAllImages() {
    // Select all currently visible images
    state.images.forEach(img => {
        state.selectedImages.add(img.id);
    });

    updateSelectionUI();
}

function deselectAllImages() {
    state.selectedImages.clear();
    updateSelectionUI();
}

function updateSelectionUI() {
    const count = state.selectedImages.size;
    const batchBar = document.getElementById('batchOperationsBar');
    const selectedCountEl = document.getElementById('selectedCount');

    // Update count
    if (selectedCountEl) {
        selectedCountEl.textContent = count;
    }

    // Show/hide batch operations bar
    if (count > 0) {
        batchBar.style.display = 'flex';
    } else {
        batchBar.style.display = 'none';
    }

    // Update checkboxes in the grid
    state.images.forEach(img => {
        const card = document.querySelector(`.image-card[data-id="${img.id}"]`);
        const checkbox = card?.querySelector('.image-card-checkbox');

        if (card && checkbox) {
            if (state.selectedImages.has(img.id)) {
                card.classList.add('selected');
                checkbox.classList.add('checked');
            } else {
                card.classList.remove('selected');
                checkbox.classList.remove('checked');
            }
        }
    });
}

// Batch Operations
async function batchAnalyzeImages() {
    if (state.selectedImages.size === 0) {
        showToast('No images selected', 'error');
        return;
    }

    if (state.isAnalyzing) {
        showToast('Analysis already in progress...', 'warning');
        return;
    }

    // Open AI style selector
    state.pendingBatchOperation = 'analyze';
    openAIStyleModal(true); // true indicates batch mode
}

async function performBatchAnalyze(style, customPrompt = null) {
    const selectedIds = Array.from(state.selectedImages);
    const total = selectedIds.length;
    const CONCURRENT_LIMIT = 3; // Process 3 images in parallel

    state.isAnalyzing = true;
    showToast(`Analyzing ${total} images...`, 'info');

    let completed = 0;
    let failed = 0;

    // Helper to analyze a single image
    const analyzeOne = async (imageId) => {
        try {
            const requestBody = { style };
            if (customPrompt) {
                requestBody.custom_prompt = customPrompt;
            }

            await apiCall(`/images/${imageId}/analyze`, {
                method: 'POST',
                body: JSON.stringify(requestBody)
            });

            completed++;
            showToast(`Analyzed ${completed}/${total} images...`, 'info');
        } catch (error) {
            console.error(`Failed to analyze image ${imageId}:`, error);
            failed++;
        }
    };

    // Process in chunks for parallel execution
    for (let i = 0; i < selectedIds.length; i += CONCURRENT_LIMIT) {
        const chunk = selectedIds.slice(i, i + CONCURRENT_LIMIT);
        await Promise.all(chunk.map(analyzeOne));
    }

    state.isAnalyzing = false;

    // Reload images to get updated data
    await loadImages();
    renderImages();

    if (failed > 0) {
        showToast(`Analysis complete: ${completed} succeeded, ${failed} failed`, 'warning');
    } else {
        showToast(`Successfully analyzed ${completed} images! ✨`, 'success');
    }

    // Clear selection and exit selection mode
    deselectAllImages();
    if (state.selectionMode) {
        toggleSelectionMode();
    }
}

async function batchTagImages() {
    if (state.selectedImages.size === 0) {
        showToast('No images selected', 'error');
        return;
    }

    if (state.isAnalyzing) {
        showToast('Analysis already in progress...', 'warning');
        return;
    }

    const selectedIds = Array.from(state.selectedImages);
    const total = selectedIds.length;

    state.isAnalyzing = true;
    showToast(`Generating AI tags for ${total} images...`, 'info');

    let completed = 0;
    let failed = 0;

    for (const imageId of selectedIds) {
        try {
            await apiCall(`/images/${imageId}/analyze`, {
                method: 'POST',
                body: JSON.stringify({ style: 'tags' })
            });

            completed++;
            showToast(`Tagged ${completed}/${total} images...`, 'info');
        } catch (error) {
            console.error(`Failed to tag image ${imageId}:`, error);
            failed++;
        }
    }

    state.isAnalyzing = false;

    await loadImages();
    await loadTags();
    renderImages();
    renderTagCloud();

    if (failed > 0) {
        showToast(`Tagging complete: ${completed} succeeded, ${failed} failed`, 'warning');
    } else {
        showToast(`Successfully tagged ${completed} images! 🏷️`, 'success');
    }

    deselectAllImages();
    if (state.selectionMode) {
        toggleSelectionMode();
    }
}

async function batchNameImages() {
    if (state.selectedImages.size === 0) {
        showToast('No images selected', 'error');
        return;
    }

    if (state.isAnalyzing) {
        showToast('Analysis already in progress...', 'warning');
        return;
    }

    const selectedIds = Array.from(state.selectedImages);
    const total = selectedIds.length;

    state.isAnalyzing = true;
    showToast(`Generating AI names for ${total} images...`, 'info');

    let completed = 0;
    let failed = 0;

    for (const imageId of selectedIds) {
        try {
            // Use a custom prompt focused on generating descriptive names
            await apiCall(`/images/${imageId}/analyze`, {
                method: 'POST',
                body: JSON.stringify({
                    style: 'custom',
                    custom_prompt: 'Generate a short, descriptive name for this image (max 5 words). Only return the name, nothing else.'
                })
            });

            completed++;
            showToast(`Named ${completed}/${total} images...`, 'info');
        } catch (error) {
            console.error(`Failed to name image ${imageId}:`, error);
            failed++;
        }
    }

    state.isAnalyzing = false;

    await loadImages();
    renderImages();

    if (failed > 0) {
        showToast(`Naming complete: ${completed} succeeded, ${failed} failed`, 'warning');
    } else {
        showToast(`Successfully named ${completed} images! ✏️`, 'success');
    }

    deselectAllImages();
    if (state.selectionMode) {
        toggleSelectionMode();
    }
}

async function batchAddImagesToBoard() {
    if (state.selectedImages.size === 0) {
        showToast('No images selected', 'error');
        return;
    }

    // Open the add to board modal with selected images
    const selectedIds = Array.from(state.selectedImages);

    // Store selected IDs for batch operation
    state.pendingBatchBoardImageIds = selectedIds;

    // Open modal (reuse existing add to board modal)
    openAddToBoardModal(selectedIds[0], true); // true indicates batch mode
}

// ============ Delete Image ============

function confirmDeleteImage(imageId, filename) {
    // Create confirmation modal
    const existingModal = document.getElementById('deleteConfirmModal');
    if (existingModal) {
        existingModal.remove();
    }

    const modal = document.createElement('div');
    modal.id = 'deleteConfirmModal';
    modal.className = 'modal';
    modal.style.display = 'block';
    modal.innerHTML = `
        <div class="modal-overlay" onclick="closeDeleteConfirmModal()"></div>
        <div class="modal-content modal-small" style="max-width: 400px;">
            <button class="modal-close" onclick="closeDeleteConfirmModal()">&times;</button>
            <div class="modal-body" style="text-align: center;">
                <h2 style="color: var(--error); margin-bottom: var(--spacing-lg);">🗑️ Delete Image</h2>
                <p style="margin-bottom: var(--spacing-md); color: var(--text-secondary);">
                    Are you sure you want to delete<br>
                    <strong style="color: var(--text-primary);">${filename}</strong>?
                </p>
                <div style="display: flex; flex-direction: column; gap: var(--spacing-sm); margin-top: var(--spacing-lg);">
                    <button class="btn btn-danger" onclick="deleteImage(${imageId}, false)">
                        Remove from Gallery Only
                    </button>
                    <button class="btn btn-danger" style="background: #8b0000;" onclick="deleteImage(${imageId}, true)">
                        Delete File from Disk
                    </button>
                    <button class="btn btn-secondary" onclick="closeDeleteConfirmModal()">
                        Cancel
                    </button>
                </div>
                <p style="font-size: 12px; color: var(--text-muted); margin-top: var(--spacing-md);">
                    "Remove from Gallery" keeps the file on your disk.<br>
                    "Delete File" permanently removes it.
                </p>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
}

function closeDeleteConfirmModal() {
    const modal = document.getElementById('deleteConfirmModal');
    if (modal) {
        modal.remove();
    }
}

async function deleteImage(imageId, deleteFile = false) {
    try {
        const response = await fetch(`/api/images/${imageId}?delete_file=${deleteFile}`, {
            method: 'DELETE'
        });

        const data = await response.json();

        if (response.ok) {
            // Close modals
            closeDeleteConfirmModal();
            closeImageModal();

            // Remove from state
            state.images = state.images.filter(img => img.id !== imageId);

            // Re-render
            renderImages();
            updateCounts();

            // Refresh duplicates modal if open
            const duplicatesModal = document.getElementById('duplicatesModal');
            if (duplicatesModal && duplicatesModal.style.display === 'block') {
                findDuplicates();
            }

            // Show success message
            const message = deleteFile
                ? 'Image deleted from gallery and disk'
                : 'Image removed from gallery';
            showToast(message, 'success');
        } else {
            showToast(data.error || 'Failed to delete image', 'error');
        }
    } catch (error) {
        console.error('Error deleting image:', error);
        showToast('Failed to delete image', 'error');
    }
}

// ============ Duplicate Finder ============

async function findDuplicates() {
    const modal = document.getElementById('duplicatesModal');
    const loading = document.getElementById('duplicatesLoading');
    const content = document.getElementById('duplicatesContent');
    const empty = document.getElementById('duplicatesEmpty');

    // Show modal
    if (modal) modal.style.display = 'block';
    if (loading) loading.style.display = 'block';
    if (content) content.innerHTML = '';
    if (empty) empty.style.display = 'none';

    try {
        // Get all images from current view
        const images = state.images;

        if (images.length === 0) {
            showToast('No images to analyze', 'warning');
            closeDuplicatesModal();
            return;
        }

        // Group images by file size (quick first pass)
        const sizeGroups = new Map();
        images.forEach(img => {
            const size = img.file_size || 0;
            if (!sizeGroups.has(size)) {
                sizeGroups.set(size, []);
            }
            sizeGroups.get(size).push(img);
        });

        // Find potential duplicates (same size)
        const duplicateGroups = [];
        sizeGroups.forEach((group, size) => {
            if (group.length > 1 && size > 0) {
                // Further group by filename similarity
                const nameGroups = new Map();
                group.forEach(img => {
                    // Extract base filename without extension and numbers
                    const baseName = img.filename
                        .replace(/\.[^.]+$/, '') // remove extension
                        .replace(/[_\-\s]*\d+[_\-\s]*$/, '') // remove trailing numbers
                        .toLowerCase();

                    if (!nameGroups.has(baseName)) {
                        nameGroups.set(baseName, []);
                    }
                    nameGroups.get(baseName).push(img);
                });

                nameGroups.forEach(nameGroup => {
                    if (nameGroup.length > 1) {
                        duplicateGroups.push(nameGroup);
                    }
                });
            }
        });

        if (loading) loading.style.display = 'none';

        if (duplicateGroups.length === 0) {
            if (empty) empty.style.display = 'block';
        } else {
            if (content) {
                content.innerHTML = `
                    <p style="margin-bottom: var(--spacing-lg); color: var(--text-secondary);">
                        Found ${duplicateGroups.length} group${duplicateGroups.length > 1 ? 's' : ''} of potential duplicates
                    </p>
                    ${duplicateGroups.map((group, index) => createDuplicateGroup(group, index)).join('')}
                `;
            }
        }
    } catch (error) {
        console.error('Error finding duplicates:', error);
        showToast('Error analyzing duplicates', 'error');
        if (loading) loading.style.display = 'none';
    }
}

function createDuplicateGroup(images, groupIndex) {
    return `
        <div class="duplicate-group" style="margin-bottom: var(--spacing-xl);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--spacing-md);">
                <h3 style="font-size: 16px; color: var(--text-primary);">
                    Group ${groupIndex + 1}
                    <span style="color: var(--text-secondary); font-size: 14px; font-weight: normal;">
                        (${images.length} images, ${formatFileSize(images[0].file_size || 0)})
                    </span>
                </h3>
            </div>
            <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: var(--spacing-md);">
                ${images.map(img => createDuplicateCard(img)).join('')}
            </div>
        </div>
    `;
}

function createDuplicateCard(image) {
    const isVideo = image.media_type === 'video';
    const escapedFilename = escapeHtml(image.filename).replace(/'/g, "\\'");

    return `
        <div class="duplicate-card" style="position: relative; border: 1px solid var(--border-color); border-radius: var(--radius-md); overflow: hidden;">
            <div style="position: relative; aspect-ratio: 1; overflow: hidden; background: var(--bg-tertiary); cursor: pointer;" onclick="openImageModal(state.images.find(img => img.id === ${image.id}))">
                ${isVideo ?
            `<img
                        src="/api/images/${image.id}/thumbnail?size=300"
                        alt="${escapeHtml(image.filename)}"
                        style="width: 100%; height: 100%; object-fit: cover;"
                    >
                    <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); background: rgba(0,0,0,0.7); border-radius: 50%; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center;">
                        <div style="font-size: 20px;">▶</div>
                    </div>` :
            `<img
                        src="/api/images/${image.id}/thumbnail?size=300"
                        alt="${escapeHtml(image.filename)}"
                        style="width: 100%; height: 100%; object-fit: cover;"
                    >`
        }
            </div>
            <div style="padding: var(--spacing-sm); background: var(--bg-secondary);">
                <div style="font-size: 12px; color: var(--text-primary); font-weight: 600; margin-bottom: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(image.filename)}">
                    ${escapeHtml(image.filename)}
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="font-size: 11px; color: var(--text-secondary);">
                        ${image.width || 0}×${image.height || 0}
                    </div>
                    <button class="btn btn-danger btn-sm" onclick="event.stopPropagation(); confirmDeleteImage(${image.id}, '${escapedFilename}')" style="padding: 4px 8px; font-size: 11px;">
                        🗑️
                    </button>
                </div>
            </div>
        </div>
    `;
}

function closeDuplicatesModal() {
    const modal = document.getElementById('duplicatesModal');
    if (modal) modal.style.display = 'none';
}

// ============ Export Functions ============

function showExportMenu(event, imageId) {
    event.stopPropagation();

    const existingMenu = document.querySelector('.export-dropdown');
    if (existingMenu) {
        existingMenu.remove();
        return;
    }

    const menu = document.createElement('div');
    menu.className = 'export-dropdown';
    menu.style.cssText = `
        position: fixed;
        top: ${event.clientY}px;
        left: ${event.clientX}px;
        background: var(--bg-secondary);
        border: 1px solid var(--border);
        border-radius: var(--radius-md);
        padding: var(--spacing-sm);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        z-index: 10000;
        min-width: 180px;
    `;

    menu.innerHTML = `
        <div class="menu-item" onclick="exportSingleImage(${imageId}, 'csv')">
            📊 Export to CSV
        </div>
        <div class="menu-item" onclick="exportSingleImage(${imageId}, 'json')">
            📋 Export to JSON
        </div>
        <div class="menu-item" onclick="exportSingleImage(${imageId}, 'pdf')">
            📄 Generate PDF
        </div>
    `;

    document.body.appendChild(menu);

    setTimeout(() => {
        document.addEventListener('click', function closeMenu() {
            menu.remove();
            document.removeEventListener('click', closeMenu);
        });
    }, 100);
}

async function exportSingleImage(imageId, format) {
    try {
        showToast(`Preparing ${format.toUpperCase()} export...`, 'info');

        let url, method, body;

        if (format === 'csv') {
            url = '/api/export/images/csv';
            method = 'POST';
            body = JSON.stringify({ image_ids: [imageId] });
        } else if (format === 'json') {
            url = '/api/export/images/json';
            method = 'POST';
            body = JSON.stringify({ image_ids: [imageId], include_summary: true });
        } else if (format === 'pdf') {
            url = '/api/export/images/pdf';
            method = 'POST';
            body = JSON.stringify({
                image_ids: [imageId],
                title: 'Image Catalog',
                page_size: 'A4',
                orientation: 'portrait'
            });
        }

        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json'
            },
            body: body
        });

        if (!response.ok) {
            throw new Error('Export failed');
        }

        // Get filename from Content-Disposition header
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = `export.${format}`;
        if (contentDisposition) {
            const matches = /filename="(.+?)"/.exec(contentDisposition);
            if (matches) {
                filename = matches[1];
            }
        }

        // Download the file
        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(downloadUrl);

        showToast(`${format.toUpperCase()} exported successfully!`, 'success');
    } catch (error) {
        console.error('Export error:', error);
        showToast('Export failed. Please try again.', 'error');
    }
}

function showBoardExportMenu(event, boardId) {
    event.stopPropagation();

    const existingMenu = document.querySelector('.export-dropdown');
    if (existingMenu) {
        existingMenu.remove();
        return;
    }

    const menu = document.createElement('div');
    menu.className = 'export-dropdown';
    menu.style.cssText = `
        position: fixed;
        top: ${event.clientY}px;
        left: ${event.clientX}px;
        background: var(--bg-secondary);
        border: 1px solid var(--border);
        border-radius: var(--radius-md);
        padding: var(--spacing-sm);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        z-index: 10000;
        min-width: 200px;
    `;

    menu.innerHTML = `
        <div class="menu-item" onclick="exportBoard(${boardId}, 'csv')">
            📊 Export to CSV
        </div>
        <div class="menu-item" onclick="exportBoard(${boardId}, 'json')">
            📋 Export to JSON
        </div>
        <div class="menu-item" onclick="showBoardPDFOptions(${boardId})">
            📄 Generate PDF Catalog
        </div>
    `;

    document.body.appendChild(menu);

    setTimeout(() => {
        document.addEventListener('click', function closeMenu() {
            menu.remove();
            document.removeEventListener('click', closeMenu);
        });
    }, 100);
}

async function exportBoard(boardId, format) {
    try {
        showToast(`Preparing ${format.toUpperCase()} export...`, 'info');

        const url = `/api/export/boards/${boardId}/${format}`;
        const response = await fetch(url);

        if (!response.ok) {
            throw new Error('Export failed');
        }

        // Get filename from Content-Disposition header
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = `board_export.${format}`;
        if (contentDisposition) {
            const matches = /filename="(.+?)"/.exec(contentDisposition);
            if (matches) {
                filename = matches[1];
            }
        }

        // Download the file
        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(downloadUrl);

        showToast(`${format.toUpperCase()} exported successfully!`, 'success');
    } catch (error) {
        console.error('Export error:', error);
        showToast('Export failed. Please try again.', 'error');
    }
}

function showBoardPDFOptions(boardId) {
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.style.display = 'block';

    modal.innerHTML = `
        <div class="modal-overlay" onclick="this.parentElement.remove()"></div>
        <div class="modal-content modal-small">
            <button class="modal-close" onclick="this.closest('.modal').remove()">&times;</button>
            <div class="modal-body">
                <h2>PDF Export Options</h2>

                <div class="form-group">
                    <label>Page Size</label>
                    <select id="pdfPageSize" style="width: 100%; padding: var(--spacing-sm); background: var(--bg-tertiary); border: 1px solid var(--border); border-radius: var(--radius-sm); color: var(--text-primary);">
                        <option value="A4">A4 (210 × 297 mm)</option>
                        <option value="letter">Letter (8.5 × 11 in)</option>
                    </select>
                </div>

                <div class="form-group">
                    <label>Orientation</label>
                    <select id="pdfOrientation" style="width: 100%; padding: var(--spacing-sm); background: var(--bg-tertiary); border: 1px solid var(--border); border-radius: var(--radius-sm); color: var(--text-primary);">
                        <option value="portrait">Portrait</option>
                        <option value="landscape">Landscape</option>
                    </select>
                </div>

                <div class="form-actions">
                    <button class="btn btn-secondary" onclick="this.closest('.modal').remove()">Cancel</button>
                    <button class="btn btn-primary" onclick="generateBoardPDF(${boardId})">Generate PDF</button>
                </div>
            </div>
        </div>
    `;

    document.body.appendChild(modal);
}

async function generateBoardPDF(boardId) {
    try {
        const pageSize = document.getElementById('pdfPageSize').value;
        const orientation = document.getElementById('pdfOrientation').value;

        // Close the options modal
        document.querySelector('.modal').remove();

        showToast('Generating PDF catalog...', 'info');

        const response = await fetch(`/api/export/boards/${boardId}/pdf`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                page_size: pageSize,
                orientation: orientation
            })
        });

        if (!response.ok) {
            throw new Error('PDF generation failed');
        }

        // Get filename from Content-Disposition header
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = 'catalog.pdf';
        if (contentDisposition) {
            const matches = /filename="(.+?)"/.exec(contentDisposition);
            if (matches) {
                filename = matches[1];
            }
        }

        // Download the file
        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(downloadUrl);

        showToast('PDF catalog generated successfully!', 'success');
    } catch (error) {
        console.error('PDF generation error:', error);
        showToast('PDF generation failed. Please try again.', 'error');
    }
}

async function exportSelectedImages(format) {
    const selectedImageIds = Array.from(state.selectedImages);

    if (selectedImageIds.length === 0) {
        showToast('No images selected', 'warning');
        return;
    }

    try {
        showToast(`Exporting ${selectedImageIds.length} images to ${format.toUpperCase()}...`, 'info');

        let url, method, body;

        if (format === 'csv') {
            url = '/api/export/images/csv';
            method = 'POST';
            body = JSON.stringify({ image_ids: selectedImageIds });
        } else if (format === 'json') {
            url = '/api/export/images/json';
            method = 'POST';
            body = JSON.stringify({ image_ids: selectedImageIds, include_summary: true });
        } else if (format === 'pdf') {
            url = '/api/export/images/pdf';
            method = 'POST';
            body = JSON.stringify({
                image_ids: selectedImageIds,
                title: 'Selected Images',
                subtitle: `${selectedImageIds.length} images`,
                page_size: 'A4',
                orientation: 'portrait'
            });
        }

        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json'
            },
            body: body
        });

        if (!response.ok) {
            throw new Error('Export failed');
        }

        // Get filename from Content-Disposition header
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = `export.${format}`;
        if (contentDisposition) {
            const matches = /filename="(.+?)"/.exec(contentDisposition);
            if (matches) {
                filename = matches[1];
            }
        }

        // Download the file
        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(downloadUrl);

        showToast(`${format.toUpperCase()} exported successfully!`, 'success');
    } catch (error) {
        console.error('Export error:', error);
        showToast('Export failed. Please try again.', 'error');
    }
}

function showBatchExportMenu(event) {
    if (state.selectedImages.size === 0) {
        showToast('No images selected', 'warning');
        return;
    }

    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.style.display = 'block';

    modal.innerHTML = `
        <div class="modal-overlay" onclick="this.parentElement.remove()"></div>
        <div class="modal-content modal-small">
            <button class="modal-close" onclick="this.closest('.modal').remove()">&times;</button>
            <div class="modal-body">
                <h2>Export Selected Images</h2>
                <p style="color: var(--text-secondary); margin-bottom: var(--spacing-lg);">
                    ${state.selectedImages.size} image(s) selected
                </p>

                <div class="form-group">
                    <button class="btn btn-primary" onclick="exportSelectedImages('csv'); this.closest('.modal').remove();" style="width: 100%; margin-bottom: var(--spacing-sm);">
                        📊 Export to CSV
                    </button>
                    <button class="btn btn-primary" onclick="exportSelectedImages('json'); this.closest('.modal').remove();" style="width: 100%; margin-bottom: var(--spacing-sm);">
                        📋 Export to JSON
                    </button>
                    <button class="btn btn-primary" onclick="exportSelectedImages('pdf'); this.closest('.modal').remove();" style="width: 100%;">
                        📄 Generate PDF Catalog
                    </button>
                </div>

                <div class="form-actions" style="margin-top: var(--spacing-lg);">
                    <button class="btn btn-secondary" onclick="this.closest('.modal').remove()">Cancel</button>
                </div>
            </div>
        </div>
    `;

    document.body.appendChild(modal);
}

// ============ Reverse Image Search ============

async function openReverseSearchModal(imageId) {
    try {
        const response = await fetch(`/api/images/${imageId}/reverse-search`);
        const data = await response.json();

        if (!response.ok || !data.success) {
            showToast('Failed to load search options', 'error');
            return;
        }

        const modal = document.createElement('div');
        modal.className = 'modal';
        modal.style.display = 'block';

        const searchOptionsHTML = data.search_options.map(option => `
            <div style="border: 1px solid var(--border); border-radius: var(--radius-md); padding: var(--spacing-md); margin-bottom: var(--spacing-md); background: var(--bg-tertiary);">
                <div style="display: flex; align-items: start; gap: var(--spacing-md);">
                    <div style="font-size: 32px; flex-shrink: 0;">${option.icon}</div>
                    <div style="flex: 1;">
                        <h3 style="margin: 0 0 var(--spacing-xs) 0; font-size: 16px; color: var(--text-primary);">
                            ${escapeHtml(option.provider)}
                        </h3>
                        <p style="margin: 0 0 var(--spacing-sm) 0; color: var(--text-secondary); font-size: 14px;">
                            ${escapeHtml(option.description)}
                        </p>
                        ${option.features ? `
                            <div style="display: flex; flex-wrap: wrap; gap: var(--spacing-xs); margin-bottom: var(--spacing-sm);">
                                ${option.features.map(feature => `
                                    <span style="font-size: 11px; padding: 2px 8px; background: var(--bg-secondary); border-radius: var(--radius-sm); color: var(--text-secondary);">
                                        ${escapeHtml(feature)}
                                    </span>
                                `).join('')}
                            </div>
                        ` : ''}
                        ${option.download ? `
                            <a href="${option.url}" download="${data.image_filename}" class="btn btn-primary" style="display: inline-block; text-decoration: none; margin-top: var(--spacing-sm);">
                                💾 Download Image
                            </a>
                        ` : `
                            <button class="btn btn-primary" onclick="openSearchAndDownload('${option.url}', '/api/images/${imageId}/file', '${escapeHtml(data.image_filename)}', '${escapeHtml(option.provider)}')" style="margin-top: var(--spacing-sm);">
                                🔗 Open ${escapeHtml(option.provider)}
                            </button>
                        `}
                    </div>
                </div>
            </div>
        `).join('');

        const copyrightTipsHTML = data.copyright_tips.map(tip => `
            <li style="margin-bottom: var(--spacing-xs); color: var(--text-secondary);">${escapeHtml(tip)}</li>
        `).join('');

        modal.innerHTML = `
            <div class="modal-overlay" onclick="this.parentElement.remove()"></div>
            <div class="modal-content" style="max-width: 800px; max-height: 90vh; overflow-y: auto;">
                <button class="modal-close" onclick="this.closest('.modal').remove()">&times;</button>
                <div class="modal-body">
                    <h2>🔍 Reverse Image Search</h2>
                    <p style="color: var(--text-secondary); margin-bottom: var(--spacing-lg);">
                        Find where this image appears online, discover its original source, and check copyright information.
                    </p>

                    <div style="background: var(--bg-secondary); padding: var(--spacing-md); border-radius: var(--radius-md); margin-bottom: var(--spacing-lg);">
                        <div style="display: flex; align-items: center; gap: var(--spacing-md);">
                            <img src="/api/images/${imageId}/thumbnail?size=200"
                                 alt="${escapeHtml(data.image_filename)}"
                                 style="width: 150px; height: 150px; object-fit: cover; border-radius: var(--radius-sm);">
                            <div style="flex: 1;">
                                <strong style="color: var(--text-primary); display: block; margin-bottom: var(--spacing-sm);">
                                    ${escapeHtml(data.image_filename)}
                                </strong>
                                <button class="btn btn-secondary btn-sm" onclick="openImageFolder(${imageId})" style="margin-bottom: var(--spacing-xs);">
                                    📁 Open Folder
                                </button>
                                <a href="/api/images/${imageId}/file" download="${escapeHtml(data.image_filename)}" class="btn btn-secondary btn-sm" style="display: inline-block; text-decoration: none;">
                                    💾 Download
                                </a>
                            </div>
                        </div>
                    </div>

                    <h3 style="margin-bottom: var(--spacing-md);">Search Engines</h3>
                    ${searchOptionsHTML}

                    <details style="margin-top: var(--spacing-xl);">
                        <summary style="cursor: pointer; font-weight: 600; color: var(--text-primary); margin-bottom: var(--spacing-md);">
                            📋 Copyright & Usage Tips
                        </summary>
                        <div style="padding: var(--spacing-md); background: var(--bg-tertiary); border-radius: var(--radius-md); margin-top: var(--spacing-md);">
                            <ul style="margin: 0; padding-left: var(--spacing-lg);">
                                ${copyrightTipsHTML}
                            </ul>
                        </div>
                    </details>

                    <div class="form-actions" style="margin-top: var(--spacing-xl);">
                        <button class="btn btn-secondary" onclick="this.closest('.modal').remove()">Close</button>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(modal);
    } catch (error) {
        console.error('Reverse search error:', error);
        showToast('Failed to open reverse search', 'error');
    }
}

function openSearchAndDownload(searchUrl, imageUrl, filename, provider) {
    // Open search engine in new tab
    window.open(searchUrl, '_blank');

    // Trigger download
    const link = document.createElement('a');
    link.href = imageUrl;
    link.download = filename;
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    // Show instructions
    showToast(`📥 Image downloaded! Now drag and drop it to ${provider} or use their upload button.`, 'success', 6000);
}

// ============ Send to Telegram ============

async function openSendToTelegramModal(imageId) {
    try {
        // Get image details
        const response = await fetch(`/api/images/${imageId}`);
        const image = await response.json();

        if (!response.ok) {
            showToast('Failed to load image details', 'error');
            return;
        }

        // Retrieve saved chat_id from localStorage
        const savedChatId = localStorage.getItem('telegram_chat_id') || '';
        const savedCaption = localStorage.getItem('telegram_default_caption') || '';

        const modal = document.createElement('div');
        modal.className = 'modal';
        modal.id = 'telegram-send-modal';
        modal.style.display = 'block';

        const mediaType = image.media_type || 'image';
        const mediaLabel = mediaType === 'video' ? 'video' : 'image';
        const mediaIcon = mediaType === 'video' ? '🎥' : '📤';

        modal.innerHTML = `
            <div class="modal-overlay" onclick="this.parentElement.remove()"></div>
            <div class="modal-content" style="max-width: 600px;">
                <button class="modal-close" onclick="this.closest('.modal').remove()">&times;</button>
                <div class="modal-body">
                    <h2>${mediaIcon} Send to Telegram</h2>
                    <p style="color: var(--text-secondary); margin-bottom: var(--spacing-lg);">
                        Send this ${mediaLabel} to your Telegram chat or group.
                    </p>

                    <div style="background: var(--bg-secondary); padding: var(--spacing-md); border-radius: var(--radius-md); margin-bottom: var(--spacing-lg);">
                        <div style="display: flex; align-items: center; gap: var(--spacing-md);">
                            <img src="/api/images/${imageId}/thumbnail?size=200"
                                 alt="${escapeHtml(image.filename)}"
                                 style="width: 100px; height: 100px; object-fit: cover; border-radius: var(--radius-sm);">
                            <div style="flex: 1;">
                                <strong style="color: var(--text-primary); display: block; margin-bottom: var(--spacing-xs);">
                                    ${escapeHtml(image.filename)}
                                </strong>
                                <span style="font-size: 13px; color: var(--text-secondary);">
                                    ${image.width} × ${image.height}
                                </span>
                            </div>
                        </div>
                    </div>

                    <div style="margin-bottom: var(--spacing-lg);">
                        <label style="display: block; margin-bottom: var(--spacing-sm); font-weight: 600; color: var(--text-primary);">
                            Chat ID <span style="color: red;">*</span>
                        </label>
                        <input type="text"
                               id="telegram-chat-id"
                               class="form-control"
                               value="${escapeHtml(savedChatId)}"
                               placeholder="-1001234567890"
                               style="width: 100%; padding: var(--spacing-sm); border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--bg-primary); color: var(--text-primary);">
                        <small style="color: var(--text-secondary); display: block; margin-top: var(--spacing-xs);">
                            Enter your Telegram chat ID or group ID. To get your chat ID, send /start to the bot.
                        </small>
                    </div>

                    <div style="margin-bottom: var(--spacing-lg);">
                        <label style="display: block; margin-bottom: var(--spacing-sm); font-weight: 600; color: var(--text-primary);">
                            Caption (Optional)
                        </label>
                        <textarea id="telegram-caption"
                                  class="form-control"
                                  rows="3"
                                  placeholder="Add a caption to your photo..."
                                  style="width: 100%; padding: var(--spacing-sm); border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--bg-primary); color: var(--text-primary); resize: vertical;">${escapeHtml(savedCaption)}</textarea>
                        <small style="color: var(--text-secondary); display: block; margin-top: var(--spacing-xs);">
                            Add an optional message to accompany the photo. Supports Markdown formatting.
                        </small>
                    </div>

                    <div style="background: var(--bg-tertiary); padding: var(--spacing-md); border-radius: var(--radius-sm); margin-bottom: var(--spacing-lg);">
                        <strong style="display: block; margin-bottom: var(--spacing-xs); color: var(--text-primary);">💡 How to find your Chat ID:</strong>
                        <ol style="margin: 0; padding-left: var(--spacing-lg); color: var(--text-secondary); font-size: 14px;">
                            <li>Start your bot (make sure it's running)</li>
                            <li>Send <code>/start</code> to your bot in Telegram</li>
                            <li>The bot will reply with your Chat ID</li>
                            <li>For groups: Add the bot to your group and send <code>/start</code> there</li>
                        </ol>
                    </div>

                    <div class="form-actions">
                        <button class="btn btn-secondary" onclick="this.closest('.modal').remove()">Cancel</button>
                        <button class="btn btn-primary" onclick="sendPhotoToTelegram(${imageId})">
                            ${mediaIcon} Send ${mediaLabel.charAt(0).toUpperCase() + mediaLabel.slice(1)}
                        </button>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(modal);
    } catch (error) {
        console.error('Error opening Telegram modal:', error);
        showToast('Failed to open Telegram modal', 'error');
    }
}

async function sendPhotoToTelegram(imageId) {
    const chatId = document.getElementById('telegram-chat-id').value.trim();
    const caption = document.getElementById('telegram-caption').value.trim();

    if (!chatId) {
        showToast('Please enter a Chat ID', 'error');
        return;
    }

    // Save chat_id and caption for next time
    localStorage.setItem('telegram_chat_id', chatId);
    localStorage.setItem('telegram_default_caption', caption);

    try {
        showToast('Sending to Telegram...', 'info');

        const response = await fetch('/api/telegram/send-photo', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                image_id: imageId,
                chat_id: chatId,
                caption: caption || null
            })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            const mediaType = data.media_type === 'video' ? 'Video' : 'Photo';
            showToast(`✅ ${mediaType} sent to Telegram successfully!`, 'success');
            // Close only the Telegram modal
            const telegramModal = document.getElementById('telegram-send-modal');
            if (telegramModal) {
                telegramModal.remove();
            }
        } else {
            showToast(`Failed to send: ${data.error || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        console.error('Error sending to Telegram:', error);
        showToast('Failed to send to Telegram', 'error');
    }
}

async function openImageFolder(imageId) {
    try {
        const response = await fetch(`/api/images/${imageId}/open-folder`, {
            method: 'POST'
        });

        const data = await response.json();

        if (response.ok && data.success) {
            showToast('Folder opened', 'success');
        } else {
            showToast(data.error || 'Failed to open folder', 'error');
        }
    } catch (error) {
        console.error('Error opening folder:', error);
        showToast('Failed to open folder', 'error');
    }
}

// ============ External Apps Management ============

async function loadExternalAppsForSettings() {
    try {
        const response = await fetch('/api/external-apps');
        const data = await response.json();

        // Update state for Open With menus
        state.externalApps = data.apps;

        // Update Settings UI
        renderAppsList('image', data.apps.image || []);
        renderAppsList('video', data.apps.video || []);
    } catch (error) {
        console.error('Error loading external apps:', error);
    }
}

function renderAppsList(mediaType, apps) {
    const container = document.getElementById(`${mediaType}AppsList`);
    if (!container) return;

    if (apps.length === 0) {
        container.innerHTML = '<p style="color: var(--text-secondary); font-style: italic;">No applications configured</p>';
        return;
    }

    container.innerHTML = apps.map(app => `
        <div style="border: 1px solid var(--border); border-radius: var(--radius-sm); padding: var(--spacing-sm); margin-bottom: var(--spacing-sm); display: flex; align-items: center; gap: var(--spacing-sm); background: var(--bg-tertiary);">
            <div style="flex: 1;">
                <div style="display: flex; align-items: center; gap: var(--spacing-xs); margin-bottom: 2px;">
                    <strong style="color: var(--text-primary);">${escapeHtml(app.name)}</strong>
                    ${app.enabled ? '<span style="color: var(--success); font-size: 12px;">✓ Enabled</span>' : '<span style="color: var(--text-muted); font-size: 12px;">✗ Disabled</span>'}
                </div>
                <div style="font-size: 12px; color: var(--text-secondary);">
                    ${app.path ? `Path: ${escapeHtml(app.path)}` : `Command: ${escapeHtml(app.command)}`}
                </div>
            </div>
            <div style="display: flex; gap: var(--spacing-xs);">
                <button class="btn btn-sm btn-secondary" onclick="editApp('${mediaType}', '${escapeHtml(app.id)}')" title="Edit">
                    ✏️
                </button>
                ${app.id !== 'system' ? `
                    <button class="btn btn-sm btn-danger" onclick="deleteApp('${mediaType}', '${escapeHtml(app.id)}')" title="Delete">
                        🗑️
                    </button>
                ` : ''}
            </div>
        </div>
    `).join('');
}

function showAddAppModal(mediaType) {
    const modal = document.getElementById('addAppModal');
    const title = document.getElementById('addAppModalTitle');
    const form = document.getElementById('addAppForm');

    // Reset form
    form.reset();
    document.getElementById('appMediaType').value = mediaType;
    document.getElementById('appEditId').value = '';
    document.getElementById('appEnabled').checked = true;

    title.textContent = `Add ${mediaType === 'image' ? 'Image Editor' : 'Video Player'}`;
    modal.style.display = 'block';
}

async function editApp(mediaType, appId) {
    try {
        const response = await fetch('/api/external-apps');
        const data = await response.json();

        const app = data.apps[mediaType]?.find(a => a.id === appId);
        if (!app) {
            showToast('Application not found', 'error');
            return;
        }

        const modal = document.getElementById('addAppModal');
        const title = document.getElementById('addAppModalTitle');

        document.getElementById('appMediaType').value = mediaType;
        document.getElementById('appEditId').value = appId;
        document.getElementById('appName').value = app.name;
        document.getElementById('appId').value = app.id;
        document.getElementById('appId').readOnly = true; // Can't change ID when editing
        document.getElementById('appPath').value = app.path || '';
        document.getElementById('appCommand').value = app.command;
        document.getElementById('appEnabled').checked = app.enabled !== false;

        title.textContent = `Edit ${app.name}`;
        modal.style.display = 'block';
    } catch (error) {
        console.error('Error loading app for editing:', error);
        showToast('Failed to load application', 'error');
    }
}

async function deleteApp(mediaType, appId) {
    if (!confirm(`Are you sure you want to delete this application?`)) {
        return;
    }

    try {
        const response = await fetch(`/api/settings/external-apps/${mediaType}/${appId}`, {
            method: 'DELETE'
        });

        const data = await response.json();

        if (response.ok && data.success) {
            showToast('Application deleted', 'success');
            loadExternalAppsForSettings();
        } else {
            showToast(data.error || 'Failed to delete application', 'error');
        }
    } catch (error) {
        console.error('Error deleting app:', error);
        showToast('Failed to delete application', 'error');
    }
}

// Add App Form Handler
document.addEventListener('DOMContentLoaded', () => {
    const addAppForm = document.getElementById('addAppForm');
    if (addAppForm) {
        addAppForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            const mediaType = document.getElementById('appMediaType').value;
            const editId = document.getElementById('appEditId').value;
            const appData = {
                id: document.getElementById('appId').value,
                name: document.getElementById('appName').value,
                path: document.getElementById('appPath').value,
                command: document.getElementById('appCommand').value,
                enabled: document.getElementById('appEnabled').checked
            };

            try {
                let response;

                if (editId) {
                    // Update existing app
                    response = await fetch(`/api/settings/external-apps/${mediaType}/${editId}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(appData)
                    });
                } else {
                    // Add new app
                    response = await fetch('/api/settings/external-apps', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            media_type: mediaType,
                            app: appData
                        })
                    });
                }

                const data = await response.json();

                if (response.ok && data.success) {
                    showToast(editId ? 'Application updated' : 'Application added', 'success');
                    document.getElementById('addAppModal').style.display = 'none';
                    document.getElementById('appId').readOnly = false; // Reset readonly
                    loadExternalAppsForSettings();
                } else {
                    showToast(data.error || 'Failed to save application', 'error');
                }
            } catch (error) {
                console.error('Error saving app:', error);
                showToast('Failed to save application', 'error');
            }
        });
    }
});

// ============================================================================
// EXIF Sync Function
// ============================================================================

async function syncToExif(imageId) {
    // Sync image description and tags to EXIF metadata
    // Writes the data directly into the image file
    try {
        showToast('Saving to EXIF...', 'info');

        const response = await fetch(`/api/images/${imageId}/exif/sync`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (data.success) {
            showToast(`✓ ${data.message}`, 'success');
        } else {
            showToast(`✗ ${data.message || 'Failed to save to EXIF'}`, 'error');
        }
    } catch (error) {
        console.error('Error syncing to EXIF:', error);
        showToast('Failed to save to EXIF', 'error');
    }
}

// ============================================================================
// YouTube Download Functions
// ============================================================================

let youtubeVideoData = null;

function initYouTubeModal() {
    const modal = document.getElementById('youtubeModal');
    const overlay = document.getElementById('youtubeOverlay');
    const closeBtn = document.getElementById('youtubeClose');
    const cancelBtn = document.getElementById('youtubeCancelBtn');
    const infoBtn = document.getElementById('youtubeInfoBtn');
    const downloadBtn = document.getElementById('youtubeDownloadBtn');
    const urlInput = document.getElementById('youtubeUrl');
    const menuBtn = document.getElementById('youtubeDownloadBtnMenu');
    const headerBtn = document.getElementById('youtubeHeaderBtn');

    // Open modal from header button (direct access)
    if (headerBtn) {
        headerBtn.addEventListener('click', () => {
            openYouTubeModal();
        });
    }

    // Open modal from menu
    if (menuBtn) {
        menuBtn.addEventListener('click', () => {
            openYouTubeModal();
            document.getElementById('moreMenu').classList.remove('show');
        });
    }

    // Close handlers
    if (closeBtn) closeBtn.addEventListener('click', closeYouTubeModal);
    if (cancelBtn) cancelBtn.addEventListener('click', closeYouTubeModal);
    if (overlay) overlay.addEventListener('click', closeYouTubeModal);

    // Info button
    if (infoBtn) {
        infoBtn.addEventListener('click', () => {
            const url = urlInput.value.trim();
            if (url) {
                fetchYouTubeInfo(url);
            } else {
                showToast('Please enter a YouTube URL', 'warning');
            }
        });
    }

    // Download button
    if (downloadBtn) {
        downloadBtn.addEventListener('click', () => {
            if (youtubeVideoData) {
                downloadYouTubeVideo();
            }
        });
    }

    // Enter key in URL input
    if (urlInput) {
        urlInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                const url = urlInput.value.trim();
                if (url) {
                    fetchYouTubeInfo(url);
                }
            }
        });
    }
}

function openYouTubeModal() {
    const modal = document.getElementById('youtubeModal');
    modal.style.display = 'block';
    resetYouTubeModal();
    document.getElementById('youtubeUrl').focus();
}

function closeYouTubeModal() {
    document.getElementById('youtubeModal').style.display = 'none';
    resetYouTubeModal();
}

function resetYouTubeModal() {
    youtubeVideoData = null;
    document.getElementById('youtubeUrl').value = '';
    document.getElementById('youtubeVideoInfo').style.display = 'none';
    document.getElementById('youtubeOptions').style.display = 'none';
    document.getElementById('youtubeProgress').style.display = 'none';
    document.getElementById('youtubeResult').style.display = 'none';
    document.getElementById('youtubeExistsWarning').style.display = 'none';
    document.getElementById('youtubeDownloadBtn').disabled = true;
    document.getElementById('youtubeSubtitles').checked = true;
    document.getElementById('youtubeOriginalSubtitles').checked = true;
    document.getElementById('youtubeKeyframes').checked = true;
    document.getElementById('youtubeQuality').value = '1080';
}

async function fetchYouTubeInfo(url) {
    const infoBtn = document.getElementById('youtubeInfoBtn');
    const originalText = infoBtn.textContent;
    infoBtn.textContent = '...';
    infoBtn.disabled = true;

    try {
        const response = await fetch(`/api/videos/info?url=${encodeURIComponent(url)}`);
        const data = await response.json();

        if (!response.ok) {
            showToast(data.error || 'Failed to get video info', 'error');
            return;
        }

        youtubeVideoData = data;
        displayYouTubeInfo(data);

    } catch (error) {
        console.error('Error fetching YouTube info:', error);
        showToast('Failed to get video information', 'error');
    } finally {
        infoBtn.textContent = originalText;
        infoBtn.disabled = false;
    }
}

function displayYouTubeInfo(data) {
    const infoSection = document.getElementById('youtubeVideoInfo');
    const thumbnail = document.getElementById('youtubeThumbnail');
    const title = document.getElementById('youtubeTitle');
    const channel = document.getElementById('youtubeChannel');
    const duration = document.getElementById('youtubeDuration');
    const existsWarning = document.getElementById('youtubeExistsWarning');
    const options = document.getElementById('youtubeOptions');
    const downloadBtn = document.getElementById('youtubeDownloadBtn');

    // Set thumbnail
    thumbnail.src = data.thumbnail || '';
    thumbnail.onerror = () => { thumbnail.src = ''; };

    // Set text info
    title.textContent = data.title || 'Unknown Title';
    channel.textContent = data.channel || data.uploader || '';

    // Format duration
    if (data.duration) {
        const mins = Math.floor(data.duration / 60);
        const secs = data.duration % 60;
        duration.textContent = `${mins}:${secs.toString().padStart(2, '0')}`;
    } else {
        duration.textContent = '';
    }

    // Show exists warning
    if (data.exists_in_gallery) {
        existsWarning.style.display = 'block';
        downloadBtn.textContent = 'Already Exists';
        downloadBtn.disabled = true;
    } else {
        existsWarning.style.display = 'none';
        downloadBtn.textContent = 'Download';
        downloadBtn.disabled = false;
    }

    // Show sections
    infoSection.style.display = 'block';
    options.style.display = 'block';
}

async function downloadYouTubeVideo() {
    if (!youtubeVideoData) return;

    const downloadBtn = document.getElementById('youtubeDownloadBtn');
    const progress = document.getElementById('youtubeProgress');
    const progressText = document.getElementById('youtubeProgressText');
    const result = document.getElementById('youtubeResult');
    const resultText = document.getElementById('youtubeResultText');
    const urlInput = document.getElementById('youtubeUrl');

    const autoSubtitles = document.getElementById('youtubeSubtitles').checked;
    const originalSubtitles = document.getElementById('youtubeOriginalSubtitles').checked;
    const keyframes = document.getElementById('youtubeKeyframes').checked;
    const quality = document.getElementById('youtubeQuality').value;

    downloadBtn.disabled = true;
    downloadBtn.textContent = 'Downloading...';
    progress.style.display = 'block';
    progressText.textContent = 'Starting download...';
    result.style.display = 'none';

    try {
        const response = await fetch('/api/videos/download', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                url: urlInput.value.trim(),
                subtitles: autoSubtitles,
                original_subtitles: originalSubtitles,
                keyframes: keyframes,
                quality: quality
            })
        });

        const data = await response.json();

        progress.style.display = 'none';

        if (!response.ok) {
            showToast(data.error || 'Download failed', 'error');
            downloadBtn.textContent = 'Download';
            downloadBtn.disabled = false;
            return;
        }

        // Show success
        result.style.display = 'block';

        if (data.status === 'exists') {
            result.style.background = 'var(--warning-bg, rgba(255, 193, 7, 0.1))';
            result.style.color = 'var(--warning-text, #ffc107)';
            resultText.textContent = 'Video already exists in gallery';
        } else {
            result.style.background = 'var(--success-bg, rgba(40, 167, 69, 0.1))';
            result.style.color = 'var(--success-text, #28a745)';

            let message = `Downloaded: ${data.title || 'Video'}`;
            if (data.keyframe_count > 0) {
                message += ` (${data.keyframe_count} keyframes)`;
            }
            if (data.subtitle_languages && data.subtitle_languages.length > 0) {
                message += ` [${data.subtitle_languages.join(', ')}]`;
            }
            resultText.textContent = message;
        }

        downloadBtn.textContent = 'Done';
        showToast('Video downloaded successfully!', 'success');

        // Close modal after short delay
        setTimeout(() => {
            closeYouTubeModal();
        }, 2000);

        // Reload gallery and refresh view immediately
        setTimeout(async () => {
            await loadImages();
            await updateStats();
            renderImages();
            
            // Show the new video in the gallery
            showToast('Video added to gallery!', 'success', 3000);
        }, 1500);

    } catch (error) {
        console.error('Error downloading video:', error);
        showToast('Download failed', 'error');
        progress.style.display = 'none';
        downloadBtn.textContent = 'Download';
        downloadBtn.disabled = false;
    }
}

// Initialize YouTube modal on page load
document.addEventListener('DOMContentLoaded', initYouTubeModal);

// ============================================================================
// Karaoke Subtitle Panel
// ============================================================================

let subtitleData = {
    subtitles: [],
    languages: [],
    currentLang: null,
    videoElement: null,
    syncInterval: null,
    teleprompterMode: false
};

async function loadSubtitlesForVideo(imageId) {
    try {
        const response = await fetch(`/api/images/${imageId}/subtitles`);
        if (!response.ok) {
            return null;
        }
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Error loading subtitles:', error);
        return null;
    }
}

function createSubtitlePanel(subtitles, languages) {
    if (!subtitles || subtitles.length === 0) {
        return `
            <div class="subtitle-panel">
                <div class="no-subtitles">
                    <p>No subtitles available for this video</p>
                </div>
            </div>
        `;
    }

    const langOptions = languages.map(lang =>
        `<option value="${lang}">${lang.toUpperCase()}</option>`
    ).join('');

    const subtitleLines = subtitles.map((sub, idx) => {
        const startTime = formatSubtitleTime(sub.start_time_ms);
        return `
            <div class="subtitle-line" data-index="${idx}" data-start="${sub.start_time_ms}" data-end="${sub.end_time_ms}">
                <span class="timestamp">${startTime}</span>
                <span class="text">${escapeHtml(sub.text)}</span>
            </div>
        `;
    }).join('');

    return `
        <div class="subtitle-panel" id="subtitlePanel">
            <div class="subtitle-resize-handle" id="subtitleResizeHandle" title="Drag to resize">
                <span class="resize-grip"></span>
            </div>
            <div class="subtitle-panel-header">
                <h4>🎤 Subtitles</h4>
                <select class="subtitle-lang-select" id="subtitleLangSelect" onchange="changeSubtitleLanguage(this.value)">
                    ${langOptions}
                </select>
            </div>
            <div class="subtitle-content" id="subtitleContent">
                ${subtitleLines}
            </div>
            <div class="subtitle-panel-controls">
                <button onclick="toggleTeleprompterMode()" id="teleprompterBtn">📺 Teleprompter</button>
                <button onclick="toggleAutoScroll()" id="autoScrollBtn" class="active">🔄 Auto-scroll</button>
                <button onclick="jumpToCurrentSubtitle()">⏱️ Jump to current</button>
                <button onclick="addBookmarkAtCurrentTime()" title="Add bookmark at current time">🔖 Bookmark</button>
                <button onclick="captureCurrentFrame()" title="Capture current frame as image">📸 Screenshot</button>
                <button onclick="toggleABLoop()" id="abLoopBtn" title="A-B Loop: repeat section">🔁 A-B Loop</button>
                <button onclick="addNoteAtCurrentTime()" title="Add timestamped note">📝 Note</button>
                <button onclick="showExportMenu(event)" title="Export options">📤 Export</button>
                <button onclick="generateVideoSummary()" title="AI Summary">🤖 Summary</button>
            </div>
        </div>
    `;
}

// ============ VIDEO BOOKMARKS ============

let currentVideoBookmarks = [];

async function loadVideoBookmarks(imageId) {
    try {
        const response = await fetch(`/api/images/${imageId}/bookmarks`);
        if (response.ok) {
            const data = await response.json();
            currentVideoBookmarks = data.bookmarks || [];
            renderBookmarkMarkers();
            return currentVideoBookmarks;
        }
    } catch (error) {
        console.error('Error loading bookmarks:', error);
    }
    return [];
}

function renderBookmarkMarkers() {
    const video = document.getElementById('modalVideoPlayer');
    if (!video || !video.duration) return;

    // Remove existing markers
    document.querySelectorAll('.bookmark-marker').forEach(m => m.remove());

    const container = video.parentElement;
    if (!container) return;

    // Get video's position within container
    const videoRect = video.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();
    const videoLeft = videoRect.left - containerRect.left;
    const videoWidth = videoRect.width;
    const videoBottom = containerRect.height - (videoRect.bottom - containerRect.top);

    currentVideoBookmarks.forEach(bookmark => {
        const timePercent = (bookmark.timestamp_ms / 1000) / video.duration;
        const leftPx = videoLeft + (timePercent * videoWidth);

        const marker = document.createElement('div');
        marker.className = 'bookmark-marker';
        marker.style.left = `${leftPx}px`;
        marker.style.bottom = `${videoBottom + 45}px`;  // Position above video controls
        marker.style.backgroundColor = bookmark.color || '#ff4444';
        marker.title = `${bookmark.title} (${formatTimeReadable(bookmark.timestamp_ms)})`;
        marker.onclick = () => {
            video.currentTime = bookmark.timestamp_ms / 1000;
        };
        container.appendChild(marker);
    });
}

// Re-render markers on window resize (debounced)
let bookmarkResizeTimeout;
window.addEventListener('resize', () => {
    clearTimeout(bookmarkResizeTimeout);
    bookmarkResizeTimeout = setTimeout(renderBookmarkMarkers, 100);
});

async function addBookmarkAtCurrentTime() {
    const video = document.getElementById('modalVideoPlayer');
    if (!video) {
        showToast('No video playing', 'error');
        return;
    }

    const currentTimeMs = Math.floor(video.currentTime * 1000);
    const title = prompt('Bookmark title:', `Bookmark at ${formatTimeReadable(currentTimeMs)}`);

    if (!title) return;

    const imageId = state.currentImage?.id;
    if (!imageId) return;

    try {
        const response = await fetch(`/api/images/${imageId}/bookmarks`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                timestamp_ms: currentTimeMs,
                title: title,
                color: '#ff4444'
            })
        });

        if (response.ok) {
            showToast('Bookmark added!', 'success');
            await loadVideoBookmarks(imageId);
        } else {
            showToast('Failed to add bookmark', 'error');
        }
    } catch (error) {
        console.error('Error adding bookmark:', error);
        showToast('Error adding bookmark', 'error');
    }
}

function formatTimeReadable(ms) {
    const totalSeconds = Math.floor(ms / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

// ============ EXPORT MENU ============

function showExportMenu(event) {
    event.stopPropagation();

    // Remove existing menu
    document.querySelectorAll('.export-dropdown').forEach(m => m.remove());

    const menu = document.createElement('div');
    menu.className = 'export-dropdown';
    menu.innerHTML = `
        <div class="export-menu-title">Export Options</div>
        <div class="export-menu-section">Transcript</div>
        <div class="export-item" onclick="exportTranscript('txt')">📄 Plain Text (.txt)</div>
        <div class="export-item" onclick="exportTranscript('txt_timestamps')">⏱️ Text with Timestamps</div>
        <div class="export-item" onclick="exportTranscript('srt')">🎬 SRT Subtitles (.srt)</div>
        <div class="export-item" onclick="exportTranscript('vtt')">🌐 WebVTT (.vtt)</div>
        <div class="export-menu-section">Video Clip</div>
        <div class="export-item" onclick="showClipExportDialog()">✂️ Export Clip...</div>
    `;

    document.body.appendChild(menu);

    // Position near button
    const rect = event.target.getBoundingClientRect();
    menu.style.position = 'fixed';
    menu.style.top = `${rect.top - menu.offsetHeight - 5}px`;
    menu.style.left = `${rect.left}px`;
    menu.style.zIndex = '10000';

    // Close on click outside
    setTimeout(() => {
        document.addEventListener('click', function closeMenu(e) {
            if (!menu.contains(e.target)) {
                menu.remove();
                document.removeEventListener('click', closeMenu);
            }
        });
    }, 100);
}

async function exportTranscript(format) {
    const imageId = state.currentImage?.id;
    if (!imageId) return;

    document.querySelectorAll('.export-dropdown').forEach(m => m.remove());

    const url = `/api/images/${imageId}/transcript?format=${format}`;
    window.open(url, '_blank');
    showToast(`Exporting transcript as ${format.toUpperCase()}...`, 'info');
}

function showClipExportDialog() {
    document.querySelectorAll('.export-dropdown').forEach(m => m.remove());

    const video = document.getElementById('modalVideoPlayer');
    if (!video) {
        showToast('No video loaded', 'error');
        return;
    }

    const currentTimeMs = Math.floor(video.currentTime * 1000);
    const durationMs = Math.floor(video.duration * 1000);

    const dialog = document.createElement('div');
    dialog.className = 'modal';
    dialog.style.display = 'flex';
    dialog.innerHTML = `
        <div class="modal-overlay" onclick="this.parentElement.remove()"></div>
        <div class="modal-content modal-small">
            <button class="modal-close" onclick="this.closest('.modal').remove()">&times;</button>
            <div class="modal-body">
                <h2>✂️ Export Video Clip</h2>
                <div class="form-group">
                    <label>Start Time (seconds)</label>
                    <input type="number" id="clipStartTime" value="${Math.floor(currentTimeMs/1000)}" min="0" max="${Math.floor(durationMs/1000)}">
                </div>
                <div class="form-group">
                    <label>End Time (seconds)</label>
                    <input type="number" id="clipEndTime" value="${Math.min(Math.floor(currentTimeMs/1000) + 30, Math.floor(durationMs/1000))}" min="0" max="${Math.floor(durationMs/1000)}">
                </div>
                <div class="form-group">
                    <button class="btn btn-primary" onclick="exportVideoClip()">Export Clip</button>
                    <button class="btn btn-secondary" onclick="this.closest('.modal').remove()">Cancel</button>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(dialog);
}

async function exportVideoClip() {
    const startSec = parseFloat(document.getElementById('clipStartTime').value);
    const endSec = parseFloat(document.getElementById('clipEndTime').value);

    if (isNaN(startSec) || isNaN(endSec) || endSec <= startSec) {
        showToast('Invalid time range', 'error');
        return;
    }

    const imageId = state.currentImage?.id;
    if (!imageId) return;

    document.querySelectorAll('.modal').forEach(m => {
        if (m.querySelector('#clipStartTime')) m.remove();
    });

    showToast('Creating clip... This may take a moment.', 'info');

    try {
        const response = await fetch(`/api/images/${imageId}/clip`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                start_ms: Math.floor(startSec * 1000),
                end_ms: Math.floor(endSec * 1000)
            })
        });

        if (response.ok) {
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `clip_${imageId}_${startSec}-${endSec}.mp4`;
            a.click();
            URL.revokeObjectURL(url);
            showToast('Clip exported successfully!', 'success');
        } else {
            const error = await response.json();
            showToast(error.error || 'Failed to create clip', 'error');
        }
    } catch (error) {
        console.error('Error exporting clip:', error);
        showToast('Error creating clip', 'error');
    }
}

// ============ AI VIDEO SUMMARY ============

async function generateVideoSummary() {
    const imageId = state.currentImage?.id;
    if (!imageId) return;

    showToast('Generating AI summary...', 'info');

    try {
        const response = await fetch(`/api/images/${imageId}/summary`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        const data = await response.json();

        if (response.ok && data.success) {
            showSummaryModal(data.summary, data.video_title);
        } else {
            showToast(data.error || 'Failed to generate summary', 'error');
        }
    } catch (error) {
        console.error('Error generating summary:', error);
        showToast('Error generating summary', 'error');
    }
}

function showSummaryModal(summary, title) {
    const dialog = document.createElement('div');
    dialog.className = 'modal';
    dialog.style.display = 'flex';
    dialog.innerHTML = `
        <div class="modal-overlay" onclick="this.parentElement.remove()"></div>
        <div class="modal-content">
            <button class="modal-close" onclick="this.closest('.modal').remove()">&times;</button>
            <div class="modal-body">
                <h2>🤖 AI Summary: ${escapeHtml(title || 'Video')}</h2>
                <div class="summary-content" style="white-space: pre-wrap; line-height: 1.6;">
                    ${formatMarkdown(summary)}
                </div>
                <div class="form-group" style="margin-top: 20px;">
                    <button class="btn btn-secondary" onclick="copySummaryToClipboard()">📋 Copy to Clipboard</button>
                    <button class="btn btn-secondary" onclick="this.closest('.modal').remove()">Close</button>
                </div>
            </div>
        </div>
    `;
    dialog.querySelector('.summary-content').dataset.rawSummary = summary;
    document.body.appendChild(dialog);
}

function formatMarkdown(text) {
    // Simple markdown formatting
    return text
        .replace(/## (.*)/g, '<h3>$1</h3>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/^- (.*)/gm, '<li>$1</li>')
        .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
        .replace(/\n/g, '<br>');
}

function copySummaryToClipboard() {
    const content = document.querySelector('.summary-content');
    if (content && content.dataset.rawSummary) {
        navigator.clipboard.writeText(content.dataset.rawSummary);
        showToast('Summary copied to clipboard!', 'success');
    }
}

// ============ FRAME CAPTURE ============

async function captureCurrentFrame() {
    const video = document.getElementById('modalVideoPlayer');
    if (!video) {
        showToast('No video playing', 'error');
        return;
    }

    const imageId = state.currentImage?.id;
    if (!imageId) return;

    const currentTimeMs = Math.floor(video.currentTime * 1000);

    showToast('Capturing frame...', 'info');

    try {
        const response = await fetch(`/api/images/${imageId}/capture-frame`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ timestamp_ms: currentTimeMs })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            showToast(`Frame captured! Added to gallery (ID: ${data.image_id})`, 'success');
        } else {
            showToast(data.error || 'Failed to capture frame', 'error');
        }
    } catch (error) {
        console.error('Error capturing frame:', error);
        showToast('Error capturing frame', 'error');
    }
}

// ============ A-B LOOP ============

let abLoopState = {
    active: false,
    pointA: null,
    pointB: null
};

function toggleABLoop() {
    const video = document.getElementById('modalVideoPlayer');
    const btn = document.getElementById('abLoopBtn');
    if (!video) return;

    if (!abLoopState.active) {
        // Start: Set point A
        abLoopState.pointA = video.currentTime;
        abLoopState.pointB = null;
        abLoopState.active = true;
        btn.textContent = '🔁 Set B';
        btn.classList.add('active');
        showToast(`Point A set at ${formatTimeReadable(abLoopState.pointA * 1000)}. Now set point B.`, 'info');
    } else if (abLoopState.pointB === null) {
        // Set point B and start looping
        if (video.currentTime <= abLoopState.pointA) {
            showToast('Point B must be after point A', 'error');
            return;
        }
        abLoopState.pointB = video.currentTime;
        btn.textContent = '🔁 Stop Loop';
        video.currentTime = abLoopState.pointA;
        video.play();
        showToast(`Looping ${formatTimeReadable(abLoopState.pointA * 1000)} → ${formatTimeReadable(abLoopState.pointB * 1000)}`, 'success');

        // Add timeupdate listener for looping
        video.addEventListener('timeupdate', handleABLoop);
    } else {
        // Stop loop
        video.removeEventListener('timeupdate', handleABLoop);
        abLoopState = { active: false, pointA: null, pointB: null };
        btn.textContent = '🔁 A-B Loop';
        btn.classList.remove('active');
        showToast('A-B Loop stopped', 'info');
    }
}

function handleABLoop(e) {
    const video = e.target;
    if (abLoopState.active && abLoopState.pointB !== null) {
        if (video.currentTime >= abLoopState.pointB) {
            video.currentTime = abLoopState.pointA;
        }
    }
}

// ============ TIMESTAMPED NOTES ============

let currentVideoNotes = [];

async function loadVideoNotes(imageId) {
    try {
        const response = await fetch(`/api/images/${imageId}/notes`);
        if (response.ok) {
            const data = await response.json();
            currentVideoNotes = data.notes || [];
            return currentVideoNotes;
        }
    } catch (error) {
        console.error('Error loading notes:', error);
    }
    return [];
}

async function addNoteAtCurrentTime() {
    const video = document.getElementById('modalVideoPlayer');
    if (!video) {
        showToast('No video playing', 'error');
        return;
    }

    const currentTimeMs = Math.floor(video.currentTime * 1000);
    const timeStr = formatTimeReadable(currentTimeMs);

    // Show note input dialog
    const dialog = document.createElement('div');
    dialog.className = 'modal';
    dialog.style.display = 'flex';
    dialog.innerHTML = `
        <div class="modal-overlay" onclick="this.parentElement.remove()"></div>
        <div class="modal-content" style="max-width: 500px;">
            <button class="modal-close" onclick="this.closest('.modal').remove()">&times;</button>
            <div class="modal-body">
                <h2>📝 Add Note at ${timeStr}</h2>
                <div class="form-group">
                    <textarea id="noteContent" placeholder="Enter your note..." rows="4" style="width: 100%; padding: 10px; border-radius: 8px; border: 1px solid var(--border-color); background: var(--bg-secondary); color: var(--text-primary);"></textarea>
                </div>
                <div class="form-group" style="display: flex; gap: 10px; justify-content: flex-end;">
                    <button class="btn btn-secondary" onclick="this.closest('.modal').remove()">Cancel</button>
                    <button class="btn btn-primary" onclick="saveVideoNote(${currentTimeMs})">Save Note</button>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(dialog);
    document.getElementById('noteContent').focus();
}

async function saveVideoNote(timestampMs) {
    const content = document.getElementById('noteContent')?.value?.trim();
    if (!content) {
        showToast('Note cannot be empty', 'error');
        return;
    }

    const imageId = state.currentImage?.id;
    if (!imageId) return;

    try {
        const response = await fetch(`/api/images/${imageId}/notes`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                timestamp_ms: timestampMs,
                content: content
            })
        });

        if (response.ok) {
            showToast('Note saved!', 'success');
            document.querySelector('.modal')?.remove();
            await loadVideoNotes(imageId);
        } else {
            const error = await response.json();
            showToast(error.error || 'Failed to save note', 'error');
        }
    } catch (error) {
        console.error('Error saving note:', error);
        showToast('Error saving note', 'error');
    }
}

function showVideoNotes() {
    if (currentVideoNotes.length === 0) {
        showToast('No notes for this video', 'info');
        return;
    }

    const video = document.getElementById('modalVideoPlayer');

    const dialog = document.createElement('div');
    dialog.className = 'modal';
    dialog.style.display = 'flex';
    dialog.innerHTML = `
        <div class="modal-overlay" onclick="this.parentElement.remove()"></div>
        <div class="modal-content" style="max-width: 600px;">
            <button class="modal-close" onclick="this.closest('.modal').remove()">&times;</button>
            <div class="modal-body">
                <h2>📝 Video Notes (${currentVideoNotes.length})</h2>
                <div class="notes-list" style="max-height: 400px; overflow-y: auto;">
                    ${currentVideoNotes.map(note => `
                        <div class="note-item" style="padding: 12px; margin: 8px 0; background: var(--bg-secondary); border-radius: 8px; cursor: pointer;"
                             onclick="jumpToNoteTime(${note.timestamp_ms})">
                            <div style="color: var(--accent-color); font-weight: bold; margin-bottom: 4px;">
                                ⏱️ ${formatTimeReadable(note.timestamp_ms)}
                            </div>
                            <div style="white-space: pre-wrap;">${escapeHtml(note.content)}</div>
                        </div>
                    `).join('')}
                </div>
                <div class="form-group" style="margin-top: 15px; display: flex; gap: 10px; justify-content: flex-end;">
                    <button class="btn btn-secondary" onclick="exportVideoNotes()">📤 Export as Markdown</button>
                    <button class="btn btn-secondary" onclick="this.closest('.modal').remove()">Close</button>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(dialog);
}

function jumpToNoteTime(timestampMs) {
    const video = document.getElementById('modalVideoPlayer');
    if (video) {
        video.currentTime = timestampMs / 1000;
        document.querySelector('.modal')?.remove();
    }
}

async function exportVideoNotes() {
    const imageId = state.currentImage?.id;
    if (!imageId) return;

    window.open(`/api/images/${imageId}/notes/export`, '_blank');
}

// Subtitle panel resize functionality
function initSubtitleResize() {
    const handle = document.getElementById('subtitleResizeHandle');
    const panel = document.getElementById('subtitlePanel');
    const video = document.getElementById('modalVideoPlayer');
    const container = document.querySelector('.image-main-view');

    if (!handle || !panel) return;

    let isResizing = false;
    let startY = 0;
    let startPanelHeight = 0;
    let startVideoHeight = 0;
    let containerHeight = 0;

    const updateHeights = (panelHeight) => {
        // Calculate available space for video (container height minus panel height and some padding)
        const padding = 40; // spacing between elements
        const minVideoHeight = 150;
        const minPanelHeight = 100;
        const maxPanelHeight = containerHeight - minVideoHeight - padding;

        // Clamp panel height
        const clampedPanelHeight = Math.min(Math.max(panelHeight, minPanelHeight), maxPanelHeight);

        // Calculate video height
        const videoHeight = containerHeight - clampedPanelHeight - padding;

        // Apply heights
        panel.style.maxHeight = clampedPanelHeight + 'px';
        panel.style.height = clampedPanelHeight + 'px';

        if (video) {
            video.style.maxHeight = Math.max(videoHeight, minVideoHeight) + 'px';
            video.style.height = 'auto';
        }
    };

    handle.addEventListener('mousedown', (e) => {
        isResizing = true;
        startY = e.clientY;
        startPanelHeight = panel.offsetHeight;
        if (video) startVideoHeight = video.offsetHeight;
        if (container) containerHeight = container.offsetHeight;

        document.body.style.cursor = 'ns-resize';
        document.body.style.userSelect = 'none';
        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (!isResizing) return;

        const deltaY = startY - e.clientY;
        const newPanelHeight = startPanelHeight + deltaY;
        updateHeights(newPanelHeight);
    });

    document.addEventListener('mouseup', () => {
        if (isResizing) {
            isResizing = false;
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        }
    });

    // Touch support for mobile
    handle.addEventListener('touchstart', (e) => {
        isResizing = true;
        startY = e.touches[0].clientY;
        startPanelHeight = panel.offsetHeight;
        if (video) startVideoHeight = video.offsetHeight;
        if (container) containerHeight = container.offsetHeight;
        e.preventDefault();
    }, { passive: false });

    document.addEventListener('touchmove', (e) => {
        if (!isResizing) return;

        const deltaY = startY - e.touches[0].clientY;
        const newPanelHeight = startPanelHeight + deltaY;
        updateHeights(newPanelHeight);
    }, { passive: true });

    document.addEventListener('touchend', () => {
        isResizing = false;
    });
}

function formatSubtitleTime(ms) {
    const totalSeconds = Math.floor(ms / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

function initSubtitleSync(videoElement) {
    subtitleData.videoElement = videoElement;

    // Clear any existing interval
    if (subtitleData.syncInterval) {
        clearInterval(subtitleData.syncInterval);
    }

    // Sync every 100ms for smooth updates
    subtitleData.syncInterval = setInterval(() => {
        updateActiveSubtitle();
    }, 100);

    // Also update on video events
    videoElement.addEventListener('timeupdate', updateActiveSubtitle);
    videoElement.addEventListener('seeked', updateActiveSubtitle);

    // Clean up on video end or close
    videoElement.addEventListener('ended', () => {
        if (subtitleData.syncInterval) {
            clearInterval(subtitleData.syncInterval);
        }
    });
}

function updateActiveSubtitle() {
    if (!subtitleData.videoElement || !subtitleData.subtitles.length) return;

    const currentTimeMs = subtitleData.videoElement.currentTime * 1000;
    const subtitleContent = document.getElementById('subtitleContent');
    if (!subtitleContent) return;

    const lines = subtitleContent.querySelectorAll('.subtitle-line');
    let activeIdx = -1;

    lines.forEach((line, idx) => {
        const start = parseInt(line.dataset.start);
        const end = parseInt(line.dataset.end);

        line.classList.remove('active', 'upcoming');

        if (currentTimeMs >= start && currentTimeMs <= end) {
            line.classList.add('active');
            activeIdx = idx;

            // Karaoke word highlighting
            highlightWords(line, currentTimeMs, start, end);
        } else if (currentTimeMs < start) {
            line.classList.add('upcoming');
        }
    });

    // Auto-scroll to active subtitle
    if (activeIdx >= 0 && document.getElementById('autoScrollBtn')?.classList.contains('active')) {
        const activeLine = lines[activeIdx];
        if (activeLine) {
            activeLine.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }
}

function highlightWords(line, currentTimeMs, startMs, endMs) {
    const textSpan = line.querySelector('.text');
    if (!textSpan) return;

    const text = textSpan.textContent;
    const words = text.split(/\s+/);
    const duration = endMs - startMs;
    const elapsed = currentTimeMs - startMs;
    const progress = elapsed / duration;

    const wordsToHighlight = Math.floor(words.length * progress);

    const highlightedHtml = words.map((word, idx) => {
        const isSpoken = idx < wordsToHighlight;
        return `<span class="word ${isSpoken ? 'spoken' : ''}">${escapeHtml(word)}</span>`;
    }).join(' ');

    textSpan.innerHTML = highlightedHtml;
}

function toggleTeleprompterMode() {
    const panel = document.getElementById('subtitlePanel');
    const btn = document.getElementById('teleprompterBtn');

    if (panel) {
        panel.classList.toggle('teleprompter-mode');
        subtitleData.teleprompterMode = panel.classList.contains('teleprompter-mode');

        if (btn) {
            btn.classList.toggle('active', subtitleData.teleprompterMode);
        }
    }
}

function toggleAutoScroll() {
    const btn = document.getElementById('autoScrollBtn');
    if (btn) {
        btn.classList.toggle('active');
    }
}

function jumpToCurrentSubtitle() {
    const activeLine = document.querySelector('.subtitle-line.active');
    if (activeLine) {
        activeLine.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}

async function changeSubtitleLanguage(lang) {
    if (!state.currentImage) return;

    try {
        const response = await fetch(`/api/images/${state.currentImage.id}/subtitles?language=${lang}`);
        if (!response.ok) return;

        const data = await response.json();
        subtitleData.subtitles = data.subtitles;
        subtitleData.currentLang = lang;

        // Re-render subtitle content
        const subtitleContent = document.getElementById('subtitleContent');
        if (subtitleContent && data.subtitles) {
            subtitleContent.innerHTML = data.subtitles.map((sub, idx) => {
                const startTime = formatSubtitleTime(sub.start_time_ms);
                return `
                    <div class="subtitle-line" data-index="${idx}" data-start="${sub.start_time_ms}" data-end="${sub.end_time_ms}">
                        <span class="timestamp">${startTime}</span>
                        <span class="text">${escapeHtml(sub.text)}</span>
                    </div>
                `;
            }).join('');

            // Re-attach click handlers
            attachSubtitleClickHandlers();
        }
    } catch (error) {
        console.error('Error changing subtitle language:', error);
    }
}

function attachSubtitleClickHandlers() {
    const lines = document.querySelectorAll('.subtitle-line');
    lines.forEach(line => {
        line.addEventListener('click', () => {
            const startMs = parseInt(line.dataset.start);
            if (subtitleData.videoElement) {
                subtitleData.videoElement.currentTime = startMs / 1000;
            }
        });
    });
}

function cleanupSubtitleSync() {
    if (subtitleData.syncInterval) {
        clearInterval(subtitleData.syncInterval);
        subtitleData.syncInterval = null;
    }

    // Remove event listeners from video element to prevent memory leaks
    if (subtitleData.videoElement) {
        subtitleData.videoElement.removeEventListener('timeupdate', updateActiveSubtitle);
        subtitleData.videoElement.removeEventListener('seeked', updateActiveSubtitle);
    }

    subtitleData.subtitles = [];
    subtitleData.languages = [];
    subtitleData.currentLang = null;
    subtitleData.videoElement = null;
    subtitleData.teleprompterMode = false;
}

// ============================================================================
// Full-screen Drag & Drop Upload
// ============================================================================

let dragCounter = 0;

function initFullscreenDropZone() {
    const dropZone = document.getElementById('fullscreenDropZone');
    if (!dropZone) return;

    // Prevent default drag behaviors on document
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        document.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
        }, false);
    });

    // Show drop zone when dragging files over the document
    document.addEventListener('dragenter', (e) => {
        // Only show for file drags
        if (!e.dataTransfer.types.includes('Files')) return;

        dragCounter++;
        dropZone.classList.add('active');
    });

    document.addEventListener('dragleave', (e) => {
        dragCounter--;
        if (dragCounter <= 0) {
            dragCounter = 0;
            dropZone.classList.remove('active');
        }
    });

    // Handle drop on the drop zone
    dropZone.addEventListener('drop', async (e) => {
        dragCounter = 0;
        dropZone.classList.remove('active');

        const files = Array.from(e.dataTransfer.files);
        if (files.length === 0) return;

        // Filter for valid media files
        const validFiles = files.filter(file =>
            file.type.startsWith('image/') || file.type.startsWith('video/')
        );

        if (validFiles.length === 0) {
            showToast('No valid image or video files found', 'warning');
            return;
        }

        // Upload files directly
        await uploadFilesDirectly(validFiles);
    });
}

async function uploadFilesDirectly(files) {
    showToast(`Uploading ${files.length} file(s)...`, 'info');

    let successCount = 0;
    let failCount = 0;
    let duplicateCount = 0;
    const uploadedImageIds = [];

    for (const file of files) {
        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (response.ok && data.success) {
                successCount++;
                if (data.image_id) {
                    uploadedImageIds.push(data.image_id);
                }
                // Check for duplicate warning
                if (data.is_duplicate) {
                    duplicateCount++;
                    showToast(`⚠️ "${file.name}" is duplicate of "${data.duplicate_of.filename}"`, 'warning');
                }
            } else {
                failCount++;
                console.error(`Failed to upload ${file.name}:`, data.error);
            }
        } catch (error) {
            failCount++;
            console.error(`Error uploading ${file.name}:`, error);
        }
    }

    // Show result
    let message = `Uploaded ${successCount} file(s)`;
    if (duplicateCount > 0) {
        message += ` (${duplicateCount} duplicates)`;
    }
    if (failCount > 0) {
        message += `, ${failCount} failed`;
    }

    if (successCount > 0 && failCount === 0) {
        showToast(message, duplicateCount > 0 ? 'warning' : 'success');
    } else if (successCount > 0 && failCount > 0) {
        showToast(message, 'warning');
    } else {
        showToast('Upload failed', 'error');
    }

    // Reload gallery
    if (successCount > 0) {
        await loadImages();

        // Auto-analyze uploaded images with AI
        if (uploadedImageIds.length > 0) {
            showToast(`🤖 Auto-analyzing ${uploadedImageIds.length} uploaded file(s)...`, 'info');

            for (const imageId of uploadedImageIds) {
                try {
                    await analyzeImage(imageId, 'classic', null);
                } catch (error) {
                    console.error(`Auto-analysis failed for image ${imageId}:`, error);
                }
            }
        }
    }
}

// ============================================================================
// Duplicate Detection Functions
// ============================================================================

async function findDuplicates() {
    showToast('🔍 Searching for duplicates...', 'info');

    try {
        const response = await fetch('/api/duplicates');
        const data = await response.json();

        if (data.success) {
            if (data.duplicate_groups === 0) {
                showToast('✅ No duplicates found!', 'success');
            } else {
                showToast(`Found ${data.duplicate_groups} duplicate group(s)`, 'warning');
                showDuplicatesModal(data.duplicates);
            }
        } else {
            showToast('Failed to find duplicates', 'error');
        }
    } catch (error) {
        console.error('Error finding duplicates:', error);
        showToast('Error finding duplicates', 'error');
    }
}

async function computeMissingHashes() {
    showToast('🔄 Computing hashes for images...', 'info');

    try {
        const response = await fetch('/api/duplicates/compute-hashes?limit=500', {
            method: 'POST'
        });
        const data = await response.json();

        if (data.success) {
            let message = `Computed ${data.computed} hashes`;
            if (data.failed > 0) {
                message += `, ${data.failed} failed`;
            }
            if (data.remaining > 0) {
                message += `. ${data.remaining} remaining.`;
            }
            showToast(message, data.remaining > 0 ? 'warning' : 'success');
        } else {
            showToast('Failed to compute hashes', 'error');
        }
    } catch (error) {
        console.error('Error computing hashes:', error);
        showToast('Error computing hashes', 'error');
    }
}

function showDuplicatesModal(duplicates) {
    // Create modal HTML
    const modalHtml = `
        <div class="modal" id="duplicatesModal" style="display: block;">
            <div class="modal-overlay" onclick="closeDuplicatesModal()"></div>
            <div class="modal-content" style="max-width: 900px;">
                <button class="modal-close" onclick="closeDuplicatesModal()">&times;</button>
                <div class="modal-body">
                    <h2>🔍 Duplicate Images Found</h2>
                    <p style="color: var(--text-secondary); margin-bottom: var(--spacing-lg);">
                        Found ${duplicates.length} groups of duplicate images.
                        The first image in each group is the original (oldest).
                    </p>
                    <div class="duplicates-list">
                        ${duplicates.map((group, idx) => `
                            <div class="duplicate-group">
                                <h4>Group ${idx + 1} (${group.count} images)</h4>
                                <div class="duplicate-images">
                                    ${group.images.map((img, imgIdx) => `
                                        <div class="duplicate-image ${imgIdx === 0 ? 'original' : 'duplicate'}">
                                            <img src="/api/images/${img.id}/thumbnail" alt="${img.filename}">
                                            <div class="duplicate-info">
                                                <span class="duplicate-filename">${img.filename}</span>
                                                <span class="duplicate-badge">${imgIdx === 0 ? 'Original' : 'Duplicate'}</span>
                                                ${imgIdx > 0 ? `<button class="btn btn-sm btn-danger" onclick="confirmDeleteImage(${img.id}, '${img.filename.replace(/'/g, "\\'")}')">Delete</button>` : ''}
                                            </div>
                                        </div>
                                    `).join('')}
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            </div>
        </div>
    `;

    // Add styles if not already added
    if (!document.getElementById('duplicatesStyles')) {
        const styles = document.createElement('style');
        styles.id = 'duplicatesStyles';
        styles.textContent = `
            .duplicates-list { max-height: 60vh; overflow-y: auto; }
            .duplicate-group {
                background: var(--bg-tertiary);
                border-radius: var(--radius-md);
                padding: var(--spacing-md);
                margin-bottom: var(--spacing-md);
            }
            .duplicate-group h4 { margin-bottom: var(--spacing-sm); color: var(--text-primary); }
            .duplicate-images { display: flex; gap: var(--spacing-sm); flex-wrap: wrap; }
            .duplicate-image {
                width: 150px;
                background: var(--bg-secondary);
                border-radius: var(--radius-sm);
                overflow: hidden;
                border: 2px solid var(--border-color);
            }
            .duplicate-image.original { border-color: var(--success); }
            .duplicate-image.duplicate { border-color: var(--warning); }
            .duplicate-image img { width: 100%; height: 120px; object-fit: cover; }
            .duplicate-info { padding: var(--spacing-xs); text-align: center; }
            .duplicate-filename {
                display: block;
                font-size: 10px;
                color: var(--text-muted);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .duplicate-badge {
                display: inline-block;
                font-size: 9px;
                padding: 2px 6px;
                border-radius: 10px;
                margin: 4px 0;
            }
            .duplicate-image.original .duplicate-badge { background: var(--success); color: white; }
            .duplicate-image.duplicate .duplicate-badge { background: var(--warning); color: white; }
        `;
        document.head.appendChild(styles);
    }

    // Remove existing modal if any
    const existingModal = document.getElementById('duplicatesModal');
    if (existingModal) existingModal.remove();

    // Add modal to body
    document.body.insertAdjacentHTML('beforeend', modalHtml);
}

function closeDuplicatesModal() {
    const modal = document.getElementById('duplicatesModal');
    if (modal) modal.remove();
}

// Initialize fullscreen drop zone on page load
document.addEventListener('DOMContentLoaded', initFullscreenDropZone);

// ============ TRANSCRIPT SEARCH ============

function initTranscriptSearchModal() {
    const modal = document.getElementById('transcriptSearchModal');
    const overlay = document.getElementById('transcriptSearchOverlay');
    const closeBtn = document.getElementById('transcriptSearchClose');
    const searchInput = document.getElementById('transcriptSearchInput');
    const searchBtn = document.getElementById('transcriptSearchBtn2');
    const headerBtn = document.getElementById('transcriptSearchBtn');
    const menuBtn = document.getElementById('transcriptSearchBtnMenu');

    const openModal = () => {
        if (modal) modal.style.display = 'flex';
        if (searchInput) searchInput.focus();
    };

    const closeModal = () => {
        if (modal) modal.style.display = 'none';
    };

    if (headerBtn) headerBtn.addEventListener('click', openModal);
    if (menuBtn) menuBtn.addEventListener('click', openModal);
    if (overlay) overlay.addEventListener('click', closeModal);
    if (closeBtn) closeBtn.addEventListener('click', closeModal);

    if (searchBtn) {
        searchBtn.addEventListener('click', performTranscriptSearch);
    }

    if (searchInput) {
        searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') performTranscriptSearch();
        });
    }
}

async function performTranscriptSearch() {
    const input = document.getElementById('transcriptSearchInput');
    const resultsDiv = document.getElementById('transcriptSearchResults');
    const query = input?.value.trim();

    if (!query) {
        showToast('Please enter a search term', 'warning');
        return;
    }

    resultsDiv.innerHTML = '<div style="text-align: center; padding: 20px;"><div class="spinner"></div><p>Searching...</p></div>';

    try {
        const response = await fetch(`/api/videos/search/subtitles?q=${encodeURIComponent(query)}&limit=50`);
        const data = await response.json();

        if (data.results && data.results.length > 0) {
            resultsDiv.innerHTML = `
                <p style="color: var(--text-secondary); margin-bottom: 15px;">Found ${data.count} results for "<strong>${escapeHtml(query)}</strong>"</p>
                <div class="transcript-search-results">
                    ${data.results.map(result => `
                        <div class="transcript-result-item" onclick="openVideoAtTimestamp(${result.youtube_video_id}, ${result.start_time_ms}, '${escapeHtml(result.filepath || '')}')">
                            <div class="result-video-title">${escapeHtml(result.title || 'Unknown Video')}</div>
                            <div class="result-timestamp">${formatTimeReadable(result.start_time_ms)}</div>
                            <div class="result-text">${highlightText(result.text, query)}</div>
                        </div>
                    `).join('')}
                </div>
            `;
        } else {
            resultsDiv.innerHTML = `<p style="color: var(--text-muted); text-align: center;">No results found for "${escapeHtml(query)}"</p>`;
        }
    } catch (error) {
        console.error('Search error:', error);
        resultsDiv.innerHTML = '<p style="color: var(--error-color); text-align: center;">Error performing search</p>';
    }
}

function highlightText(text, query) {
    const escaped = escapeHtml(text);
    const regex = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
    return escaped.replace(regex, '<mark>$1</mark>');
}

async function openVideoAtTimestamp(youtubeVideoId, timestampMs, filepath) {
    // Close search modal
    const modal = document.getElementById('transcriptSearchModal');
    if (modal) modal.style.display = 'none';

    // Find the image by filepath
    if (filepath) {
        const image = allImages.find(img => img.filepath === filepath);
        if (image) {
            await openImageDetail(image);

            // Wait for video to load then seek
            setTimeout(() => {
                const video = document.getElementById('modalVideoPlayer');
                if (video) {
                    video.currentTime = timestampMs / 1000;
                    video.play();
                }
            }, 500);
        }
    }
}

// Initialize transcript search modal on page load
document.addEventListener('DOMContentLoaded', initTranscriptSearchModal);

console.log('AI Gallery initialized ✨');