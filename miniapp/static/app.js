/**
 * Киновечер — Mini App
 */

const SYNC_WS_URL = window.location.hostname === 'localhost'
    ? 'ws://localhost:8765/ws'
    : `wss://${window.location.host}/ws`;

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
};

const els = {
    screenLobby: document.getElementById('screen-lobby'),
    screenRoom: document.getElementById('screen-room'),
    screenTheater: document.getElementById('screen-theater'),
    screenChat: document.getElementById('screen-chat'),
    roomCodeInput: document.getElementById('room-code-input'),
    btnJoin: document.getElementById('btn-join'),
    btnCreate: document.getElementById('btn-create'),
    btnBack: document.getElementById('btn-back'),
    roomTitle: document.getElementById('room-title'),
    roomCodeBadge: document.getElementById('room-code-badge'),
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
    els.screenRoom.classList.remove('active');
    els.screenTheater.classList.remove('active');
    els.screenChat.classList.remove('active');
    screen.classList.add('active');
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
els.btnTheme?.addEventListener('click', () => els.themeModal.classList.remove('hidden'));

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
    enterRoom(code);
});

els.btnCreate.addEventListener('click', () => {
    tg?.sendData(JSON.stringify({ action: 'create_room' }));
    tg?.HapticFeedback?.notificationOccurred('success');
});

els.btnBack.addEventListener('click', () => {
    if (state.ws) state.ws.close();
    state.roomCode = null;
    showScreen(els.screenLobby);
});

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

function enterRoom(roomCode) {
    state.roomCode = roomCode;
    els.roomCodeBadge.textContent = roomCode;
    els.roomTitle.textContent = 'Киновечер';
    showScreen(els.screenRoom);
    wsConnect(roomCode);
    tg?.sendData(JSON.stringify({ action: 'get_room_info', room_code: roomCode }));
    tg?.HapticFeedback?.notificationOccurred('success');
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
}

function applyTierFeatures() {
    if (state.userTier === 'vip') {
        els.tabTwitch.style.display = '';
        els.tabUpload.style.display = '';
        els.btnTheme.style.display = '';
    } else if (state.userTier === 'paid') {
        els.tabUpload.style.display = '';
    }
}

init();
