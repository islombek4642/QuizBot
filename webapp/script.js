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

    // 1. Check for initData (Primary for WebApp)
    if (tg.initData) {
        headers['X-Telegram-Init-Data'] = tg.initData;
    }

    // 2. Check for token in URL (Legacy/Fallback)
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('token')) {
        authToken = urlParams.get('token');
        headers['X-Auth-Token'] = authToken;
    }

    // 2. Always send initData if available (Fallback)
    if (tg.initData) {
        headers['X-Telegram-Init-Data'] = tg.initData;
    }

    return headers;
}

// Localization
const urlParams = new URLSearchParams(window.location.search);
const lang = (urlParams.get('lang') || 'uz').toUpperCase(); // default UZ

const TRANSLATIONS = {
    UZ: {
        my_quizzes: "Mening Testlarim",
        editing_test: "Tahrirlash",
        no_quizzes: "Testlar topilmadi. Bot orqali yangi test yarating!",
        save_changes: "Saqlash",
        search_placeholder: "Savollarni izlash...",
        question_label: "Savol #",
        question_placeholder: "Savol matni...",
        option_placeholder: "Variant",
        error_auth: "Autentifikatsiya xatosi. Iltimos, bot orqali qaytadan kiring.",
        error_load: "Testlarni yuklashda xatolik.",
        error_empty: "Xatolik: Ba'zi maydonlar bo'sh. Iltimos, to'ldiring.",
        error_limit: "Xatolik: Ba'zi maydonlar belgi limitidan oshdi.",
        success_save: "O'zgarishlar saqlandi! ✅",
        error_save: "Saqlashda xatolik. Internetni tekshiring.",
        retry: "Qayta urinish",
        error_title: "Xatolik",
        questions_count: "savol",
        date_format: "uz-UZ"
    },
    EN: {
        my_quizzes: "My Quizzes",
        editing_test: "Editing Test",
        no_quizzes: "No quizzes found. Go to the bot to create one!",
        save_changes: "Save Changes",
        search_placeholder: "Search questions...",
        question_label: "Question #",
        question_placeholder: "Question text...",
        option_placeholder: "Option",
        error_auth: "Authentication Failed. Please retry via the Bot link.",
        error_load: "Failed to load quizzes",
        error_empty: "Error: Some fields are empty. Please fill them.",
        error_limit: "Error: Some fields exceed the character limit.",
        success_save: "Changes saved successfully! ✅",
        error_save: "Failed to save changes. Check your connection.",
        retry: "Retry",
        error_title: "Error",
        questions_count: "questions",
        date_format: "en-US"
    }
};

function t(key) {
    return TRANSLATIONS[lang]?.[key] || TRANSLATIONS['EN'][key] || key;
}

// Initialize
async function init() {
    tg.expand();
    tg.ready();

    // Set theme colors
    document.documentElement.style.setProperty('--bg-color', tg.backgroundColor || '#0f172a');

    // Set static texts
    document.getElementById('save-btn').innerText = t('save_changes');
    document.getElementById('search-input').placeholder = t('search_placeholder');
    document.querySelector('#no-quizzes p').innerText = t('no_quizzes');
    pageTitle.innerText = t('my_quizzes');

    // Update Main Button text if needed (though we use custom button)
    tg.MainButton.setText(t('save_changes'));

    await loadQuizzes();
    hideLoader();
}

async function loadQuizzes() {
    try {
        const headers = getAuthHeaders();

        // Validation: Must have at least one auth method
        if (!headers['X-Auth-Token'] && !headers['X-Telegram-Init-Data']) {
            try {
                const hash = window.location.hash.slice(1);
                const params = new URLSearchParams(hash);
                if (params.get('tgWebAppData')) headers['X-Telegram-Init-Data'] = params.get('tgWebAppData');
            } catch (e) { }
        }

        const res = await fetch(`${API_BASE}/quizzes`, { headers });

        if (res.status === 401) {
            showError(t('error_auth'));
            return;
        }
        if (!res.ok) throw new Error(t('error_load'));

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
            <h3>${t('error_title')}</h3>
            <p>${msg}</p>
            <br>
            <button onclick="window.location.reload()" style="padding: 10px 20px;">${t('retry')}</button>
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
            <p>${quiz.questions_count} ${t('questions_count')} • ${new Date(quiz.created_at).toLocaleDateString(t('date_format'))}</p>
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
        if (!res.ok) throw new Error(t('error_load'));

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
function escapeHtml(text) {
    if (!text) return "";
    return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

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
    pageTitle.innerText = t('editing_test');

    currentQuizData.questions.forEach((q, index) => {
        const item = document.createElement('div');
        item.className = 'question-item glass';
        item.dataset.index = index;

        // Escape values to prevent HTML attribute breakage
        const safeQuestion = escapeHtml(q.question);

        item.innerHTML = `
            <div class="q-header">
                <span class="q-label">${t('question_label')}${index + 1}</span>
            </div>
            <div class="input-group">
                <textarea class="q-text" placeholder="${t('question_placeholder')}">${safeQuestion}</textarea>
                <small class="char-count">${q.question.length}/300</small>
            </div>
            <div class="options-grid">
                ${q.options.map((opt, optIndex) => {
            const safeOpt = escapeHtml(opt);
            return `
                    <div class="option-row ${optIndex === q.correct_option_id ? 'correct' : 'wrong'}">
                        <div class="indicator">${optIndex === 0 ? '✓' : '✗'}</div>
                        <div class="input-group">
                            <input type="text" class="option-input" value="${safeOpt}" placeholder="${t('option_placeholder')} ${optIndex + 1}">
                            <small class="char-count">${opt.length}/100</small>
                        </div>
                    </div>
                `}).join('')}
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
    const updatedQuestions = [];
    const items = questionsContainer.querySelectorAll('.question-item');
    let hasError = false;

    items.forEach(item => {
        const qInput = item.querySelector('.q-text');

        // Use shared validation logic
        if (!validateInput(qInput, 300)) {
            hasError = true;
        }

        const options = [];
        const optionInputs = item.querySelectorAll('.option-input');

        optionInputs.forEach(optInput => {
            if (!validateInput(optInput, 100)) {
                hasError = true;
            }
            options.push(optInput.value.trim());
        });

        updatedQuestions.push({
            question: qInput.value.trim(),
            options: options,
            correct_option_id: 0
        });
    });



    if (hasError) {
        tg.MainButton.hideProgress();

        // Reset search to ensure target is visible
        searchInput.value = '';
        items.forEach(item => {
            item.style.display = 'flex';
            item.classList.remove('highlight-pulse');
        });

        const firstError = questionsContainer.querySelector('.input-error');
        if (firstError) {
            firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
            // More specific message based on the error
            const val = firstError.value.trim();
            if (!val) tg.showAlert(t('error_empty'));
            else tg.showAlert(t('error_limit'));
        }
        return;
    }

    try {
        const headers = getAuthHeaders();
        headers['Content-Type'] = 'application/json';

        const res = await fetch(`${API_BASE}/quizzes/${currentQuizData.id}`, {
            method: 'PUT',
            headers: headers,
            body: JSON.stringify({
                title: currentQuizData.title,
                questions: updatedQuestions
            })
        });

        if (!res.ok) throw new Error("Save failed");

        tg.showAlert(t('success_save'));
        setTimeout(() => switchView('dashboard'), 1000);
    } catch (err) {
        console.error(err);
        tg.showAlert(t('error_save'));
    } finally {
        tg.MainButton.hideProgress();
    }
}

// Search Logic
searchInput.oninput = (e) => {
    const query = e.target.value.toLowerCase().trim();
    const items = questionsContainer.querySelectorAll('.question-item');
    const isNumber = /^\d+$/.test(query);

    // Reset highlights
    items.forEach(i => i.classList.remove('highlight-pulse'));

    if (isNumber && query) {
        // "Scroll To" Mode for numbers
        items.forEach(item => item.style.display = 'flex'); // Show all

        const targetIndex = parseInt(query) - 1;
        const targetItem = Array.from(items).find(item => parseInt(item.dataset.index) === targetIndex);

        if (targetItem) {
            targetItem.scrollIntoView({ behavior: 'smooth', block: 'center' });
            targetItem.classList.add('highlight-pulse');
        }
    } else {
        // "Filter" Mode for text
        items.forEach(item => {
            if (!query) {
                item.style.display = 'flex';
                return;
            }

            const text = item.innerText.toLowerCase();
            const match = text.includes(query);
            item.style.display = match ? 'flex' : 'none';
        });
    }
};

function switchView(view) {
    currentView = view;
    if (view === 'dashboard') {
        dashboardView.style.display = 'grid';
        editorView.style.display = 'none';
        backBtn.style.display = 'none';
        editorActions.style.display = 'none';
        pageTitle.innerText = t('my_quizzes');
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
