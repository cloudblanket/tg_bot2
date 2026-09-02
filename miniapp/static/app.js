/**
 * абсолют синема — Mini App
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
    controlMode: 'everyone',
    creatorId: 0,
    hasControl: true,
    connectedUsers: 0,
    votersWithControl: [],
    activeVote: null,
    isFounder: false,
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
    tabVote: document.getElementById('tab-vote'),
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
    voteList: document.getElementById('vote-list'),
    activeVote: document.getElementById('active-vote'),
    activeVoteContent: document.getElementById('active-vote-content'),
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
    if (typeof screen === 'string') {
        document.getElementById(`screen-${screen}`)?.classList.add('active');
    } else {
        screen.classList.add('active');
    }
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ==========================================
// LOBBY
// ==========================================

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

    const title = els.createTitle.value.trim() || 'абсолют синема';
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
        state.isFounder = true;
        enterRoom(data.code, data.title);
    } catch (e) {
        alert('Ошибка создания комнаты');
    }
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
        const res = await fetch(`${API_BASE}/api/rooms/my/${state.userInfo.id}`);
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

// ==========================================
// CHAT
// ==========================================

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
// ROOM TABS
// ==========================================

document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        tab.classList.add('active');
        const tabName = tab.dataset.tab;
        document.getElementById(`tab-content-${tabName}`)?.classList.add('active');
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
                if (!state.hasControl) return;
                if (event.data === 1) {
                    state.isPlaying = true;
                    els.btnPlayPause.textContent = '⏸';
                    els.theaterPlayPause.textContent = '⏸';
                    wsSend({ a: 'p', ts: getCurrentTime(), s: getUserDisplayName(), u: state.userInfo?.id || 0 });
                } else if (event.data === 2) {
                    state.isPlaying = false;
                    els.btnPlayPause.textContent = '▶️';
                    els.theaterPlayPause.textContent = '▶️';
                    wsSend({ a: 'a', ts: getCurrentTime(), s: getUserDisplayName(), u: state.userInfo?.id || 0 });
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
        wsSend({ a: 'k', ts: seconds, s: getUserDisplayName(), u: state.userInfo?.id || 0 });
    }
}

function playVideo() {
    const p = ytPlayer || state.theaterPlayer;
    if (p && typeof p.playVideo === 'function') {
        state.isSyncing = true;
        p.playVideo();
        setTimeout(() => { state.isSyncing = false; }, 300);
    }
}

function pauseVideo() {
    const p = ytPlayer || state.theaterPlayer;
    if (p && typeof p.pauseVideo === 'function') {
        state.isSyncing = true;
        p.pauseVideo();
        setTimeout(() => { state.isSyncing = false; }, 300);
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
    wsSend({ a: 'c', tx: text, s: getUserDisplayName(), u: state.userInfo?.id || 0 });
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
    wsSend({ a: 'sv', v: `https://twitch.tv/${channel}`, s: getUserDisplayName(), u: state.userInfo?.id || 0 });
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
        const res = await fetch(`${API_BASE}/api/personalize/${state.userInfo.id}`);
        if (!res.ok) return;
        const data = await res.json();
        applyPersonalization(data);
        highlightActiveButtons(data);
        personalizationLoaded = true;
    } catch (e) {}
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
        await fetch(`${API_BASE}/api/personalize/${state.userInfo.id}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
    } catch (e) {}
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
        wsSend({ a: 'i', u: state.userInfo?.id || 0, s: getUserDisplayName() });
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
    switch (data.t) {
        case 'state':
            handleInitialState(data);
            break;
        case 'rs':
            handleRoomState(data);
            break;
        case 'cmd':
            handleCommand(data);
            break;
        case 'sync':
            handleSync(data);
            break;
        case 'c':
            addChatMessage(data.s, data.tx);
            break;
        case 'cm':
            state.controlMode = data.m;
            updateControlUI();
            break;
        case 'cg':
            state.hasControl = true;
            addChatMessage('Система', data.m);
            updateControlUI();
            break;
        case 'vs':
        case 'vu':
            state.activeVote = data.v;
            renderActiveVote();
            break;
        case 'vc':
        case 'vcl':
            state.activeVote = null;
            renderActiveVote();
            if (data.m) addChatMessage('Система', data.m);
            break;
        case 've':
            addChatMessage('Система', data.m);
            break;
        case 'vr':
            if (data.a === 'clr') {
                if (ytPlayer) { ytPlayer.destroy(); ytPlayer = null; }
                state.playerReady = false;
                els.playerPlaceholder.classList.remove('hidden');
                els.controls.classList.add('hidden');
            }
            if (data.a === 'gc' && data.vc) {
                state.votersWithControl = data.vc;
                state.hasControl = data.vc.includes(state.userInfo?.id);
                updateControlUI();
            }
            addChatMessage('Система', data.m || 'Голосование завершено');
            break;
        case 'd':
            addChatMessage('Система', data.m);
            tg?.HapticFeedback?.notificationOccurred('error');
            break;
        case 'kicked':
            alert(data.m);
            state.roomCode = null;
            if (state.ws) state.ws.close();
            showScreen(els.screenLobby);
            break;
        case 'rc':
            addChatMessage('Система', 'Комната закрыта');
            state.roomCode = null;
            if (state.ws) state.ws.close();
            showScreen(els.screenLobby);
            loadPublicRooms();
            break;
    }
}

function handleInitialState(data) {
    if (data.v) {
        if (data.v.includes('twitch.tv')) {
            els.tabTwitch.style.display = '';
            createTwitchPlayer(data.v.split('/').pop());
        } else {
            const videoId = extractVideoId(data.v);
            if (videoId) createPlayer(videoId);
        }
    }

    if (data.cm) state.controlMode = data.cm;
    if (data.cr) {
        state.creatorId = data.cr;
        state.isFounder = data.cr === state.userInfo?.id;
    }
    if (data.cu) state.connectedUsers = data.cu;
    if (data.vc) state.votersWithControl = data.vc;
    if (data.av) state.activeVote = data.av;

    state.hasControl = state.controlMode === 'everyone' || state.isFounder || state.votersWithControl.includes(state.userInfo?.id);
    updateControlUI();
    renderActiveVote();

    if (data.p && ytPlayer) {
        state.isSyncing = true;
        ytPlayer.seekTo(data.ts, true);
        ytPlayer.playVideo();
        setTimeout(() => { state.isSyncing = false; }, 300);
    } else if (!data.p && ytPlayer) {
        state.isSyncing = true;
        ytPlayer.seekTo(data.ts, true);
        ytPlayer.pauseVideo();
        setTimeout(() => { state.isSyncing = false; }, 300);
    }
}

function handleRoomState(data) {
    if (data.cm) state.controlMode = data.cm;
    if (data.cr) {
        state.creatorId = data.cr;
        state.isFounder = data.cr === state.userInfo?.id;
    }
    if (data.cu) state.connectedUsers = data.cu;
    if (data.vc) state.votersWithControl = data.vc;

    state.hasControl = state.controlMode === 'everyone' || state.isFounder || state.votersWithControl.includes(state.userInfo?.id);
    updateControlUI();
}

function handleCommand(data) {
    addChatMessage(data.s || '?', getActionText(data));

    if (data.a === 'sv') {
        if (data.v?.includes('twitch.tv')) {
            els.tabTwitch.style.display = '';
            createTwitchPlayer(data.v.split('/').pop());
        } else {
            const videoId = extractVideoId(data.v);
            if (videoId) createPlayer(videoId);
        }
        return;
    }

    if (!ytPlayer) return;
    state.isSyncing = true;
    switch (data.a) {
        case 'p': ytPlayer.seekTo(data.ts, true); ytPlayer.playVideo(); break;
        case 'a': ytPlayer.seekTo(data.ts, true); ytPlayer.pauseVideo(); break;
        case 'k': ytPlayer.seekTo(data.ts, true); break;
    }
    setTimeout(() => { state.isSyncing = false; }, 300);
}

function handleSync(data) {
    if (!ytPlayer) return;
    const diff = Math.abs(ytPlayer.getCurrentTime() - data.ts);
    if (diff > 2) {
        state.isSyncing = true;
        ytPlayer.seekTo(data.ts, true);
        setTimeout(() => { state.isSyncing = false; }, 200);
    }
    if (data.p && !state.isPlaying) {
        state.isSyncing = true;
        ytPlayer.playVideo();
        setTimeout(() => { state.isSyncing = false; }, 200);
    } else if (!data.p && state.isPlaying) {
        state.isSyncing = true;
        ytPlayer.pauseVideo();
        setTimeout(() => { state.isSyncing = false; }, 200);
    }
}

function getActionText(data) {
    switch (data.a) {
        case 'p': return `▶️ Воспроизведение (${formatTime(data.ts)})`;
        case 'a': return `⏸ Пауза (${formatTime(data.ts)})`;
        case 'k': return `⏩ Перемотка на ${formatTime(data.ts)}`;
        case 'sv': return '🎬 Новое видео';
        default: return data.a;
    }
}

function getUserDisplayName() {
    return state.userInfo?.first_name || state.userInfo?.username || 'Аноним';
}

// ==========================================
// VOTING
// ==========================================

function updateControlUI() {
    const controlsDisabled = !state.hasControl;
    els.btnPlayPause.disabled = controlsDisabled;
    els.btnSeekBack.disabled = controlsDisabled;
    els.btnSeekForward.disabled = controlsDisabled;
    els.btnAddVideo.disabled = controlsDisabled;
    els.videoUrlInput.disabled = controlsDisabled;

    if (controlsDisabled) {
        els.btnPlayPause.style.opacity = '0.4';
        els.btnAddVideo.style.opacity = '0.4';
    } else {
        els.btnPlayPause.style.opacity = '1';
        els.btnAddVideo.style.opacity = '1';
    }
}

function renderActiveVote() {
    const container = els.activeVote;
    const content = els.activeVoteContent;
    if (!container || !content) return;

    if (!state.activeVote) {
        container.classList.add('hidden');
        return;
    }

    container.classList.remove('hidden');
    const v = state.activeVote;
    const required = v.required || 1;

    const voteLabels = {
        skip: '⏭ Пропустить видео',
        next: '🎬 Следующее видео',
        control: '🎮 Право управления',
        kick: '🚫 Исключить участника',
    };

    const targetText = v.target_user_name ? ` (${v.target_user_name})` : '';
    content.innerHTML = `
        <div class="vote-header">
            <span class="vote-type">${voteLabels[v.type] || v.type}</span>
            <span class="vote-initiator">от ${escapeHtml(v.initiator_name)}</span>
        </div>
        <div class="vote-progress">
            <div class="vote-bar">
                <div class="vote-fill" style="width: ${Math.min(100, (v.votes_count / required) * 100)}%"></div>
            </div>
            <span class="vote-count">${v.votes_count} / ${required}</span>
        </div>
        <div class="vote-actions">
            ${!v.voters?.includes(state.userInfo?.id) ? `
                <button class="btn btn-primary btn-sm" onclick="voteYes()">👍 За</button>
                <button class="btn btn-secondary btn-sm" onclick="voteNo()">✕ Отмена</button>
            ` : '<span class="vote-waiting">Ожидаем голоса...</span>'}
        </div>
    `;
}

function startVote(type, targetUserId = 0, targetUserName = '') {
    wsSend({
        a: 'v', va: 's', vt: type,
        tid: targetUserId, tn: targetUserName,
        u: state.userInfo?.id || 0, s: getUserDisplayName(),
    });
}

function voteYes() {
    wsSend({ a: 'v', va: 'y', u: state.userInfo?.id || 0, s: getUserDisplayName() });
}

function voteNo() {
    wsSend({ a: 'v', va: 'n', u: state.userInfo?.id || 0, s: getUserDisplayName() });
}

function setControlMode(mode) {
    wsSend({ a: 'cm', m: mode, u: state.userInfo?.id || 0 });
}

// ==========================================
// VOTE LIST (static buttons)
// ==========================================

function renderVoteList() {
    if (!els.voteList) return;
    els.voteList.innerHTML = `
        <div class="vote-option" onclick="startVote('skip')">
            <span class="vote-icon">⏭</span>
            <div>
                <div class="vote-option-title">Пропустить видео</div>
                <div class="vote-option-desc">Остановить и сбросить текущее видео</div>
            </div>
        </div>
        <div class="vote-option" onclick="startVote('next')">
            <span class="vote-icon">🎬</span>
            <div>
                <div class="vote-option-title">Следующее видео</div>
                <div class="vote-option-desc">Убрать текущее видео, выбрать новое</div>
            </div>
        </div>
        <div class="vote-option" onclick="startVote('control')">
            <span class="vote-icon">🎮</span>
            <div>
                <div class="vote-option-title">Получить управление</div>
                <div class="vote-option-desc">Голос за право управлять видео</div>
            </div>
        </div>
    `;

    if (state.isFounder) {
        els.voteList.innerHTML += `
            <div class="vote-divider"></div>
            <div class="vote-section-title">Настройки создателя</div>
            <div class="control-mode-buttons">
                <button class="btn btn-sm ${state.controlMode === 'everyone' ? 'btn-primary' : 'btn-secondary'}" onclick="setControlMode('everyone')">Все</button>
                <button class="btn btn-sm ${state.controlMode === 'creator' ? 'btn-primary' : 'btn-secondary'}" onclick="setControlMode('creator')">Только я</button>
                <button class="btn btn-sm ${state.controlMode === 'voted' ? 'btn-primary' : 'btn-secondary'}" onclick="setControlMode('voted')">По голосованию</button>
            </div>
        `;
    }
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
    state.isFounder = false;
    showScreen(els.screenLobby);
    loadPublicRooms();
});

els.btnCloseRoom?.addEventListener('click', closeRoom);

els.btnPlayPause.addEventListener('click', () => {
    if (!state.playerReady || !state.hasControl) return;
    tg?.HapticFeedback?.impactOccurred('medium');
    if (state.isPlaying) pauseVideo(); else playVideo();
});

els.btnSeekBack.addEventListener('click', () => {
    if (!state.playerReady || !state.hasControl) return;
    seekTo(Math.max(0, getCurrentTime() - 10));
});

els.btnSeekForward.addEventListener('click', () => {
    if (!state.playerReady || !state.hasControl) return;
    seekTo(getCurrentTime() + 10);
});

els.btnAddVideo.addEventListener('click', () => {
    const url = els.videoUrlInput.value.trim();
    if (!url || !state.hasControl) return;
    tg?.HapticFeedback?.notificationOccurred('success');

    wsSend({ a: 'sv', v: url, s: getUserDisplayName(), u: state.userInfo?.id || 0 });

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
    wsSend({ a: 'c', tx: text, s: getUserDisplayName(), u: state.userInfo?.id || 0 });
    addChatMessage('Я', text);
    els.chatInput.value = '';
}

// ==========================================
// ROOM ENTRY
// ==========================================

function enterRoom(roomCode, roomTitle) {
    state.roomCode = roomCode;
    els.roomCodeBadge.textContent = roomCode;
    els.roomTitle.textContent = roomTitle || 'абсолют синема';
    els.roomLockBadge.style.display = 'none';
    state.hasControl = true;
    state.activeVote = null;
    renderVoteList();
    renderActiveVote();
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
// UPLOAD
// ==========================================

const uploadArea = document.getElementById('upload-area');
const uploadInput = document.getElementById('upload-input');
const uploadProgress = document.getElementById('upload-progress');
const uploadProgressFill = document.getElementById('upload-progress-fill');
const uploadStatus = document.getElementById('upload-status');

uploadArea?.addEventListener('click', () => uploadInput?.click());

uploadArea?.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.style.borderColor = 'rgba(99, 102, 241, 0.6)';
    uploadArea.style.background = 'rgba(99, 102, 241, 0.08)';
});

uploadArea?.addEventListener('dragleave', () => {
    uploadArea.style.borderColor = '';
    uploadArea.style.background = '';
});

uploadArea?.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.style.borderColor = '';
    uploadArea.style.background = '';
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith('video/')) uploadFile(file);
});

uploadInput?.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) uploadFile(file);
});

async function uploadFile(file) {
    if (!state.userInfo?.id) return;
    if (file.size > 350 * 1024 * 1024) {
        alert('Файл слишком большой (макс 350 МБ)');
        return;
    }

    uploadProgress.classList.remove('hidden');
    uploadProgressFill.style.width = '0%';
    uploadStatus.textContent = `Загрузка ${file.name}...`;

    const formData = new FormData();
    formData.append('file', file);
    formData.append('user_id', state.userInfo.id);
    formData.append('room_code', state.roomCode || '');

    try {
        const xhr = new XMLHttpRequest();
        xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
                const pct = Math.round((e.loaded / e.total) * 100);
                uploadProgressFill.style.width = pct + '%';
                uploadStatus.textContent = `Загрузка ${pct}%`;
            }
        });

        await new Promise((resolve, reject) => {
            xhr.onload = () => {
                if (xhr.status === 200) resolve(JSON.parse(xhr.responseText));
                else reject(new Error(xhr.responseText));
            };
            xhr.onerror = () => reject(new Error('Network error'));
            xhr.open('POST', `${API_BASE}/api/upload`);
            xhr.send(formData);
        });

        uploadStatus.textContent = 'Готово!';
        uploadProgressFill.style.width = '100%';
        setTimeout(() => uploadProgress.classList.add('hidden'), 1500);
        uploadInput.value = '';
    } catch (e) {
        uploadStatus.textContent = 'Ошибка: ' + (e.message || 'неизвестная');
        uploadProgressFill.style.width = '0%';
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
    els.tabVote.style.display = '';
}

init();
