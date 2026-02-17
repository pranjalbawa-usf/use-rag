/**
 * RAG Document Assistant - Frontend
 * ==================================
 * Handles page navigation, document uploads, chat interactions, and UI updates.
 */

// ============================================
// DOM Elements
// ============================================
const fileInputs = document.querySelectorAll('input[type="file"]');
const uploadProgressContainer = document.getElementById('upload-progress-container');
const documentList = document.getElementById('document-list');
const chatMessages = document.getElementById('chat-messages');
const questionInput = document.getElementById('question-input');
const sendButton = document.getElementById('send-button');
const uploadArea = document.getElementById('upload-area');
const emptyState = document.getElementById('empty-state');

// Stats elements
const statDocs = document.getElementById('stat-docs');
const statChunks = document.getElementById('stat-chunks');
const docCount = document.getElementById('doc-count');
const chunkCount = document.getElementById('chunk-count');
const settingsDocs = document.getElementById('settings-docs');
const settingsChunks = document.getElementById('settings-chunks');

// ============================================
// Constants
// ============================================
const MAX_FILE_SIZE = 10 * 1024 * 1024;
const MAX_FILES = 10;
const ALLOWED_TYPES = ['.txt', '.pdf', '.md', '.docx', '.xlsx', '.csv', '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'];

// ============================================
// State
// ============================================
let isLoading = false;
let currentPage = 'overview';
let chatUploadedFiles = []; // Track files uploaded via chat
let currentUser = null;
let authToken = null;

// Auth service URL
const AUTH_URL = 'http://localhost:8001';

// ============================================
// Initialization
// ============================================
document.addEventListener('DOMContentLoaded', () => {
    checkAuth();
    loadDocuments();
    loadStats();
    setupNavigation();
    setupFileUpload();
    setupChat();
    setupDragAndDrop();
    setupChatFileUpload();
    setupPreviewModal();
    setupAdmin();
    setupDeleteAll();
    setupUserProfile();
});

// ============================================
// Authentication
// ============================================
function checkAuth() {
    authToken = localStorage.getItem('auth_token');
    const userStr = localStorage.getItem('user');
    
    if (authToken && userStr) {
        try {
            currentUser = JSON.parse(userStr);
            updateUserDisplay();
        } catch (e) {
            logout();
        }
    }
}

function updateUserDisplay() {
    const userNameEl = document.querySelector('.user-name');
    const userEmailEl = document.querySelector('.user-email');
    const loginBtn = document.querySelector('.login-btn');
    const logoutBtn = document.querySelector('.logout-btn');
    
    if (currentUser) {
        if (userNameEl) userNameEl.textContent = currentUser.name;
        if (userEmailEl) userEmailEl.textContent = currentUser.email;
        if (loginBtn) loginBtn.style.display = 'none';
        if (logoutBtn) logoutBtn.style.display = 'flex';
    } else {
        if (userNameEl) userNameEl.textContent = 'Guest';
        if (userEmailEl) userEmailEl.textContent = 'Not logged in';
        if (loginBtn) loginBtn.style.display = 'flex';
        if (logoutBtn) logoutBtn.style.display = 'none';
    }
}

function logout() {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('user');
    currentUser = null;
    authToken = null;
    window.location.href = '/login';
}

// Make logout globally accessible
window.logout = logout;

function setupUserProfile() {
    const logoutBtn = document.querySelector('.logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', logout);
    }
}

// Get auth headers for API calls
function getAuthHeaders() {
    if (authToken) {
        return { 'Authorization': `Bearer ${authToken}` };
    }
    return {};
}

function setupDeleteAll() {
    const deleteAllBtn = document.getElementById('delete-all-docs');
    if (deleteAllBtn) {
        deleteAllBtn.addEventListener('click', deleteAllDocuments);
    }
}

// ============================================
// Page Navigation
// ============================================
function setupNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    const featureCards = document.querySelectorAll('.feature-card[data-page]');
    
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const page = item.dataset.page;
            if (page) navigateToPage(page);
        });
    });
    
    featureCards.forEach(card => {
        card.addEventListener('click', () => {
            const page = card.dataset.page;
            if (page) navigateToPage(page);
        });
    });
}

function navigateToPage(pageName) {
    // Update nav items
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.page === pageName);
    });
    
    // Update pages
    document.querySelectorAll('.page').forEach(page => {
        page.classList.toggle('active', page.id === `page-${pageName}`);
    });
    
    currentPage = pageName;
    
    // Load admin data when navigating to admin page
    if (pageName === 'admin') {
        loadAdminData();
    }
}

// ============================================
// File Upload
// ============================================
function setupFileUpload() {
    fileInputs.forEach(input => {
        input.addEventListener('change', handleFileUpload);
    });
    
    if (uploadArea) {
        uploadArea.addEventListener('click', () => {
            document.getElementById('file-input-docs')?.click();
        });
    }
}

function setupDragAndDrop() {
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        document.body.addEventListener(eventName, preventDefaults, false);
    });
    
    if (uploadArea) {
        ['dragenter', 'dragover'].forEach(eventName => {
            uploadArea.addEventListener(eventName, () => {
                uploadArea.classList.add('dragover');
            }, false);
        });
        
        ['dragleave', 'drop'].forEach(eventName => {
            uploadArea.addEventListener(eventName, () => {
                uploadArea.classList.remove('dragover');
            }, false);
        });
        
        uploadArea.addEventListener('drop', handleDrop, false);
    }
}

function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

function handleDrop(e) {
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        processFiles(Array.from(files));
    }
}

async function handleFileUpload(e) {
    const files = Array.from(e.target.files);
    if (files.length > 0) {
        await processFiles(files);
        e.target.value = '';
    }
}

async function processFiles(files) {
    const validFiles = files.filter(file => {
        const ext = '.' + file.name.split('.').pop().toLowerCase();
        if (!ALLOWED_TYPES.includes(ext)) {
            showToast(`${file.name}: Unsupported file type`, 'error');
            return false;
        }
        if (file.size > MAX_FILE_SIZE) {
            showToast(`${file.name}: File too large (max 10MB)`, 'error');
            return false;
        }
        return true;
    }).slice(0, MAX_FILES);
    
    if (validFiles.length === 0) return;
    
    // Show progress container
    uploadProgressContainer.classList.remove('hidden');
    uploadProgressContainer.innerHTML = validFiles.map((file, i) => `
        <div class="file-progress-item" id="progress-${i}">
            <div class="file-progress-header">
                <span class="file-progress-name">${file.name}</span>
                <span class="file-progress-status pending">Pending</span>
            </div>
            <div class="file-progress-bar">
                <div class="file-progress-fill" style="width: 0%"></div>
            </div>
        </div>
    `).join('');
    
    // Upload files sequentially
    for (let i = 0; i < validFiles.length; i++) {
        await uploadFile(validFiles[i], i);
    }
    
    // Refresh data
    await loadDocuments();
    await loadStats();
    
    // Hide progress after delay
    setTimeout(() => {
        uploadProgressContainer.classList.add('hidden');
    }, 2000);
}

async function uploadFile(file, index) {
    const progressItem = document.getElementById(`progress-${index}`);
    const statusEl = progressItem.querySelector('.file-progress-status');
    const fillEl = progressItem.querySelector('.file-progress-fill');
    
    statusEl.textContent = 'Uploading';
    statusEl.className = 'file-progress-status uploading';
    fillEl.style.width = '50%';
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            throw new Error('Upload failed');
        }
        
        // Register document with auth service if logged in
        if (authToken) {
            try {
                await fetch(`${AUTH_URL}/documents/register`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        ...getAuthHeaders()
                    },
                    body: JSON.stringify({ filename: file.name })
                });
            } catch (e) {
                console.log('Could not register document with auth service');
            }
        }
        
        fillEl.style.width = '100%';
        fillEl.classList.add('success');
        statusEl.textContent = 'Complete';
        statusEl.className = 'file-progress-status success';
        showToast(`${file.name} uploaded successfully`, 'success');
        
    } catch (error) {
        fillEl.style.width = '100%';
        fillEl.classList.add('error');
        statusEl.textContent = 'Failed';
        statusEl.className = 'file-progress-status error';
        showToast(`Failed to upload ${file.name}`, 'error');
    }
}

// ============================================
// Documents
// ============================================
async function loadDocuments() {
    try {
        // If logged in, get user's documents from auth service
        if (authToken && currentUser) {
            try {
                const isAdmin = currentUser.role === 'admin';
                const endpoint = isAdmin ? `${AUTH_URL}/documents/all` : `${AUTH_URL}/documents/my`;
                
                const authResponse = await fetch(endpoint, {
                    headers: getAuthHeaders()
                });
                
                if (authResponse.ok) {
                    const authData = await authResponse.json();
                    
                    if (isAdmin) {
                        // Admin sees all documents grouped by user
                        renderAdminDocumentList(authData);
                        return;
                    } else {
                        // Regular user sees only their documents
                        renderDocumentList(authData.documents || []);
                        return;
                    }
                }
            } catch (e) {
                console.log('Auth service unavailable, showing all documents');
            }
        }
        
        // Fallback: show all documents (guest mode or auth service down)
        const response = await fetch('/stats');
        const data = await response.json();
        renderDocumentList(data.documents);
    } catch (error) {
        console.error('Failed to load documents:', error);
    }
}

function renderAdminDocumentList(data) {
    if (!documentList) return;
    
    const users = data.users || [];
    
    if (users.length === 0) {
        if (emptyState) emptyState.style.display = 'block';
        documentList.innerHTML = '';
        return;
    }
    
    if (emptyState) emptyState.style.display = 'none';
    
    let html = '';
    
    for (const user of users) {
        html += `
            <div class="user-documents-section">
                <div class="user-header">
                    <div class="user-avatar-small">${user.user_name ? user.user_name.charAt(0).toUpperCase() : 'U'}</div>
                    <div class="user-info-small">
                        <span class="user-name-small">${user.user_name || 'Unknown User'}</span>
                        <span class="user-email-small">${user.user_email || ''}</span>
                    </div>
                    <span class="doc-count-badge">${user.count} docs</span>
                </div>
                <div class="user-docs-list">
        `;
        
        for (const doc of user.documents) {
            const ext = doc.split('.').pop().toLowerCase();
            const iconClass = ext === 'pdf' ? 'pdf' : 
                              ext === 'docx' ? 'docx' :
                              ext === 'xlsx' ? 'xlsx' :
                              ext === 'csv' ? 'csv' :
                              ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'].includes(ext) ? 'image' :
                              ext === 'md' ? 'md' : 'txt';
            
            html += `
                <div class="document-card">
                    <div class="document-icon ${iconClass}">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                            <polyline points="14 2 14 8 20 8"/>
                        </svg>
                    </div>
                    <div class="document-info">
                        <div class="document-name">${doc}</div>
                        <div class="document-meta">${ext.toUpperCase()} file</div>
                    </div>
                    <div class="document-actions">
                        <button class="preview-btn" onclick="previewDocument('${doc}')" title="Preview">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                                <circle cx="12" cy="12" r="3"/>
                            </svg>
                        </button>
                        <button class="delete-btn" onclick="deleteDocument('${doc}')" title="Delete">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="3 6 5 6 21 6"/>
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                            </svg>
                        </button>
                    </div>
                </div>
            `;
        }
        
        html += '</div></div>';
    }
    
    documentList.innerHTML = html;
}

function renderDocumentList(documents) {
    if (!documentList) return;
    
    if (documents.length === 0) {
        if (emptyState) emptyState.style.display = 'block';
        documentList.innerHTML = '';
        return;
    }
    
    if (emptyState) emptyState.style.display = 'none';
    
    documentList.innerHTML = documents.map(doc => {
        const ext = doc.split('.').pop().toLowerCase();
        const iconClass = ext === 'pdf' ? 'pdf' : 
                          ext === 'docx' ? 'docx' :
                          ext === 'xlsx' ? 'xlsx' :
                          ext === 'csv' ? 'csv' :
                          ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'].includes(ext) ? 'image' :
                          ext === 'md' ? 'md' : 'txt';
        
        return `
            <div class="document-card">
                <div class="document-icon ${iconClass}">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                        <polyline points="14 2 14 8 20 8"/>
                    </svg>
                </div>
                <div class="document-info">
                    <div class="document-name">${doc}</div>
                    <div class="document-meta">${ext.toUpperCase()} file</div>
                </div>
                <div class="document-actions">
                    <button class="preview-btn" onclick="previewDocument('${doc}')" title="Preview">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                            <circle cx="12" cy="12" r="3"/>
                        </svg>
                    </button>
                    <button class="delete-btn" onclick="deleteDocument('${doc}')" title="Delete">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="3 6 5 6 21 6"/>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                        </svg>
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

async function deleteDocument(filename) {
    if (!confirm(`Delete "${filename}"?`)) return;
    
    try {
        const response = await fetch(`/document/${encodeURIComponent(filename)}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showToast('Document deleted', 'success');
            await loadDocuments();
            await loadStats();
        } else {
            throw new Error('Delete failed');
        }
    } catch (error) {
        showToast('Failed to delete document', 'error');
    }
}

async function deleteAllDocuments() {
    const docCount = document.getElementById('doc-count')?.textContent || '0';
    if (!confirm(`Delete ALL ${docCount} documents? This cannot be undone.`)) return;
    
    try {
        const response = await fetch('/documents/all', {
            method: 'DELETE'
        });
        
        if (response.ok) {
            const data = await response.json();
            showToast(`Deleted ${data.files_deleted} documents`, 'success');
            await loadDocuments();
            await loadStats();
        } else {
            throw new Error('Delete all failed');
        }
    } catch (error) {
        showToast('Failed to delete documents', 'error');
    }
}

// ============================================
// Stats
// ============================================
async function loadStats() {
    try {
        const response = await fetch('/stats');
        const data = await response.json();
        
        const docs = data.documents.length;
        const chunks = data.total_chunks;
        
        // Update all stat displays
        if (statDocs) statDocs.textContent = docs;
        if (statChunks) statChunks.textContent = chunks;
        if (docCount) docCount.textContent = docs;
        if (chunkCount) chunkCount.textContent = chunks;
        if (settingsDocs) settingsDocs.textContent = docs;
        if (settingsChunks) settingsChunks.textContent = chunks;
        
    } catch (error) {
        console.error('Failed to load stats:', error);
    }
}

// ============================================
// Chat
// ============================================
function setupChat() {
    if (sendButton) {
        sendButton.addEventListener('click', handleSendQuestion);
    }
    
    if (questionInput) {
        questionInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSendQuestion();
            }
        });
    }
    
    const clearChat = document.getElementById('clear-chat');
    if (clearChat) {
        clearChat.addEventListener('click', () => {
            if (chatMessages) {
                chatMessages.innerHTML = `
                    <div class="message assistant">
                        <div class="message-avatar">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M12 2L2 7L12 12L22 7L12 2Z"/>
                                <path d="M2 17L12 22L22 17"/>
                                <path d="M2 12L12 17L22 12"/>
                            </svg>
                        </div>
                        <div class="message-content">
                            <p>🔮 I read documents so you don't have to. Upload your files and watch the magic happen.</p>
                        </div>
                    </div>
                `;
            }
            
            // Clear uploaded files from chat
            chatUploadedFiles = [];
            const chatFilesList = document.getElementById('chat-files-list');
            const chatFilesBar = document.getElementById('chat-files-bar');
            if (chatFilesList) {
                chatFilesList.innerHTML = '';
            }
            if (chatFilesBar) {
                chatFilesBar.classList.add('hidden');
            }
        });
    }
}

async function handleSendQuestion() {
    if (!questionInput) return;
    
    const question = questionInput.value.trim();
    if (!question || isLoading) return;
    
    // Add user message
    addMessage(question, 'user');
    questionInput.value = '';
    
    isLoading = true;
    if (sendButton) sendButton.disabled = true;
    
    // Add streaming message
    const streamingMessage = addStreamingMessage();
    const contentEl = streamingMessage.querySelector('.streaming-content');
    
    let fullResponse = '';
    let sources = [];
    
    // Get uploaded file names to filter search
    const uploadedFileNames = chatUploadedFiles.map(f => f.name);
    
    try {
        const response = await fetch('/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                question, 
                n_chunks: 3,
                filter_sources: uploadedFileNames.length > 0 ? uploadedFileNames : null
            })
        });
        
        if (!response.ok) throw new Error('Request failed');
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = line.slice(6);
                    
                    if (data === '[DONE]') {
                        break;
                    } else if (data.startsWith('[SOURCES]')) {
                        const match = data.match(/\[SOURCES\](.*?)\[\/SOURCES\]/);
                        if (match) {
                            sources = match[1].split(',').filter(s => s.trim());
                        }
                    } else if (data.startsWith('[ERROR]')) {
                        const match = data.match(/\[ERROR\](.*?)\[\/ERROR\]/);
                        throw new Error(match ? match[1] : 'Unknown error');
                    } else {
                        // Display immediately as chunks arrive
                        fullResponse += data;
                        if (contentEl) {
                            contentEl.innerHTML = formatMessage(fullResponse);
                        }
                        if (chatMessages) {
                            chatMessages.scrollTop = chatMessages.scrollHeight;
                        }
                    }
                }
            }
        }
        
        finalizeStreamingMessage(streamingMessage, fullResponse, sources);
        
    } catch (error) {
        streamingMessage.remove();
        addMessage(`Sorry, something went wrong: ${error.message}`, 'assistant');
    } finally {
        isLoading = false;
        if (sendButton) sendButton.disabled = false;
    }
}

function addMessage(content, role, sources = []) {
    if (!chatMessages) return;
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    
    let sourcesHtml = '';
    if (sources.length > 0) {
        sourcesHtml = `
            <div class="message-sources">
                <span class="sources-label">📎 Sources:</span>
                ${sources.map(s => `<span class="source-tag">${s}</span>`).join('')}
            </div>
        `;
    }
    
    const avatarHtml = role === 'assistant' ? `
        <div class="message-avatar">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 2L2 7L12 12L22 7L12 2Z"/>
                <path d="M2 17L12 22L22 17"/>
                <path d="M2 12L12 17L22 12"/>
            </svg>
        </div>
    ` : '';
    
    messageDiv.innerHTML = `
        ${avatarHtml}
        <div class="message-content">
            ${formatMessage(content)}
            ${sourcesHtml}
        </div>
    `;
    
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    return messageDiv;
}

function addStreamingMessage() {
    if (!chatMessages) return document.createElement('div');
    
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    
    messageDiv.innerHTML = `
        <div class="message-avatar">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 2L2 7L12 12L22 7L12 2Z"/>
                <path d="M2 17L12 22L22 17"/>
                <path d="M2 12L12 17L22 12"/>
            </svg>
        </div>
        <div class="message-content">
            <div class="streaming-content"><span class="typing-cursor"></span></div>
        </div>
    `;
    
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    return messageDiv;
}

function finalizeStreamingMessage(messageDiv, content, sources) {
    const contentEl = messageDiv.querySelector('.message-content');
    if (!contentEl) return;
    
    let sourcesHtml = '';
    if (sources.length > 0) {
        sourcesHtml = `
            <div class="message-sources">
                <span class="sources-label">📎 Sources:</span>
                ${sources.map(s => `<span class="source-tag">${s}</span>`).join('')}
            </div>
        `;
    }
    
    const streamingEl = contentEl.querySelector('.streaming-content');
    if (streamingEl) {
        streamingEl.outerHTML = formatMessage(content) + sourcesHtml;
    }
}

function formatMessage(text) {
    if (!text) return '';
    
    // Escape HTML first
    let formatted = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    
    // Format markdown-style text - bold first (before single asterisk)
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    
    // Handle headers (lines ending with colon that are bold)
    formatted = formatted.replace(/<strong>([^<]+:)<\/strong>/g, '<h4 class="response-header">$1</h4>');
    
    // Italic (single asterisk, but not inside words)
    formatted = formatted.replace(/(?<!\w)\*([^*]+)\*(?!\w)/g, '<em>$1</em>');
    
    // Code
    formatted = formatted.replace(/`(.*?)`/g, '<code>$1</code>');
    
    // Process line by line for better list handling
    const lines = formatted.split('\n');
    let result = [];
    let inList = false;
    let listType = null;
    
    for (let i = 0; i < lines.length; i++) {
        let line = lines[i].trim();
        
        // Check for bullet list item
        const bulletMatch = line.match(/^[-•]\s+(.+)$/);
        // Check for numbered list item
        const numberMatch = line.match(/^\d+\.\s+(.+)$/);
        
        if (bulletMatch) {
            if (!inList || listType !== 'ul') {
                if (inList) result.push(listType === 'ol' ? '</ol>' : '</ul>');
                result.push('<ul class="response-list">');
                inList = true;
                listType = 'ul';
            }
            result.push(`<li>${bulletMatch[1]}</li>`);
        } else if (numberMatch) {
            if (!inList || listType !== 'ol') {
                if (inList) result.push(listType === 'ol' ? '</ol>' : '</ul>');
                result.push('<ol class="response-list">');
                inList = true;
                listType = 'ol';
            }
            result.push(`<li>${numberMatch[1]}</li>`);
        } else {
            if (inList) {
                result.push(listType === 'ol' ? '</ol>' : '</ul>');
                inList = false;
                listType = null;
            }
            if (line) {
                // Check if it's a header
                if (line.startsWith('<h4')) {
                    result.push(line);
                } else {
                    result.push(`<p>${line}</p>`);
                }
            } else if (result.length > 0 && !result[result.length - 1].match(/<\/(ul|ol|h4)>/)) {
                // Add spacing for empty lines (but not after lists/headers)
                result.push('<div class="response-spacer"></div>');
            }
        }
    }
    
    // Close any open list
    if (inList) {
        result.push(listType === 'ol' ? '</ol>' : '</ul>');
    }
    
    return result.join('');
}

// ============================================
// Toast Notifications
// ============================================
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.remove();
    }, 3000);
}

// ============================================
// Chat File Upload
// ============================================
function setupChatFileUpload() {
    const chatFileInput = document.getElementById('chat-file-input');
    if (chatFileInput) {
        chatFileInput.addEventListener('change', handleChatFileUpload);
    }
}

async function handleChatFileUpload(e) {
    const files = Array.from(e.target.files);
    if (files.length === 0) return;
    
    const chatFilesBar = document.getElementById('chat-files-bar');
    const chatFilesList = document.getElementById('chat-files-list');
    
    if (!chatFilesBar || !chatFilesList) return;
    
    // Show the files bar
    chatFilesBar.classList.remove('hidden');
    
    for (const file of files) {
        const ext = '.' + file.name.split('.').pop().toLowerCase();
        
        // Validate file
        if (!ALLOWED_TYPES.includes(ext)) {
            showToast(`${file.name}: Unsupported file type`, 'error');
            continue;
        }
        if (file.size > MAX_FILE_SIZE) {
            showToast(`${file.name}: File too large (max 10MB)`, 'error');
            continue;
        }
        
        const fileId = `chat-file-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        const iconClass = ext === '.pdf' ? 'pdf' : ext === '.md' ? 'md' : 'txt';
        
        // Add file item to the bar
        const fileItem = document.createElement('div');
        fileItem.className = 'chat-file-item';
        fileItem.id = fileId;
        fileItem.innerHTML = `
            <div class="file-icon ${iconClass}">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                </svg>
            </div>
            <span class="file-name">${file.name}</span>
            <span class="file-status uploading">Uploading...</span>
        `;
        chatFilesList.appendChild(fileItem);
        
        // Upload the file
        try {
            const formData = new FormData();
            formData.append('file', file);
            
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) throw new Error('Upload failed');
            
            // Update status to success and add preview button
            const statusEl = fileItem.querySelector('.file-status');
            statusEl.textContent = 'Uploaded';
            statusEl.className = 'file-status success';
            
            // Add preview and remove buttons
            fileItem.innerHTML = `
                <div class="file-icon ${iconClass}">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                        <polyline points="14 2 14 8 20 8"/>
                    </svg>
                </div>
                <span class="file-name">${file.name}</span>
                <span class="file-status success">Uploaded</span>
                <button class="preview-btn" onclick="previewDocument('${file.name}')" title="Preview">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                        <circle cx="12" cy="12" r="3"/>
                    </svg>
                </button>
                <button class="remove-btn" onclick="removeChatFileItem('${fileId}')" title="Remove">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="18" y1="6" x2="6" y2="18"/>
                        <line x1="6" y1="6" x2="18" y2="18"/>
                    </svg>
                </button>
            `;
            
            chatUploadedFiles.push({ id: fileId, name: file.name });
            showToast(`${file.name} uploaded successfully`, 'success');
            
            // Refresh documents list and stats
            await loadDocuments();
            await loadStats();
            
        } catch (error) {
            const statusEl = fileItem.querySelector('.file-status');
            statusEl.textContent = 'Failed';
            statusEl.className = 'file-status error';
            showToast(`Failed to upload ${file.name}`, 'error');
        }
    }
    
    // Reset input
    e.target.value = '';
}

function removeChatFileItem(fileId) {
    const fileItem = document.getElementById(fileId);
    if (fileItem) {
        fileItem.remove();
    }
    
    chatUploadedFiles = chatUploadedFiles.filter(f => f.id !== fileId);
    
    // Hide bar if no files
    const chatFilesList = document.getElementById('chat-files-list');
    const chatFilesBar = document.getElementById('chat-files-bar');
    if (chatFilesList && chatFilesBar && chatFilesList.children.length === 0) {
        chatFilesBar.classList.add('hidden');
    }
}

// ============================================
// Document Preview Modal
// ============================================
function setupPreviewModal() {
    const previewClose = document.getElementById('preview-close');
    const previewModal = document.getElementById('preview-modal');
    
    if (previewClose) {
        previewClose.addEventListener('click', closePreviewModal);
    }
    
    if (previewModal) {
        previewModal.addEventListener('click', (e) => {
            if (e.target === previewModal) {
                closePreviewModal();
            }
        });
    }
    
    // Close on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closePreviewModal();
        }
    });
    
    // Tab switching
    const tabPreview = document.getElementById('tab-preview');
    const tabJson = document.getElementById('tab-json');
    
    if (tabPreview) {
        tabPreview.addEventListener('click', () => {
            tabPreview.classList.add('active');
            tabJson?.classList.remove('active');
            document.getElementById('content-preview')?.classList.remove('hidden');
            document.getElementById('content-json')?.classList.add('hidden');
        });
    }
    
    if (tabJson) {
        tabJson.addEventListener('click', () => {
            tabJson.classList.add('active');
            tabPreview?.classList.remove('active');
            document.getElementById('content-preview')?.classList.add('hidden');
            document.getElementById('content-json')?.classList.remove('hidden');
            
            // Load JSON if not already loaded
            const jsonContent = document.getElementById('json-content');
            if (jsonContent && !jsonContent.textContent && currentPreviewFilename) {
                loadDocumentJson(currentPreviewFilename);
            }
        });
    }
}

// Store current filename for JSON tab
let currentPreviewFilename = '';

async function previewDocument(filename) {
    const previewModal = document.getElementById('preview-modal');
    const previewTitle = document.getElementById('preview-title');
    const previewContent = document.getElementById('preview-content');
    const previewIframe = document.getElementById('preview-iframe');
    
    if (!previewModal || !previewTitle || !previewContent) return;
    
    currentPreviewFilename = filename;
    previewTitle.textContent = filename;
    previewModal.classList.remove('hidden');
    
    // Reset tabs to preview
    document.getElementById('tab-preview')?.classList.add('active');
    document.getElementById('tab-json')?.classList.remove('active');
    document.getElementById('content-preview')?.classList.remove('hidden');
    document.getElementById('content-json')?.classList.add('hidden');
    
    // Reset JSON content
    const jsonContent = document.getElementById('json-content');
    if (jsonContent) jsonContent.textContent = '';
    
    // Reset both views
    if (previewIframe) {
        previewIframe.classList.add('hidden');
        previewIframe.src = '';
    }
    previewContent.classList.remove('hidden');
    previewContent.textContent = 'Loading...';
    
    const ext = filename.split('.').pop().toLowerCase();
    
    try {
        // For PDFs, show directly in iframe (fast)
        if (ext === 'pdf') {
            previewContent.classList.add('hidden');
            if (previewIframe) {
                previewIframe.classList.remove('hidden');
                previewIframe.src = `/file?name=${encodeURIComponent(filename)}`;
            }
            return;
        }
        
        // For images, show directly (fast - no content fetch needed)
        if (['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'].includes(ext)) {
            previewContent.innerHTML = `<img src="/file?name=${encodeURIComponent(filename)}" alt="${filename}" style="max-width: 100%; max-height: 70vh; border-radius: 8px;" onerror="this.parentElement.textContent='Failed to load image'">`;
            return;
        }
        
        // For text files, fetch content
        const checkResponse = await fetch(`/content?name=${encodeURIComponent(filename)}`);
        
        if (!checkResponse.ok) {
            previewContent.textContent = `Document not found: "${filename}"\n\nThis file may have been deleted or renamed.\n\nPlease upload the document again.`;
            return;
        }
        
        const data = await checkResponse.json();
        previewContent.textContent = data.content || 'No content available';
        
    } catch (error) {
        previewContent.textContent = `Error loading document: ${error.message}`;
    }
}

async function loadDocumentJson(filename) {
    const jsonContent = document.getElementById('json-content');
    const jsonLoading = document.getElementById('json-loading');
    
    if (!jsonContent) return;
    
    jsonContent.textContent = '';
    if (jsonLoading) jsonLoading.classList.remove('hidden');
    
    try {
        const response = await fetch(`/json?name=${encodeURIComponent(filename)}`);
        
        if (!response.ok) {
            jsonContent.textContent = JSON.stringify({ error: 'Failed to extract JSON' }, null, 2);
            return;
        }
        
        const data = await response.json();
        // Filter out empty fields before displaying
        const filteredData = filterEmptyFields(data.data);
        jsonContent.textContent = JSON.stringify(filteredData, null, 2);
        
    } catch (error) {
        jsonContent.textContent = JSON.stringify({ error: error.message }, null, 2);
    } finally {
        if (jsonLoading) jsonLoading.classList.add('hidden');
    }
}

// Filter out empty, null, undefined, or placeholder values from JSON
function filterEmptyFields(obj) {
    if (obj === null || obj === undefined) return null;
    
    if (Array.isArray(obj)) {
        const filtered = obj
            .map(item => filterEmptyFields(item))
            .filter(item => !isEmptyValue(item));
        return filtered.length > 0 ? filtered : null;
    }
    
    if (typeof obj === 'object') {
        const result = {};
        for (const [key, value] of Object.entries(obj)) {
            const filteredValue = filterEmptyFields(value);
            if (!isEmptyValue(filteredValue)) {
                result[key] = filteredValue;
            }
        }
        return Object.keys(result).length > 0 ? result : null;
    }
    
    return obj;
}

// Check if a value is considered "empty"
function isEmptyValue(value) {
    if (value === null || value === undefined) return true;
    if (value === '') return true;
    if (value === '-') return true;
    if (value === '--') return true;
    if (value === 'N/A' || value === 'n/a') return true;
    if (value === 'null' || value === 'undefined') return true;
    if (value === 'None' || value === 'none') return true;
    if (typeof value === 'string' && value.trim() === '') return true;
    if (typeof value === 'string' && value.trim() === '-') return true;
    if (Array.isArray(value) && value.length === 0) return true;
    if (typeof value === 'object' && value !== null && Object.keys(value).length === 0) return true;
    return false;
}

function closePreviewModal() {
    const previewModal = document.getElementById('preview-modal');
    const previewIframe = document.getElementById('preview-iframe');
    const previewContent = document.getElementById('preview-content');
    
    if (previewModal) {
        previewModal.classList.add('hidden');
    }
    // Reset iframe to stop any loading
    if (previewIframe) {
        previewIframe.src = '';
        previewIframe.classList.add('hidden');
    }
    if (previewContent) {
        previewContent.classList.remove('hidden');
    }
    
    // Reset current filename
    currentPreviewFilename = '';
}

// ============================================
// Toast Notifications
// ============================================
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.remove();
    }, 3000);
}

// ============================================
// Admin Page Functions
// ============================================
function setupAdmin() {
    const refreshBtn = document.getElementById('admin-refresh');
    const searchBtn = document.getElementById('chunk-search-btn');
    const searchInput = document.getElementById('chunk-search-input');
    const clearSearchBtn = document.getElementById('clear-search-results');
    const closeChunkViewerBtn = document.getElementById('close-chunk-viewer');
    const clearChatHistoryBtn = document.getElementById('clear-chat-history');
    const optimizeDbBtn = document.getElementById('admin-optimize-db');
    const clearAllBtn = document.getElementById('admin-clear-all');
    
    if (refreshBtn) {
        refreshBtn.addEventListener('click', loadAdminData);
    }
    
    if (searchBtn) {
        searchBtn.addEventListener('click', searchChunks);
    }
    
    if (searchInput) {
        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') searchChunks();
        });
    }
    
    if (clearSearchBtn) {
        clearSearchBtn.addEventListener('click', () => {
            document.getElementById('chunk-search-results').classList.add('hidden');
            document.getElementById('chunk-search-input').value = '';
        });
    }
    
    if (closeChunkViewerBtn) {
        closeChunkViewerBtn.addEventListener('click', () => {
            document.getElementById('chunk-viewer-section').classList.add('hidden');
        });
    }
    
    if (clearChatHistoryBtn) {
        clearChatHistoryBtn.addEventListener('click', clearAllChatHistory);
    }
    
    if (optimizeDbBtn) {
        optimizeDbBtn.addEventListener('click', optimizeDatabase);
    }
    
    if (clearAllBtn) {
        clearAllBtn.addEventListener('click', clearAllData);
    }
}

async function loadAdminData() {
    await Promise.all([
        loadAdminOverview(),
        loadAdminHealth(),
        loadAdminDocuments(),
        loadAdminChatHistory()
    ]);
}

async function loadAdminOverview() {
    try {
        const response = await fetch('/api/admin/overview');
        const data = await response.json();
        
        document.getElementById('admin-docs-count').textContent = data.total_documents;
        document.getElementById('admin-chunks-count').textContent = data.total_chunks;
        document.getElementById('admin-messages-count').textContent = data.total_messages;
        document.getElementById('admin-storage-size').textContent = data.storage_size_formatted;
    } catch (error) {
        console.error('Failed to load admin overview:', error);
    }
}

async function loadAdminHealth() {
    try {
        const response = await fetch('/api/admin/database/health');
        const data = await response.json();
        
        const indicator = document.getElementById('health-indicator');
        const statusText = document.getElementById('health-status-text');
        
        if (data.status === 'healthy') {
            indicator.className = 'health-indicator healthy';
            statusText.textContent = 'Healthy';
        } else {
            indicator.className = 'health-indicator error';
            statusText.textContent = data.status;
        }
        
        document.getElementById('health-vector-store').textContent = data.vector_store_type;
        document.getElementById('health-embedding-model').textContent = data.embedding_model;
        document.getElementById('health-total-chunks').textContent = data.total_chunks;
    } catch (error) {
        console.error('Failed to load admin health:', error);
    }
}

async function loadAdminDocuments() {
    const tbody = document.getElementById('admin-documents-tbody');
    if (!tbody) return;
    
    tbody.innerHTML = '<tr class="loading-row"><td colspan="6">Loading documents...</td></tr>';
    
    try {
        const response = await fetch('/api/admin/documents');
        const documents = await response.json();
        
        if (documents.length === 0) {
            tbody.innerHTML = '<tr class="loading-row"><td colspan="6">No documents uploaded yet.</td></tr>';
            return;
        }
        
        tbody.innerHTML = documents.map(doc => `
            <tr>
                <td title="${doc.filename}">${doc.filename.length > 40 ? doc.filename.substring(0, 40) + '...' : doc.filename}</td>
                <td>${doc.file_type}</td>
                <td>${doc.file_size_formatted}</td>
                <td>${doc.chunk_count}</td>
                <td>${doc.uploaded_at ? new Date(doc.uploaded_at).toLocaleDateString() : '-'}</td>
                <td>
                    <div class="table-actions">
                        <button class="btn-icon" onclick="viewDocumentChunks('${encodeURIComponent(doc.filename)}')" title="View Chunks">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                                <circle cx="12" cy="12" r="3"/>
                            </svg>
                        </button>
                        <button class="btn-icon danger" onclick="deleteDocumentAdmin('${encodeURIComponent(doc.filename)}')" title="Delete">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="3 6 5 6 21 6"/>
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                            </svg>
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');
    } catch (error) {
        tbody.innerHTML = '<tr class="loading-row"><td colspan="6">Failed to load documents.</td></tr>';
        console.error('Failed to load admin documents:', error);
    }
}

async function viewDocumentChunks(encodedFilename) {
    const filename = decodeURIComponent(encodedFilename);
    const section = document.getElementById('chunk-viewer-section');
    const filenameEl = document.getElementById('chunk-viewer-filename');
    const listEl = document.getElementById('chunk-viewer-list');
    
    if (!section || !listEl) return;
    
    filenameEl.textContent = filename;
    listEl.innerHTML = '<p class="empty-text">Loading chunks...</p>';
    section.classList.remove('hidden');
    
    try {
        const response = await fetch(`/api/admin/documents/${encodedFilename}/chunks`);
        const data = await response.json();
        
        if (data.chunks.length === 0) {
            listEl.innerHTML = '<p class="empty-text">No chunks found for this document.</p>';
            return;
        }
        
        listEl.innerHTML = data.chunks.map(chunk => `
            <div class="chunk-item">
                <div class="chunk-item-header">
                    <span class="chunk-index">Chunk ${chunk.chunk_index}</span>
                </div>
                <div class="chunk-content">${escapeHtml(chunk.content)}</div>
            </div>
        `).join('');
    } catch (error) {
        listEl.innerHTML = '<p class="empty-text">Failed to load chunks.</p>';
        console.error('Failed to load chunks:', error);
    }
}

async function deleteDocumentAdmin(encodedFilename) {
    const filename = decodeURIComponent(encodedFilename);
    if (!confirm(`Delete "${filename}" and all its chunks?`)) return;
    
    try {
        const response = await fetch(`/document/${encodedFilename}`, { method: 'DELETE' });
        if (response.ok) {
            showToast(`Deleted ${filename}`, 'success');
            loadAdminData();
        } else {
            showToast('Failed to delete document', 'error');
        }
    } catch (error) {
        showToast('Failed to delete document', 'error');
    }
}

async function searchChunks() {
    const input = document.getElementById('chunk-search-input');
    const resultsSection = document.getElementById('chunk-search-results');
    const resultsList = document.getElementById('search-results-list');
    const countEl = document.getElementById('search-results-count');
    
    const query = input.value.trim();
    if (!query) return;
    
    resultsSection.classList.remove('hidden');
    resultsList.innerHTML = '<p class="empty-text">Searching...</p>';
    
    try {
        const response = await fetch(`/api/admin/chunks/search?q=${encodeURIComponent(query)}`);
        const data = await response.json();
        
        countEl.textContent = `${data.total} results`;
        
        if (data.results.length === 0) {
            resultsList.innerHTML = '<p class="empty-text">No matching chunks found.</p>';
            return;
        }
        
        resultsList.innerHTML = data.results.map(result => {
            const highlightedContent = highlightKeyword(result.content_preview, query);
            return `
                <div class="search-result-item">
                    <div class="search-result-source">${result.source} (Chunk ${result.chunk_index})</div>
                    <div class="search-result-content">${highlightedContent}</div>
                </div>
            `;
        }).join('');
    } catch (error) {
        resultsList.innerHTML = '<p class="empty-text">Search failed.</p>';
        console.error('Search failed:', error);
    }
}

function highlightKeyword(text, keyword) {
    const escaped = escapeHtml(text);
    const regex = new RegExp(`(${escapeRegex(keyword)})`, 'gi');
    return escaped.replace(regex, '<mark>$1</mark>');
}

function escapeRegex(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function loadAdminChatHistory() {
    const container = document.getElementById('admin-chat-history');
    if (!container) return;
    
    try {
        const response = await fetch('/api/admin/chat-history?limit=50');
        const data = await response.json();
        
        if (data.messages.length === 0) {
            container.innerHTML = '<p class="empty-text">No chat history yet.</p>';
            return;
        }
        
        container.innerHTML = data.messages.slice(-20).map(msg => `
            <div class="chat-history-item ${msg.role}">
                <span class="chat-history-role">${msg.role === 'user' ? 'User' : 'Assistant'}</span>
                <span class="chat-history-content">${escapeHtml(msg.content.substring(0, 200))}${msg.content.length > 200 ? '...' : ''}</span>
                <span class="chat-history-time">${new Date(msg.timestamp).toLocaleTimeString()}</span>
            </div>
        `).join('');
    } catch (error) {
        container.innerHTML = '<p class="empty-text">Failed to load chat history.</p>';
        console.error('Failed to load chat history:', error);
    }
}

async function clearAllChatHistory() {
    if (!confirm('Clear all chat history? This cannot be undone.')) return;
    
    try {
        const response = await fetch('/api/admin/chat-history', { method: 'DELETE' });
        const data = await response.json();
        showToast(data.message, 'success');
        loadAdminChatHistory();
        loadAdminOverview();
    } catch (error) {
        showToast('Failed to clear chat history', 'error');
    }
}

async function optimizeDatabase() {
    try {
        const response = await fetch('/api/admin/database/optimize', { method: 'POST' });
        const data = await response.json();
        showToast(data.message, 'success');
    } catch (error) {
        showToast('Optimization failed', 'error');
    }
}

async function clearAllData() {
    if (!confirm('⚠️ WARNING: This will delete ALL documents, chunks, and chat history. This cannot be undone!\n\nAre you sure?')) return;
    if (!confirm('This is your last chance. Type "DELETE" in the next prompt to confirm.')) return;
    
    const confirmation = prompt('Type DELETE to confirm:');
    if (confirmation !== 'DELETE') {
        showToast('Deletion cancelled', 'error');
        return;
    }
    
    try {
        const response = await fetch('/api/admin/database/clear-all?confirm=true', { method: 'DELETE' });
        const data = await response.json();
        showToast(data.message, 'success');
        loadAdminData();
        loadStats();
        loadDocuments();
    } catch (error) {
        showToast('Failed to clear data', 'error');
    }
}

// Make functions available globally
window.deleteDocument = deleteDocument;
window.previewDocument = previewDocument;
window.removeChatFileItem = removeChatFileItem;
window.viewDocumentChunks = viewDocumentChunks;
window.deleteDocumentAdmin = deleteDocumentAdmin;
