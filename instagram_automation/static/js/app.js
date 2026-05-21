/**
 * Instagram Automation Dashboard — JavaScript
 * Handles: modal open/close, keyword input, action builder, CRUD API calls, toasts,
 * plus Button/Quick Reply builders and Live Chat Inbox polling/sends.
 */

// ============ State ============
let keywords = [];
let actionSteps = [{ type: 'send_private_reply', text: '' }];
let actionCounter = 1;

// Live Chat State
let conversations = [];
let activeConvo = null;
let messagePollingInterval = null;
let inboxPollingInterval = null;
let windowCountdownInterval = null;

// ============ Modal ============
function openModal(editId) {
    const modal = document.getElementById('automation-modal');
    const title = document.getElementById('modal-title');
    const saveBtn = document.getElementById('btn-save-automation');
    const editIdInput = document.getElementById('edit-automation-id');

    if (editId) {
        title.textContent = 'Edit Automation';
        saveBtn.textContent = 'Save Changes';
        editIdInput.value = editId;
    } else {
        title.textContent = 'New Automation';
        saveBtn.textContent = 'Create Automation';
        editIdInput.value = '';
        resetForm();
    }

    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';

    // Focus on name input
    setTimeout(() => document.getElementById('auto-name').focus(), 100);
}

function closeModal() {
    const modal = document.getElementById('automation-modal');
    modal.style.display = 'none';
    document.body.style.overflow = '';
}

function resetForm() {
    document.getElementById('auto-name').value = '';
    keywords = [];
    renderKeywords();
    actionSteps = [{ type: 'send_private_reply', text: '' }];
    actionCounter = 1;
    renderActions();

    // Reset trigger type
    document.querySelectorAll('input[name="trigger_type"]').forEach(r => {
        r.checked = r.value === 'comment_keyword';
    });
    updateTriggerUI();

    // Reset media target selection
    const optAll = document.getElementById('media-opt-all');
    if (optAll) {
        optAll.querySelector('input').checked = true;
    }
    const mediaIdInput = document.getElementById('selected-media-id');
    if (mediaIdInput) {
        mediaIdInput.value = '';
    }
    toggleMediaTargetUI();
}

// Close modal on overlay click
document.addEventListener('click', (e) => {
    if (e.target.id === 'automation-modal') {
        closeModal();
    }
});

// Close modal on Escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
});

// ============ Trigger Type Selection ============
document.querySelectorAll('input[name="trigger_type"]').forEach(radio => {
    radio.addEventListener('change', updateTriggerUI);
});

function updateTriggerUI() {
    let selectedTrigger = 'comment_keyword';
    document.querySelectorAll('.trigger-option').forEach(opt => {
        const input = opt.querySelector('input');
        if (input.checked) {
            opt.classList.add('selected');
            selectedTrigger = input.value;
        } else {
            opt.classList.remove('selected');
        }
    });

    const mediaTargetGroup = document.getElementById('media-target-group');
    if (mediaTargetGroup) {
        if (selectedTrigger === 'comment_keyword') {
            mediaTargetGroup.style.display = 'block';
        } else {
            mediaTargetGroup.style.display = 'none';
            // Reset selection when changing away
            const optAll = document.getElementById('media-opt-all');
            if (optAll) optAll.querySelector('input').checked = true;
            toggleMediaTargetUI();
        }
    }
}

// ============ Media Target Selection Grid Helpers ============
let mediaLoaded = false;
let userMedia = [];

function toggleMediaTargetUI() {
    const isSpecific = document.querySelector('input[name="media_target_type"]:checked').value === 'specific';
    const container = document.getElementById('media-select-container');
    
    // Toggle active state classes for UI styling
    document.querySelectorAll('.media-target-option').forEach(opt => {
        const r = opt.querySelector('input');
        if (r.checked) {
            opt.classList.add('selected');
        } else {
            opt.classList.remove('selected');
        }
    });

    if (isSpecific) {
        container.style.display = 'block';
        if (!mediaLoaded) {
            fetchUserMedia();
        }
    } else {
        container.style.display = 'none';
    }
}

async function fetchUserMedia() {
    const loadingEl = document.getElementById('media-grid-loading');
    const gridEl = document.getElementById('media-grid');
    
    loadingEl.style.display = 'block';
    gridEl.style.display = 'none';
    
    try {
        const resp = await fetch('/ig/api/media');
        const data = await resp.json();
        
        loadingEl.style.display = 'none';
        
        if (Array.isArray(data) && data.length > 0) {
            userMedia = data;
            gridEl.innerHTML = data.map(item => {
                const imgUrl = item.thumbnail_url || item.media_url || '/ig/static/images/post_placeholder.png';
                const caption = escapeHtml(item.caption || 'No caption');
                const typeLabel = item.media_type === 'VIDEO' ? 'REEL' : item.media_type;
                const isSelected = document.getElementById('selected-media-id').value === item.id;
                
                return `
                    <div class="media-grid-item ${isSelected ? 'active' : ''}" data-id="${item.id}" onclick="selectMediaItem('${item.id}')" title="${caption}">
                        <img src="${imgUrl}" alt="Instagram Post">
                        <div class="media-grid-item-badge">${typeLabel}</div>
                        <div class="media-grid-item-overlay">
                            <div class="media-grid-item-caption">${caption}</div>
                        </div>
                        <div class="media-grid-item-check">✓</div>
                    </div>
                `;
            }).join('');
            gridEl.style.display = 'grid';
            mediaLoaded = true;
        } else {
            gridEl.innerHTML = `<div style="grid-column: span 3; text-align: center; color: var(--text-muted); padding: 2rem 0;">No posts or Reels found on this account.</div>`;
            gridEl.style.display = 'block';
        }
    } catch (err) {
        loadingEl.style.display = 'none';
        gridEl.innerHTML = `<div style="grid-column: span 3; text-align: center; color: var(--danger); padding: 2rem 0;">Failed to load media: ${escapeHtml(err.message)}</div>`;
        gridEl.style.display = 'block';
    }
}

function selectMediaItem(mediaId) {
    document.getElementById('selected-media-id').value = mediaId;
    
    // Highlight selection in UI
    document.querySelectorAll('.media-grid-item').forEach(item => {
        if (item.getAttribute('data-id') === mediaId) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });
}

// ============ Keywords Input ============
function handleKeywordInput(event) {
    if (event.key === 'Enter' || event.key === ',') {
        event.preventDefault();
        const input = event.target;
        const value = input.value.trim().replace(/,/g, '');

        if (value && !keywords.includes(value.toUpperCase())) {
            keywords.push(value.toUpperCase());
            renderKeywords();
        }
        input.value = '';
    }
}

function renderKeywords() {
    const container = document.getElementById('keywords-tags');
    if (!container) return;
    container.innerHTML = keywords.map((kw, i) =>
        `<span class="keyword-tag">
            ${escapeHtml(kw)}
            <span class="keyword-tag-remove" onclick="removeKeyword(${i})">×</span>
        </span>`
    ).join('');
}

function removeKeyword(index) {
    keywords.splice(index, 1);
    renderKeywords();
}

// ============ Action Steps Builder ============
function renderActions() {
    const container = document.getElementById('actions-builder');
    if (!container) return;

    container.innerHTML = actionSteps.map((action, i) => {
        const num = i + 1;
        let bodyHtml = '';

        if (action.type === 'add_tag') {
            bodyHtml = `
                <input type="text" class="form-input" id="action-text-${i}" 
                       placeholder="Tag name (e.g. interested, vip)" 
                       value="${escapeHtml(action.tag || '')}">
            `;
        } else if (action.type === 'send_button_template') {
            const buttons = action.buttons || [];
            let buttonsHtml = buttons.map((btn, btnIdx) => `
                <div class="builder-element-row button-row-${i}" data-index="${btnIdx}" style="margin-top: 0.25rem;">
                    <input type="text" class="form-input btn-title" placeholder="Button text" 
                           value="${escapeHtml(btn.title || '')}" 
                           oninput="updateButtonData(${i}, ${btnIdx}, 'title', this.value)">
                    <select class="form-select btn-type" 
                            onchange="updateButtonData(${i}, ${btnIdx}, 'type', this.value)">
                        <option value="web_url" ${btn.type === 'web_url' ? 'selected' : ''}>Open URL</option>
                        <option value="postback" ${btn.type === 'postback' ? 'selected' : ''}>Trigger Flow</option>
                    </select>
                    <input type="text" class="form-input btn-value" 
                           placeholder="${btn.type === 'web_url' ? 'URL (https://...)' : 'Automation ID (e.g. 5)'}" 
                           value="${escapeHtml(btn.type === 'web_url' ? (btn.url || '') : (btn.payload || '').replace('TRIGGER_AUTO_', ''))}" 
                           oninput="updateButtonData(${i}, ${btnIdx}, '${btn.type === 'web_url' ? 'url' : 'payload'}', this.value)">
                    <button type="button" class="builder-remove-btn" onclick="removeButton(${i}, ${btnIdx})">✕</button>
                </div>
            `).join('');

            bodyHtml = `
                <textarea class="form-textarea" id="action-text-${i}" 
                          placeholder="Check out these options:" 
                          rows="3">${escapeHtml(action.text || '')}</textarea>
                <div class="builder-subfield-group">
                    <div class="builder-subfield-title">
                        <span>Buttons (max 3)</span>
                        ${buttons.length < 3 ? `<button type="button" class="btn-builder-add" onclick="addButton(${i})">+ Add Button</button>` : ''}
                    </div>
                    <div class="builder-elements-list" id="buttons-list-${i}">
                        ${buttonsHtml || '<div class="pane-loading" style="height:auto;padding:0.5rem 0;">No buttons added yet</div>'}
                    </div>
                </div>
            `;
        } else if (action.type === 'send_quick_replies') {
            const replies = action.replies || [];
            let repliesHtml = replies.map((rep, repIdx) => `
                <div class="builder-element-row quick-reply-row quick-reply-row-${i}" data-index="${repIdx}" style="margin-top: 0.25rem;">
                    <input type="text" class="form-input rep-title" placeholder="Reply option text" 
                           value="${escapeHtml(rep.title || '')}" 
                           oninput="updateReplyData(${i}, ${repIdx}, 'title', this.value)">
                    <input type="text" class="form-input rep-value" 
                           placeholder="Automation ID to trigger" 
                           value="${escapeHtml((rep.payload || '').replace('TRIGGER_AUTO_', ''))}" 
                           oninput="updateReplyData(${i}, ${repIdx}, 'payload', this.value)">
                    <button type="button" class="builder-remove-btn" onclick="removeReply(${i}, ${repIdx})">✕</button>
                </div>
            `).join('');

            bodyHtml = `
                <textarea class="form-textarea" id="action-text-${i}" 
                          placeholder="Select an option below:" 
                          rows="3">${escapeHtml(action.text || '')}</textarea>
                <div class="builder-subfield-group">
                    <div class="builder-subfield-title">
                        <span>Quick Replies (max 13)</span>
                        ${replies.length < 13 ? `<button type="button" class="btn-builder-add" onclick="addReply(${i})">+ Add Quick Reply</button>` : ''}
                    </div>
                    <div class="builder-elements-list" id="replies-list-${i}">
                        ${repliesHtml || '<div class="pane-loading" style="height:auto;padding:0.5rem 0;">No quick replies added yet</div>'}
                    </div>
                </div>
            `;
        } else {
            bodyHtml = `
                <textarea class="form-textarea" id="action-text-${i}" 
                          placeholder="${getPlaceholder(action.type)}" 
                          rows="3">${escapeHtml(action.text || '')}</textarea>
                <span class="form-hint">Use {{username}} to insert the commenter's name</span>
            `;
        }

        return `
            <div class="action-step" data-index="${i}" id="action-step-${i}">
                <div class="action-step-header">
                    <span class="action-step-number">${num}</span>
                    <select class="form-select action-type-select" 
                            onchange="actionTypeChanged(${i}, this.value)" 
                            id="action-type-${i}">
                        <option value="send_private_reply" ${action.type === 'send_private_reply' ? 'selected' : ''}>📨 Private Reply (DM from comment)</option>
                        <option value="send_text" ${action.type === 'send_text' ? 'selected' : ''}>💬 Send Text Message</option>
                        <option value="send_button_template" ${action.type === 'send_button_template' ? 'selected' : ''}>🔘 Send Button Template</option>
                        <option value="send_quick_replies" ${action.type === 'send_quick_replies' ? 'selected' : ''}>⚡ Send Quick Replies</option>
                        <option value="add_tag" ${action.type === 'add_tag' ? 'selected' : ''}>🏷️ Add Tag</option>
                    </select>
                    <button type="button" class="btn-remove-action" onclick="removeAction(${i})" title="Remove step">✕</button>
                </div>
                <div class="action-step-body" id="action-body-${i}">
                    ${bodyHtml}
                </div>
            </div>
        `;
    }).join('');
}

function getPlaceholder(type) {
    switch (type) {
        case 'send_private_reply':
            return 'Hey {{username}}! Here\'s the link you asked for 🔗\n\nhttps://your-link.com';
        case 'send_text':
            return 'Thanks for reaching out! Here\'s more info...';
        case 'send_button_template':
            return 'Check out these options:';
        case 'send_quick_replies':
            return 'Pick an option:';
        default:
            return 'Enter your message...';
    }
}

function actionTypeChanged(index, newType) {
    // Save current text before changing type
    const textEl = document.getElementById(`action-text-${index}`);
    const currentText = textEl ? textEl.value : '';

    actionSteps[index].type = newType;
    
    // Clear and build clean objects
    if (newType === 'add_tag') {
        actionSteps[index].tag = currentText;
        delete actionSteps[index].text;
        delete actionSteps[index].buttons;
        delete actionSteps[index].replies;
    } else if (newType === 'send_button_template') {
        actionSteps[index].text = currentText;
        actionSteps[index].buttons = [];
        delete actionSteps[index].tag;
        delete actionSteps[index].replies;
    } else if (newType === 'send_quick_replies') {
        actionSteps[index].text = currentText;
        actionSteps[index].replies = [];
        delete actionSteps[index].tag;
        delete actionSteps[index].buttons;
    } else {
        actionSteps[index].text = currentText;
        delete actionSteps[index].tag;
        delete actionSteps[index].buttons;
        delete actionSteps[index].replies;
    }

    renderActions();
}

function addAction() {
    actionSteps.push({ type: 'send_text', text: '' });
    actionCounter++;
    renderActions();

    // Scroll to new action
    const newStep = document.getElementById(`action-step-${actionSteps.length - 1}`);
    if (newStep) newStep.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function removeAction(index) {
    if (actionSteps.length <= 1) {
        showToast('You need at least one action', 'error');
        return;
    }
    actionSteps.splice(index, 1);
    renderActions();
}

// ============ Button/Reply Builder UI State modifiers ============
function addButton(actionIdx) {
    if (!actionSteps[actionIdx].buttons) {
        actionSteps[actionIdx].buttons = [];
    }
    if (actionSteps[actionIdx].buttons.length >= 3) return;
    actionSteps[actionIdx].buttons.push({ type: 'web_url', title: '', url: '' });
    renderActions();
}

function removeButton(actionIdx, btnIdx) {
    actionSteps[actionIdx].buttons.splice(btnIdx, 1);
    renderActions();
}

function updateButtonData(actionIdx, btnIdx, field, value) {
    const btn = actionSteps[actionIdx].buttons[btnIdx];
    if (field === 'type') {
        btn.type = value;
        if (value === 'web_url') {
            btn.url = '';
            delete btn.payload;
        } else {
            btn.payload = '';
            delete btn.url;
        }
    } else if (field === 'title') {
        btn.title = value;
    } else if (field === 'url') {
        btn.url = value;
    } else if (field === 'payload') {
        btn.payload = value.startsWith('TRIGGER_AUTO_') ? value : 'TRIGGER_AUTO_' + value;
    }
    // Update direct state, no need to trigger full re-render on input keypress (to avoid cursor jump)
}

function addReply(actionIdx) {
    if (!actionSteps[actionIdx].replies) {
        actionSteps[actionIdx].replies = [];
    }
    if (actionSteps[actionIdx].replies.length >= 13) return;
    actionSteps[actionIdx].replies.push({ content_type: 'text', title: '', payload: '' });
    renderActions();
}

function removeReply(actionIdx, repIdx) {
    actionSteps[actionIdx].replies.splice(repIdx, 1);
    renderActions();
}

function updateReplyData(actionIdx, repIdx, field, value) {
    const rep = actionSteps[actionIdx].replies[repIdx];
    if (field === 'title') {
        rep.title = value;
    } else if (field === 'payload') {
        rep.payload = value.startsWith('TRIGGER_AUTO_') ? value : 'TRIGGER_AUTO_' + value;
    }
}

// ============ CRUD Operations ============
async function saveAutomation() {
    const editId = document.getElementById('edit-automation-id').value;
    const name = document.getElementById('auto-name').value.trim();
    const triggerType = document.querySelector('input[name="trigger_type"]:checked').value;

    if (!name) {
        showToast('Please enter an automation name', 'error');
        return;
    }

    if (keywords.length === 0) {
        showToast('Please add at least one keyword', 'error');
        return;
    }

    // Collect action data from the DOM/state
    const actions = actionSteps.map((action, i) => {
        const textEl = document.getElementById(`action-text-${i}`);
        const text = textEl ? textEl.value.trim() : '';

        if (action.type === 'add_tag') {
            return { type: 'add_tag', tag: text };
        }
        
        const res = { type: action.type, text: text };
        if (action.type === 'send_button_template') {
            res.buttons = action.buttons || [];
        } else if (action.type === 'send_quick_replies') {
            res.replies = action.replies || [];
        }
        return res;
    }).filter(a => (a.text || a.tag || a.type === 'send_button_template' || a.type === 'send_quick_replies'));

    if (actions.length === 0) {
        showToast('Please add at least one action with content', 'error');
        return;
    }

    let triggerConfig = { keywords: keywords };
    if (triggerType === 'comment_keyword') {
        const targetType = document.querySelector('input[name="media_target_type"]:checked').value;
        if (targetType === 'specific') {
            const mediaId = document.getElementById('selected-media-id').value;
            if (!mediaId) {
                showToast('Please select a specific post or Reel', 'error');
                return;
            }
            triggerConfig.media_id = mediaId;
        }
    }

    const payload = {
        name: name,
        trigger_type: triggerType,
        trigger_config: triggerConfig,
        actions: actions,
        is_active: true
    };

    try {
        const url = editId
            ? `/ig/api/automations/${editId}`
            : '/ig/api/automations';
        const method = editId ? 'PUT' : 'POST';

        const resp = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await resp.json();

        if (data.success || data.automation) {
            showToast(editId ? 'Automation updated!' : 'Automation created!', 'success');
            closeModal();
            setTimeout(() => location.reload(), 500);
        } else {
            showToast(data.error || 'Something went wrong', 'error');
        }
    } catch (err) {
        showToast('Network error: ' + err.message, 'error');
    }
}

async function toggleAutomation(id, isActive) {
    try {
        const resp = await fetch(`/ig/api/automations/${id}/toggle`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await resp.json();
        if (data.success) {
            showToast(data.is_active ? 'Automation activated' : 'Automation paused', 'success');
        } else {
            showToast(data.error || 'Failed to toggle', 'error');
        }
    } catch (err) {
        showToast('Network error: ' + err.message, 'error');
    }
}

async function deleteAutomation(id) {
    if (!confirm('Are you sure you want to delete this automation? This cannot be undone.')) return;

    try {
        const resp = await fetch(`/ig/api/automations/${id}`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await resp.json();
        if (data.success) {
            showToast('Automation deleted', 'success');
            // Animate card removal
            const card = document.querySelector(`.automation-card[data-id="${id}"]`);
            if (card) {
                card.style.transition = 'all 0.3s ease';
                card.style.opacity = '0';
                card.style.transform = 'translateX(-20px)';
                setTimeout(() => card.remove(), 300);
            }
        } else {
            showToast(data.error || 'Failed to delete', 'error');
        }
    } catch (err) {
        showToast('Network error: ' + err.message, 'error');
    }
}

async function editAutomation(id) {
    try {
        const resp = await fetch(`/ig/api/automations/${id}`);
        const data = await resp.json();

        if (data.error) {
            showToast(data.error, 'error');
            return;
        }

        // Populate form
        document.getElementById('auto-name').value = data.name || '';

        // Set trigger type
        const triggerRadio = document.querySelector(`input[name="trigger_type"][value="${data.trigger_type}"]`);
        if (triggerRadio) {
            triggerRadio.checked = true;
            updateTriggerUI();
        }

        // Set keywords
        keywords = (data.trigger_config || {}).keywords || [];
        renderKeywords();

        // Set media target selection
        if (data.trigger_type === 'comment_keyword') {
            const mediaId = (data.trigger_config || {}).media_id;
            const targetGroup = document.getElementById('media-target-group');
            if (targetGroup) {
                targetGroup.style.display = 'block';
                if (mediaId) {
                    const specificRadio = document.getElementById('media-opt-specific');
                    if (specificRadio) specificRadio.querySelector('input').checked = true;
                    document.getElementById('selected-media-id').value = mediaId;
                } else {
                    const allRadio = document.getElementById('media-opt-all');
                    if (allRadio) allRadio.querySelector('input').checked = true;
                    document.getElementById('selected-media-id').value = '';
                }
                mediaLoaded = false; // Reset to force re-fetch and render with selected highlight
                toggleMediaTargetUI();
            }
        }

        // Set actions
        actionSteps = (data.actions || []).map(a => ({ ...a }));
        if (actionSteps.length === 0) {
            actionSteps = [{ type: 'send_private_reply', text: '' }];
        }
        renderActions();

        // Populate values in UI
        setTimeout(() => {
            actionSteps.forEach((action, i) => {
                const textEl = document.getElementById(`action-text-${i}`);
                if (textEl) {
                    textEl.value = action.text || action.tag || '';
                }
            });
        }, 50);

        openModal(id);
    } catch (err) {
        showToast('Failed to load automation: ' + err.message, 'error');
    }
}

// ============ Toast Notifications ============
function showToast(message, type = 'success') {
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.transition = 'all 0.3s ease';
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(30px)';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ============ Live Chat Inbox Implementation ============

function initInbox(activeConvoId) {
    loadConversations(activeConvoId);
    
    // Poll active conversations list every 8 seconds
    if (inboxPollingInterval) clearInterval(inboxPollingInterval);
    inboxPollingInterval = setInterval(() => loadConversations(null, true), 8000);
}

async function loadConversations(selectConvoId = null, isPoll = false) {
    try {
        const resp = await fetch('/ig/api/inbox');
        const data = await resp.json();
        conversations = data;

        renderConversationList(isPoll);

        if (selectConvoId) {
            selectConversation(selectConvoId);
        } else if (!isPoll && conversations.length > 0 && !activeConvo) {
            // Auto-select first convo on load if none selected
            selectConversation(conversations[0].id);
        }
    } catch (err) {
        console.error('Error loading conversations:', err);
    }
}

function renderConversationList(isPoll = false) {
    const listContainer = document.getElementById('thread-list');
    if (!listContainer) return;

    if (conversations.length === 0) {
        listContainer.innerHTML = `
            <div class="empty-state" style="padding: 2rem 1rem;">
                <span class="empty-icon">📥</span>
                <h3>No DMs yet</h3>
                <p>Conversations will appear here when users interact.</p>
            </div>
        `;
        return;
    }

    // Keep scroll position if it's a background poll
    const scrollTop = listContainer.scrollTop;

    listContainer.innerHTML = conversations.map(convo => {
        const isActive = activeConvo && activeConvo.id === convo.id;
        const lastMsg = convo.last_message;
        let lastMsgText = 'No messages';
        if (lastMsg) {
            if (lastMsg.message_type === 'text') lastMsgText = lastMsg.content.text || '';
            else if (lastMsg.message_type === 'image') lastMsgText = '📷 Sent an image';
            else if (lastMsg.message_type === 'button_template') lastMsgText = '🔘 Sent button menu';
            else if (lastMsg.message_type === 'quick_reply') lastMsgText = '⚡ Sent quick replies';
            else if (lastMsg.message_type === 'private_reply') lastMsgText = '📨 Comment reply';
        }

        const isWindowOpen = convo.is_window_open;
        const lastMsgTime = lastMsg && lastMsg.sent_at ? formatTime(lastMsg.sent_at) : '';

        return `
            <div class="thread-card ${isActive ? 'active' : ''}" onclick="selectConversation(${convo.id})" data-id="${convo.id}">
                <div class="user-avatar user-avatar-sm">${(convo.contact.username || 'C')[0].toUpperCase()}</div>
                <div class="thread-card-content">
                    <div class="thread-card-header">
                        <span class="thread-username">@${escapeHtml(convo.contact.username || convo.contact.igsid.slice(0, 12))}</span>
                        <span class="thread-time">${lastMsgTime}</span>
                    </div>
                    <div class="thread-card-body">
                        <span class="thread-preview">${escapeHtml(lastMsgText)}</span>
                        <span class="thread-window-indicator ${isWindowOpen ? 'thread-window-open' : 'thread-window-closed'}" title="${isWindowOpen ? '24h messaging window is OPEN' : '24h messaging window is CLOSED'}"></span>
                    </div>
                </div>
            </div>
        `;
    }).join('');

    if (isPoll) {
        listContainer.scrollTop = scrollTop;
    }
}

function selectConversation(convoId) {
    const convo = conversations.find(c => c.id === convoId);
    if (!convo) return;

    activeConvo = convo;

    // Highlight selected card in DOM
    document.querySelectorAll('.thread-card').forEach(card => {
        if (parseInt(card.dataset.id) === convoId) {
            card.classList.add('active');
        } else {
            card.classList.remove('active');
        }
    });

    // Toggle layouts for mobile view
    const leftPane = document.querySelector('.inbox-left-pane');
    const middlePane = document.querySelector('.inbox-middle-pane');
    if (window.innerWidth <= 768) {
        if (leftPane) leftPane.style.display = 'none';
        if (middlePane) middlePane.style.display = 'flex';
    }

    // Show active chat layout
    const noChat = document.getElementById('no-chat-selected');
    const activeChat = document.getElementById('active-chat-container');
    if (noChat) noChat.style.display = 'none';
    if (activeChat) activeChat.style.display = 'flex';

    // Set header details
    const headerAvatar = document.getElementById('chat-header-avatar');
    const headerUsername = document.getElementById('chat-header-username');
    if (headerAvatar) headerAvatar.textContent = (convo.contact.username || 'C')[0].toUpperCase();
    if (headerUsername) headerUsername.textContent = '@' + (convo.contact.username || convo.contact.igsid);
    
    // Set 24h countdown window
    if (windowCountdownInterval) clearInterval(windowCountdownInterval);
    updateCountdown(convo.window_expires_at);
    windowCountdownInterval = setInterval(() => updateCountdown(convo.window_expires_at), 15000);

    // Setup mobile Back button
    const headerUser = document.querySelector('.chat-header-user');
    if (headerUser) {
        const existingBack = headerUser.querySelector('.btn-back-inbox');
        if (window.innerWidth <= 768) {
            if (!existingBack) {
                const btn = document.createElement('button');
                btn.className = 'btn btn-ghost btn-sm btn-back-inbox';
                btn.style.marginRight = '0.5rem';
                btn.style.padding = '0.25rem 0.5rem';
                btn.style.fontSize = '0.75rem';
                btn.innerHTML = '⬅ Back';
                btn.onclick = goBackToThreadList;
                headerUser.insertBefore(btn, headerUser.firstChild);
            }
        } else {
            if (existingBack) existingBack.remove();
        }
    }

    // Load message timeline
    loadMessages(convoId);

    // Poll messages every 4 seconds
    if (messagePollingInterval) clearInterval(messagePollingInterval);
    messagePollingInterval = setInterval(() => loadMessages(convoId, true), 4000);

    // Show details pane
    showDetailsPane(convo.contact);
}

function goBackToThreadList() {
    const leftPane = document.querySelector('.inbox-left-pane');
    const middlePane = document.querySelector('.inbox-middle-pane');
    if (leftPane) leftPane.style.display = 'block';
    if (middlePane) middlePane.style.display = 'none';
    activeConvo = null;
    if (messagePollingInterval) clearInterval(messagePollingInterval);
}

async function loadMessages(convoId, isPoll = false) {
    if (!activeConvo || activeConvo.id !== convoId) return;
    try {
        const resp = await fetch(`/ig/api/inbox/${convoId}/messages`);
        const messages = await resp.json();

        const container = document.getElementById('chat-messages-container');
        if (!container) return;

        // Check if there are new messages before re-rendering
        const currentMsgCount = container.querySelectorAll('.message-wrapper').length;
        if (isPoll && currentMsgCount === messages.length) {
            return; // No new messages, skip re-render
        }

        container.innerHTML = messages.map(msg => {
            const isOutgoing = msg.direction === 'outgoing';
            const body = msg.content || {};
            
            let bubbleContent = '';
            let isPrivateReply = msg.message_type === 'private_reply';

            if (msg.message_type === 'text' || isPrivateReply) {
                bubbleContent = `<div class="message-text">${escapeHtml(body.text || '')}</div>`;
            } else if (msg.message_type === 'image') {
                bubbleContent = `<img src="${escapeHtml(body.url || '')}" alt="Image" style="max-width: 100%; border-radius: var(--radius-sm);">`;
            } else if (msg.message_type === 'button_template') {
                const buttons = body.buttons || [];
                const buttonsHtml = buttons.map(b => `
                    <div class="chat-bubble-button ${b.type === 'web_url' ? 'link-button' : ''}">
                        ${escapeHtml(b.title || '')}
                        ${b.type === 'web_url' ? ' 🔗' : ''}
                    </div>
                `).join('');
                bubbleContent = `
                    <div class="message-text">${escapeHtml(body.text || '')}</div>
                    <div class="message-buttons-container">${buttonsHtml}</div>
                `;
            } else if (msg.message_type === 'quick_reply') {
                const replies = body.replies || [];
                const repliesHtml = replies.map(r => `
                    <div class="chat-bubble-quick-reply">${escapeHtml(r.title || '')}</div>
                `).join('');
                bubbleContent = `
                    <div class="message-text">${escapeHtml(body.text || '')}</div>
                    <div class="message-quick-replies-container">${repliesHtml}</div>
                `;
            }

            const timeStr = msg.sent_at ? new Date(msg.sent_at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }) : '';
            const bubbleClass = isPrivateReply ? 'message-bubble message-bubble-private-reply' : 'message-bubble';
            const commentInfoHtml = isPrivateReply ? `
                <div class="message-bubble-comment-info">
                    💬 Private reply to comment
                </div>
            ` : '';

            return `
                <div class="message-wrapper ${msg.direction}">
                    ${commentInfoHtml}
                    <div class="${bubbleClass}">
                        ${bubbleContent}
                    </div>
                    <span class="message-meta">${timeStr}</span>
                </div>
            `;
        }).join('');

        // Scroll to bottom
        container.scrollTop = container.scrollHeight;
    } catch (err) {
        console.error('Error loading messages:', err);
    }
}

async function handleSendMessage(e) {
    if (e) e.preventDefault();
    if (!activeConvo) return;

    const textarea = document.getElementById('composer-textarea');
    const btn = document.getElementById('btn-send-message');
    if (!textarea) return;
    const text = textarea.value.trim();
    if (!text) return;

    // Temporarily disable input
    textarea.disabled = true;
    if (btn) btn.disabled = true;

    try {
        const resp = await fetch(`/ig/api/inbox/${activeConvo.id}/send`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text })
        });
        const data = await resp.json();

        if (data.success) {
            textarea.value = '';
            // Load messages instantly
            await loadMessages(activeConvo.id);
            // Refresh conversation list to show last message preview
            loadConversations(null, true);
        } else {
            alert(data.error || 'Failed to send message');
        }
    } catch (err) {
        alert('Error sending message: ' + err.message);
    } finally {
        textarea.disabled = false;
        if (btn) btn.disabled = false;
        textarea.focus();
    }
}

function handleComposerKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSendMessage();
    }
}

function updateCountdown(windowExpiresAtStr) {
    const badge = document.getElementById('chat-window-badge');
    const countdown = document.getElementById('chat-header-countdown');
    const warning = document.getElementById('window-expired-warning');
    const textarea = document.getElementById('composer-textarea');
    const btn = document.getElementById('btn-send-message');

    if (!windowExpiresAtStr) {
        if (badge) {
            badge.className = 'badge badge-inactive';
            badge.textContent = 'Window Closed';
        }
        if (countdown) {
            countdown.className = 'chat-header-timer window-closed';
            countdown.textContent = 'Window closed';
        }
        if (warning) warning.style.display = 'block';
        if (textarea) textarea.disabled = true;
        if (btn) btn.disabled = true;
        return;
    }

    const expires = new Date(windowExpiresAtStr);
    const now = new Date();
    const remaining = expires - now;

    if (remaining <= 0) {
        if (badge) {
            badge.className = 'badge badge-inactive';
            badge.textContent = 'Window Closed';
        }
        if (countdown) {
            countdown.className = 'chat-header-timer window-closed';
            countdown.textContent = 'Window closed';
        }
        if (warning) warning.style.display = 'block';
        if (textarea) textarea.disabled = true;
        if (btn) btn.disabled = true;
    } else {
        if (badge) {
            badge.className = 'badge badge-active';
            badge.textContent = 'Window Open';
        }
        if (countdown) {
            countdown.className = 'chat-header-timer window-open';
        }
        
        const hours = Math.floor(remaining / (1000 * 60 * 60));
        const minutes = Math.floor((remaining % (1000 * 60 * 60)) / (1000 * 60));
        if (countdown) countdown.textContent = `Expires in ${hours}h ${minutes}m`;
        
        if (warning) warning.style.display = 'none';
        if (textarea) textarea.disabled = false;
        if (btn) btn.disabled = false;
    }
}

// Right Details Pane Tag Management
let currentDetailsTags = [];
let currentDetailsContactId = null;

function showDetailsPane(contact) {
    const pane = document.getElementById('contact-details-pane');
    if (!pane) return;

    pane.style.visibility = 'visible';
    currentDetailsContactId = contact.id;

    // Fill fields
    const avatar = document.getElementById('details-avatar');
    const userDisplay = document.getElementById('details-username');
    const igsid = document.getElementById('details-igsid');
    const email = document.getElementById('details-email');
    const phone = document.getElementById('details-phone');

    if (avatar) avatar.textContent = (contact.username || 'C')[0].toUpperCase();
    if (userDisplay) userDisplay.textContent = '@' + (contact.username || contact.igsid);
    if (igsid) igsid.textContent = 'IGSID: ' + contact.igsid;
    if (email) email.value = contact.email || '';
    if (phone) phone.value = contact.phone || '';
    
    // Fill tags
    currentDetailsTags = [...(contact.tags || [])];
    renderDetailsTags();

    // Fill custom fields json representation
    const jsonPre = document.getElementById('details-custom-fields-json');
    if (jsonPre) jsonPre.textContent = JSON.stringify(contact.custom_fields || {}, null, 2);
}

function renderDetailsTags() {
    const container = document.getElementById('details-tags-container');
    if (!container) return;
    
    container.innerHTML = currentDetailsTags.map((tag, idx) => `
        <span class="keyword-tag">
            ${escapeHtml(tag)}
            <span class="keyword-tag-remove" onclick="removeDetailsTag(${idx})">×</span>
        </span>
    `).join('');
}

function handleDetailsTagInput(e) {
    if (e.key === 'Enter' || e.key === ',') {
        e.preventDefault();
        const val = e.target.value.trim().toUpperCase();
        if (val && !currentDetailsTags.includes(val)) {
            currentDetailsTags.push(val);
            renderDetailsTags();
            saveDetailsContactChanges();
        }
        e.target.value = '';
    }
}

function removeDetailsTag(idx) {
    currentDetailsTags.splice(idx, 1);
    renderDetailsTags();
    saveDetailsContactChanges();
}

function handleSaveContactDetails(e) {
    if (e) e.preventDefault();
    saveDetailsContactChanges();
}

async function saveDetailsContactChanges() {
    if (!currentDetailsContactId) return;

    const email = document.getElementById('details-email').value;
    const phone = document.getElementById('details-phone').value;

    const payload = {
        email: email,
        phone: phone,
        tags: currentDetailsTags
    };

    try {
        const resp = await fetch(`/ig/api/contacts/${currentDetailsContactId}/update`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await resp.json();
        if (data.success) {
            // Update local memory of conversation contact
            if (activeConvo && activeConvo.contact.id === currentDetailsContactId) {
                activeConvo.contact.email = data.contact.email;
                activeConvo.contact.phone = data.contact.phone;
                activeConvo.contact.tags = data.contact.tags;
            }
            // Reload contacts lists in background
            loadConversations(null, true);
        } else {
            console.error('Failed to update contact:', data.error);
        }
    } catch (err) {
        console.error('Error updating contact:', err);
    }
}

function filterConversations() {
    const searchInput = document.getElementById('inbox-search');
    if (!searchInput) return;
    const query = searchInput.value.toLowerCase().trim();
    document.querySelectorAll('#thread-list .thread-card').forEach(card => {
        const username = card.querySelector('.thread-username').textContent.toLowerCase();
        if (username.includes(query)) {
            card.style.display = 'flex';
        } else {
            card.style.display = 'none';
        }
    });
}

// ============ Utility ============
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatTime(isoStr) {
    if (!isoStr) return '';
    try {
        const date = new Date(isoStr);
        const now = new Date();
        const diffMs = now - date;
        const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
        
        if (diffDays > 0) {
            return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
        }
        
        return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    } catch (e) {
        return '';
    }
}
