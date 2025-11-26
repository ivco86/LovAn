/**
 * Video App - Frontend JavaScript
 * Handles video management, playback, and UI interactions
 */

// State
let videos = [];
let currentVideo = null;
let currentVideoId = null;
let currentPlatform = 'all';

// DOM Elements
const videoGrid = document.getElementById('videoGrid');
const searchInput = document.getElementById('searchInput');
const totalVideosEl = document.getElementById('totalVideos');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadVideos();
    setupEventListeners();
});

// Event Listeners
function setupEventListeners() {
    // Search
    searchInput.addEventListener('input', debounce(handleSearch, 300));

    // Add Video Button
    document.getElementById('addVideoBtn').addEventListener('click', openAddVideoModal);

    // Platform filter buttons
    document.querySelectorAll('.platform-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.platform-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentPlatform = btn.dataset.platform;
            filterVideos();
        });
    });

    // Tab switching
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });
}

// Debounce helper
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// ============ VIDEO LOADING ============

async function loadVideos() {
    try {
        const response = await fetch('/api/videos');
        const data = await response.json();
        videos = data.videos || [];
        renderVideos(videos);
        updateStats();
    } catch (error) {
        console.error('Error loading videos:', error);
        showEmptyState('Failed to load videos');
    }
}

function renderVideos(videosToRender) {
    if (videosToRender.length === 0) {
        showEmptyState('No videos found');
        return;
    }

    videoGrid.innerHTML = videosToRender.map(video => `
        <div class="video-card" onclick="openVideoPlayer(${video.id})">
            <div class="video-thumbnail">
                <img src="${video.thumbnail_url || '/static/img/placeholder.png'}" alt="${video.title}">
                <span class="video-duration">${formatDuration(video.duration)}</span>
            </div>
            <div class="video-info">
                <h3 class="video-title">${escapeHtml(video.title)}</h3>
                <p class="video-channel">${escapeHtml(video.channel_name || 'Unknown channel')}</p>
            </div>
        </div>
    `).join('');
}

function showEmptyState(message) {
    videoGrid.innerHTML = `
        <div class="empty-state">
            <h3>${message}</h3>
            <p>Click "Add Video" to download a new video</p>
        </div>
    `;
}

function updateStats() {
    totalVideosEl.textContent = videos.length;

    // Count by platform
    const youtubeCount = videos.filter(v => detectPlatform(v.youtube_id) === 'youtube').length;
    const tiktokCount = videos.filter(v => detectPlatform(v.youtube_id) === 'tiktok').length;

    const youtubeEl = document.getElementById('youtubeCount');
    const tiktokEl = document.getElementById('tiktokCount');

    if (youtubeEl) youtubeEl.textContent = youtubeCount;
    if (tiktokEl) tiktokEl.textContent = tiktokCount;
}

// ============ SEARCH & FILTER ============

function handleSearch() {
    filterVideos();
}

function filterVideos() {
    const query = searchInput.value.toLowerCase().trim();

    let filtered = videos;

    // Filter by platform
    if (currentPlatform !== 'all') {
        filtered = filtered.filter(v => detectPlatform(v.youtube_id) === currentPlatform);
    }

    // Filter by search query
    if (query) {
        filtered = filtered.filter(v =>
            v.title.toLowerCase().includes(query) ||
            (v.channel_name && v.channel_name.toLowerCase().includes(query))
        );
    }

    renderVideos(filtered);
}

function detectPlatform(videoId) {
    if (!videoId) return 'other';
    if (videoId.startsWith('tt_')) return 'tiktok';
    if (videoId.startsWith('fb_')) return 'facebook';
    if (videoId.startsWith('ig_')) return 'instagram';
    if (videoId.startsWith('tw_')) return 'twitter';
    // YouTube IDs are 11 characters
    if (/^[a-zA-Z0-9_-]{11}$/.test(videoId)) return 'youtube';
    return 'other';
}

// ============ ADD VIDEO MODAL ============

function openAddVideoModal() {
    document.getElementById('addVideoModal').classList.add('active');
    document.getElementById('videoUrl').value = '';
    document.getElementById('videoPreview').classList.add('hidden');
    document.getElementById('downloadBtn').disabled = true;
    document.getElementById('downloadProgress').classList.add('hidden');
}

function closeAddVideoModal() {
    document.getElementById('addVideoModal').classList.remove('active');
}

async function fetchVideoInfo() {
    const url = document.getElementById('videoUrl').value.trim();
    if (!url) {
        alert('Please enter a video URL');
        return;
    }

    const fetchBtn = document.getElementById('fetchInfoBtn');
    fetchBtn.disabled = true;
    fetchBtn.textContent = 'Fetching...';

    try {
        const response = await fetch(`/api/videos/info?url=${encodeURIComponent(url)}`);
        const data = await response.json();

        if (data.error) {
            alert(data.error);
            return;
        }

        // Show preview
        document.getElementById('previewThumb').src = data.thumbnail_url || '';
        document.getElementById('previewTitle').textContent = data.title;
        document.getElementById('previewChannel').textContent = data.channel_name || '';
        document.getElementById('previewDuration').textContent = formatDuration(data.duration);
        document.getElementById('videoPreview').classList.remove('hidden');
        document.getElementById('downloadBtn').disabled = false;

        // Store info for download
        window.videoInfo = data;

        if (data.exists_in_gallery) {
            alert('This video is already in your gallery!');
        }
    } catch (error) {
        console.error('Error fetching video info:', error);
        alert('Failed to fetch video information');
    } finally {
        fetchBtn.disabled = false;
        fetchBtn.textContent = 'Fetch Info';
    }
}

async function downloadVideo() {
    const url = document.getElementById('videoUrl').value.trim();
    const subtitles = document.getElementById('downloadSubtitles').checked;
    const keyframes = document.getElementById('extractKeyframes').checked;
    const quality = document.getElementById('videoQuality').value;

    const downloadBtn = document.getElementById('downloadBtn');
    const progressContainer = document.getElementById('downloadProgress');
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');

    downloadBtn.disabled = true;
    progressContainer.classList.remove('hidden');
    progressFill.style.width = '0%';
    progressText.textContent = 'Starting download...';

    try {
        // Simulate progress while downloading
        let progress = 0;
        const progressInterval = setInterval(() => {
            progress = Math.min(progress + 5, 90);
            progressFill.style.width = `${progress}%`;
        }, 500);

        const response = await fetch('/api/videos/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url,
                subtitles,
                original_subtitles: subtitles,
                keyframes,
                quality
            })
        });

        clearInterval(progressInterval);
        const data = await response.json();

        if (data.error) {
            progressText.textContent = `Error: ${data.error}`;
            progressFill.style.width = '100%';
            progressFill.style.background = 'var(--danger-color)';
        } else if (data.status === 'exists') {
            progressText.textContent = 'Video already exists in gallery!';
            progressFill.style.width = '100%';
        } else {
            progressFill.style.width = '100%';
            progressText.textContent = 'Download complete!';

            // Refresh video list
            await loadVideos();

            // Close modal after a short delay
            setTimeout(() => {
                closeAddVideoModal();
            }, 1500);
        }
    } catch (error) {
        console.error('Error downloading video:', error);
        progressText.textContent = 'Download failed!';
        progressFill.style.background = 'var(--danger-color)';
    }
}

// ============ VIDEO PLAYER ============

async function openVideoPlayer(videoId) {
    currentVideoId = videoId;

    try {
        const response = await fetch(`/api/videos/${videoId}`);
        currentVideo = await response.json();

        if (currentVideo.error) {
            alert(currentVideo.error);
            return;
        }

        // Set up player
        document.getElementById('playerTitle').textContent = currentVideo.title;
        const videoPlayer = document.getElementById('videoPlayer');

        // Use image_id for file serving
        videoPlayer.src = `/api/images/${currentVideo.image_id}/file`;

        // Load subtitles
        loadSubtitles(currentVideo.image_id);

        // Load bookmarks
        loadBookmarks(currentVideo.image_id);

        // Load notes
        loadNotes(currentVideo.image_id);

        // Show modal
        document.getElementById('videoPlayerModal').classList.add('active');

    } catch (error) {
        console.error('Error opening video:', error);
        alert('Failed to open video');
    }
}

function closeVideoPlayer() {
    document.getElementById('videoPlayerModal').classList.remove('active');
    document.getElementById('videoPlayer').pause();
    currentVideo = null;
    currentVideoId = null;
}

// ============ SUBTITLES ============

async function loadSubtitles(imageId) {
    try {
        const response = await fetch(`/api/images/${imageId}/subtitles`);
        const data = await response.json();

        const subtitleList = document.getElementById('subtitleList');

        if (!data.subtitles || data.subtitles.length === 0) {
            subtitleList.innerHTML = '<p class="empty-state">No subtitles available</p>';
            return;
        }

        subtitleList.innerHTML = data.subtitles.map((sub, idx) => `
            <div class="subtitle-item" data-time="${sub.start_time_ms}" onclick="seekToTime(${sub.start_time_ms})">
                <span class="subtitle-time">${formatTime(sub.start_time_ms)}</span>
                ${escapeHtml(sub.text)}
            </div>
        `).join('');

    } catch (error) {
        console.error('Error loading subtitles:', error);
    }
}

// ============ BOOKMARKS ============

async function loadBookmarks(imageId) {
    try {
        const response = await fetch(`/api/images/${imageId}/bookmarks`);
        const data = await response.json();

        const bookmarkList = document.getElementById('bookmarkList');

        if (!data.bookmarks || data.bookmarks.length === 0) {
            bookmarkList.innerHTML = '<p class="empty-state">No bookmarks yet</p>';
            return;
        }

        bookmarkList.innerHTML = data.bookmarks.map(bm => `
            <div class="bookmark-item" onclick="seekToTime(${bm.timestamp_ms})">
                <div class="bookmark-color" style="background: ${bm.color}"></div>
                <div class="bookmark-info">
                    <div class="bookmark-title">${escapeHtml(bm.title)}</div>
                    <div class="bookmark-time">${formatTime(bm.timestamp_ms)}</div>
                </div>
            </div>
        `).join('');

    } catch (error) {
        console.error('Error loading bookmarks:', error);
    }
}

async function addBookmark() {
    if (!currentVideo) return;

    const video = document.getElementById('videoPlayer');
    const timestamp_ms = Math.floor(video.currentTime * 1000);
    const title = prompt('Bookmark title:');

    if (!title) return;

    try {
        const response = await fetch(`/api/images/${currentVideo.image_id}/bookmarks`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                timestamp_ms,
                title,
                color: '#ff4444'
            })
        });

        if (response.ok) {
            loadBookmarks(currentVideo.image_id);
        }
    } catch (error) {
        console.error('Error adding bookmark:', error);
    }
}

// ============ NOTES ============

async function loadNotes(imageId) {
    try {
        const response = await fetch(`/api/images/${imageId}/notes`);
        const data = await response.json();

        const notesList = document.getElementById('notesList');

        if (!data.notes || data.notes.length === 0) {
            notesList.innerHTML = '<p class="empty-state">No notes yet</p>';
            return;
        }

        notesList.innerHTML = data.notes.map(note => `
            <div class="note-item" onclick="seekToTime(${note.timestamp_ms})">
                <div class="note-time">${formatTime(note.timestamp_ms)}</div>
                <div class="note-content">${escapeHtml(note.content)}</div>
            </div>
        `).join('');

    } catch (error) {
        console.error('Error loading notes:', error);
    }
}

async function addNote() {
    if (!currentVideo) return;

    const video = document.getElementById('videoPlayer');
    const timestamp_ms = Math.floor(video.currentTime * 1000);
    const content = prompt('Enter your note:');

    if (!content) return;

    try {
        const response = await fetch(`/api/images/${currentVideo.image_id}/notes`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                timestamp_ms,
                content
            })
        });

        if (response.ok) {
            loadNotes(currentVideo.image_id);
        }
    } catch (error) {
        console.error('Error adding note:', error);
    }
}

// ============ TABS ============

function switchTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.tab === tabName);
    });

    // Update tab content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.add('hidden');
    });
    document.getElementById(`${tabName}Tab`).classList.remove('hidden');
}

// ============ HELPERS ============

function seekToTime(ms) {
    const video = document.getElementById('videoPlayer');
    video.currentTime = ms / 1000;
    video.play();
}

function formatDuration(seconds) {
    if (!seconds) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    if (mins >= 60) {
        const hours = Math.floor(mins / 60);
        const remainMins = mins % 60;
        return `${hours}:${remainMins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function formatTime(ms) {
    const totalSeconds = Math.floor(ms / 1000);
    const mins = Math.floor(totalSeconds / 60);
    const secs = totalSeconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============ AI ANALYSIS ============

async function analyzeVideo() {
    if (!currentVideo) return;

    const analyzeBtn = document.getElementById('analyzeBtn');
    const originalText = analyzeBtn.textContent;

    analyzeBtn.disabled = true;
    analyzeBtn.textContent = 'Analyzing...';

    try {
        const response = await fetch(`/api/videos/${currentVideo.id}/analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        const data = await response.json();

        if (data.success) {
            alert(`Analysis complete!\n\nDescription: ${data.description}\n\nTags: ${data.tags.join(', ')}`);
            // Refresh video list to show updated data
            await loadVideos();
        } else {
            alert(`Analysis failed: ${data.error}`);
        }
    } catch (error) {
        console.error('Error analyzing video:', error);
        alert('Failed to analyze video');
    } finally {
        analyzeBtn.disabled = false;
        analyzeBtn.textContent = originalText;
    }
}
