const tg = window.Telegram.WebApp;
const API_BASE = "/api";

// State
let currentQuizzes = [];
let currentQuizData = null;
let currentView = 'dashboard';
let authToken = null;

// Elements
const loader = document.getElementById('loader');
const appContainer = document.getElementById('app');
const quizList = document.getElementById('quiz-list');
const dashboardView = document.getElementById('dashboard');
const editorView = document.getElementById('editor');
const questionsContainer = document.getElementById('questions-container');
const pageTitle = document.getElementById('page-title');
const backBtn = document.getElementById('back-btn');
const editorActions = document.getElementById('editor-actions');
const saveBtn = document.getElementById('save-btn');
const searchInput = document.getElementById('search-input');

// Helper to get params
function getAuthHeaders() {
    const headers = {};

    // 1. Check for token in URL (Priority)
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('token')) {
        authToken = urlParams.get('token');
    }

    if (authToken) {
        headers['X-Auth-Token'] = authToken;
    }

    // 2. Always send initData if available (Fallback)
    if (tg.initData) {
        headers['X-Telegram-Init-Data'] = tg.initData;
    }

    return headers;
}

// Initialize
async function init() {
    tg.expand();
    tg.ready();

    // Set theme colors
    document.documentElement.style.setProperty('--bg-color', tg.backgroundColor || '#0f172a');

    await loadQuizzes();
    hideLoader();
}

async function loadQuizzes() {
    try {
        const headers = getAuthHeaders();

        // Validation: Must have at least one auth method
        if (!headers['X-Auth-Token'] && !headers['X-Telegram-Init-Data']) {
            // Try manual parsing as last resort for initData
            try {
                const hash = window.location.hash.slice(1);
                const params = new URLSearchParams(hash);
                if (params.get('tgWebAppData')) headers['X-Telegram-Init-Data'] = params.get('tgWebAppData');
            } catch (e) { }
        }

        const res = await fetch(`${API_BASE}/quizzes`, { headers });

        if (res.status === 401) {
            showError("Authentication Failed. Please retry via the Bot link.");
            return;
        }
        if (!res.ok) throw new Error("Failed to load quizzes");

        currentQuizzes = await res.json();
        renderQuizList();
    } catch (err) {
        console.error(err);
        showError(err.message);
    }
}

function showError(msg) {
    const debugHTML = `
        <div style="background: var(--bg-color); color: var(--text-color); padding: 20px; text-align: center;">
            <h3>Error</h3>
            <p>${msg}</p>
            <br>
            <button onclick="window.location.reload()" style="padding: 10px 20px;">Retry</button>
        </div>
    `;
    appContainer.innerHTML = debugHTML;
}

function renderQuizList() {
    quizList.innerHTML = '';
    if (currentQuizzes.length === 0) {
        document.getElementById('no-quizzes').style.display = 'block';
        return;
    }

    currentQuizzes.forEach(quiz => {
        const card = document.createElement('div');
        card.className = 'quiz-card glass';
        card.innerHTML = `
            <h3>${quiz.title}</h3>
            <p>${quiz.questions_count} questions • ${new Date(quiz.created_at).toLocaleDateString()}</p>
        `;
        card.onclick = () => openEditor(quiz.id);
        quizList.appendChild(card);
    });
}

async function openEditor(quizId) {
    showLoader();
    try {
        const headers = getAuthHeaders();
        const res = await fetch(`${API_BASE}/quizzes/${quizId}`, {
            headers: headers
        });
        if (!res.ok) throw new Error("Failed to load quiz");

        currentQuizData = await res.json();
        renderEditor();
        switchView('editor');
    } catch (err) {
        console.error(err);
    } finally {
        hideLoader();
    }
}

// Validation Helpers
function markError(el) {
    el.classList.add('input-error');
    const countEl = el.parentElement.querySelector('.char-count');
    if (countEl) countEl.classList.add('error');
}

function clearError(el) {
    el.classList.remove('input-error');
    const countEl = el.parentElement.querySelector('.char-count');
    if (countEl) countEl.classList.remove('error');
}

function validateInput(el, limit) {
    const len = el.value.trim().length;
    const countEl = el.parentElement.querySelector('.char-count');
    if (countEl) countEl.innerText = `${len}/${limit}`;

    if (len > limit || len === 0) {
        markError(el);
        return false;
    } else {
        clearError(el);
        return true;
    }
}

function renderEditor() {
    questionsContainer.innerHTML = '';
    pageTitle.innerText = "Editing Test";

    currentQuizData.questions.forEach((q, index) => {
        const item = document.createElement('div');
        item.className = 'question-item glass';
        item.dataset.index = index;

        item.innerHTML = `
            <div class="q-header">
                <span class="q-label">Question #${index + 1}</span>
            </div>
            <div class="input-group">
                <textarea class="q-text" placeholder="Question text...">${q.question}</textarea>
                <small class="char-count">${q.question.length}/300</small>
            </div>
            <div class="options-grid">
                ${q.options.map((opt, optIndex) => `
                    <div class="option-row ${optIndex === q.correct_option_id ? 'correct' : 'wrong'}">
                        <div class="indicator">${optIndex === 0 ? '✓' : '✗'}</div>
                        <div class="input-group">
                            <input type="text" class="option-input" value="${opt}" placeholder="Option ${optIndex + 1}">
                            <small class="char-count">${opt.length}/100</small>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;

        // Attach listeners
        const qInput = item.querySelector('.q-text');
        qInput.oninput = () => validateInput(qInput, 300);

        item.querySelectorAll('.option-input').forEach(optInput => {
            optInput.oninput = () => validateInput(optInput, 100);
        });

        questionsContainer.appendChild(item);
    });
}

async function saveChanges() {
    tg.MainButton.showProgress();

    // Collect data
    // Collect data
    const updatedQuestions = [];
    const items = questionsContainer.querySelectorAll('.question-item');
    let hasError = false;

    items.forEach(item => {
        const qInput = item.querySelector('.q-text');
        const qText = qInput.value.trim();

        if (!qText || qText.length > 300) {
            markError(qInput);
            hasError = true;
        } else {
            clearError(qInput);
        }

        const options = [];
        const optionInputs = item.querySelectorAll('.option-input');

        optionInputs.forEach(optInput => {
            const val = optInput.value.trim();
            if (!val || val.length > 100) {
                markError(optInput);
                hasError = true;
            } else {
                clearError(optInput);
                options.push(val);
            }
        });

        updatedQuestions.push({
            question: qText,
            options: options,
            correct_option_id: 0
        });
    });

    if (hasError) {
        tg.MainButton.hideProgress();
        tg.showAlert("Please fix errors: ensure all fields are filled and within character limits (Question: 300, Option: 100).");
        return;
    }

    try {
        const headers = getAuthHeaders();
        headers['Content-Type'] = 'application/json';

        const res = await fetch(`${API_BASE}/quizzes/${currentQuizData.id}`, {
            method: 'PUT',
            headers: headers,
            body: JSON.stringify({
                title: currentQuizData.title, // Title editing can be added easily
                questions: updatedQuestions
            })
        });

        if (!res.ok) throw new Error("Save failed");

        tg.showScanQrPopup({ text: "Changes saved successfully! ✅" }); // Or just showAlert
        setTimeout(() => switchView('dashboard'), 1500);
    } catch (err) {
        console.error(err);
        tg.showAlert("Failed to save changes. Check your connection.");
    } finally {
        tg.MainButton.hideProgress();
    }
}

// Search Logic
// Search Logic
searchInput.oninput = (e) => {
    const query = e.target.value.toLowerCase().trim();
    const items = questionsContainer.querySelectorAll('.question-item');
    const isNumber = /^\d+$/.test(query);

    items.forEach(item => {
        const index = parseInt(item.dataset.index) + 1; // 1-based index

        let match = false;
        if (isNumber) {
            // Strict match for numbers (User request: "aniq usha savolni topadigan qil")
            match = (index.toString() === query);
        } else {
            // Normal text match
            const text = item.innerText.toLowerCase();
            match = text.includes(query);
        }

        item.style.display = match ? 'flex' : 'none';
    });
};

function switchView(view) {
    currentView = view;
    if (view === 'dashboard') {
        dashboardView.style.display = 'grid';
        editorView.style.display = 'none';
        backBtn.style.display = 'none';
        editorActions.style.display = 'none';
        pageTitle.innerText = "My Quizzes";
        loadQuizzes(); // Refresh list
    } else {
        dashboardView.style.display = 'none';
        editorView.style.display = 'block';
        backBtn.style.display = 'block';
        editorActions.style.display = 'block';
    }
}

function showLoader() {
    loader.style.display = 'flex';
    appContainer.style.display = 'none';
    document.body.classList.add('loading');
}
function hideLoader() {
    loader.style.display = 'none';
    appContainer.style.display = 'block';
    document.body.classList.remove('loading');
}

backBtn.onclick = () => switchView('dashboard');
saveBtn.onclick = saveChanges;

// Start
init();
