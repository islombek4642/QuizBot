// Global error handler for debugging
window.onerror = function (msg, url, line, col, error) {
    const errorMsg = `JavaScript Error: ${msg} \nAt: ${url}:${line}:${col}`;
    console.error(errorMsg);
    if (document.body) {
        // Only show if we are still loading or if app is hidden
        const loader = document.getElementById('loader');
        if (loader && loader.style.display !== 'none') {
            document.body.innerHTML = `
                <div style="background: #1a1a1a; color: #ff5555; padding: 20px; font-family: monospace; height: 100vh; overflow: auto; box-sizing: border-box;">
                    <h2 style="color: white; border-bottom: 1px solid #333; padding-bottom: 10px;">FATAL ERROR ❌</h2>
                    <pre style="white-space: pre-wrap; word-break: break-all; margin-top: 20px; background: #000; padding: 15px; border-radius: 8px;">${errorMsg}\n\n${error ? error.stack : ''}</pre>
                    <button onclick="window.location.reload()" style="margin-top: 20px; padding: 12px 24px; background: #333; color: white; border: none; border-radius: 5px; cursor: pointer;">Retry</button>
                    <p style="margin-top: 30px; font-size: 11px; color: #888;">Debug Version: 33</p>
                </div>
            `;
        }
    }
    return false;
};

const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : {
    expand: () => { },
    ready: () => { },
    showAlert: (m) => alert(m),
    showPopup: (p, cb) => { if (confirm(p.message)) cb('ok'); },
    MainButton: { setText: () => { }, showProgress: () => { }, hideProgress: () => { }, hide: () => { } },
    backgroundColor: '#0f172a',
    platform: 'unknown'
};

const CONFIG = {
    API_BASE: "/api",
    DEFAULT_SPLIT_PARTS: "2",
    DEFAULT_SPLIT_SIZE: "20",
    MAX_QUESTION_LEN: 500,
    MAX_OPTION_LEN: 100,
    THEME_COLORS: {
        bg: '#0f172a'
    }
};

function createRipple(event) {
    const button = event.currentTarget;
    const ripple = document.createElement("span");
    const diameter = Math.max(button.clientWidth, button.clientHeight) * 1.5;
    const radius = diameter / 2;

    ripple.style.width = ripple.style.height = `${diameter}px`;

    // Support both mouse and touch events
    const clientX = event.clientX || (event.touches && event.touches[0].clientX);
    const clientY = event.clientY || (event.touches && event.touches[0].clientY);

    const rect = button.getBoundingClientRect();
    ripple.style.left = `${clientX - rect.left - radius}px`;
    ripple.style.top = `${clientY - rect.top - radius}px`;
    ripple.classList.add("ripple");

    const oldRipple = button.getElementsByClassName("ripple")[0];
    if (oldRipple) oldRipple.remove();

    button.appendChild(ripple);
}

// State
let currentQuizzes = [];
let currentQuizData = null;
let currentView = 'dashboard';
let authToken = null;

function updateEditorCounter() {
    if (currentView !== 'editor') return;
    const count = questionsContainer.querySelectorAll('.question-item').length;
    const countText = ` <span style="font-size: 0.9rem; opacity: 0.8; font-weight: normal;">(${count} ${t('questions_count')})</span>`;
    pageTitle.innerHTML = t('editing_test') + countText;
}

// Elements
let loader, appContainer, quizList, dashboardView, editorView, questionsContainer, pageTitle, backBtn, editorActions, saveBtn, searchInput, splitView, splitQuizList, navDashboard, navSplit, bottomNav, leaderboardView, lbList, navLeaderboard, myRankBar, performanceView, perfHistoryList, navPerformance, rulesModal, rulesClose, showRulesBtn;

function initElements() {
    loader = document.getElementById('loader');
    appContainer = document.getElementById('app');
    quizList = document.getElementById('quiz-list');
    dashboardView = document.getElementById('dashboard');
    editorView = document.getElementById('editor');
    questionsContainer = document.getElementById('questions-container');
    pageTitle = document.getElementById('page-title');
    backBtn = document.getElementById('back-btn');
    editorActions = document.getElementById('editor-actions');
    saveBtn = document.getElementById('save-btn');
    searchInput = document.getElementById('search-input');
    splitView = document.getElementById('split-view');
    splitQuizList = document.getElementById('split-quiz-list');
    navDashboard = document.getElementById('nav-dashboard');
    navSplit = document.getElementById('nav-split');
    bottomNav = document.querySelector('.bottom-nav');
    leaderboardView = document.getElementById('leaderboard');
    lbList = document.getElementById('lb-list');
    navLeaderboard = document.getElementById('nav-leaderboard');
    myRankBar = document.getElementById('my-rank-bar');
    performanceView = document.getElementById('performance');
    perfHistoryList = document.getElementById('perf-history-list');
    navPerformance = document.getElementById('nav-performance');
    rulesModal = document.getElementById('rules-modal');
    rulesClose = document.getElementById('rules-close');
    showRulesBtn = document.getElementById('show-rules-btn');

    // Split Modal Elements
    const splitModal = document.getElementById('split-modal');
    const btnTypeParts = document.getElementById('btn-type-parts');
    const btnTypeSize = document.getElementById('btn-type-size');
    const groupParts = document.getElementById('group-parts');
    const groupSize = document.getElementById('group-size');
    const inputParts = document.getElementById('input-parts');
    const inputSize = document.getElementById('input-size');
    const splitCancel = document.getElementById('split-cancel');
    const splitConfirm = document.getElementById('split-confirm');

    // Confirmation Modal Elements
    const confirmModal = document.getElementById('confirm-modal');
    const confirmTitle = document.getElementById('confirm-modal-title');
    const confirmText = document.getElementById('confirm-modal-text');
    const confirmIcon = document.getElementById('confirm-modal-icon');
    const confirmBtnYes = document.getElementById('confirm-btn-yes');
    const confirmBtnNo = document.getElementById('confirm-btn-no');

    window.showConfirmModal = (options) => {
        confirmTitle.innerText = options.title || 'Are you sure?';
        confirmText.innerText = options.text || '';
        confirmIcon.innerText = options.icon || '❓';
        confirmBtnYes.innerText = options.yesLabel || 'Yes';
        confirmBtnNo.innerText = options.noLabel || 'No';

        if (options.isDanger) confirmBtnYes.classList.add('danger');
        else confirmBtnYes.classList.remove('danger');

        confirmModal.style.display = 'flex';

        confirmBtnYes.onclick = () => {
            confirmModal.style.display = 'none';
            if (options.onConfirm) options.onConfirm();
        };

        confirmBtnNo.onclick = () => {
            confirmModal.style.display = 'none';
            if (options.onCancel) options.onCancel();
        };
    };

    // Attach event listeners safely
    if (searchInput) {
        searchInput.oninput = handleSearch;
    }
    if (backBtn) {
        backBtn.onclick = () => switchView('dashboard');
    }
    if (saveBtn) {
        saveBtn.onclick = saveChanges;
    }
    if (navDashboard) {
        navDashboard.onclick = () => switchView('dashboard');
    }
    if (navSplit) {
        navSplit.onclick = () => {
            if (currentView === 'editor') {
                // If in editor, go back to dashboard first OR just switch
                switchView('split');
            } else {
                switchView('split');
            }
        };
    }

    // Modal Events
    if (btnTypeParts) {
        btnTypeParts.onclick = () => {
            btnTypeParts.classList.add('active');
            btnTypeSize.classList.remove('active');
            groupParts.classList.add('active');
            groupSize.classList.remove('active');
        };
    }
    if (btnTypeSize) {
        btnTypeSize.onclick = () => {
            btnTypeSize.classList.add('active');
            btnTypeParts.classList.remove('active');
            groupSize.classList.add('active');
            groupParts.classList.remove('active');
        };
    }
    if (splitCancel) {
        splitCancel.onclick = () => {
            splitModal.style.display = 'none';
        };
    }
    if (splitConfirm) {
        splitConfirm.onclick = async () => {
            const quizId = splitModal.dataset.quizId;
            const totalCount = parseInt(splitModal.dataset.totalCount);
            const isParts = btnTypeParts.classList.contains('active');

            const paramName = isParts ? 'parts' : 'size';
            const val = parseInt(isParts ? inputParts.value : inputSize.value);

            if (isNaN(val) || val <= 0) return;

            // Validation
            if (paramName === 'size' && val < 10) {
                tg.showAlert(t('error_min_chunk'));
                return;
            }
            if (paramName === 'parts') {
                const size = Math.ceil(totalCount / val);
                if (size < 10) {
                    tg.showAlert(t('error_min_chunk'));
                    return;
                }
            }

            splitModal.style.display = 'none';
            await performSplit(quizId, paramName, val);
        };
    }
    if (navLeaderboard) {
        navLeaderboard.onclick = () => switchView('leaderboard');
    }
    if (navPerformance) {
        navPerformance.onclick = () => switchView('performance');
    }
    if (showRulesBtn) {
        showRulesBtn.onclick = () => rulesModal.style.display = 'flex';
    }
    if (rulesClose) {
        rulesClose.onclick = () => rulesModal.style.display = 'none';
    }

    // Leaderboard Tab Events
    document.querySelectorAll('.lb-tab').forEach(tab => {
        tab.onclick = () => {
            document.querySelectorAll('.lb-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            loadLeaderboard(tab.dataset.period);
        };
    });

    const lbTypeUsers = document.getElementById('lb-type-users');
    const lbTypeGroups = document.getElementById('lb-type-groups');
    if (lbTypeUsers && lbTypeGroups) {
        lbTypeUsers.onclick = () => {
            lbTypeUsers.classList.add('active');
            lbTypeGroups.classList.remove('active');
            renderLeaderboard();
        };
        lbTypeGroups.onclick = () => {
            lbTypeGroups.classList.add('active');
            lbTypeUsers.classList.remove('active');
            renderLeaderboard();
        };
    }
}

function handleSearch(e) {
    const query = e.target.value.toLowerCase().trim();
    if (!questionsContainer) return;

    const items = questionsContainer.querySelectorAll('.question-item');
    const isNumber = /^\d+$/.test(query);

    // Reset highlights
    items.forEach(i => {
        i.classList.remove('highlight-pulse');
        // Force reflow to allow re-triggering animation
        void i.offsetWidth;
    });

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
}


// Helper to get params
function getAuthHeaders() {
    const headers = {};
    let debugSource = "none";
    let initData = "";

    // Debug collection
    const debugKeys = [];

    // 1. Try initData from Telegram Object (Standard)
    if (tg.initData) {
        initData = tg.initData;
        debugSource = "tg.initData";
    }
    // 2. Fallback: Parse from URL (search/hash)
    else {
        // Strategy 0: URL query param (some environments provide tgWebAppData here)
        try {
            const sp = new URLSearchParams(window.location.search);
            if (sp.get('tgWebAppData')) {
                initData = sp.get('tgWebAppData');
                debugSource = "search_params";
            }
        } catch (e) { }

        try {
            const hash = window.location.hash.slice(1);
            let decoded = hash;
            try { decoded = decodeURIComponent(hash); } catch (e) { }

            // Strategy A: Standard tgWebAppData param
            const params = new URLSearchParams(hash);
            if (params.get('tgWebAppData')) {
                initData = params.get('tgWebAppData');
                debugSource = "hash_params";
            }

            // Strategy B: Aggressive "Filtration"
            // If we don't have explicit data, maybe the hash IS the data mixed with meta params.
            // We'll extract everything that looks like an auth param.
            if (!initData) {
                const searchParams = new URLSearchParams(decoded);
                const authParams = [];

                // Known meta params to IGNORE
                const metaKeys = [
                    'tgWebAppVersion',
                    'tgWebAppPlatform',
                    'tgWebAppThemeParams',
                    'tgWebAppBotInline'
                ];

                searchParams.forEach((val, key) => {
                    debugKeys.push(key);
                    if (!metaKeys.includes(key)) {
                        // This implies it's a data param (user, auth_date, hash, query_id, etc)
                        authParams.push(`${key}=${val}`);
                    }
                });

                if (authParams.length > 0) {
                    // Reconstruct into a standard initData string
                    // We join with & but do NOT re-encode, as we want the raw data string format expected by backend
                    initData = authParams.join('&');
                    debugSource = "hash_filtered_reconstruction";
                }
            }

            // Strategy C: Regex fallback (Last Resort)
            if (!initData) {
                const match = hash.match(/tgWebAppData=([^&]+)/);
                if (match && match[1]) {
                    initData = decodeURIComponent(match[1]);
                    debugSource = "hash_regex_fallback";
                }
            }

        } catch (e) {
            console.error("Hash parse error", e);
            window.lastAuthError = e.message;
        }
    }

    if (initData) {
        headers['X-Telegram-Init-Data'] = initData;
        // Optional: docs-compatible auth header
        headers['Authorization'] = `tma ${initData}`;
    }

    // 3. Check for token (Legacy)
    const urlParams = new URLSearchParams(window.location.search);
    if (!headers['X-Telegram-Init-Data'] && urlParams.get('token')) {
        const token = urlParams.get('token');
        headers['X-Auth-Token'] = token;
        if (debugSource === "none") debugSource = "token";

        // Keep token for this session so navigation (e.g. Edit) keeps working even after we strip it from the URL
        try {
            sessionStorage.setItem('legacy_auth_token', token);
        } catch (e) { }

        // Prevent reusing a cached/expired token on reloads
        try {
            if (!window.__tokenStrippedFromUrl) {
                const url = new URL(window.location.href);
                url.searchParams.delete('token');
                window.history.replaceState({}, document.title, url.toString());
                window.__tokenStrippedFromUrl = true;
            }
        } catch (e) { }
    }

    // 4. Legacy token fallback from sessionStorage (when initData is absent and token was stripped)
    if (!headers['X-Telegram-Init-Data'] && !headers['X-Auth-Token']) {
        try {
            const stored = sessionStorage.getItem('legacy_auth_token');
            if (stored) {
                headers['X-Auth-Token'] = stored;
                if (debugSource === "none") debugSource = "token_session";
            }
        } catch (e) { }
    }

    // Store debug info globally
    window.lastAuthDebug = {
        source: debugSource,
        hasHeader: !!headers['X-Telegram-Init-Data'],
        dataLen: headers['X-Telegram-Init-Data'] ? headers['X-Telegram-Init-Data'].length : 0,
        keysFound: debugKeys.join(', '),
        hashPreview: window.location.hash.slice(1, 100) + "...",
        fullHashLen: window.location.hash.length
    };

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
        date_format: "uz-UZ",
        delete_question: "O'chirish",
        add_question: "➕ Savol qo'shish",
        confirm_delete: "Rostdan ham bu savolni o'chirmoqchimisiz?",
        split_quiz: "Bo'lish",
        split_parts: "Testni nechta qismga bo'lmoqchisiz?",
        split_size: "Har bir qismda nechta savol bo'lsin?",
        split_success: "Test muvaffaqiyatli bo'lindi! ✅",
        split_info: "Katta testni kichikroq testlarga bo'lish.",
        split_type_parts: "Qismlar soni bo'yicha",
        split_type_size: "Savollar soni bo'yicha",
        nav_dashboard: "Testlarim",
        nav_split: "...",
        error_min_questions: "Testni bo'lish uchun jami kamida 20 ta savol bo'lishi kerak!",
        error_min_chunk: "Har bir qismda kamida 10 ta savol bo'lishi shart!",
        split_modal_title: "Testni Bo'lish",
        label_type_parts: "Qismlar soni bo'yicha",
        desc_type_parts: "Testni teng qismlarga taqsimlash",
        label_type_size: "Savollar soni bo'yicha",
        desc_type_size: "Har bir qismda nechta savol bo'lishi",
        btn_cancel: "Bekor qilish",
        btn_confirm_split: "Bo'lishni tasdiqlash",
        leaderboard_title: "Reyting 🏆",
        nav_leaderboard: "Reyting",
        lb_users: "Foydalanuvchilar",
        lb_groups: "Guruhlar",
        pts: "ball",
        my_rank: "Sizning o'riningiz",
        lb_total: "Umumiy",
        lb_weekly: "Haftalik",
        lb_daily: "Kunlik",
        nav_performance: "Natijalar",
        results_title: "Mening natijalarim",
        results_history: "Testlar tarixi",
        total_score: "Jami ball",
        rank_label: "O‘rningiz",
        correct_short: "To‘g‘ri",
        errors_short: "Xato",
        rules_modal_title: "Ballar tizimi",
        close_btn: "Tushunarli"
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
        date_format: "en-US",
        delete_question: "Delete",
        add_question: "➕ Add Question",
        confirm_delete: "Are you sure you want to delete this question?",
        split_quiz: "Split",
        split_parts: "How many parts do you want to split into?",
        split_size: "How many questions per part?",
        split_success: "Quiz split successfully! ✅",
        split_info: "Split a large quiz into smaller parts.",
        split_type_parts: "By number of parts",
        split_type_size: "By questions per part",
        nav_dashboard: "My Quizzes",
        nav_split: "...",
        error_min_questions: "A quiz must have at least 20 questions to be split!",
        error_min_chunk: "Each part must have at least 10 questions!",
        split_modal_title: "Split Quiz",
        label_type_parts: "By Parts",
        desc_type_parts: "Divide into equal parts",
        label_type_size: "By Questions",
        desc_type_size: "Questions per part",
        btn_cancel: "Cancel",
        btn_confirm_split: "Confirm Split",
        leaderboard_title: "Leaderboard 🏆",
        nav_leaderboard: "Ranking",
        lb_users: "Users",
        lb_groups: "Groups",
        pts: "pts",
        my_rank: "Your Rank",
        lb_total: "All-time",
        lb_weekly: "Weekly",
        lb_daily: "Daily",
        nav_performance: "Results",
        results_title: "My Results",
        results_history: "Test History",
        total_score: "Total Score",
        rank_label: "Rank",
        correct_short: "Correct",
        errors_short: "Errors",
        rules_modal_title: "Scoring Rules",
        close_btn: "Got it"
    }
};

function t(key) {
    return TRANSLATIONS[lang]?.[key] || TRANSLATIONS['EN'][key] || key;
}

// Initialize
async function init() {
    initElements();
    tg.expand();
    tg.ready();

    // Set theme colors
    document.documentElement.style.setProperty('--bg-color', tg.backgroundColor || '#0f172a');

    // If opened outside Telegram / without auth, show landing immediately (avoid dashboard flash)
    try {
        if (!tg || !tg.platform || tg.platform === 'unknown') {
            console.warn("Telegram WebApp not detected or unknown platform.");
        }

        const headers = getAuthHeaders();
        if (!headers['X-Auth-Token'] && !headers['X-Telegram-Init-Data']) {
            const hash = window.location.hash.slice(1);
            const params = new URLSearchParams(hash);
            if (params.get('tgWebAppData')) headers['X-Telegram-Init-Data'] = params.get('tgWebAppData');
        }
        if (!headers['X-Auth-Token'] && !headers['X-Telegram-Init-Data']) {
            await showAuthRedirect();
            hideLoader();
            return;
        }
    } catch (e) {
        await showAuthRedirect();
        hideLoader();
        return;
    }

    // Set static texts
    if (pageTitle) pageTitle.innerText = t('my_quizzes');

    const labelDashboard = document.getElementById('label-nav-dashboard');
    if (labelDashboard) labelDashboard.innerText = t('nav_dashboard');

    const labelLeaderboard = document.getElementById('label-nav-leaderboard');
    if (labelLeaderboard) labelLeaderboard.innerText = t('nav_leaderboard');

    const labelPerformance = document.getElementById('label-nav-performance');
    if (labelPerformance) labelPerformance.innerText = t('nav_performance');

    const labelSplit = document.getElementById('label-nav-split');
    if (labelSplit) labelSplit.innerText = t('nav_split');

    // Set LB type buttons
    const lbUsersBtn = document.getElementById('lb-type-users');
    if (lbUsersBtn) lbUsersBtn.innerText = "👤 " + t('lb_users');
    const lbGroupsBtn = document.getElementById('lb-type-groups');
    if (lbGroupsBtn) lbGroupsBtn.innerText = "👥 " + t('lb_groups');

    // Localization for split modal
    const elementsToLocalize = {
        'split-modal-title': 'split_modal_title',
        'label-type-parts': 'label_type_parts',
        'desc-type-parts': 'desc_type_parts',
        'label-type-size': 'label_type_size',
        'desc-type-size': 'desc_type_size',
        'split-cancel': 'btn_cancel',
        'split-confirm': 'btn_confirm_split',
        'save-btn': 'save_changes',
        'lb-tab-total': 'lb_total',
        'lb-tab-weekly': 'lb_weekly',
        'lb-tab-daily': 'lb_daily'
    };

    for (const [id, key] of Object.entries(elementsToLocalize)) {
        const el = document.getElementById(id);
        if (el) el.innerText = t(key);
    }

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

        // Guard: If still no auth, show redirect message
        if (!headers['X-Auth-Token'] && !headers['X-Telegram-Init-Data']) {
            console.warn("No auth credentials found, skipping fetch.");
            await showAuthRedirect();
            return;
        }

        const res = await fetch(`${CONFIG.API_BASE}/quizzes`, { headers });

        if (res.status === 401) {
            await showAuthRedirect();
            return;
        }
        if (!res.ok) throw new Error(t('error_load'));

        currentQuizzes = await res.json();
        // Initial render based on current view
        if (currentView === 'split') {
            renderQuizList(splitQuizList, true);
        } else {
            renderQuizList(quizList, false);
        }
    } catch (err) {
        console.error(err);
        showError(err.message);
        hideLoader(); // Ensure loader is hidden even on error
    }
}

function showError(msg) {
    const authStats = window.lastAuthDebug || {};
    const debugInfo = `
        <div style="font-size: 10px; text-align: left; margin-top: 10px; opacity: 0.8; overflow-wrap: break-word; background: rgba(0,0,0,0.2); padding: 10px; border-radius: 5px;">
            <p><strong>Debug Info (v6):</strong></p>
            <p>Source: ${authStats.source}</p>
            <p>Keys Found: ${authStats.keysFound || 'none'}</p>
            <p>Extracted Len: ${authStats.dataLen}</p>
            <p>Hash Preview: ${authStats.hashPreview}</p>
            <p>Platform: ${tg.platform}</p>
            <p style="margin-top:5px; color:#ffaaaa;">Raw Hash (First 200):</p>
            <code style="display:block; font-size:9px; word-break:break-all;">${window.location.hash.slice(1, 201)}</code>
        </div>
    `;

    const debugHTML = `
        <div style="background: var(--bg-color); color: var(--text-color); padding: 20px; text-align: center; height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center;">
            <h3 style="margin-bottom: 10px;">${t('error_title')}</h3>
            <p>${msg}</p>
            <br>
            <button onclick="window.location.reload()" style="padding: 10px 20px; background: var(--button-color); border: none; border-radius: 8px; color: white;">${t('retry')}</button>
            ${debugInfo}
        </div>
    `;
    appContainer.innerHTML = debugHTML;
}

async function showAuthRedirect() {
    appContainer.classList.add('landing');
    let botLink = "https://t.me/comfortquizbot";
    let botUsername = "comfortquizbot";
    let stats = { users: null, quizzes: null, questions: null };

    function normalizeBotLink(rawBotLink, rawBotUsername) {
        const cleanUsername = (rawBotUsername || "").replace("@", "").trim();

        if (!rawBotLink || typeof rawBotLink !== "string") {
            return cleanUsername ? `https://t.me/${cleanUsername}` : "https://t.me";
        }

        let link = rawBotLink.trim();

        // @username yoki username bo'lib kelsa
        if (!link.startsWith("http")) {
            link = link.replace("@", "").trim();
            return `https://t.me/${link}`;
        }

        // https://t.me/@username xato bo'ladi
        link = link.replace("t.me/@", "t.me/");
        return link;
    }

    try {
        const res = await fetch(`${CONFIG.API_BASE}/bot-info`);
        if (res.ok) {
            const data = await res.json();
            botUsername = (data.bot_username ?? botUsername).replace("@", "").trim();
            botLink = normalizeBotLink(data.bot_link ?? botLink, botUsername);
            if (data.stats && typeof data.stats === 'object') {
                stats = {
                    users: typeof data.stats.users === 'number' ? data.stats.users : null,
                    quizzes: typeof data.stats.quizzes === 'number' ? data.stats.quizzes : null,
                    questions: typeof data.stats.questions === 'number' ? data.stats.questions : null,
                };
            }
        }
    } catch (e) {
        console.warn("Failed to fetch bot info:", e);
    }

    const usersTarget = (typeof stats.users === 'number' && Number.isFinite(stats.users)) ? stats.users : null;
    const quizzesTarget = (typeof stats.quizzes === 'number' && Number.isFinite(stats.quizzes)) ? stats.quizzes : null;
    const questionsTarget = (typeof stats.questions === 'number' && Number.isFinite(stats.questions)) ? stats.questions : null;

    const usersLabel = usersTarget === null ? '—' : '0';
    const quizzesLabel = quizzesTarget === null ? '—' : '0';
    const questionsLabel = questionsTarget === null ? '—' : '0';

    window.__openBotLink = function (e) {
        if (e && typeof e.preventDefault === 'function') e.preventDefault();
        try {
            if (window.Telegram && window.Telegram.WebApp && typeof window.Telegram.WebApp.openTelegramLink === 'function') {
                window.Telegram.WebApp.openTelegramLink(botLink);
                return false;
            }
        } catch (_) { }
        window.open(botLink, '_blank');
        return false;
    };

    const landingHTML = `
        <style>
            @keyframes float {
                0%, 100% { transform: translateY(0px) rotate(0deg); }
                50% { transform: translateY(-20px) rotate(5deg); }
            }

            @keyframes pageEnter {
                from {
                    opacity: 0;
                    transform: translateY(16px) scale(0.98);
                }
                to {
                    opacity: 1;
                    transform: translateY(0) scale(1);
                }
            }
            
            @keyframes fadeInUp {
                from {
                    opacity: 0;
                    transform: translateY(50px) scale(0.8);
                }
                to {
                    opacity: 1;
                    transform: translateY(0) scale(1);
                }
            }
            
            @keyframes pulse {
                0%, 100% { transform: scale(1); }
                50% { transform: scale(1.05); }
            }
            
            @keyframes slideInLeft {
                from {
                    opacity: 0;
                    transform: translateX(-100px) rotate(-5deg);
                }
                to {
                    opacity: 1;
                    transform: translateX(0) rotate(0deg);
                }
            }
            
            @keyframes slideInRight {
                from {
                    opacity: 0;
                    transform: translateX(100px) rotate(5deg);
                }
                to {
                    opacity: 1;
                    transform: translateX(0) rotate(0deg);
                }
            }
            
            @keyframes slideInUp {
                from {
                    opacity: 0;
                    transform: translateY(50px) scale(0.9);
                }
                to {
                    opacity: 1;
                    transform: translateY(0) scale(1);
                }
            }
            
            @keyframes glow {
                0%, 100% { 
                    box-shadow: 0 20px 60px rgba(102, 126, 234, 0.3), 0 0 0 1px rgba(255,255,255,0.2);
                    transform: scale(1);
                }
                50% { 
                    box-shadow: 0 25px 70px rgba(102, 126, 234, 0.4), 0 0 0 2px rgba(255,255,255,0.3);
                    transform: scale(1.02);
                }
            }
            
            @keyframes titleGlow {
                0%, 100% { 
                    text-shadow: 0 4px 8px rgba(102, 126, 234, 0.3), 0 0 30px rgba(102, 126, 234, 0.2);
                }
                50% { 
                    text-shadow: 0 6px 12px rgba(102, 126, 234, 0.4), 0 0 40px rgba(102, 126, 234, 0.3);
                }
            }
            
            @keyframes numberPulse {
                0%, 100% { 
                    transform: scale(1);
                    text-shadow: 0 0 20px rgba(255,255,255,0.3);
                }
                50% { 
                    transform: scale(1.05);
                    text-shadow: 0 0 30px rgba(255,255,255,0.5);
                }
            }
            
            @keyframes iconBounce {
                0%, 20%, 50%, 80%, 100% { transform: translateY(0); }
                40% { transform: translateY(-10px); }
                60% { transform: translateY(-5px); }
            }
            
            .floating {
                animation: float 3s ease-in-out infinite;
            }
            
            .fade-in-up {
                animation: fadeInUp 0.8s ease-out;
            }
            
            .pulse {
                animation: pulse 2s ease-in-out infinite;
            }
            
            .slide-in-left {
                animation: slideInLeft 0.6s ease-out;
            }
            
            .slide-in-right {
                animation: slideInRight 0.6s ease-out;
            }
            
            .feature-card {
                transition: all 0.3s ease;
                cursor: pointer;
            }
            
            .feature-card:hover {
                transform: translateY(-5px);
                box-shadow: 0 10px 25px rgba(0,0,0,0.2);
            }
            
            .cta-button {
                transition: all 0.3s ease;
                position: relative;
                overflow: hidden;
            }
            
            .cta-button:hover {
                transform: translateY(-2px);
                box-shadow: 0 8px 25px rgba(0,0,0,0.3);
            }
            
            .cta-button::before {
                content: '';
                position: absolute;
                top: 0;
                left: -100%;
                width: 100%;
                height: 100%;
                background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
                transition: left 0.5s;
            }
            
            .cta-button:hover::before {
                left: 100%;
            }
            
            .stat-number {
                font-size: 2.5rem;
                font-weight: bold;
                background: linear-gradient(45deg, #fff, #f0f0f0);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }
            
            @media (min-width: 1401px) {
                .landing-container {
                    max-width: 1400px !important;
                }
                
                .features-grid {
                    grid-template-columns: repeat(3, 1fr) !important;
                }
                
                .main-title {
                    font-size: 4rem !important;
                }
                
                .subtitle {
                    font-size: 1.8rem !important;
                }
            }
            
            @media (min-width: 1201px) and (max-width: 1400px) {
                .landing-container {
                    max-width: 1200px !important;
                }
                
                .features-grid {
                    grid-template-columns: repeat(3, 1fr) !important;
                }
                
                .main-title {
                    font-size: 3.8rem !important;
                }
                
                .subtitle {
                    font-size: 1.6rem !important;
                }
            }
            
            @media (max-width: 1200px) {
                .landing-container {
                    max-width: 1000px !important;
                }
                
                .features-grid {
                    grid-template-columns: repeat(2, 1fr) !important;
                }
                
                .main-title {
                    font-size: 3.2rem !important;
                }
                
                .subtitle {
                    font-size: 1.4rem !important;
                }
            }
            
            @media (max-width: 768px) {
                .landing-container {
                    padding: 20px 15px !important;
                    max-width: 100% !important;
                }
                
                .main-title {
                    font-size: 2.8rem !important;
                }
                
                .subtitle {
                    font-size: 1.3rem !important;
                }
                
                .features-grid {
                    grid-template-columns: 1fr !important;
                    gap: 30px !important;
                }
                
                .cta-button {
                    padding: 20px 45px !important;
                    font-size: 1.2rem !important;
                }
                
                .stat-number {
                    font-size: 2.5rem !important;
                }
                
                .logo-container {
                    width: 100px !important;
                    height: 100px !important;
                    font-size: 50px !important;
                }
            }
            
            @media (max-width: 480px) {
                .main-title {
                    font-size: 2.2rem !important;
                }
                
                .logo-container {
                    width: 80px !important;
                    height: 80px !important;
                    font-size: 40px !important;
                }
                
                .stat-number {
                    font-size: 2.2rem !important;
                }
                
                .subtitle {
                    font-size: 1.1rem !important;
                }
            }
        </style>
        
        <div style="background: transparent; color: white; padding: 0; text-align: center; min-height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; position: relative; overflow-x: hidden; width: 100%; animation: pageEnter 520ms ease-out both;">
            <!-- Animated Background Particles -->
            <div style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: 0; pointer-events: none;">
                <div style="position: absolute; top: 10%; left: 5%; width: 80px; height: 80px; background: radial-gradient(circle, rgba(102, 126, 234, 0.3) 0%, transparent 70%); border-radius: 50%; animation: float 6s ease-in-out infinite;"></div>
                <div style="position: absolute; top: 20%; right: 10%; width: 60px; height: 60px; background: radial-gradient(circle, rgba(118, 75, 162, 0.25) 0%, transparent 70%); border-radius: 50%; animation: float 8s ease-in-out infinite 1s;"></div>
                <div style="position: absolute; top: 60%; left: 15%; width: 100px; height: 100px; background: radial-gradient(circle, rgba(240, 147, 251, 0.2) 0%, transparent 70%); border-radius: 50%; animation: float 10s ease-in-out infinite 2s;"></div>
                <div style="position: absolute; top: 80%; right: 20%; width: 40px; height: 40px; background: radial-gradient(circle, rgba(102, 126, 234, 0.35) 0%, transparent 70%); border-radius: 50%; animation: float 7s ease-in-out infinite 3s;"></div>
                <div style="position: absolute; top: 30%; left: 80%; width: 70px; height: 70px; background: radial-gradient(circle, rgba(118, 75, 162, 0.3) 0%, transparent 70%); border-radius: 50%; animation: float 9s ease-in-out infinite 4s;"></div>
                <div style="position: absolute; top: 50%; right: 5%; width: 90px; height: 90px; background: radial-gradient(circle, rgba(240, 147, 251, 0.25) 0%, transparent 70%); border-radius: 50%; animation: float 11s ease-in-out infinite 5s;"></div>
            </div>
            
            <div class="landing-container" style="width: 100%; max-width: none; margin: 0; position: relative; z-index: 1; padding: 20px; box-sizing: border-box; display: flex; flex-direction: column; align-items: center; justify-content: center;">
                <!-- Logo/Icon -->
                <div class="logo-container floating" style="width: 140px; height: 140px; background: linear-gradient(135deg, rgba(102, 126, 234, 0.9), rgba(118, 75, 162, 0.9), rgba(240, 147, 251, 0.9)); border-radius: 35px; display: flex; align-items: center; justify-content: center; margin: 0 auto 40px; font-size: 70px; backdrop-filter: blur(15px); box-shadow: 0 20px 60px rgba(102, 126, 234, 0.3), 0 0 0 1px rgba(255,255,255,0.2); animation: glow 3s ease-in-out infinite alternate;">
                    🎯
                </div>
                
                <!-- Main Title -->
                <h1 class="main-title fade-in-up" style="font-size: clamp(2.5rem, 6vw, 5rem); margin-bottom: 30px; font-weight: 800; text-shadow: 0 4px 8px rgba(102, 126, 234, 0.3), 0 0 30px rgba(102, 126, 234, 0.2); letter-spacing: -0.02em; background: linear-gradient(45deg, #fff, #f0f4ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; animation: titleGlow 4s ease-in-out infinite alternate;">
                    Comfort Quiz - Bot
                </h1>
                
                <!-- Subtitle -->
                <p class="subtitle fade-in-up" style="font-size: clamp(1.2rem, 3vw, 1.8rem); margin-bottom: 50px; opacity: 0.95; line-height: 1.7; animation-delay: 0.2s; max-width: 800px; margin-left: auto; margin-right: auto; font-weight: 300; text-shadow: 0 2px 4px rgba(0,0,0,0.2);">
                    Telegram'da interaktiv testlar yarating va boshqaring
                </p>
                
                <!-- Stats Section -->
                <div class="fade-in-up" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 40px; margin-bottom: 60px; animation-delay: 0.4s; width: 100%; max-width: 1200px;">
                    <div class="stat-card" style="text-align: center; padding: 35px; background: linear-gradient(135deg, rgba(102, 126, 234, 0.15), rgba(118, 75, 162, 0.1)); border-radius: 25px; backdrop-filter: blur(15px); border: 1px solid rgba(255,255,255,0.2); transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); animation: slideInUp 0.8s ease-out 0.4s both;">
                        <div class="stat-number js-count" data-target="${usersTarget ?? ''}" style="font-size: clamp(2rem, 5vw, 3.5rem); margin-bottom: 15px; font-weight: 800; background: linear-gradient(45deg, #fff, #e0e7ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; text-shadow: 0 0 20px rgba(255,255,255,0.3); animation: numberPulse 2s ease-in-out infinite;">${usersLabel}</div>
                        <p style="margin: 0; opacity: 0.9; font-size: clamp(0.9rem, 2vw, 1.2rem); font-weight: 600;">Foydalanuvchi</p>
                    </div>
                    <div class="stat-card" style="text-align: center; padding: 35px; background: linear-gradient(135deg, rgba(118, 75, 162, 0.15), rgba(240, 147, 251, 0.1)); border-radius: 25px; backdrop-filter: blur(15px); border: 1px solid rgba(255,255,255,0.2); transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); animation: slideInUp 0.8s ease-out 0.6s both;">
                        <div class="stat-number js-count" data-target="${quizzesTarget ?? ''}" style="font-size: clamp(2rem, 5vw, 3.5rem); margin-bottom: 15px; font-weight: 800; background: linear-gradient(45deg, #fff, #e0e7ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; text-shadow: 0 0 20px rgba(255,255,255,0.3); animation: numberPulse 2s ease-in-out infinite 0.3s;">${quizzesLabel}</div>
                        <p style="margin: 0; opacity: 0.9; font-size: clamp(0.9rem, 2vw, 1.2rem); font-weight: 600;">Testlar</p>
                    </div>
                    <div class="stat-card" style="text-align: center; padding: 35px; background: linear-gradient(135deg, rgba(240, 147, 251, 0.15), rgba(102, 126, 234, 0.1)); border-radius: 25px; backdrop-filter: blur(15px); border: 1px solid rgba(255,255,255,0.2); transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); animation: slideInUp 0.8s ease-out 0.8s both;">
                        <div class="stat-number js-count" data-target="${questionsTarget ?? ''}" style="font-size: clamp(2rem, 5vw, 3.5rem); margin-bottom: 15px; font-weight: 800; background: linear-gradient(45deg, #fff, #e0e7ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; text-shadow: 0 0 20px rgba(255,255,255,0.3); animation: numberPulse 2s ease-in-out infinite 0.6s;">${questionsLabel}</div>
                        <p style="margin: 0; opacity: 0.9; font-size: clamp(0.9rem, 2vw, 1.2rem); font-weight: 600;">Savollar</p>
                    </div>
                </div>
                
                <!-- Features -->
                <div class="features-grid fade-in-up" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 40px; margin-bottom: 60px; animation-delay: 0.6s; width: 100%; max-width: 1400px;">
                    <div class="feature-card slide-in-left" style="background: linear-gradient(135deg, rgba(102, 126, 234, 0.12), rgba(118, 75, 162, 0.08)); padding: 45px; border-radius: 30px; backdrop-filter: blur(15px); animation-delay: 0.8s; min-height: 250px; border: 1px solid rgba(255,255,255,0.15); transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); animation: slideInUp 0.8s ease-out 1s both;">
                        <div style="font-size: 4rem; margin-bottom: 25px; animation: iconBounce 2s ease-in-out infinite;">📝</div>
                        <h3 style="margin: 0 0 20px 0; font-size: clamp(1.2rem, 3vw, 1.6rem); font-weight: 700;">Test Yaratish</h3>
                        <p style="margin: 0; font-size: clamp(0.9rem, 2vw, 1.1rem); opacity: 0.85; line-height: 1.7; font-weight: 300;">Intuitiv interfeys bilan oson va tez test tuzish</p>
                    </div>
                    <div class="feature-card" style="background: linear-gradient(135deg, rgba(118, 75, 162, 0.12), rgba(240, 147, 251, 0.08)); padding: 45px; border-radius: 30px; backdrop-filter: blur(15px); animation-delay: 1s; min-height: 250px; border: 1px solid rgba(255,255,255,0.15); transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); animation: slideInUp 0.8s ease-out 1.2s both;">
                        <div style="font-size: 4rem; margin-bottom: 25px; animation: iconBounce 2s ease-in-out infinite 0.2s;">🤖</div>
                        <h3 style="margin: 0 0 20px 0; font-size: clamp(1.2rem, 3vw, 1.6rem); font-weight: 700;">AI Yordam</h3>
                        <p style="margin: 0; font-size: clamp(0.9rem, 2vw, 1.1rem); opacity: 0.85; line-height: 1.7; font-weight: 300;">AI bilan avtomatik savollar generatsiyasi</p>
                    </div>
                    <div class="feature-card slide-in-right" style="background: linear-gradient(135deg, rgba(240, 147, 251, 0.12), rgba(102, 126, 234, 0.08)); padding: 45px; border-radius: 30px; backdrop-filter: blur(15px); animation-delay: 1.2s; min-height: 250px; border: 1px solid rgba(255,255,255,0.15); transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); animation: slideInUp 0.8s ease-out 1.4s both;">
                        <div style="font-size: 4rem; margin-bottom: 25px; animation: iconBounce 2s ease-in-out infinite 0.4s;">📊</div>
                        <h3 style="margin: 0 0 20px 0; font-size: clamp(1.2rem, 3vw, 1.6rem); font-weight: 700;">Analitika</h3>
                        <p style="margin: 0; font-size: clamp(0.9rem, 2vw, 1.1rem); opacity: 0.85; line-height: 1.7; font-weight: 300;">Test natijalarini batafsil tahlil qilish</p>
                    </div>
                </div>
                
                <!-- CTA Button -->
                <div class="fade-in-up pulse" style="animation-delay: 1.6s; margin-bottom: 50px;">
                    <a href="${botLink}" target="_blank" rel="noopener noreferrer" onclick="return window.__openBotLink(event)" class="cta-button" style="display: inline-block; padding: 30px 70px; background: linear-gradient(135deg, #fff, #f8faff); color: #667eea; text-decoration: none; border-radius: 30px; font-weight: 700; font-size: clamp(1.2rem, 3vw, 1.5rem); box-shadow: 0 20px 50px rgba(102, 126, 234, 0.4), 0 0 0 2px rgba(255,255,255,0.3); position: relative; overflow: hidden; transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); animation: slideInUp 0.8s ease-out 1.6s both;">
                        🚀 Botga o'tish
                    </a>
                </div>
                
                <!-- Additional Info -->
                <div class="fade-in-up" style="animation-delay: 1.8s; max-width: 800px; margin-left: auto; margin-right: auto;">
                    <p style="opacity: 0.9; font-size: clamp(1rem, 2.5vw, 1.3rem); margin-bottom: 30px; font-weight: 300; text-shadow: 0 2px 4px rgba(0,0,0,0.2);">
                        💡 <strong>@${botUsername}</strong> orqali to'liq imkoniyatlardan foydalaning
                    </p>
                    
                    <!-- Trust Badges -->
                    <div style="display: flex; justify-content: center; gap: 30px; flex-wrap: wrap; margin-bottom: 40px;">
                        <div class="badge" style="background: linear-gradient(135deg, rgba(102, 126, 234, 0.15), rgba(118, 75, 162, 0.1)); padding: 18px 30px; border-radius: 35px; backdrop-filter: blur(15px); font-size: clamp(0.9rem, 2vw, 1.1rem); border: 1px solid rgba(255,255,255,0.2); transition: all 0.3s ease; animation: slideInUp 0.8s ease-out 1.8s both;">
                            ✅ 24/7 Ishlaydi
                        </div>
                        <div class="badge" style="background: linear-gradient(135deg, rgba(118, 75, 162, 0.15), rgba(240, 147, 251, 0.1)); padding: 18px 30px; border-radius: 35px; backdrop-filter: blur(15px); font-size: clamp(0.9rem, 2vw, 1.1rem); border: 1px solid rgba(255,255,255,0.2); transition: all 0.3s ease; animation: slideInUp 0.8s ease-out 2s both;">
                            🆓 Bepul
                        </div>
                        <div class="badge" style="background: linear-gradient(135deg, rgba(240, 147, 251, 0.15), rgba(102, 126, 234, 0.1)); padding: 18px 30px; border-radius: 35px; backdrop-filter: blur(15px); font-size: clamp(0.9rem, 2vw, 1.1rem); border: 1px solid rgba(255,255,255,0.2); transition: all 0.3s ease; animation: slideInUp 0.8s ease-out 2.2s both;">
                            📈 1000+ Test/kun
                        </div>
                    </div>
                    
                    <!-- Telegram Badge -->
                    <div class="telegram-badge" style="background: linear-gradient(135deg, rgba(102, 126, 234, 0.2), rgba(118, 75, 162, 0.15)); padding: 20px 40px; border-radius: 40px; display: inline-block; backdrop-filter: blur(15px); border: 1px solid rgba(255,255,255,0.25); transition: all 0.4s ease; animation: slideInUp 0.8s ease-out 2.4s both;">
                        <span style="opacity: 0.9; font-size: clamp(0.9rem, 2vw, 1.1rem);">Powered by</span> 
                        <strong style="margin-left: 15px; font-size: clamp(1rem, 2.5vw, 1.4rem);">Telegram</strong>
                    </div>
                </div>
            </div>
        </div>
    `;
    appContainer.innerHTML = landingHTML;

    // Count-up animation for landing stats
    const animateCount = (el, target) => {
        const duration = 1400;
        const startAt = performance.now() + 180;

        const formatDuring = (n) => {
            try {
                return new Intl.NumberFormat('en').format(n);
            } catch (_) {
                return String(n);
            }
        };

        const formatFinal = (n) => {
            try {
                return new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(n);
            } catch (_) {
                return String(n);
            }
        };

        const step = (now) => {
            if (now < startAt) {
                requestAnimationFrame(step);
                return;
            }

            const t = Math.min(1, (now - startAt) / duration);
            const eased = 1 - Math.pow(1 - t, 3);
            const value = Math.round(target * eased);
            el.textContent = formatDuring(value);
            if (t < 1) {
                requestAnimationFrame(step);
            } else {
                el.textContent = formatFinal(target);
            }
        };

        requestAnimationFrame(step);
    };

    const nodes = appContainer.querySelectorAll('.js-count');
    nodes.forEach((el) => {
        const raw = el.getAttribute('data-target');
        const target = raw === null || raw === '' ? NaN : Number(raw);
        if (!Number.isFinite(target) || target < 0) return;
        animateCount(el, target);
    });
}

function renderQuizList(targetList, isSplitMode = false) {
    appContainer.classList.remove('landing');
    targetList.innerHTML = '';

    // Update quiz count in header title
    const countText = ` (${currentQuizzes.length} / 50)`;
    if (pageTitle) {
        // Only append if it's the dashboard/split view and not already there
        const baseTitle = isSplitMode ? t('nav_split') : t('my_quizzes');
        pageTitle.innerText = baseTitle + countText;
    }

    if (currentQuizzes.length === 0) {
        document.getElementById('no-quizzes').style.display = 'block';
    } else {
        document.getElementById('no-quizzes').style.display = 'none';
    }

    // Flag to only wiggle once per refresh
    const shouldWiggle = !window._hasWiggled;

    currentQuizzes.forEach((quiz, idx) => {
        const wrapper = document.createElement('div');
        wrapper.className = 'quiz-card-wrapper entrance-anim';
        wrapper.style.animationDelay = `${idx * 0.05}s`;
        wrapper.style.opacity = '0'; // Initial state for anim

        wrapper.innerHTML = `
                <div class="quiz-card-swipe-actions">
                    <div class="swipe-action action-download" onclick="confirmDownload(${quiz.id}, '${escapeHtml(quiz.title)}'); createRipple(event)">
                        <span>📥</span>
                        <span>Yuklayman</span>
                    </div>
                    <div class="swipe-action action-delete" onclick="confirmDelete(${quiz.id}, '${escapeHtml(quiz.title)}'); createRipple(event)">
                        <span>🗑️</span>
                        <span>O'chiraman</span>
                    </div>
                </div>
            <div class="quiz-card glass" id="quiz-card-${quiz.id}">
                <div class="quiz-card-content">
                    <h3 style="margin-bottom: 8px;">${escapeHtml(quiz.title)}</h3>
                    <p style="opacity: 0.8; font-size: 0.85rem;">
                        <span style="color: var(--accent-color); font-weight: 600;">${quiz.questions_count}</span> ${t('questions_count')} • ${new Date(quiz.created_at).toLocaleDateString(t('date_format'))}
                    </p>
                </div>
                <div class="quiz-card-actions" style="gap: 10px;">
                    <button class="secondary-btn" onclick="openEditor(${quiz.id})" style="flex: 1; min-width: 0; font-size: 0.8rem;">
                       📝 ${t('editing_test')}
                    </button>
                    <button class="secondary-btn" onclick="requestSplit(${quiz.id}, ${quiz.questions_count})" style="flex: 1; min-width: 0; font-size: 0.8rem; border-color: rgba(255,255,255,0.2); color: #fff; background: rgba(255,255,255,0.05);">
                       ✂️ ${t('split_quiz')}
                    </button>
                </div>
            </div>
        `;

        // Add Swipe listeners
        const cardEl = wrapper.querySelector('.quiz-card');
        addSwipeListeners(cardEl, wrapper);

        // Add Wiggle Hint to first 2 cards
        if (shouldWiggle && idx < 2) {
            setTimeout(() => {
                cardEl.classList.add('wiggle-hint');
                setTimeout(() => cardEl.classList.remove('wiggle-hint'), 1000);
            }, 500 + (idx * 200));
        }

        targetList.appendChild(wrapper);
    });

    if (shouldWiggle && currentQuizzes.length > 0) window._hasWiggled = true;
}

function addSwipeListeners(el, wrapper) {
    let startX = 0;
    let currentX = 0;
    let isSwiping = false;

    el.addEventListener('touchstart', (e) => {
        startX = e.touches[0].clientX;
        isSwiping = true;
        wrapper.classList.add('swiping');
    }, { passive: true });

    el.addEventListener('touchmove', (e) => {
        if (!isSwiping) return;
        currentX = e.touches[0].clientX;
        const diff = currentX - startX;

        if (Math.abs(diff) > 20) {
            const move = Math.max(-100, Math.min(100, diff));
            el.style.transform = `translateX(${move}px)`;
        }
    }, { passive: true });

    el.addEventListener('touchend', (e) => {
        isSwiping = false;
        wrapper.classList.remove('swiping');

        const diff = currentX - startX;
        el.style.transition = 'transform 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275)';

        if (diff > 80) {
            el.style.transform = 'translateX(80px)';
            wrapper.classList.add('active-swipe');
        } else if (diff < -80) {
            el.style.transform = 'translateX(-80px)';
            wrapper.classList.add('active-swipe');
        } else {
            el.style.transform = 'translateX(0)';
            wrapper.classList.remove('active-swipe');
        }

        setTimeout(() => {
            el.style.transition = 'transform 0.2s ease-out';
        }, 500);
    });

    // Close on click or interaction
    const closeAction = () => {
        el.style.transform = 'translateX(0)';
        wrapper.classList.remove('active-swipe');
    };

    el.addEventListener('click', () => {
        if (wrapper.classList.contains('active-swipe')) {
            closeAction();
        }
    });
}

/**
 * Action Helpers
 */
function confirmDelete(quizId, title) {
    showConfirmModal({
        title: 'Testni o\'chirish',
        text: `"${title}" testini va uning barcha natijalarini o'chirib tashlamoqchimisiz?`,
        icon: '🗑️',
        yesLabel: 'O\'chirish',
        noLabel: 'Orqaga',
        isDanger: true,
        onConfirm: async () => {
            await deleteQuiz(quizId);
        },
        onCancel: () => {
            document.getElementById(`quiz-card-${quizId}`).style.transform = 'translateX(0)';
        }
    });
}

function confirmDownload(quizId, title) {
    showConfirmModal({
        title: 'Yuklab olish',
        text: `"${title}" testini Word (.docx) formatida shaxsiy xabaringizga yuboraylikmi?`,
        icon: '📥',
        yesLabel: 'Ha, yuboring',
        noLabel: 'Yo\'q',
        onConfirm: async () => {
            await downloadQuiz(quizId);
        },
        onCancel: () => {
            document.getElementById(`quiz-card-${quizId}`).style.transform = 'translateX(0)';
        }
    });
}

async function deleteQuiz(quizId) {
    try {
        const headers = getAuthHeaders();
        const res = await fetch(`${CONFIG.API_BASE}/quizzes/${quizId}`, {
            method: 'DELETE',
            headers: headers
        });

        if (res.ok) {
            tg.showAlert('Test muvaffaqiyatli o\'chirildi! 🗑️✅');
            // Reload list
            await loadQuizzes();
        } else {
            const data = await res.json();
            tg.showAlert('Xatolik: ' + (data.detail || 'O\'chirib bo\'lmadi'));
        }
    } catch (e) {
        tg.showAlert('Tarmoq xatosi: ' + e.message);
    }
}

async function downloadQuiz(quizId) {
    try {
        const headers = getAuthHeaders();
        const res = await fetch(`${CONFIG.API_BASE}/quizzes/${quizId}/download`, {
            method: 'POST',
            headers: headers
        });

        if (res.ok) {
            tg.showAlert('Fayl botdagi shaxsiy xabaringizga yuborildi! 📄✅');
        } else {
            const data = await res.json();
            tg.showAlert('Xatolik: ' + (data.detail || 'Faylni yuborib bo\'lmadi'));
        }
    } catch (e) {
        tg.showAlert('Tarmoq xatosi: ' + e.message);
    } finally {
        const card = document.getElementById(`quiz-card-${quizId}`);
        if (card) card.style.transform = 'translateX(0)';
    }
}

/**
 * Quiz Splitting logic
 */
async function requestSplit(quizId, totalCount) {
    if (totalCount < 20) {
        tg.showAlert(t('error_min_questions'));
        return;
    }

    const splitModal = document.getElementById('split-modal');
    splitModal.dataset.quizId = quizId;
    splitModal.dataset.totalCount = totalCount;
    splitModal.style.display = 'flex';
}

async function performSplit(quizId, paramName, val) {
    const body = {};
    body[paramName] = val;

    showLoader();
    try {
        const headers = getAuthHeaders();
        headers['Content-Type'] = 'application/json';
        const res = await fetch(`${CONFIG.API_BASE}/quizzes/${quizId}/split`, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(body)
        });

        if (!res.ok) {
            const data = await res.json();
            throw new Error(data.detail || t('error_save'));
        }

        tg.showAlert(t('split_success'));
        await loadQuizzes(); // Refresh list
    } catch (err) {
        console.error(err);
        tg.showAlert(err.message);
    } finally {
        hideLoader();
    }
}

async function openEditor(quizId) {
    showLoader();
    try {
        const headers = getAuthHeaders();
        const res = await fetch(`${CONFIG.API_BASE}/quizzes/${quizId}`, {
            headers: headers
        });
        if (res.status === 401) {
            await showAuthRedirect();
            return;
        }
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
    if (typeof text !== 'string') return String(text || "");
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
    limit = limit || CONFIG.MAX_QUESTION_LEN;
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

// New Helper: Collect current state from DOM to memory
function collectCurrentState() {
    const updatedQuestions = [];
    const items = questionsContainer.querySelectorAll('.question-item');
    items.forEach(item => {
        const qInput = item.querySelector('.q-text');
        const options = [];
        const optionInputs = item.querySelectorAll('.option-input');

        optionInputs.forEach(optInput => {
            options.push(optInput.value);
        });

        // Although inputs might be empty, we save them as is. Validation happens on Save.
        updatedQuestions.push({
            question: qInput.value,
            options: options,
            // Keep existing ID or default to 0. 
            // NOTE: In this UI, 1st option is ALWAYS correct.
            correct_option_id: 0
        });
    });
    currentQuizData.questions = updatedQuestions;
}

function deleteQuestion(index) {
    showConfirmModal({
        title: t('delete_question'),
        text: t('confirm_delete'),
        icon: '🗑️',
        isDanger: true,
        onConfirm: () => {
            collectCurrentState();
            currentQuizData.questions.splice(index, 1);
            renderEditor();
        }
    });
}

function addQuestion() {
    const count = questionsContainer.querySelectorAll('.question-item').length;
    if (count >= 50) {
        tg.showAlert('Sizda maksimal 50 ta savol bo\'lishi mumkin!');
        return;
    }

    collectCurrentState();
    currentQuizData.questions.push({
        question: "",
        options: ["", "", "", ""], // Default 4 empty options
        correct_option_id: 0
    });
    renderEditor();

    // Scroll to bottom after render
    setTimeout(() => {
        window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
    }, 100);
}

function renderEditor() {
    questionsContainer.innerHTML = '';
    pageTitle.innerText = t('editing_test');

    if (!currentQuizData || !currentQuizData.questions) return;

    currentQuizData.questions.forEach((q, index) => {
        if (!q) return;
        const item = document.createElement('div');
        item.className = 'question-item glass';
        item.dataset.index = index;

        const safeQuestion = escapeHtml(q.question || "");
        const qLen = q.question ? q.question.length : 0;
        const options = q.options || ["", "", "", ""];

        item.innerHTML = `
            <div class="q-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <span class="q-label">${t('question_label')}${index + 1}</span>
                <button class="delete-btn" style="background: #ef4444; border: none; padding: 5px 10px; border-radius: 5px; color: white; cursor: pointer; font-size: 12px;" onclick="deleteQuestion(${index})">
                    🗑 ${t('delete_question')}
                </button>
            </div>
            <div class="input-group">
                <textarea class="q-text" placeholder="${t('question_placeholder')}">${safeQuestion}</textarea>
                <small class="char-count">${qLen}/300</small>
            </div>
            <div class="options-grid">
                ${options.map((opt, optIndex) => {
            const safeOpt = escapeHtml(opt || "");
            const optLen = opt ? opt.length : 0;
            return `
                    <div class="option-row ${optIndex === (q.correct_option_id || 0) ? 'correct' : 'wrong'}">
                        <div class="indicator">${optIndex === 0 ? '✓' : '✗'}</div>
                        <div class="input-group">
                            <input type="text" class="option-input" value="${safeOpt}" placeholder="${t('option_placeholder')} ${optIndex + 1}">
                            <small class="char-count">${optLen}/100</small>
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

    updateEditorCounter();

    // Add "Add Question" button at the end
    const addBtnContainer = document.createElement('div');
    addBtnContainer.style.textAlign = 'center';
    addBtnContainer.style.marginTop = '20px';
    addBtnContainer.style.marginBottom = '40px'; // Space for fixed footer

    const addBtn = document.createElement('button');
    addBtn.className = 'add-btn';
    addBtn.innerHTML = t('add_question');
    addBtn.style.cssText = "background: var(--button-color); border: none; padding: 12px 24px; border-radius: 8px; color: white; cursor: pointer; font-size: 14px; font-weight: bold; width: 100%; max-width: 300px;";
    addBtn.onclick = addQuestion;

    addBtnContainer.appendChild(addBtn);
    questionsContainer.appendChild(addBtnContainer);
}

async function saveChanges() {
    tg.MainButton.showProgress();

    // Collect data (Validation happens here now)
    const items = questionsContainer.querySelectorAll('.question-item');
    const updatedQuestions = [];
    let hasError = false;

    items.forEach(item => {
        const qInput = item.querySelector('.q-text');

        // Use shared validation logic
        if (!validateInput(qInput, CONFIG.MAX_QUESTION_LEN)) {
            hasError = true;
        }

        const options = [];
        const optionInputs = item.querySelectorAll('.option-input');

        optionInputs.forEach(optInput => {
            if (!validateInput(optInput, CONFIG.MAX_OPTION_LEN)) {
                hasError = true;
            }
            options.push(optInput.value.trim()); // Trim on save
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

        const res = await fetch(`${CONFIG.API_BASE}/quizzes/${currentQuizData.id}`, {
            method: 'PUT',
            headers: headers,
            body: JSON.stringify({
                title: currentQuizData.title,
                questions: updatedQuestions
            })
        });

        if (res.status === 401) {
            await showAuthRedirect();
            return;
        }

        if (!res.ok) throw new Error(t('error_save'));

        tg.showAlert(t('success_save'));
        // Update local data and Refresh Dashboard
        await loadQuizzes();
        setTimeout(() => switchView('dashboard'), 1000);
    } catch (err) {
        console.error(err);
        tg.showAlert(t('error_save'));
    } finally {
        tg.MainButton.hideProgress();
    }
}


function switchView(view) {
    currentView = view;
    console.log("Switching view to:", view);

    // UI Reset - Hide all sections
    const views = ['dashboard', 'split-view', 'editor', 'leaderboard'];
    views.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = 'none';
    });

    if (backBtn) backBtn.style.display = 'none';
    if (editorActions) editorActions.style.display = 'none';
    if (bottomNav) bottomNav.style.display = 'flex';

    // Reset Nav
    if (navDashboard) navDashboard.classList.remove('active');
    if (navLeaderboard) navLeaderboard.classList.remove('active');
    if (navSplit) navSplit.classList.remove('active');

    if (view === 'dashboard') {
        if (dashboardView) dashboardView.style.display = 'grid';
        if (pageTitle) pageTitle.innerText = t('my_quizzes');
        if (navDashboard) navDashboard.classList.add('active');
        renderQuizList(quizList, false);
    } else if (view === 'split') {
        if (splitView) splitView.style.display = 'grid';
        if (pageTitle) pageTitle.innerText = t('nav_split');
        if (navSplit) navSplit.classList.add('active');
        renderQuizList(splitQuizList, true);
    } else if (view === 'editor') {
        if (editorView) editorView.style.display = 'block';
        if (backBtn) backBtn.style.display = 'block';
        if (editorActions) editorActions.style.display = 'block';
        if (bottomNav) bottomNav.style.display = 'none';
        if (pageTitle) pageTitle.innerText = t('editing_test');
        // CRITICAL FIX: Trigger rendering
        renderEditor();
    } else if (view === 'leaderboard') {
        if (leaderboardView) leaderboardView.style.display = 'block';
        if (pageTitle) pageTitle.innerText = t('leaderboard_title');
        if (navLeaderboard) navLeaderboard.classList.add('active');

        // Ensure "Total" tab is marked active visually
        document.querySelectorAll('.lb-tab').forEach(t => {
            if (t.dataset.period === 'total') t.classList.add('active');
            else t.classList.remove('active');
        });

        loadLeaderboard('total');
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

// === Leaderboard Logic ===
let lbData = null;
async function loadLeaderboard(period = 'total') {
    lbList.innerHTML = '<div class="lb-loader"><div class="spinner"></div></div>';
    myRankBar.style.display = 'none';

    try {
        const headers = getAuthHeaders();
        const res = await fetch(`${CONFIG.API_BASE}/leaderboard?period=${period}`, { headers });
        if (!res.ok) throw new Error("Failed to load leaderboard");

        lbData = await res.json();
        renderLeaderboard();
    } catch (err) {
        console.error(err);
        lbList.innerHTML = `<div class="empty-state"><p>${t('error_load')}</p></div>`;
    }
}

function renderLeaderboard() {
    if (!lbData || !lbList) return;

    const isUsers = document.getElementById('lb-type-users')?.classList.contains('active');
    const items = isUsers ? lbData.users : lbData.groups;
    lbList.innerHTML = '';

    if (!items || items.length === 0) {
        lbList.innerHTML = '<div class="empty-state"><p>No data yet.</p></div>';
        return;
    }

    items.forEach((item, index) => {
        const card = document.createElement('div');
        card.className = `lb-card ${item.rank <= 3 ? 'top-' + item.rank : ''}`;
        card.style.animationDelay = `${index * 0.05}s`;

        const name = item.name || item.title || "Unknown";
        const score = item.score || 0;
        const sub = item.username ? `@${item.username}` : "";

        card.innerHTML = `
            <div class="lb-rank">${item.rank}</div>
            <div class="lb-info">
                <span class="lb-name">${escapeHtml(name)}</span>
                <span class="lb-username">${escapeHtml(sub)}</span>
            </div>
            <div class="lb-score">
                <span class="lb-score-val">${score}</span>
                <span class="lb-score-unit">${t('pts')}</span>
            </div>
        `;
        lbList.appendChild(card);
    });

    // Handle My Rank Sticky
    if (isUsers && lbData.user_rank) {
        myRankBar.style.display = 'flex';
        const myRank = lbData.user_rank;
        myRankBar.querySelector('.rank-num').innerText = `#${myRank.rank}`;
        myRankBar.querySelector('.rank-name').innerText = t('my_rank');
        myRankBar.querySelector('.rank-score').innerText = `${myRank.score} ${t('pts')}`;
    } else {
        myRankBar.style.display = 'none';
    }
}


// Final Guard: Wait for DOM complete
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
