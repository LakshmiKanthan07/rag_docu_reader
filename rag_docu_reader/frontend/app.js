const API_URL = '/api/v1';

// DOM Elements
const authModal = document.getElementById('auth-modal');
const appContainer = document.getElementById('app-container');
const authForm = document.getElementById('auth-form');
const emailInput = document.getElementById('email');
const passwordInput = document.getElementById('password');
const authSubmitBtn = document.getElementById('auth-submit-btn');
const authError = document.getElementById('auth-error');
const tabLogin = document.getElementById('tab-login');
const tabSignup = document.getElementById('tab-signup');

const chatList = document.getElementById('chat-list');
const newChatBtn = document.getElementById('new-chat-btn');
const currentChatTitle = document.getElementById('current-chat-title');
const uploadZone = document.getElementById('upload-zone');
const fileUpload = document.getElementById('file-upload');
const uploadStatus = document.getElementById('upload-status');
const messagesContainer = document.getElementById('messages');
const inputArea = document.getElementById('input-area');
const chatForm = document.getElementById('chat-form');
const messageInput = document.getElementById('message-input');
const documentList = document.getElementById('document-list');

let isLoginMode = true;
let currentChatId = null;

function init() {
    const token = localStorage.getItem('token');
    if (token) {
        showApp();
    } else {
        showAuth();
    }
}

tabLogin.addEventListener('click', () => {
    isLoginMode = true;
    tabLogin.classList.add('active');
    tabSignup.classList.remove('active');
    authSubmitBtn.textContent = 'Login';
    authError.textContent = '';
});

tabSignup.addEventListener('click', () => {
    isLoginMode = false;
    tabSignup.classList.add('active');
    tabLogin.classList.remove('active');
    authSubmitBtn.textContent = 'Sign Up';
    authError.textContent = '';
});

authForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = emailInput.value;
    const password = passwordInput.value;
    
    try {
        if (isLoginMode) {
            const formData = new URLSearchParams();
            formData.append('username', email);
            formData.append('password', password);
            
            const res = await fetch(`${API_URL}/auth/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: formData
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail);
            
            localStorage.setItem('token', data.access_token);
            showApp();
        } else {
            const res = await fetch(`${API_URL}/auth/signup`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail);
            
            isLoginMode = true;
            authForm.dispatchEvent(new Event('submit'));
        }
    } catch (err) {
        authError.textContent = err.message;
    }
});

document.getElementById('logout-btn').addEventListener('click', () => {
    localStorage.removeItem('token');
    currentChatId = null;
    showAuth();
});

function showAuth() {
    authModal.classList.remove('hidden');
    appContainer.classList.add('hidden');
}

function showApp() {
    authModal.classList.add('hidden');
    appContainer.classList.remove('hidden');
    loadChats();
}

// ================= API UTILS =================
async function apiCall(endpoint, options = {}) {
    const token = localStorage.getItem('token');
    const headers = { 'Authorization': `Bearer ${token}`, ...options.headers };
    
    const res = await fetch(`${API_URL}${endpoint}`, { ...options, headers });
    
    // Auto logout if unauthorized
    if (res.status === 401) {
        localStorage.removeItem('token');
        showAuth();
        throw new Error('Unauthorized');
    }
    
    if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'API Error');
    }
    return res;
}

// ================= CHAT LIST =================
async function loadChats() {
    try {
        const res = await apiCall('/chats');
        const chats = await res.json();
        
        chatList.innerHTML = '';
        chats.forEach(chat => {
            const li = document.createElement('li');
            li.className = `chat-item ${chat.id === currentChatId ? 'active' : ''}`;
            li.innerHTML = `
                <span>${chat.title || 'New Chat'}</span>
                <button class="delete-chat-btn" onclick="deleteChat(event, '${chat.id}')">×</button>
            `;
            li.onclick = () => selectChat(chat.id, chat.title);
            chatList.appendChild(li);
        });
    } catch (err) {
        console.error("Failed to load chats", err);
    }
}

newChatBtn.addEventListener('click', async () => {
    try {
        const res = await apiCall('/chats', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: "New Document Chat" })
        });
        const chat = await res.json();
        await loadChats();
        selectChat(chat.id, chat.title);
    } catch (err) {
        console.error(err);
    }
});

window.deleteChat = async (e, id) => {
    e.stopPropagation();
    try {
        await apiCall(`/chats/${id}`, { method: 'DELETE' });
        if (currentChatId === id) {
            currentChatId = null;
            renderWelcome();
        }
        loadChats();
    } catch (err) {
        console.error(err);
    }
};

// ================= ACTIVE CHAT =================
async function selectChat(id, title) {
    currentChatId = id;
    currentChatTitle.textContent = title || "Document Chat";
    uploadZone.classList.remove('hidden');
    inputArea.classList.remove('hidden');
    
    // Update active class in list
    document.querySelectorAll('.chat-item').forEach(el => el.classList.remove('active'));
    const activeItem = Array.from(document.querySelectorAll('.chat-item')).find(el => el.textContent.includes(title));
    if (activeItem) activeItem.classList.add('active');
    
    // In a full implementation, you would fetch message history here.
    messagesContainer.innerHTML = '';
    loadDocuments(id);
}

// ================= DOCUMENTS =================
async function loadDocuments(chatId) {
    if (!chatId) return;
    try {
        const res = await apiCall(`/chats/${chatId}/documents`);
        const documents = await res.json();
        
        documentList.innerHTML = '';
        documents.forEach(doc => {
            const span = document.createElement('span');
            span.className = 'doc-tag';
            span.textContent = doc.filename;
            documentList.appendChild(span);
        });
    } catch (err) {
        console.error("Failed to load documents", err);
    }
}

function renderWelcome() {
    currentChatTitle.textContent = 'Select a chat';
    uploadZone.classList.add('hidden');
    inputArea.classList.add('hidden');
    messagesContainer.innerHTML = `
        <div class="welcome-screen">
            <h1 class="gradient-text">How can I help you today?</h1>
            <p>Select a chat or create a new one to begin.</p>
        </div>
    `;
}

// ================= DOCUMENT UPLOAD =================
fileUpload.addEventListener('change', async (e) => {
    if (!currentChatId || !e.target.files[0]) return;
    
    const file = e.target.files[0];
    const formData = new FormData();
    formData.append('file', file);
    
    uploadStatus.textContent = 'Uploading...';
    try {
        await apiCall(`/chats/${currentChatId}/upload`, {
            method: 'POST',
            body: formData
        });
        uploadStatus.textContent = 'Processing in background!';
        loadDocuments(currentChatId);
        setTimeout(() => uploadStatus.textContent = '', 3000);
    } catch (err) {
        uploadStatus.textContent = 'Upload failed.';
        console.error(err);
    }
    fileUpload.value = ''; // reset
});

// ================= STREAMING CHAT =================
chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!currentChatId) return;
    
    const text = messageInput.value.trim();
    if (!text) return;
    messageInput.value = '';
    
    // Add User Message
    appendMessage('human', text);
    
    // Create Assistant Message Placeholder
    const aiMessageEl = appendMessage('assistant', '');
    
    try {
        const token = localStorage.getItem('token');
        const res = await fetch(`${API_URL}/chats/${currentChatId}/ask`, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ question: text })
        });
        
        if (!res.ok) throw new Error('Failed to ask question');
        
        // Read stream
        const reader = res.body.getReader();
        const decoder = new TextDecoder('utf-8');
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            const chunk = decoder.decode(value, { stream: true });
            aiMessageEl.innerHTML += chunk.replace(/\n/g, '<br>');
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
    } catch (err) {
        aiMessageEl.innerHTML = `<span class="error-msg">Error: ${err.message}</span>`;
    }
});

function appendMessage(role, content) {
    const div = document.createElement('div');
    div.className = `message ${role}`;
    div.innerHTML = content.replace(/\n/g, '<br>');
    messagesContainer.appendChild(div);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
    return div;
}

init();
