const tg = window.Telegram.WebApp;
const API_BASE = "/api";

// State
let currentQuizzes = [];
let currentQuizData = null;
let currentView = 'dashboard';

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

// Helper to get initData with fallback and debug
function getInitData() {
    if (tg.initData) return tg.initData;

    const hash = window.location.hash.slice(1);
    const search = window.location.search.slice(1);

    const hashParams = new URLSearchParams(hash);
    const searchParams = new URLSearchParams(search);

    const data = hashParams.get('tgWebAppData') ||
        searchParams.get('tgWebAppData') ||
        (hash.includes('hash=') ? hash : "");

    if (!data) {
        console.warn("No initData found in SDK, Hash or Search.");
    }
    return data;
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
        const initData = getInitData();
        const res = await fetch(`${API_BASE}/quizzes`, {
            headers: { 'X-Telegram-Init-Data': initData }
        });

        if (res.status === 401) {
            const debugInfo = `
SDK Data: ${tg.initData ? 'Yes' : 'No'}
Hash: ${window.location.hash.substring(0, 30)}...
Version: ${tg.version}
            `;
            throw new Error("Empty Auth Data.\n" + debugInfo);
        }
        if (!res.ok) throw new Error("Failed to load quizzes");

        currentQuizzes = await res.json();
        renderQuizList();
    } catch (err) {
        console.error(err);
        tg.showAlert("Error: " + err.message);
    }
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
        const initData = tg.initData || "";
        const res = await fetch(`${API_BASE}/quizzes/${quizId}`, {
            headers: { 'X-Telegram-Init-Data': initData }
        });
        if (!res.ok) throw new Error("Failed to load quiz");

        currentQuizData = await res.json();
        renderEditor();
        switchView('editor');
    } catch (err) {
        console.error(err);
        tg.showAlert("Could not open test for editing.");
    } finally {
        hideLoader();
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
            <textarea class="q-text" placeholder="Question text...">${q.question}</textarea>
            <div class="options-grid">
                ${q.options.map((opt, optIndex) => `
                    <div class="option-row ${optIndex === q.correct_option_id ? 'correct' : 'wrong'}">
                        <div class="indicator">${optIndex === 0 ? '✓' : '✗'}</div>
                        <input type="text" class="option-input" value="${opt}" placeholder="Option ${optIndex + 1}">
                    </div>
                `).join('')}
            </div>
        `;
        questionsContainer.appendChild(item);
    });
}

async function saveChanges() {
    tg.MainButton.showProgress();

    // Collect data
    const updatedQuestions = [];
    const items = questionsContainer.querySelectorAll('.question-item');

    items.forEach(item => {
        const qText = item.querySelector('.q-text').value;
        const options = Array.from(item.querySelectorAll('.option-input')).map(i => i.value);

        updatedQuestions.push({
            question: qText,
            options: options,
            correct_option_id: 0 // In our bot, 0 is always correct
        });
    });

    try {
        const initData = tg.initData || "";
        const res = await fetch(`${API_BASE}/quizzes/${currentQuizData.id}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'X-Telegram-Init-Data': initData
            },
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
searchInput.oninput = (e) => {
    const query = e.target.value.toLowerCase();
    const items = questionsContainer.querySelectorAll('.question-item');

    items.forEach(item => {
        const text = item.innerText.toLowerCase();
        const index = item.dataset.index;
        if (text.includes(query) || (index + 1).toString() === query) {
            item.style.display = 'flex';
        } else {
            item.style.display = 'none';
        }
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

function showLoader() { loader.style.display = 'flex'; appContainer.style.display = 'none'; }
function hideLoader() { loader.style.display = 'none'; appContainer.style.display = 'block'; }

backBtn.onclick = () => switchView('dashboard');
saveBtn.onclick = saveChanges;

// Start
init();
