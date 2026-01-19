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
    let debugSource = "none";
    let initData = "";

    // Debug collection
    const debugKeys = [];

    // 1. Try initData from Telegram Object (Standard)
    if (tg.initData) {
        initData = tg.initData;
        debugSource = "tg.initData";
    }
    // 2. Fallback: Parse from Hash
    else {
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
    }

    // 3. Check for token (Legacy)
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('token')) {
        const token = urlParams.get('token');
        headers['X-Auth-Token'] = token;
        if (debugSource === "none") debugSource = "token";
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
        confirm_delete: "Rostdan ham bu savolni o'chirmoqchimisiz?"
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
        confirm_delete: "Are you sure you want to delete this question?"
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

        // Guard: If still no auth, show redirect message
        if (!headers['X-Auth-Token'] && !headers['X-Telegram-Init-Data']) {
            console.warn("No auth credentials found, skipping fetch.");
            showAuthRedirect();
            return;
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
        const res = await fetch(`${API_BASE}/bot-info`);
        if (res.ok) {
            const data = await res.json();
            botUsername = (data.bot_username ?? botUsername).replace("@", "").trim();
            botLink = normalizeBotLink(data.bot_link ?? botLink, botUsername);
        }
    } catch (e) {
        console.warn("Failed to fetch bot info:", e);
    }
    
    const landingHTML = `
        <style>
            @keyframes float {
                0%, 100% { transform: translateY(0px) rotate(0deg); }
                50% { transform: translateY(-20px) rotate(5deg); }
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
        
        <div style="background: transparent; color: white; padding: 0; text-align: center; min-height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; position: relative; overflow-x: hidden; width: 100%;">
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
                    QuizBot
                </h1>
                
                <!-- Subtitle -->
                <p class="subtitle fade-in-up" style="font-size: clamp(1.2rem, 3vw, 1.8rem); margin-bottom: 50px; opacity: 0.95; line-height: 1.7; animation-delay: 0.2s; max-width: 800px; margin-left: auto; margin-right: auto; font-weight: 300; text-shadow: 0 2px 4px rgba(0,0,0,0.2);">
                    Telegram'da interaktiv testlar yarating va boshqaring
                </p>
                
                <!-- Stats Section -->
                <div class="fade-in-up" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 40px; margin-bottom: 60px; animation-delay: 0.4s; width: 100%; max-width: 1200px;">
                    <div class="stat-card" style="text-align: center; padding: 35px; background: linear-gradient(135deg, rgba(102, 126, 234, 0.15), rgba(118, 75, 162, 0.1)); border-radius: 25px; backdrop-filter: blur(15px); border: 1px solid rgba(255,255,255,0.2); transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); animation: slideInUp 0.8s ease-out 0.4s both;">
                        <div class="stat-number" style="font-size: clamp(2rem, 5vw, 3.5rem); margin-bottom: 15px; font-weight: 800; background: linear-gradient(45deg, #fff, #e0e7ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; text-shadow: 0 0 20px rgba(255,255,255,0.3); animation: numberPulse 2s ease-in-out infinite;">10K+</div>
                        <p style="margin: 0; opacity: 0.9; font-size: clamp(0.9rem, 2vw, 1.2rem); font-weight: 600;">Foydalanuvchi</p>
                    </div>
                    <div class="stat-card" style="text-align: center; padding: 35px; background: linear-gradient(135deg, rgba(118, 75, 162, 0.15), rgba(240, 147, 251, 0.1)); border-radius: 25px; backdrop-filter: blur(15px); border: 1px solid rgba(255,255,255,0.2); transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); animation: slideInUp 0.8s ease-out 0.6s both;">
                        <div class="stat-number" style="font-size: clamp(2rem, 5vw, 3.5rem); margin-bottom: 15px; font-weight: 800; background: linear-gradient(45deg, #fff, #e0e7ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; text-shadow: 0 0 20px rgba(255,255,255,0.3); animation: numberPulse 2s ease-in-out infinite 0.3s;">50K+</div>
                        <p style="margin: 0; opacity: 0.9; font-size: clamp(0.9rem, 2vw, 1.2rem); font-weight: 600;">Test yaratildi</p>
                    </div>
                    <div class="stat-card" style="text-align: center; padding: 35px; background: linear-gradient(135deg, rgba(240, 147, 251, 0.15), rgba(102, 126, 234, 0.1)); border-radius: 25px; backdrop-filter: blur(15px); border: 1px solid rgba(255,255,255,0.2); transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); animation: slideInUp 0.8s ease-out 0.8s both;">
                        <div class="stat-number" style="font-size: clamp(2rem, 5vw, 3.5rem); margin-bottom: 15px; font-weight: 800; background: linear-gradient(45deg, #fff, #e0e7ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; text-shadow: 0 0 20px rgba(255,255,255,0.3); animation: numberPulse 2s ease-in-out infinite 0.6s;">99.9%</div>
                        <p style="margin: 0; opacity: 0.9; font-size: clamp(0.9rem, 2vw, 1.2rem); font-weight: 600;">Uptime</p>
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
                        <p style="margin: 0; font-size: clamp(0.9rem, 2vw, 1.1rem); opacity: 0.85; line-height: 1.7; font-weight: 300;">Groq AI bilan avtomatik savollar generatsiyasi</p>
                    </div>
                    <div class="feature-card slide-in-right" style="background: linear-gradient(135deg, rgba(240, 147, 251, 0.12), rgba(102, 126, 234, 0.08)); padding: 45px; border-radius: 30px; backdrop-filter: blur(15px); animation-delay: 1.2s; min-height: 250px; border: 1px solid rgba(255,255,255,0.15); transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); animation: slideInUp 0.8s ease-out 1.4s both;">
                        <div style="font-size: 4rem; margin-bottom: 25px; animation: iconBounce 2s ease-in-out infinite 0.4s;">�</div>
                        <h3 style="margin: 0 0 20px 0; font-size: clamp(1.2rem, 3vw, 1.6rem); font-weight: 700;">Analitika</h3>
                        <p style="margin: 0; font-size: clamp(0.9rem, 2vw, 1.1rem); opacity: 0.85; line-height: 1.7; font-weight: 300;">Test natijalarini batafsil tahlil qilish</p>
                    </div>
                </div>
                
                <!-- CTA Button -->
                <div class="fade-in-up pulse" style="animation-delay: 1.6s; margin-bottom: 50px;">
                    <a href="${botLink}" target="_blank" class="cta-button" style="display: inline-block; padding: 30px 70px; background: linear-gradient(135deg, #fff, #f8faff); color: #667eea; text-decoration: none; border-radius: 30px; font-weight: 700; font-size: clamp(1.2rem, 3vw, 1.5rem); box-shadow: 0 20px 50px rgba(102, 126, 234, 0.4), 0 0 0 2px rgba(255,255,255,0.3); position: relative; overflow: hidden; transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); animation: slideInUp 0.8s ease-out 1.6s both;">
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
}

function renderQuizList() {
    appContainer.classList.remove('landing');
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
    if (!confirm(t('confirm_delete'))) return;
    collectCurrentState();
    currentQuizData.questions.splice(index, 1);
    renderEditor();
}

function addQuestion() {
    collectCurrentState();
    currentQuizData.questions.push({
        question: "",
        options: ["", "", "", ""], // Default 4 empty options
        correct_option_id: 0
    });
    renderEditor();

    // Scroll to bottom after render
    setTimeout(() => {
        window.scrollTo(0, document.body.scrollHeight);
    }, 100);
}

function renderEditor() {
    questionsContainer.innerHTML = '';
    pageTitle.innerText = t('editing_test');

    if (!currentQuizData || !currentQuizData.questions) return;

    currentQuizData.questions.forEach((q, index) => {
        const item = document.createElement('div');
        item.className = 'question-item glass';
        item.dataset.index = index;

        // Escape values to prevent HTML attribute breakage
        const safeQuestion = escapeHtml(q.question);

        item.innerHTML = `
            <div class="q-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <span class="q-label">${t('question_label')}${index + 1}</span>
                <button class="delete-btn" style="background: #ef4444; border: none; padding: 5px 10px; border-radius: 5px; color: white; cursor: pointer; font-size: 12px;" onclick="deleteQuestion(${index})">
                    🗑 ${t('delete_question')}
                </button>
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
        if (!validateInput(qInput, 300)) {
            hasError = true;
        }

        const options = [];
        const optionInputs = item.querySelectorAll('.option-input');

        optionInputs.forEach(optInput => {
            if (!validateInput(optInput, 100)) {
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
        // Update local data
        currentQuizData.questions = updatedQuestions;
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
        appContainer.classList.remove('landing');
        dashboardView.style.display = 'grid';
        editorView.style.display = 'none';
        backBtn.style.display = 'none';
        editorActions.style.display = 'none';
        pageTitle.innerText = t('my_quizzes');
        loadQuizzes(); // Refresh list
    } else {
        appContainer.classList.remove('landing');
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
