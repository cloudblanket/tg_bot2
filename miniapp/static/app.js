/**
 * Абсолют Синема — Mini App
 */

const SYNC_WS_URL = window.location.hostname === 'localhost'
    ? 'ws://localhost:8765/ws'
    : `wss://${window.location.host}/ws`;

const API_BASE = window.location.hostname === 'localhost'
    ? 'http://localhost:8765'
    : `https://${window.location.host}`;

const tg = window.Telegram?.WebApp;
if (tg) {
    tg.ready();
    tg.expand();
    tg.enableClosingConfirmation();
}

const state = {
    roomCode: null,
    userInfo: null,
    player: null,
    playerReady: false,
    isPlaying: false,
    ws: null,
    isSyncing: false,
    userTier: 'free',
    theaterPlayer: null,
    joinPasswordRoom: null,
};

const els = {
    screenLobby: document.getElementById('screen-lobby'),
    screenCreate: document.getElementById('screen-create'),
    screenRoom: document.getElementById('screen-room'),
    screenTheater: document.getElementById('screen-theater'),
    screenChat: document.getElementById('screen-chat'),
    roomCodeInput: document.getElementById('room-code-input'),
    btnJoin: document.getElementById('btn-join'),
    btnCreate: document.getElementById('btn-create'),
    btnBack: document.getElementById('btn-back'),
    roomTitle: document.getElementById('room-title'),
    roomCodeBadge: document.getElementById('room-code-badge'),
    roomLockBadge: document.getElementById('room-lock-badge'),
    memberCount: document.getElementById('member-count'),
    playerContainer: document.getElementById('player-container'),
    playerPlaceholder: document.getElementById('player-placeholder'),
    playerDiv: document.getElementById('player'),
    controls: document.getElementById('controls'),
    btnPlayPause: document.getElementById('btn-play-pause'),
    btnSeekBack: document.getElementById('btn-seek-back'),
    btnSeekForward: document.getElementById('btn-seek-forward'),
    currentTime: document.getElementById('current-time'),
    videoUrlInput: document.getElementById('video-url-input'),
    btnAddVideo: document.getElementById('btn-add-video'),
    videoList: document.getElementById('video-list'),
    membersList: document.getElementById('members-list'),
    chatMessages: document.getElementById('chat-messages'),
    chatInput: document.getElementById('chat-input'),
    btnSendChat: document.getElementById('btn-send-chat'),
    tabTwitch: document.getElementById('tab-twitch'),
    tabUpload: document.getElementById('tab-upload'),
    btnTheme: document.getElementById('btn-theme'),
    btnCloseRoom: document.getElementById('btn-close-room'),
    btnFullscreen: document.getElementById('btn-fullscreen'),
    btnTwitchFullscreen: document.getElementById('btn-twitch-fullscreen'),
    twitchChannelInput: document.getElementById('twitch-channel-input'),
    btnTwitchPlay: document.getElementById('btn-twitch-play'),
    twitchPlayer: document.getElementById('twitch-player'),
    twitchPlayerPlaceholder: document.getElementById('twitch-player-placeholder'),
    themeModal: document.getElementById('theme-modal'),
    btnCloseTheme: document.getElementById('btn-close-theme'),
    btnExitTheater: document.getElementById('btn-exit-theater'),
    theaterPlayerContainer: document.getElementById('theater-player-container'),
    theaterPlayer: document.getElementById('theater-player'),
    theaterTitle: document.getElementById('theater-title'),
    theaterControls: document.getElementById('theater-controls'),
    theaterPlayPause: document.getElementById('theater-play-pause'),
    theaterSeekBack: document.getElementById('theater-seek-back'),
    theaterSeekForward: document.getElementById('theater-seek-forward'),
    theaterTime: document.getElementById('theater-time'),
    btnChatMode: document.getElementById('btn-chat-mode'),
    btnExitChat: document.getElementById('btn-exit-chat'),
    chatModeMessages: document.getElementById('chat-mode-messages'),
    chatModeInput: document.getElementById('chat-mode-input'),
    btnChatModeSend: document.getElementById('btn-chat-mode-send'),
    publicRoomsList: document.getElementById('public-rooms-list'),
    createTitle: document.getElementById('create-title'),
    createPassword: document.getElementById('create-password'),
    createTypeBadge: document.getElementById('create-type-badge'),
    createTypeHint: document.getElementById('create-type-hint'),
    btnCreateSubmit: document.getElementById('btn-create-submit'),
    btnCreateBack: document.getElementById('btn-create-back'),
    passwordModal: document.getElementById('password-modal'),
    passwordInput: document.getElementById('password-input'),
    btnPasswordSubmit: document.getElementById('btn-password-submit'),
    btnPasswordCancel: document.getElementById('btn-password-cancel'),
};

function formatTime(seconds) {
    const s = Math.floor(seconds);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
    return `${m}:${String(sec).padStart(2, '0')}`;
}

function extractVideoId(url) {
    const patterns = [
        /(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})/,
        /youtube\.com\/v\/([a-zA-Z0-9_-]{11})/,
    ];
    for (const pattern of patterns) {
        const match = url.match(pattern);
        if (match) return match[1];
    }
    return null;
}

function showScreen(screen) {
    els.screenLobby.classList.remove('active');
    els.screenCreate.classList.remove('active');
    els.screenRoom.classList.remove('active');
    els.screenTheater.classList.remove('active');
    els.screenChat.classList.remove('active');
    screen.classList.add('active');
}

async function loadPublicRooms() {
    try {
        const resp = await fetch(`${API_BASE}/api/rooms`);
        const data = await resp.json();
        const rooms = data.rooms || [];

        if (rooms.length === 0) {
            els.publicRoomsList.innerHTML = '<p class="no-rooms-text">Пока нет открытых комнат</p>';
            return;
        }

        els.publicRoomsList.innerHTML = rooms.map(r => `
            <div class="public-room-item" data-code="${escapeHtml(r.code)}" data-has-password="${r.has_password}">
                <div class="public-room-info">
                    <div class="public-room-title">${escapeHtml(r.title)}</div>
                    <div class="public-room-meta">👥 ${r.members} чел. ${r.has_password ? '🔒' : ''}</div>
                </div>
                <button class="public-room-join">Войти</button>
            </div>
        `).join('');

        els.publicRoomsList.querySelectorAll('.public-room-item').forEach(item => {
            item.addEventListener('click', () => {
                const code = item.dataset.code;
                const hasPassword = item.dataset.hasPassword === 'true';
                if (hasPassword) {
                    showPasswordModal(code);
                } else {
                    joinRoomByCode(code);
                }
            });
        });
    } catch (e) {
        els.publicRoomsList.innerHTML = '<p class="no-rooms-text">Не удалось загрузить</p>';
    }
}

function showPasswordModal(roomCode) {
    state.joinPasswordRoom = roomCode;
    els.passwordInput.value = '';
    els.passwordModal.classList.remove('hidden');
    els.passwordInput.focus();
}

function hidePasswordModal() {
    els.passwordModal.classList.add('hidden');
    state.joinPasswordRoom = null;
}

async function joinRoomByCode(code, password = '') {
    const userId = tg?.initDataUnsafe?.user?.id;
    if (!userId) {
        tg?.HapticFeedback?.notificationOccurred('error');
        return;
    }

    try {
        const resp = await fetch(`${API_BASE}/api/rooms/join`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: userId, code, password }),
        });
        const data = await resp.json();

        if (!resp.ok) {
            tg?.HapticFeedback?.notificationOccurred('error');
            alert(data.error || 'Ошибка входа');
            return;
        }

        state.userTier = data.tier || 'free';
        localStorage.setItem('kinovecher-tier', data.tier);
        enterRoom(code, data.title);
    } catch (e) {
        tg?.HapticFeedback?.notificationOccurred('error');
    }
}

async function createRoom() {
    const userId = tg?.initDataUnsafe?.user?.id;
    if (!userId) return;

    const title = els.createTitle.value.trim() || 'Абсолют Синема';
    const password = els.createPassword.value.trim();

    try {
        const resp = await fetch(`${API_BASE}/api/rooms/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: userId,
                title,
                password,
                is_public: !password,
            }),
        });
        const data = await resp.json();

        if (!resp.ok) {
            alert(data.error || 'Ошибка создания');
            return;
        }

        state.userTier = 'free';
        localStorage.setItem('kinovecher-tier', 'free');
        enterRoom(data.code, data.title);
    } catch (e) {
        alert('Ошибка создания комнаты');
    }
}

function addChatMessage(name, text) {
    const msg = document.createElement('div');
    msg.className = 'chat-msg';
    msg.innerHTML = `<span class="chat-msg-name">${escapeHtml(name)}:</span><span class="chat-msg-text">${escapeHtml(text)}</span>`;
    els.chatMessages.appendChild(msg);
    els.chatMessages.scrollTop = els.chatMessages.scrollHeight;

    const chatMsg = msg.cloneNode(true);
    els.chatModeMessages.appendChild(chatMsg);
    els.chatModeMessages.scrollTop = els.chatModeMessages.scrollHeight;
}

// ==========================================
// LOBBY TABS
// ==========================================

document.querySelectorAll('.lobby-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.lobby-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        const target = tab.dataset.tab;
        document.getElementById('tab-public').classList.toggle('hidden', target !== 'public');
        document.getElementById('tab-my').classList.toggle('hidden', target !== 'my');
        if (target === 'my') loadMyRooms();
    });
});

async function loadMyRooms() {
    if (!state.userInfo?.id) return;
    const list = document.getElementById('my-rooms-list');
    list.innerHTML = '<p class="loading-text">Загрузка...</p>';
    try {
        const res = await fetch(`${WEBAPP_URL}/api/rooms/my/${state.userInfo.id}`);
        const rooms = await res.json();
        if (!rooms.length) {
            list.innerHTML = '<p class="empty-text">У тебя нет комнат</p>';
            return;
        }
        list.innerHTML = '';
        rooms.forEach(r => {
            const el = document.createElement('div');
            el.className = 'room-card';
            el.innerHTML = `
                <div class="room-card-header">
                    <span class="room-card-title">${escapeHtml(r.title)}</span>
                    <span class="badge ${r.is_public ? 'badge-public' : 'badge-private'}">${r.is_public ? '🌐' : '🔒'}</span>
                </div>
                <div class="room-card-meta">
                    <span>👥 ${r.members}</span>
                    <span class="room-card-code">${r.code}</span>
                    ${r.is_active ? '<span class="badge badge-active">🟢 Активна</span>' : '<span class="badge badge-inactive">⚪ Неактивна</span>'}
                </div>
            `;
            el.addEventListener('click', () => {
                if (r.is_active) enterRoom(r.code);
            });
            list.appendChild(el);
        });
    } catch (e) {
        list.innerHTML = '<p class="empty-text">Ошибка загрузки</p>';
    }
}

function enterRoom(code) {
    if (!code) return;
    state.roomCode = code.trim().toUpperCase();
    state.isFounder = false;
    showScreen('room');
    connectWS();
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ==========================================
// TABS
// ==========================================

document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        tab.classList.add('active');
        const tabName = tab.dataset.tab;
        document.getElementById(`tab-content-${tabName}`).classList.add('active');
    });
});

// ==========================================
// YOUTUBE PLAYER
// ==========================================

let ytPlayer = null;

function loadYouTubeAPI() {
    const tag = document.createElement('script');
    tag.src = 'https://www.youtube.com/iframe_api';
    const firstScriptTag = document.getElementsByTagName('script')[0];
    firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);
}

window.onYouTubeIframeAPIReady = function () {};

function createPlayer(videoId, containerId) {
    const targetId = containerId || 'player';

    if (targetId === 'player' && ytPlayer) {
        ytPlayer.loadVideoById(videoId);
        return;
    }

    if (targetId === 'theater-player' && state.theaterPlayer) {
        state.theaterPlayer.loadVideoById(videoId);
        return;
    }

    if (targetId === 'player') {
        els.playerPlaceholder.classList.add('hidden');
    }

    const player = new YT.Player(targetId, {
        height: '100%',
        width: '100%',
        videoId: videoId,
        playerVars: {
            autoplay: 0,
            controls: 0,
            modestbranding: 1,
            rel: 0,
            showinfo: 0,
            iv_load_policy: 3,
            disablekb: 1,
        },
        events: {
            onReady: () => {
                if (targetId === 'player') {
                    state.playerReady = true;
                    els.controls.classList.remove('hidden');
                }
            },
            onStateChange: (event) => {
                if (state.isSyncing) return;
                if (event.data === 1) {
                    state.isPlaying = true;
                    els.btnPlayPause.textContent = '⏸';
                    els.theaterPlayPause.textContent = '⏸';
                    wsSend({ action: 'play', timestamp: getCurrentTime(), sender: getUserDisplayName() });
                } else if (event.data === 2) {
                    state.isPlaying = false;
                    els.btnPlayPause.textContent = '▶️';
                    els.theaterPlayPause.textContent = '▶️';
                    wsSend({ action: 'pause', timestamp: getCurrentTime(), sender: getUserDisplayName() });
                }
            },
        },
    });

    if (targetId === 'player') {
        ytPlayer = player;
    } else {
        state.theaterPlayer = player;
    }
}

function getCurrentTime() {
    const p = ytPlayer || state.theaterPlayer;
    if (p && typeof p.getCurrentTime === 'function') return p.getCurrentTime();
    return 0;
}

function seekTo(seconds) {
    const p = ytPlayer || state.theaterPlayer;
    if (p && typeof p.seekTo === 'function') {
        p.seekTo(seconds, true);
        wsSend({ action: 'seek', timestamp: seconds, sender: getUserDisplayName() });
    }
}

function playVideo() {
    const p = ytPlayer || state.theaterPlayer;
    if (p && typeof p.playVideo === 'function') {
        state.isSyncing = true;
        p.playVideo();
        setTimeout(() => { state.isSyncing = false; }, 500);
    }
}

function pauseVideo() {
    const p = ytPlayer || state.theaterPlayer;
    if (p && typeof p.pauseVideo === 'function') {
        state.isSyncing = true;
        p.pauseVideo();
        setTimeout(() => { state.isSyncing = false; }, 500);
    }
}

setInterval(() => {
    const time = getCurrentTime();
    els.currentTime.textContent = formatTime(time);
    els.theaterTime.textContent = formatTime(time);
}, 1000);

// ==========================================
// THEATER MODE
// ==========================================

function enterTheater() {
    showScreen(els.screenTheater);
    els.theaterTitle.textContent = els.roomTitle.textContent;

    const videoId = getCurrentVideoId();
    if (videoId) {
        createPlayer(videoId, 'theater-player');
        if (state.isPlaying) {
            setTimeout(() => {
                const p = state.theaterPlayer;
                if (p) { p.seekTo(getCurrentTime(), true); p.playVideo(); }
            }, 1000);
        }
    }
}

function exitTheater() {
    showScreen(els.screenRoom);
    if (state.theaterPlayer) {
        state.theaterPlayer.destroy();
        state.theaterPlayer = null;
    }
}

function getCurrentVideoId() {
    if (ytPlayer && typeof ytPlayer.getVideoUrl === 'function') {
        const url = ytPlayer.getVideoUrl();
        return extractVideoId(url);
    }
    return null;
}

els.btnFullscreen?.addEventListener('click', enterTheater);
els.btnTwitchFullscreen?.addEventListener('click', enterTheater);
els.btnExitTheater?.addEventListener('click', exitTheater);

els.theaterPlayPause?.addEventListener('click', () => {
    if (state.isPlaying) pauseVideo(); else playVideo();
});
els.theaterSeekBack?.addEventListener('click', () => seekTo(Math.max(0, getCurrentTime() - 10)));
els.theaterSeekForward?.addEventListener('click', () => seekTo(getCurrentTime() + 10));

// ==========================================
// CHAT MODE
// ==========================================

function enterChatMode() {
    showScreen(els.screenChat);
}

function exitChatMode() {
    showScreen(els.screenRoom);
}

els.btnChatMode?.addEventListener('click', enterChatMode);
els.btnExitChat?.addEventListener('click', exitChatMode);

els.btnChatModeSend?.addEventListener('click', () => {
    const text = els.chatModeInput.value.trim();
    if (!text) return;
    wsSend({ action: 'chat', text, sender: getUserDisplayName(), sender_id: state.userInfo?.id || 0 });
    addChatMessage('Я', text);
    els.chatModeInput.value = '';
});

els.chatModeInput?.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') els.btnChatModeSend.click();
});

// ==========================================
// TWITCH PLAYER
// ==========================================

let twitchPlayerInstance = null;

function loadTwitchAPI() {
    try {
        const tag = document.createElement('script');
        tag.src = 'https://player.twitch.tv/js/embed/v1.js';
        tag.onerror = () => console.warn('Twitch API failed to load');
        const firstScriptTag = document.getElementsByTagName('script')[0];
        firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);
    } catch(e) {}
}

function createTwitchPlayer(channel) {
    if (typeof Twitch === 'undefined') {
        els.twitchPlayerPlaceholder.innerHTML = '<span>🔴</span><p>Twitch API не загрузился</p>';
        return;
    }
    if (twitchPlayerInstance) {
        try { twitchPlayerInstance.setChannel(channel); } catch(e) {}
        return;
    }
    els.twitchPlayerPlaceholder.classList.add('hidden');
    try {
        twitchPlayerInstance = new Twitch.Player('twitch-player', {
            channel, width: '100%', height: '100%', autoplay: false, muted: false,
        });
    } catch(e) {
        els.twitchPlayerPlaceholder.classList.remove('hidden');
        els.twitchPlayerPlaceholder.innerHTML = '<span>🔴</span><p>Ошибка запуска Twitch</p>';
    }
}

els.btnTwitchPlay?.addEventListener('click', () => {
    const channel = els.twitchChannelInput.value.trim();
    if (!channel) return;
    createTwitchPlayer(channel);
    wsSend({ action: 'set_video', url: `https://twitch.tv/${channel}`, sender: getUserDisplayName() });
});

els.twitchChannelInput?.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') els.btnTwitchPlay.click();
});

// ==========================================
// THEMES
// ==========================================

function applyTheme(theme) {
    document.body.className = '';
    if (theme !== 'dark') document.body.classList.add(`theme-${theme}`);
    localStorage.setItem('kinovecher-theme', theme);
}

function loadSavedTheme() {
    const saved = localStorage.getItem('kinovecher-theme');
    if (saved) applyTheme(saved);
}

document.querySelectorAll('.theme-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        applyTheme(btn.dataset.theme);
        document.querySelectorAll('.theme-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        tg?.HapticFeedback?.impactOccurred('light');
    });
});

els.btnCloseTheme?.addEventListener('click', () => els.themeModal.classList.add('hidden'));
els.btnTheme?.addEventListener('click', () => {
    els.themeModal.classList.remove('hidden');
    if (state.userTier === 'vip') {
        document.getElementById('btn-personalize').style.display = '';
    }
});

// ==========================================
// PERSONALIZATION (VIP) — Server-side
// ==========================================

let personalizationLoaded = false;

async function loadPersonalizationFromServer() {
    if (!state.userInfo?.id) return;
    try {
        const res = await fetch(`${WEBAPP_URL}/api/personalize/${state.userInfo.id}`);
        if (!res.ok) return;
        const data = await res.json();
        applyPersonalization(data);
        highlightActiveButtons(data);
        personalizationLoaded = true;
    } catch (e) {
        console.error('Failed to load personalization:', e);
    }
}

function applyPersonalization(data) {
    if (data.font_name) {
        document.body.style.fontFamily = `'${data.font_name}', sans-serif`;
        loadGoogleFont(data.font_name);
    }
    if (data.bg_url) {
        document.body.style.background = `url('${data.bg_url}') center/cover fixed`;
    } else if (data.bg_color) {
        document.body.style.background = data.bg_color;
    }
    if (data.accent_color) {
        document.documentElement.style.setProperty('--accent', data.accent_color);
    }
    if (data.border_radius) {
        document.documentElement.style.setProperty('--radius', data.border_radius);
    }
}

function highlightActiveButtons(data) {
    document.querySelectorAll('.font-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.font === (data.font_name || ''));
    });
    document.querySelectorAll('.accent-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.accent === (data.accent_color || ''));
    });
    document.querySelectorAll('.radius-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.radius === (data.border_radius || ''));
    });
    const urlInput = document.getElementById('bg-url-input');
    if (urlInput) urlInput.value = data.bg_url || '';
}

function loadGoogleFont(name) {
    if (!name || document.querySelector(`link[href*="family=${name.replace(/ /g, '+')}"]`)) return;
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = `https://fonts.googleapis.com/css2?family=${name.replace(/ /g, '+')}:wght@400;600;700&display=swap`;
    document.head.appendChild(link);
}

function getCurrentPersonalization() {
    const bgUrl = document.getElementById('bg-url-input')?.value.trim() || '';
    const activeFont = document.querySelector('.font-btn.active');
    const activeAccent = document.querySelector('.accent-btn.active');
    const activeRadius = document.querySelector('.radius-btn.active');
    return {
        bg_url: bgUrl,
        bg_color: '',
        font_name: activeFont?.dataset.font || '',
        accent_color: activeAccent?.dataset.accent || '',
        border_radius: activeRadius?.dataset.radius || '',
    };
}

async function savePersonalizationToServer() {
    if (!state.userInfo?.id) return;
    const data = getCurrentPersonalization();
    applyPersonalization(data);
    try {
        await fetch(`${WEBAPP_URL}/api/personalize/${state.userInfo.id}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
    } catch (e) {
        console.error('Failed to save personalization:', e);
    }
}

document.getElementById('btn-personalize')?.addEventListener('click', () => {
    els.themeModal.classList.add('hidden');
    document.getElementById('personalize-modal').classList.remove('hidden');
});

document.getElementById('btn-close-personalize')?.addEventListener('click', () => {
    document.getElementById('personalize-modal').classList.add('hidden');
    savePersonalizationToServer();
});

document.querySelectorAll('.font-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        loadGoogleFont(btn.dataset.font);
        document.querySelectorAll('.font-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
    });
});

document.querySelectorAll('.accent-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.documentElement.style.setProperty('--accent', btn.dataset.accent);
        document.querySelectorAll('.accent-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
    });
});

document.querySelectorAll('.radius-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.documentElement.style.setProperty('--radius', btn.dataset.radius);
        document.querySelectorAll('.radius-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
    });
});

document.getElementById('btn-reset-personalize')?.addEventListener('click', () => {
    document.body.style.fontFamily = '';
    document.body.style.background = '';
    document.documentElement.style.setProperty('--accent', '#6c5ce7');
    document.documentElement.style.setProperty('--radius', '12px');
    document.getElementById('bg-url-input').value = '';
    document.querySelectorAll('.font-btn').forEach(b => b.classList.remove('active'));
    document.querySelector('.font-btn')?.classList.add('active');
    document.querySelectorAll('.accent-btn').forEach(b => b.classList.remove('active'));
    document.querySelector('.accent-btn')?.classList.add('active');
    document.querySelectorAll('.radius-btn').forEach(b => b.classList.remove('active'));
    document.querySelector('.radius-btn[data-radius="12px"]')?.classList.add('active');
    savePersonalizationToServer();
});

// ==========================================
// WEBSOCKET
// ==========================================

function wsConnect(roomCode) {
    if (state.ws) { state.ws.onclose = null; state.ws.close(); }

    state.ws = new WebSocket(`${SYNC_WS_URL}/${roomCode}`);
    state.reconnectAttempts = 0;

    state.ws.onopen = () => {
        state.reconnectAttempts = 0;
        addChatMessage('Система', 'Подключено к серверу синхронизации');
    };

    state.ws.onmessage = (event) => {
        try { handleWsMessage(JSON.parse(event.data)); } catch (e) {}
    };

    state.ws.onclose = () => {
        if (!state.roomCode) return;
        state.reconnectAttempts = (state.reconnectAttempts || 0) + 1;
        const delay = Math.min(1000 * state.reconnectAttempts, 10000);
        setTimeout(() => { if (state.roomCode) wsConnect(state.roomCode); }, delay);
    };
}

function wsSend(data) {
    if (state.ws?.readyState === WebSocket.OPEN) state.ws.send(JSON.stringify(data));
}

function handleWsMessage(data) {
    if (data.type === 'state') {
        if (data.current_video_url) {
            if (data.current_video_url.includes('twitch.tv')) {
                els.tabTwitch.style.display = '';
                createTwitchPlayer(data.current_video_url.split('/').pop());
            } else {
                const videoId = extractVideoId(data.current_video_url);
                if (videoId) createPlayer(videoId);
            }
        }
        if (data.is_playing && ytPlayer) {
            state.isSyncing = true;
            ytPlayer.seekTo(data.timestamp, true);
            ytPlayer.playVideo();
            setTimeout(() => { state.isSyncing = false; }, 500);
        } else if (!data.is_playing && ytPlayer) {
            state.isSyncing = true;
            ytPlayer.seekTo(data.timestamp, true);
            ytPlayer.pauseVideo();
            setTimeout(() => { state.isSyncing = false; }, 500);
        }
        return;
    }

    if (data.type === 'command') {
        addChatMessage(data.sender || '?', getActionText(data));

        if (data.action === 'set_video') {
            if (data.url?.includes('twitch.tv')) {
                els.tabTwitch.style.display = '';
                createTwitchPlayer(data.url.split('/').pop());
            } else {
                const videoId = extractVideoId(data.url);
                if (videoId) createPlayer(videoId);
            }
            return;
        }

        if (!ytPlayer) return;
        state.isSyncing = true;
        switch (data.action) {
            case 'play': ytPlayer.seekTo(data.timestamp, true); ytPlayer.playVideo(); break;
            case 'pause': ytPlayer.seekTo(data.timestamp, true); ytPlayer.pauseVideo(); break;
            case 'seek': ytPlayer.seekTo(data.timestamp, true); break;
        }
        setTimeout(() => { state.isSyncing = false; }, 500);
        return;
    }

    if (data.type === 'chat') {
        addChatMessage(data.sender, data.text);
    }
}

function getActionText(data) {
    switch (data.action) {
        case 'play': return `▶️ Воспроизведение (${formatTime(data.timestamp)})`;
        case 'pause': return `⏸ Пауза (${formatTime(data.timestamp)})`;
        case 'seek': return `⏩ Перемотка на ${formatTime(data.timestamp)}`;
        case 'set_video': return '🎬 Новое видео';
        default: return data.action;
    }
}

function getUserDisplayName() {
    return state.userInfo?.first_name || state.userInfo?.username || 'Аноним';
}

// ==========================================
// EVENT HANDLERS
// ==========================================

els.btnJoin.addEventListener('click', () => {
    const code = els.roomCodeInput.value.trim();
    if (!code) { tg?.HapticFeedback?.notificationOccurred('error'); return; }
    joinRoomByCode(code);
});

els.btnCreate?.addEventListener('click', () => {
    els.createTitle.value = '';
    els.createPassword.value = '';
    updateCreateTypeBadge();
    showScreen(els.screenCreate);
});

els.btnCreateBack?.addEventListener('click', () => {
    showScreen(els.screenLobby);
});

els.createPassword?.addEventListener('input', updateCreateTypeBadge);

function updateCreateTypeBadge() {
    const hasPassword = els.createPassword.value.trim().length > 0;
    if (hasPassword) {
        els.createTypeBadge.textContent = '🔒 Закрытая';
        els.createTypeBadge.className = 'badge badge-private';
        els.createTypeHint.textContent = 'Только по паролю';
    } else {
        els.createTypeBadge.textContent = '🌐 Открытая';
        els.createTypeBadge.className = 'badge badge-public';
        els.createTypeHint.textContent = 'Все смогут найти и войти';
    }
}

els.btnCreateSubmit?.addEventListener('click', createRoom);

els.btnPasswordSubmit?.addEventListener('click', () => {
    const password = els.passwordInput.value.trim();
    if (state.joinPasswordRoom) {
        hidePasswordModal();
        joinRoomByCode(state.joinPasswordRoom, password);
    }
});

els.btnPasswordCancel?.addEventListener('click', hidePasswordModal);

els.passwordInput?.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') els.btnPasswordSubmit.click();
});

els.btnBack.addEventListener('click', () => {
    if (state.ws) state.ws.close();
    state.roomCode = null;
    showScreen(els.screenLobby);
    loadPublicRooms();
});

els.btnCloseRoom?.addEventListener('click', closeRoom);

els.btnPlayPause.addEventListener('click', () => {
    if (!state.playerReady) return;
    tg?.HapticFeedback?.impactOccurred('medium');
    if (state.isPlaying) pauseVideo(); else playVideo();
});

els.btnSeekBack.addEventListener('click', () => {
    if (!state.playerReady) return;
    seekTo(Math.max(0, getCurrentTime() - 10));
});

els.btnSeekForward.addEventListener('click', () => {
    if (!state.playerReady) return;
    seekTo(getCurrentTime() + 10);
});

els.btnAddVideo.addEventListener('click', () => {
    const url = els.videoUrlInput.value.trim();
    if (!url) return;
    tg?.HapticFeedback?.notificationOccurred('success');

    wsSend({ action: 'set_video', url, sender: getUserDisplayName() });
    tg?.sendData(JSON.stringify({ action: 'add_video', room_code: state.roomCode, url, title: url }));

    els.videoUrlInput.value = '';
    const videoId = extractVideoId(url);
    if (videoId) createPlayer(videoId);
});

els.videoUrlInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') els.btnAddVideo.click();
});

els.btnSendChat.addEventListener('click', sendChatMessage);
els.chatInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') sendChatMessage(); });

function sendChatMessage() {
    const text = els.chatInput.value.trim();
    if (!text) return;
    wsSend({ action: 'chat', text, sender: getUserDisplayName(), sender_id: state.userInfo?.id || 0 });
    addChatMessage('Я', text);
    els.chatInput.value = '';
}

// ==========================================
// ROOM ENTRY
// ==========================================

function enterRoom(roomCode, roomTitle) {
    state.roomCode = roomCode;
    els.roomCodeBadge.textContent = roomCode;
    els.roomTitle.textContent = roomTitle || 'Абсолют Синема';
    els.roomLockBadge.style.display = 'none';
    showScreen(els.screenRoom);
    wsConnect(roomCode);
    tg?.HapticFeedback?.notificationOccurred('success');
}

async function closeRoom() {
    const userId = tg?.initDataUnsafe?.user?.id;
    if (!userId || !state.roomCode) return;

    if (!confirm('Закрыть комнату? Все участники будут отключены.')) return;

    try {
        const resp = await fetch(`${API_BASE}/api/rooms/close`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: userId, code: state.roomCode }),
        });
        const data = await resp.json();

        if (!resp.ok) {
            alert(data.error || 'Ошибка');
            return;
        }

        if (state.ws) state.ws.close();
        state.roomCode = null;
        showScreen(els.screenLobby);
        loadPublicRooms();
        tg?.HapticFeedback?.notificationOccurred('success');
    } catch (e) {
        alert('Ошибка закрытия комнаты');
    }
}

// ==========================================
// INIT
// ==========================================

function initFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const roomCode = params.get('room');
    const tier = params.get('tier');
    if (tier) { state.userTier = tier; localStorage.setItem('kinovecher-tier', tier); }
    if (roomCode) enterRoom(roomCode);
}

function init() {
    loadYouTubeAPI();
    loadTwitchAPI();
    loadSavedTheme();
    const savedTier = localStorage.getItem('kinovecher-tier');
    if (savedTier) state.userTier = savedTier;
    initFromUrl();
    if (tg?.initDataUnsafe?.user) state.userInfo = tg.initDataUnsafe.user;
    applyTierFeatures();
    loadPersonalizationFromServer();
    if (!state.roomCode) loadPublicRooms();
}

function applyTierFeatures() {
    if (state.userTier === 'vip') {
        els.tabTwitch.style.display = '';
        els.tabUpload.style.display = '';
        els.btnTheme.style.display = '';
    } else if (state.userTier === 'paid') {
        els.tabTwitch.style.display = '';
        els.btnTheme.style.display = '';
    }
}

init();
