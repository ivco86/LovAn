/**
 * Face Recognition Management
 * Handles people listing, face grouping, and naming
 */

let currentPersonId = null;

// Load all people/person groups
async function loadPeople() {
    try {
        const response = await fetch('/api/people');
        const data = await response.json();

        if (data.success) {
            await renderPeopleList(data.people);
        }
    } catch (error) {
        console.error('Error loading people:', error);
    }
}

// Toggle People section
function togglePeopleSection() {
    const content = document.getElementById('peopleContent');
    const toggle = document.getElementById('peopleSectionToggle');

    if (content.style.display === 'none') {
        content.style.display = 'block';
        toggle.textContent = '▼';
    } else {
        content.style.display = 'none';
        toggle.textContent = '▶';
    }
}

// Render people in sidebar as tags (like Popular Tags)
function renderPeopleList(people) {
    const peopleList = document.getElementById('peopleList');
    const peopleCount = document.getElementById('peopleCount');
    if (!peopleList) return;

    if (!people || people.length === 0) {
        peopleList.innerHTML = '<span style="color: var(--text-muted); font-size: 0.75rem;">No people yet</span>';
        if (peopleCount) peopleCount.textContent = '0';
        return;
    }

    // Update count
    if (peopleCount) peopleCount.textContent = people.length;

    // Render people as tags (tag-cloud-item style)
    peopleList.innerHTML = people.map(person => {
        const name = person.name || `Unknown Person #${person.id}`;
        const imageCount = person.image_count || 0;
        const faceCount = person.face_count || 0;

        // Calculate size class based on image count (like tag cloud)
        let sizeClass = 'tag-size-sm';
        if (imageCount > 20) sizeClass = 'tag-size-xl';
        else if (imageCount > 10) sizeClass = 'tag-size-lg';
        else if (imageCount > 5) sizeClass = 'tag-size-md';

        return `
            <span class="tag-cloud-item ${sizeClass}" data-person-id="${person.id}" onclick="showPersonImages(${person.id}, '${escapeHtml(name)}')">
                <span style="font-size: 0.9em;">👤</span>
                ${escapeHtml(name)}
                <span class="tag-cloud-count">${imageCount}</span>
            </span>
        `;
    }).join('');
}

// Open people modal
async function openPeopleModal() {
    try {
        const response = await fetch('/api/people');
        const data = await response.json();

        if (data.success) {
            renderPeopleModal(data.people);
            document.getElementById('peopleModal').style.display = 'block';
        }
    } catch (error) {
        console.error('Error opening people modal:', error);
        showToast('Failed to load people', 'error');
    }
}

// Render people in modal
function renderPeopleModal(people) {
    const peopleContent = document.getElementById('peopleContent');
    const peopleEmpty = document.getElementById('peopleEmpty');

    if (!people || people.length === 0) {
        peopleContent.style.display = 'none';
        peopleEmpty.style.display = 'block';
        return;
    }

    peopleContent.style.display = 'grid';
    peopleEmpty.style.display = 'none';

    peopleContent.innerHTML = people.map(person => {
        const name = person.name || 'Unknown Person';
        const faceCount = person.face_count || 0;
        const imageCount = person.image_count || 0;

        return `
            <div class="person-card" style="
                background: var(--bg-secondary);
                border: 1px solid var(--border);
                border-radius: var(--radius-md);
                padding: var(--spacing-md);
                cursor: pointer;
                transition: all 0.2s;
            " onclick="openPersonDetail(${person.id})">
                <div style="font-size: 3rem; text-align: center; margin-bottom: var(--spacing-sm);">
                    👤
                </div>
                <div style="text-align: center;">
                    <strong>${escapeHtml(name)}</strong>
                </div>
                <div style="text-align: center; font-size: 0.875rem; color: var(--text-muted); margin-top: var(--spacing-xs);">
                    ${faceCount} face${faceCount !== 1 ? 's' : ''} • ${imageCount} image${imageCount !== 1 ? 's' : ''}
                </div>
            </div>
        `;
    }).join('');
}

// Open person detail modal
async function openPersonDetail(personId) {
    currentPersonId = personId;

    try {
        const response = await fetch(`/api/people/${personId}`);
        const data = await response.json();

        if (data.success) {
            const person = data.person;
            const faces = data.faces;

            document.getElementById('personDetailName').textContent = person.name || 'Unknown Person';
            document.getElementById('personNameInput').value = person.name || '';
            document.getElementById('personFaceCount').textContent = person.face_count || 0;
            document.getElementById('personImageCount').textContent = person.image_count || 0;

            // Render face thumbnails with remove buttons
            const facesGrid = document.getElementById('personFacesGrid');
            if (faces && faces.length > 0) {
                facesGrid.innerHTML = faces.map(face => `
                    <div style="position: relative; aspect-ratio: 1; background: var(--bg-tertiary); border-radius: var(--radius-sm); overflow: hidden; group;">
                        <img src="/api/images/${face.image_id}/thumbnail" alt="Face" style="width: 100%; height: 100%; object-fit: cover;" loading="lazy">
                        <button
                            onclick="removeFaceFromPerson(${face.id}, ${personId}); event.stopPropagation();"
                            style="
                                position: absolute;
                                top: var(--spacing-xs);
                                right: var(--spacing-xs);
                                background: rgba(220, 38, 38, 0.9);
                                color: white;
                                border: none;
                                border-radius: var(--radius-sm);
                                padding: var(--spacing-xs) var(--spacing-sm);
                                cursor: pointer;
                                font-size: 0.75rem;
                                opacity: 0.8;
                                transition: opacity 0.2s;
                            "
                            onmouseover="this.style.opacity='1'"
                            onmouseout="this.style.opacity='0.8'"
                            title="Remove face from this person"
                        >✕</button>
                    </div>
                `).join('');
            } else {
                facesGrid.innerHTML = '<p style="color: var(--text-muted);">No faces found</p>';
            }

            // Close people modal if open
            document.getElementById('peopleModal').style.display = 'none';

            // Open detail modal
            document.getElementById('personDetailModal').style.display = 'block';
        }
    } catch (error) {
        console.error('Error loading person details:', error);
        showToast('Failed to load person details', 'error');
    }
}

// Save person name
async function savePersonName() {
    if (!currentPersonId) return;

    const name = document.getElementById('personNameInput').value.trim();

    if (!name) {
        showToast('Please enter a name', 'error');
        return;
    }

    try {
        const response = await fetch(`/api/people/${currentPersonId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });

        const data = await response.json();

        if (data.success) {
            showToast(`Name updated to "${name}"`, 'success');
            document.getElementById('personDetailName').textContent = name;
            loadPeople(); // Refresh sidebar
        } else {
            showToast(data.error || 'Failed to update name', 'error');
        }
    } catch (error) {
        console.error('Error saving person name:', error);
        showToast('Failed to save name', 'error');
    }
}

// Delete person
async function deletePerson() {
    if (!currentPersonId) return;

    if (!confirm('Delete this person? Faces will become unassigned.')) {
        return;
    }

    try {
        const response = await fetch(`/api/people/${currentPersonId}`, {
            method: 'DELETE'
        });

        const data = await response.json();

        if (data.success) {
            showToast('Person deleted', 'success');
            document.getElementById('personDetailModal').style.display = 'none';
            loadPeople();
        } else {
            showToast(data.error || 'Failed to delete person', 'error');
        }
    } catch (error) {
        console.error('Error deleting person:', error);
        showToast('Failed to delete person', 'error');
    }
}

// Cluster faces automatically
async function clusterFaces() {
    if (!confirm('Auto-group similar faces? This may take a moment.')) {
        return;
    }

    showToast('Clustering faces...', 'info');

    try {
        const response = await fetch('/api/faces/cluster', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ similarity_threshold: 0.6 })
        });

        const data = await response.json();

        if (data.success) {
            showToast(`Grouped ${data.faces_clustered} faces into ${data.groups_created} people`, 'success');
            loadPeople();
        } else {
            showToast(data.error || 'Failed to cluster faces', 'error');
        }
    } catch (error) {
        console.error('Error clustering faces:', error);
        showToast('Failed to cluster faces', 'error');
    }
}

// Show People view (grid of all people)
async function showPeopleView() {
    try {
        const response = await fetch('/api/people');
        const data = await response.json();

        if (!data.success) {
            showToast('Failed to load people', 'error');
            return;
        }

        const people = data.people || [];
        const imageGrid = document.getElementById('imageGrid');
        const breadcrumb = document.getElementById('breadcrumb');

        // Update breadcrumb
        breadcrumb.innerHTML = '<span class="breadcrumb-item">👤 People</span>';

        if (people.length === 0) {
            imageGrid.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">👤</div>
                    <h2>No People Detected Yet</h2>
                    <p>Analyze images with AI to automatically detect faces</p>
                    <button class="btn btn-primary" onclick="document.getElementById('analyzeBtn').click()">🤖 Analyze Images</button>
                </div>
            `;
            return;
        }

        // Render people as tag-like cards (similar to tag cloud)
        imageGrid.innerHTML = `
            <div style="display: flex; flex-wrap: wrap; gap: var(--spacing-sm); padding: var(--spacing-lg);">
                ${people.map(person => {
            const name = person.name || `Unknown Person #${person.id}`;
            const imageCount = person.image_count || 0;

            // Calculate size class based on image count (like tag cloud)
            let sizeClass = 'tag-sm';
            if (imageCount > 20) sizeClass = 'tag-xl';
            else if (imageCount > 10) sizeClass = 'tag-lg';
            else if (imageCount > 5) sizeClass = 'tag-md';

            return `
                        <div
                            class="person-tag ${sizeClass}"
                            onclick="showPersonImages(${person.id}, '${escapeHtml(name)}')"
                            style="
                                display: inline-flex;
                                align-items: center;
                                gap: var(--spacing-xs);
                                padding: var(--spacing-sm) var(--spacing-md);
                                background: var(--bg-secondary);
                                border: 1px solid var(--border);
                                border-radius: var(--radius-full);
                                cursor: pointer;
                                transition: all 0.2s;
                                white-space: nowrap;
                            "
                            onmouseover="this.style.background='var(--bg-tertiary)'; this.style.borderColor='var(--primary)';"
                            onmouseout="this.style.background='var(--bg-secondary)'; this.style.borderColor='var(--border)';"
                        >
                            <span style="font-size: 1.2em;">👤</span>
                            <span style="font-weight: 500;">${escapeHtml(name)}</span>
                            <span style="
                                background: var(--bg-tertiary);
                                padding: 2px 8px;
                                border-radius: var(--radius-full);
                                font-size: 0.85em;
                                color: var(--text-muted);
                            ">${imageCount}</span>
                            <button
                                onclick="event.stopPropagation(); openPersonDetailForEdit(${person.id});"
                                style="
                                    background: transparent;
                                    border: none;
                                    cursor: pointer;
                                    padding: 2px 4px;
                                    font-size: 0.9em;
                                    opacity: 0.6;
                                "
                                onmouseover="this.style.opacity='1'"
                                onmouseout="this.style.opacity='0.6'"
                                title="Edit person"
                            >✏️</button>
                        </div>
                    `;
        }).join('')}
            </div>
        `;

        // Update count
        const peopleViewCount = document.getElementById('peopleViewCount');
        if (peopleViewCount) peopleViewCount.textContent = people.length;

    } catch (error) {
        console.error('Error showing people view:', error);
        showToast('Failed to load people', 'error');
    }
}

// Show all images for a person (like gallery view)
async function showPersonImages(personId, personName) {
    try {
        const response = await fetch(`/api/people/${personId}`);
        const data = await response.json();

        if (!data.success) {
            showToast('Failed to load person details', 'error');
            return;
        }

        const faces = data.faces || [];
        const imageGrid = document.getElementById('imageGrid');
        const breadcrumb = document.getElementById('breadcrumb');

        // Update breadcrumb
        breadcrumb.innerHTML = `
            <span class="breadcrumb-item" onclick="showPeopleView()" style="cursor: pointer;">👤 People</span>
            <span class="breadcrumb-separator">›</span>
            <span class="breadcrumb-item">${escapeHtml(personName)}</span>
        `;

        if (faces.length === 0) {
            imageGrid.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">👤</div>
                    <h2>No Faces Found</h2>
                    <p>This person has no detected faces</p>
                </div>
            `;
            return;
        }

        // Group faces by image_id to get unique images
        const imageMap = new Map();
        faces.forEach(face => {
            if (!imageMap.has(face.image_id)) {
                imageMap.set(face.image_id, {
                    image_id: face.image_id,
                    faces: []
                });
            }
            imageMap.get(face.image_id).faces.push(face);
        });

        const uniqueImageIds = Array.from(imageMap.keys());

        // Load full image details for each image
        const imagePromises = uniqueImageIds.map(async (imageId) => {
            try {
                const imgResponse = await fetch(`/api/images/${imageId}`);
                const imgData = await imgResponse.json();
                return imgData;
            } catch (error) {
                console.error(`Error loading image ${imageId}:`, error);
                return null;
            }
        });

        const images = (await Promise.all(imagePromises)).filter(img => img !== null);

        if (images.length === 0) {
            imageGrid.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">👤</div>
                    <h2>No Images Found</h2>
                    <p>Could not load images for this person</p>
                </div>
            `;
            return;
        }

        // Render images using createImageCard (like in gallery)
        if (typeof createImageCard === 'function') {
            imageGrid.innerHTML = images.map(image => createImageCard(image)).join('');

            // Add click handlers for image cards
            imageGrid.querySelectorAll('.image-card').forEach(card => {
                card.addEventListener('click', async (e) => {
                    // Don't trigger if clicking checkbox or favorite
                    if (e.target.closest('.image-card-checkbox') || e.target.closest('.image-card-favorite')) {
                        return;
                    }
                    
                    const imageId = parseInt(card.dataset.id);
                    if (imageId && typeof openImageModal === 'function') {
                        const imageDetails = await getImageDetails(imageId);
                        if (imageDetails) {
                            openImageModal(imageDetails);
                        }
                    }
                });
            });
        } else {
            // Fallback if createImageCard is not available
            imageGrid.innerHTML = images.map(image => `
                <div class="image-card" data-id="${image.id}" onclick="openImageModal({id: ${image.id}})">
                    <img class="image-card-image" src="/api/images/${image.id}/thumbnail?size=500" alt="${escapeHtml(image.filename)}" loading="lazy">
                    <div class="image-card-content">
                        <div class="image-card-header">
                            <div class="image-card-filename">${escapeHtml(image.filename)}</div>
                        </div>
                    </div>
                </div>
            `).join('');
        }

    } catch (error) {
        console.error('Error showing person images:', error);
        showToast('Failed to load person images', 'error');
    }
}

// Open person detail modal for editing
function openPersonDetailForEdit(personId) {
    openPersonDetail(personId);
}

// Remove face from person group
async function removeFaceFromPerson(faceId, personId) {
    if (!confirm('Remove this face from the person group?')) {
        return;
    }

    try {
        const response = await fetch(`/api/faces/${faceId}/unassign`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            showToast('Face removed from group', 'success');
            // Reload person detail
            openPersonDetail(personId);
            loadPeople(); // Refresh sidebar
            loadUnknownFaces(); // Refresh unknown faces
        } else {
            showToast(data.error || 'Failed to remove face', 'error');
        }
    } catch (error) {
        console.error('Error removing face:', error);
        showToast('Failed to remove face', 'error');
    }
}

// Load unknown (unassigned) faces
async function loadUnknownFaces() {
    try {
        const response = await fetch('/api/faces/unassigned');
        const data = await response.json();

        if (data.success) {
            renderUnknownFaces(data.faces);
        }
    } catch (error) {
        console.error('Error loading unknown faces:', error);
    }
}

// Render unknown faces in sidebar
function renderUnknownFaces(faces) {
    const unknownFacesList = document.getElementById('unknownFacesList');
    if (!unknownFacesList) return;

    if (!faces || faces.length === 0) {
        unknownFacesList.innerHTML = '<p style="color: var(--text-muted); font-size: 0.75rem; text-align: center; padding: var(--spacing-sm);">No unknown faces</p>';
        return;
    }

    // Show first 9 unknown faces
    const displayFaces = faces.slice(0, 9);

    unknownFacesList.innerHTML = displayFaces.map(face => `
        <div
            onclick="openAssignFaceModal(${face.id}, ${face.image_id})"
            style="
                position: relative;
                aspect-ratio: 1;
                background: var(--bg-tertiary);
                border-radius: var(--radius-sm);
                overflow: hidden;
                cursor: pointer;
                border: 2px solid transparent;
                transition: all 0.2s;
            "
            onmouseover="this.style.borderColor='var(--primary)'"
            onmouseout="this.style.borderColor='transparent'"
            title="Click to assign to person"
        >
            <img src="/api/images/${face.image_id}/thumbnail" alt="Unknown face" style="width: 100%; height: 100%; object-fit: cover;" loading="lazy">
            <div style="
                position: absolute;
                bottom: 0;
                left: 0;
                right: 0;
                background: rgba(0, 0, 0, 0.7);
                color: white;
                padding: 2px;
                font-size: 0.65rem;
                text-align: center;
            ">+</div>
        </div>
    `).join('');

    // Show count if there are more
    if (faces.length > 9) {
        unknownFacesList.innerHTML += `<p style="grid-column: 1 / -1; color: var(--text-muted); font-size: 0.75rem; text-align: center; margin-top: var(--spacing-xs);">+${faces.length - 9} more</p>`;
    }
}

// Current face being assigned
let currentAssignFaceId = null;
let allPeopleForAssign = [];

// Open inline assign face form
async function openAssignFaceModal(faceId, imageId) {
    currentAssignFaceId = faceId;

    // Set preview image
    document.getElementById('inlineAssignPreview').src = `/api/images/${imageId}/thumbnail`;

    // Load all people
    try {
        const response = await fetch('/api/people');
        const data = await response.json();

        if (data.success) {
            allPeopleForAssign = data.people || [];
            renderInlinePersonSuggestions(allPeopleForAssign);
        }
    } catch (error) {
        console.error('Error loading people:', error);
    }

    // Clear search
    document.getElementById('inlinePersonSearch').value = '';

    // Show inline form and expand People section
    document.getElementById('inlineAssignForm').style.display = 'block';
    const peopleContent = document.getElementById('peopleContent');
    const toggle = document.getElementById('peopleSectionToggle');
    if (peopleContent.style.display === 'none') {
        peopleContent.style.display = 'block';
        toggle.textContent = '▼';
    }
}

// Render person suggestions in inline form
function renderInlinePersonSuggestions(people, searchTerm = '') {
    const suggestionsDiv = document.getElementById('inlinePersonSuggestions');

    if (!people || people.length === 0) {
        if (searchTerm) {
            // Show create new option
            suggestionsDiv.innerHTML = `
                <div
                    onclick="createNewPersonFromInline('${escapeHtml(searchTerm)}')"
                    style="
                        padding: var(--spacing-xs);
                        background: var(--bg-secondary);
                        border: 1px solid var(--primary);
                        border-radius: var(--radius-sm);
                        cursor: pointer;
                        margin-bottom: var(--spacing-xs);
                        transition: all 0.2s;
                        font-size: 0.875rem;
                    "
                    onmouseover="this.style.background='var(--bg-tertiary)'"
                    onmouseout="this.style.background='var(--bg-secondary)'"
                >
                    ➕ Create "${escapeHtml(searchTerm)}"
                </div>
            `;
        } else {
            suggestionsDiv.innerHTML = '<p style="color: var(--text-muted); text-align: center; font-size: 0.75rem; padding: var(--spacing-xs);">Type to search or create</p>';
        }
        return;
    }

    let html = people.map(person => {
        const name = person.name || `Unknown Person #${person.id}`;
        const faceCount = person.face_count || 0;

        return `
            <div
                onclick="assignFaceToPerson(${currentAssignFaceId}, ${person.id}, '${escapeHtml(name)}')"
                style="
                    padding: var(--spacing-xs);
                    background: var(--bg-secondary);
                    border: 1px solid var(--border);
                    border-radius: var(--radius-sm);
                    cursor: pointer;
                    margin-bottom: var(--spacing-xs);
                    display: flex;
                    align-items: center;
                    gap: var(--spacing-xs);
                    transition: all 0.2s;
                    font-size: 0.875rem;
                "
                onmouseover="this.style.background='var(--bg-tertiary)'"
                onmouseout="this.style.background='var(--bg-secondary)'"
            >
                <div>👤</div>
                <div style="flex: 1;">
                    <div style="font-weight: 500;">${escapeHtml(name)}</div>
                    <div style="font-size: 0.7rem; color: var(--text-muted);">${faceCount} face${faceCount !== 1 ? 's' : ''}</div>
                </div>
                <div style="color: var(--primary);">→</div>
            </div>
        `;
    }).join('');

    // Add create new option if searching
    if (searchTerm && !people.some(p => (p.name || '').toLowerCase() === searchTerm.toLowerCase())) {
        html = `
            <div
                onclick="createNewPersonFromInline('${escapeHtml(searchTerm)}')"
                style="
                    padding: var(--spacing-xs);
                    background: var(--bg-secondary);
                    border: 1px solid var(--primary);
                    border-radius: var(--radius-sm);
                    cursor: pointer;
                    margin-bottom: var(--spacing-xs);
                    transition: all 0.2s;
                    font-size: 0.875rem;
                "
                onmouseover="this.style.background='var(--bg-tertiary)'"
                onmouseout="this.style.background='var(--bg-secondary)'"
            >
                ➕ Create "${escapeHtml(searchTerm)}"
            </div>
        ` + html;
    }

    suggestionsDiv.innerHTML = html;
}

// Assign face to person
async function assignFaceToPerson(faceId, personId, personName) {
    try {
        const response = await fetch(`/api/faces/${faceId}/assign`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ person_group_id: personId })
        });

        const data = await response.json();

        if (data.success) {
            showToast(`Face assigned to ${personName}`, 'success');
            document.getElementById('inlineAssignForm').style.display = 'none';
            loadUnknownFaces(); // Refresh unknown faces
            loadPeople(); // Refresh people list
        } else {
            showToast(data.error || 'Failed to assign face', 'error');
        }
    } catch (error) {
        console.error('Error assigning face:', error);
        showToast('Failed to assign face', 'error');
    }
}

// Create new person from inline form
async function createNewPersonFromInline(name) {
    if (!name || !currentAssignFaceId) return;

    try {
        // Create new person
        const createResponse = await fetch('/api/people', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });

        const createData = await createResponse.json();

        if (createData.success) {
            // Assign face to new person
            await assignFaceToPerson(currentAssignFaceId, createData.person_id, name);
        } else {
            showToast(createData.error || 'Failed to create person', 'error');
        }
    } catch (error) {
        console.error('Error creating person:', error);
        showToast('Failed to create person', 'error');
    }
}

// Filter people by search term in inline form
function filterInlinePersonSearch() {
    const searchTerm = document.getElementById('inlinePersonSearch').value.trim().toLowerCase();

    if (!searchTerm) {
        renderInlinePersonSuggestions(allPeopleForAssign);
        return;
    }

    const filtered = allPeopleForAssign.filter(person => {
        const name = (person.name || '').toLowerCase();
        return name.includes(searchTerm);
    });

    renderInlinePersonSuggestions(filtered, searchTerm);
}

// Cancel inline assign
function cancelInlineAssign() {
    document.getElementById('inlineAssignForm').style.display = 'none';
    document.getElementById('inlinePersonSearch').value = '';
    currentAssignFaceId = null;
}

// Initialize face recognition UI
function initFacesUI() {
    // Load people and unknown faces on startup
    loadPeople();
    loadUnknownFaces();

    // Cluster faces button (sidebar)
    const clusterBtn = document.getElementById('clusterFacesBtn');
    if (clusterBtn) {
        clusterBtn.addEventListener('click', clusterFaces);
    }

    // Cluster faces button (modal)
    const clusterModalBtn = document.getElementById('clusterFacesModalBtn');
    if (clusterModalBtn) {
        clusterModalBtn.addEventListener('click', clusterFaces);
    }

    // People modal close
    const peopleClose = document.getElementById('peopleClose');
    const peopleOverlay = document.getElementById('peopleOverlay');
    if (peopleClose) peopleClose.addEventListener('click', () => {
        document.getElementById('peopleModal').style.display = 'none';
    });
    if (peopleOverlay) peopleOverlay.addEventListener('click', () => {
        document.getElementById('peopleModal').style.display = 'none';
    });

    // Person detail modal close
    const personDetailClose = document.getElementById('personDetailClose');
    if (personDetailClose) personDetailClose.addEventListener('click', () => {
        document.getElementById('personDetailModal').style.display = 'none';
        currentPersonId = null;
    });

    // Inline assign form - cancel button
    const inlineCancelAssignBtn = document.getElementById('inlineCancelAssignBtn');
    if (inlineCancelAssignBtn) {
        inlineCancelAssignBtn.addEventListener('click', cancelInlineAssign);
    }

    // Inline person search input
    const inlinePersonSearch = document.getElementById('inlinePersonSearch');
    if (inlinePersonSearch) {
        inlinePersonSearch.addEventListener('input', filterInlinePersonSearch);
    }

    // Save person name
    const saveNameBtn = document.getElementById('savePersonNameBtn');
    if (saveNameBtn) {
        saveNameBtn.addEventListener('click', savePersonName);
    }

    // Delete person
    const deleteBtn = document.getElementById('deletePersonBtn');
    if (deleteBtn) {
        deleteBtn.addEventListener('click', deletePerson);
    }
}

// Call init when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initFacesUI);
} else {
    initFacesUI();
}