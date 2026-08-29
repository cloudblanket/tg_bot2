/**
 * Киновечер — Mini App
 * Совместный просмотр видео через Telegram WebApp
 */

// ==========================================
// НАСТРОЙКИ
// ==========================================

// URL WebSocket сервера синхронизации.
// Замени на свой адрес при деплое.
// Для локальной разработки: ws://localhost:8765
// Для продакшена: wss://your-domain.com/ws
const SYNC_WS_URL = window.location.hostname === 'localhost'
    ? 'ws://localhost:8765/ws'
    : `wss://${window.location.host}/ws`;

// ==========================================
// ИНИЦИАЛИЗАЦИЯ TELEGRAM WEB APP
// ==========================================

const tg = window.Telegram?.WebApp;
if (tg) {
    tg.ready();
    tg.expand();
    tg.enableClosingConfirmation();
}

// ==========================================
// СОСТОЯНИЕ ПРИЛОЖЕНИЯ
// ==========================================

const state = {
    roomCode: null,
    userInfo: null,
    isCreator: false,
    player: null,
    playerReady: false,
    isPlaying: false,
    currentVideoId: null,
    members: [],
    videos: [],
    ws: null,
    isSyncing: false, // флаг, чтобы не обрабатывать свои же команды
};

// ==========================================
// DOM ЭЛЕМЕНТЫ
// ==========================================

const els = {
    screenLobby: document.getElementById('screen-lobby'),
    screenRoom: document.getElementById('screen-room'),
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
};

// ==========================================
// УТИЛИТЫ
// ==========================================

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
    screen.classList.add('active');
}

function addChatMessage(name, text) {
    const msg = document.createElement('div');
    msg.className = 'chat-msg';
    msg.innerHTML = `<span class="chat-msg-name">${escapeHtml(name)}:</span><span class="chat-msg-text">${escapeHtml(text)}</span>`;
    els.chatMessages.appendChild(msg);
    els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ==========================================
// YOUTUBE PLAYER
// ==========================================

let ytPlayer = null;
let ytApiReady = false;

// Загружаем YouTube IFrame API
// ВНИМАНИЕ: Если YouTube заблокирован, замени URL на прокси-сервер или
// используй альтернативный плеер (например, html5 <video> тег для VK Video, Rutube и т.д.)
// Пример: const YT_API_URL = 'https://your-proxy.com/youtube/iframe_api';
function loadYouTubeAPI() {
    const tag = document.createElement('script');
    // YouTube IFrame API
    // Если YouTube заблокирован, замени на зеркало или прокси:
    // tag.src = 'https://your-mirror.com/youtube/iframe_api';
    tag.src = 'https://www.youtube.com/iframe_api';
    const firstScriptTag = document.getElementsByTagName('script')[0];
    firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);
}

window.onYouTubeIframeAPIReady = function () {
    ytApiReady = true;
    console.log('YouTube IFrame API ready');
};

function createPlayer(videoId) {
    // Если YouTube заблокирован, используй альтернативный плеер:
    // 1. Rutube: <iframe src="https://rutube.ru/..."/>
    // 2. VK Video: <iframe src="https://vk.com/video_ext.php?..."/>
    // 3. Кастомный HTML5 плеер через прокси

    if (ytPlayer) {
        ytPlayer.loadVideoById(videoId);
        return;
    }

    els.playerPlaceholder.classList.add('hidden');

    ytPlayer = new YT.Player('player', {
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
            onReady: onPlayerReady,
            onStateChange: onPlayerStateChange,
        },
    });
}

function onPlayerReady(event) {
    state.playerReady = true;
    els.controls.classList.remove('hidden');
    console.log('Player ready');
}

function onPlayerStateChange(event) {
    if (state.isSyncing) return; // Игнорируем свои команды

    const YT_PLAYING = 1;
    const YT_PAUSED = 2;

    if (event.data === YT_PLAYING) {
        state.isPlaying = true;
        els.btnPlayPause.textContent = '⏸';
        wsSend({ action: 'play', timestamp: getCurrentTime(), sender: getUserDisplayName() });
    } else if (event.data === YT_PAUSED) {
        state.isPlaying = false;
        els.btnPlayPause.textContent = '▶️';
        wsSend({ action: 'pause', timestamp: getCurrentTime(), sender: getUserDisplayName() });
    }

    updateTimeDisplay();
}

function getCurrentTime() {
    if (ytPlayer && typeof ytPlayer.getCurrentTime === 'function') {
        return ytPlayer.getCurrentTime();
    }
    return 0;
}

function seekTo(seconds) {
    if (ytPlayer && typeof ytPlayer.seekTo === 'function') {
        ytPlayer.seekTo(seconds, true);
        wsSend({ action: 'seek', timestamp: seconds, sender: getUserDisplayName() });
    }
    updateTimeDisplay();
}

function playVideo() {
    if (ytPlayer && typeof ytPlayer.playVideo === 'function') {
        state.isSyncing = true;
        ytPlayer.playVideo();
        setTimeout(() => { state.isSyncing = false; }, 500);
    }
}

function pauseVideo() {
    if (ytPlayer && typeof ytPlayer.pauseVideo === 'function') {
        state.isSyncing = true;
        ytPlayer.pauseVideo();
        setTimeout(() => { state.isSyncing = false; }, 500);
    }
}

function updateTimeDisplay() {
    const time = getCurrentTime();
    els.currentTime.textContent = formatTime(time);
}

// Обновляем время каждую секунду
setInterval(updateTimeDisplay, 1000);

// ==========================================
// WEBSOCKET СИНХРОНИЗАЦИЯ
// ==========================================

function wsConnect(roomCode) {
    if (state.ws) {
        state.ws.close();
    }

    const url = `${SYNC_WS_URL}/${roomCode}`;
    console.log('Connecting to WebSocket:', url);

    state.ws = new WebSocket(url);

    state.ws.onopen = () => {
        console.log('WebSocket connected');
        addChatMessage('Система', 'Подключено к серверу синхронизации');
    };

    state.ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleWsMessage(data);
        } catch (e) {
            console.error('WS parse error:', e);
        }
    };

    state.ws.onclose = () => {
        console.log('WebSocket disconnected');
        // Переподключение через 3 секунды
        setTimeout(() => {
            if (state.roomCode) wsConnect(state.roomCode);
        }, 3000);
    };

    state.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
}

function wsSend(data) {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify(data));
    }
}

function handleWsMessage(data) {
    console.log('WS message:', data);

    if (data.type === 'state') {
        // Начальное состояние при подключении
        if (data.current_video_url) {
            const videoId = extractVideoId(data.current_video_url);
            if (videoId) createPlayer(videoId);
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
        const sender = data.sender || 'Неизвестный';
        addChatMessage(sender, getActionText(data));

        if (!ytPlayer) return;

        state.isSyncing = true;
        switch (data.action) {
            case 'play':
                ytPlayer.seekTo(data.timestamp, true);
                ytPlayer.playVideo();
                break;
            case 'pause':
                ytPlayer.seekTo(data.timestamp, true);
                ytPlayer.pauseVideo();
                break;
            case 'seek':
                ytPlayer.seekTo(data.timestamp, true);
                break;
            case 'set_video':
                const newVideoId = extractVideoId(data.url);
                if (newVideoId) createPlayer(newVideoId);
                break;
        }
        setTimeout(() => { state.isSyncing = false; }, 500);
        return;
    }

    if (data.type === 'chat') {
        addChatMessage(data.sender, data.text);
        return;
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
    if (state.userInfo) {
        return state.userInfo.first_name || state.userInfo.username || 'Аноним';
    }
    return 'Аноним';
}

// ==========================================
// ОБРАБОТЧИКИ СОБЫТИЙ
// ==========================================

// Кнопка "Присоединиться"
els.btnJoin.addEventListener('click', () => {
    const code = els.roomCodeInput.value.trim();
    if (!code) {
        tg?.HapticFeedback?.notificationOccurred('error');
        return;
    }
    enterRoom(code);
});

// Кнопка "Создать комнату"
els.btnCreate.addEventListener('click', () => {
    // Отправляем команду боту через WebApp
    tg?.sendData(JSON.stringify({ action: 'create_room' }));
    tg?.HapticFeedback?.notificationOccurred('success');
});

// Кнопка "Назад"
els.btnBack.addEventListener('click', () => {
    if (state.ws) state.ws.close();
    state.roomCode = null;
    showScreen(els.screenLobby);
});

// Кнопка Play/Pause
els.btnPlayPause.addEventListener('click', () => {
    if (!state.playerReady) return;
    tg?.HapticFeedback?.impactOccurred('medium');

    if (state.isPlaying) {
        pauseVideo();
    } else {
        playVideo();
    }
});

// Кнопка перемотки -10 сек
els.btnSeekBack.addEventListener('click', () => {
    if (!state.playerReady) return;
    tg?.HapticFeedback?.impactOccurred('light');
    seekTo(Math.max(0, getCurrentTime() - 10));
});

// Кнопка перемотки +10 сек
els.btnSeekForward.addEventListener('click', () => {
    if (!state.playerReady) return;
    tg?.HapticFeedback?.impactOccurred('light');
    seekTo(getCurrentTime() + 10);
});

// Кнопка "Добавить видео"
els.btnAddVideo.addEventListener('click', () => {
    const url = els.videoUrlInput.value.trim();
    if (!url) return;
    tg?.HapticFeedback?.notificationOccurred('success');

    // Отправляем через WebSocket для мгновенной синхронизации
    wsSend({
        action: 'set_video',
        url: url,
        sender: getUserDisplayName(),
    });

    // Также отправляем боту для сохранения в БД
    tg?.sendData(JSON.stringify({
        action: 'add_video',
        room_code: state.roomCode,
        url: url,
        title: url,
    }));

    els.videoUrlInput.value = '';

    // Создаём плеер если ещё нет
    const videoId = extractVideoId(url);
    if (videoId) createPlayer(videoId);
});

// Enter в поле видео
els.videoUrlInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') els.btnAddVideo.click();
});

// Кнопка "Отправить" в чате
els.btnSendChat.addEventListener('click', () => {
    sendChatMessage();
});

// Enter в чате
els.chatInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendChatMessage();
});

function sendChatMessage() {
    const text = els.chatInput.value.trim();
    if (!text) return;

    wsSend({
        action: 'chat',
        text: text,
        sender: getUserDisplayName(),
        sender_id: state.userInfo?.id || 0,
    });

    addChatMessage('Я', text);
    els.chatInput.value = '';
}

// ==========================================
// ВХОД В КОМНАТУ
// ==========================================

function enterRoom(roomCode) {
    state.roomCode = roomCode;
    els.roomCodeBadge.textContent = roomCode;
    els.roomTitle.textContent = 'Киновечер';

    showScreen(els.screenRoom);
    wsConnect(roomCode);

    // Запрашиваем данные о комнате у бота
    tg?.sendData(JSON.stringify({
        action: 'get_room_info',
        room_code: roomCode,
    }));

    tg?.HapticFeedback?.notificationOccurred('success');
}

// ==========================================
// ПАРСИНГ URL ПАРАМЕТРОВ
// ==========================================

function initFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const roomCode = params.get('room');
    if (roomCode) {
        enterRoom(roomCode);
    }
}

// ==========================================
// ИНИЦИАЛИЗАЦИЯ
// ==========================================

function init() {
    loadYouTubeAPI();
    initFromUrl();

    // Получаем данные пользователя из Telegram
    if (tg?.initDataUnsafe?.user) {
        state.userInfo = tg.initDataUnsafe.user;
        console.log('User:', state.userInfo);
    }
}

init();
