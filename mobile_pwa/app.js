// Spotify OAuth Configurations (Normalized Redirect URI with manual override support)
function getNormalizedRedirectURI() {
    const savedCustomUri = localStorage.getItem("spotify_custom_redirect_uri");
    if (savedCustomUri && savedCustomUri.trim()) {
        return savedCustomUri.trim();
    }

    let origin = window.location.origin;
    let pathname = window.location.pathname;
    
    // Strip index.html if present
    if (pathname.endsWith("index.html")) {
        pathname = pathname.substring(0, pathname.length - "index.html".length);
    }
    
    // Ensure trailing slash
    if (!pathname.endsWith("/")) {
        pathname += "/";
    }
    
    return origin + pathname;
}

let REDIRECT_URI = getNormalizedRedirectURI();
const AUTH_ENDPOINT = "https://accounts.spotify.com/authorize";
const TOKEN_ENDPOINT = "https://accounts.spotify.com/api/token";
const SCOPES = "user-modify-playback-state user-read-playback-state user-read-private user-library-read";

// DOM Elements
const loginBtn = document.getElementById("login-btn");
const logoutBtn = document.getElementById("logout-btn");
const authSection = document.getElementById("auth-section");
const loggedOutDiv = authSection.querySelector(".auth-logged-out");
const loggedInDiv = authSection.querySelector(".auth-logged-in");
const userName = document.getElementById("user-name");
const userAvatar = document.getElementById("user-avatar");
const activeDeviceName = document.getElementById("active-device-name");
const wakeLockStatus = document.getElementById("wake-lock-status");
const micTriggerBtn = document.getElementById("mic-trigger-btn");
const assistantPrompt = document.getElementById("assistant-prompt");
const transcriptDisplay = document.getElementById("transcript-display");
const assistantSection = document.getElementById("assistant-section");

// Playback Elements
const playBtn = document.getElementById("play-btn");
const playIcon = document.getElementById("play-icon");
const pauseIcon = document.getElementById("pause-icon");
const prevBtn = document.getElementById("prev-btn");
const nextBtn = document.getElementById("next-btn");

// Global State
let accessToken = localStorage.getItem("spotify_access_token") || null;
let refreshToken = localStorage.getItem("spotify_refresh_token") || null;
let tokenExpiry = localStorage.getItem("spotify_token_expiry") || 0;
let clientID = localStorage.getItem("spotify_client_id") || "";
let likedSongsCache = [];
let recognition = null;
let wakeLock = null;
let isListeningLoopActive = false;
let activePlaybackDevice = null;
let isWakeWordActive = false;
let wakeWordTimeout = null;
let ignoreAudioUntil = 0;
let mediaStream = null;

function suppressAcousticFeedback(durationMs = 2500) {
    ignoreAudioUntil = Date.now() + durationMs;
    console.log(`[Speech Engine] Suppressing acoustic feedback for ${durationMs}ms`);
}

// ==========================================
// 1. OAUTH 2.0 PKCE CRYPTOGRAPHY HELPERS
// ==========================================

function generateCodeVerifier() {
    const array = new Uint8Array(56);
    window.crypto.getRandomValues(array);
    return Array.from(array, dec => ('0' + dec.toString(16)).substr(-2)).join('');
}

async function sha256(plain) {
    const encoder = new TextEncoder();
    const data = encoder.encode(plain);
    return window.crypto.subtle.digest('SHA-256', data);
}

function base64urlencode(a) {
    let str = "";
    const bytes = new Uint8Array(a);
    const len = bytes.byteLength;
    for (let i = 0; i < len; i++) {
        str += String.fromCharCode(bytes[i]);
    }
    return btoa(str)
        .replace(/\+/g, "-")
        .replace(/\//g, "_")
        .replace(/=+$/, "");
}

async function generateCodeChallenge(v) {
    const hashed = await sha256(v);
    return base64urlencode(hashed);
}

// ==========================================
// 2. AUTHENTICATION FLOWS
// ==========================================

async function redirectToSpotifyAuth() {
    const clientIdInput = document.getElementById("client-id-input");
    const redirectUriInput = document.getElementById("redirect-uri-input");

    const inputVal = clientIdInput ? clientIdInput.value.trim() : "";
    if (inputVal) {
        clientID = inputVal;
        localStorage.setItem("spotify_client_id", clientID);
    }

    const customUriVal = redirectUriInput ? redirectUriInput.value.trim() : "";
    if (customUriVal) {
        localStorage.setItem("spotify_custom_redirect_uri", customUriVal);
        REDIRECT_URI = customUriVal;
    }

    if (!clientID) {
        showDebugError("Please paste your Spotify Client ID in the input box above first.");
        if (clientIdInput) clientIdInput.focus();
        return;
    }

    const verifier = generateCodeVerifier();
    localStorage.setItem("spotify_code_verifier", verifier);
    const challenge = await generateCodeChallenge(verifier);

    const params = new URLSearchParams({
        client_id: clientID,
        response_type: "code",
        redirect_uri: REDIRECT_URI,
        code_challenge_method: "S256",
        code_challenge: challenge,
        scope: SCOPES
    });

    console.log("[OAuth] Initiating authorization with Redirect URI:", REDIRECT_URI);
    window.location.href = `${AUTH_ENDPOINT}?${params.toString()}`;
}

async function handleAuthRedirectCallback() {
    const urlParams = new URLSearchParams(window.location.search);
    const errorParam = urlParams.get("error");
    
    if (errorParam) {
        console.error("Auth error parameter from Spotify:", errorParam);
        showDebugError(`Spotify Auth Error: ${errorParam}. Make sure Redirect URI matches exactly!`);
        return;
    }

    const code = urlParams.get("code");
    if (!code) return;

    const verifier = localStorage.getItem("spotify_code_verifier");
    clientID = localStorage.getItem("spotify_client_id");

    if (!verifier || !clientID) {
        console.error("Missing verifier or Client ID.");
        showDebugError("Missing OAuth session data. Please re-enter your Client ID and try again.");
        return;
    }

    try {
        const response = await fetch(TOKEN_ENDPOINT, {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: new URLSearchParams({
                client_id: clientID,
                grant_type: "authorization_code",
                code: code,
                redirect_uri: REDIRECT_URI,
                code_verifier: verifier
            })
        });

        const data = await response.json();
        if (data.access_token) {
            saveTokens(data);
            // Clear URL query parameters cleanly
            window.history.replaceState({}, document.title, window.location.pathname);
            initializeDashboard();
        } else {
            console.error("Token exchange failed:", data);
            showDebugError(`Token Error: ${data.error_description || data.error || 'Token exchange failed'}`);
        }
    } catch (err) {
        console.error("Redirect exchange error:", err);
    }
}

function saveTokens(data) {
    accessToken = data.access_token;
    if (data.refresh_token) {
        refreshToken = data.refresh_token;
        localStorage.setItem("spotify_refresh_token", refreshToken);
    }
    tokenExpiry = Date.now() + (data.expires_in * 1000);
    localStorage.setItem("spotify_access_token", accessToken);
    localStorage.setItem("spotify_token_expiry", tokenExpiry);
}

async function getValidToken() {
    if (Date.now() < tokenExpiry - 60000) {
        return accessToken;
    }

    if (!refreshToken) {
        logout();
        return null;
    }

    console.log("[Auth] Token expired. Fetching fresh access token...");
    try {
        const response = await fetch(TOKEN_ENDPOINT, {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: new URLSearchParams({
                client_id: clientID,
                grant_type: "refresh_token",
                refresh_token: refreshToken
            })
        });

        const data = await response.json();
        if (data.access_token) {
            saveTokens(data);
            return accessToken;
        } else {
            logout();
            return null;
        }
    } catch (err) {
        console.error("[Auth] Error refreshing token:", err);
        return null;
    }
}

function logout() {
    localStorage.clear();
    accessToken = null;
    refreshToken = null;
    tokenExpiry = 0;
    clientID = "";
    likedSongsCache = [];
    releaseWakeLock();
    stopListeningLoop();
    
    loggedOutDiv.classList.remove("hidden");
    loggedInDiv.classList.add("hidden");
    activeDeviceName.textContent = "No active device";
    activeDeviceName.className = "status-value warning-text";
}

// ==========================================
// 3. SPOTIFY PLAYER CLIENT API
// ==========================================

async function fetchFromSpotify(endpoint, method = "GET", body = null) {
    const token = await getValidToken();
    if (!token) {
        showDebugError("Token Error: Please disconnect and log in again.");
        return null;
    }

    const options = {
        method: method,
        headers: {
            "Authorization": `Bearer ${token}`,
            "Content-Type": "application/json"
        }
    };

    if (body) {
        options.body = JSON.stringify(body);
    }

    try {
        const response = await fetch(`https://api.spotify.com${endpoint}`, options);
        if (response.status === 204) return true;
        if (response.status === 403) {
            console.warn("[Spotify API] 403 Restriction violated.");
            showDebugError("Spotify Error 403: Restriction Violated (Is Spotify Premium active?)");
            return false;
        }
        if (response.status === 404) {
            showDebugError("Spotify Error 404: No active device found. Play a song in the Spotify app first!");
            return false;
        }
        if (response.status === 401) {
            showDebugError("Spotify Error 401: Session expired. Please logout and log back in.");
            return false;
        }
        
        // Handle endpoints that don't return JSON but aren't 204
        if (response.status >= 200 && response.status < 300) {
            const textContent = await response.text();
            try {
                return textContent ? JSON.parse(textContent) : true;
            } catch (e) {
                return true;
            }
        }
        
        const data = await response.json();
        if (data && data.error) {
            showDebugError(`Spotify Error: ${data.error.message}`);
        }
        return data;
    } catch (err) {
        console.error(`[Spotify API Error] ${endpoint}:`, err);
        showDebugError(`Network Error: ${err.message}`);
        return null;
    }
}

function showDebugError(msg) {
    transcriptDisplay.innerHTML = `<span style="color: var(--accent-red); font-weight: 600;">${msg}</span>`;
}

async function loadUserProfile() {
    const data = await fetchFromSpotify("/v1/me");
    if (data) {
        userName.textContent = data.display_name || "Spotify User";
        if (data.images && data.images.length > 0) {
            userAvatar.src = data.images[0].url;
        }
        loggedOutDiv.classList.add("hidden");
        loggedInDiv.classList.remove("hidden");
    }
}

async function checkActiveDevice() {
    const data = await fetchFromSpotify("/v1/me/player");
    if (data && data.device) {
        activePlaybackDevice = data.device;
        activeDeviceName.textContent = data.device.name;
        activeDeviceName.className = "status-value success-text";
        
        // Update local play/pause icon states
        if (data.is_playing) {
            playIcon.classList.add("hidden");
            pauseIcon.classList.remove("hidden");
        } else {
            playIcon.classList.remove("hidden");
            pauseIcon.classList.add("hidden");
        }
    } else {
        activeDeviceName.textContent = "No active device";
        activeDeviceName.className = "status-value warning-text";
    }
}

async function cacheLikedSongs() {
    likedSongsCache = [];
    console.log("[Cache] Preloading Liked Songs for Queue Rotation...");
    
    // Fetch top 50 Liked Songs (single chunk is fast and sufficient for mobile)
    const data = await fetchFromSpotify("/v1/me/tracks?limit=50");
    if (data && data.items) {
        likedSongsCache = data.items.map(item => ({
            name: item.track.name.toLowerCase().trim(),
            artist: item.track.artists[0].name.toLowerCase().trim(),
            uri: item.track.uri
        }));
        console.log(`[Cache] Loaded ${likedSongsCache.length} liked songs.`);
    }
}

// ==========================================
// 4. SCREEN WAKE LOCK CONTROL
// ==========================================

async function requestWakeLock() {
    try {
        if ('wakeLock' in navigator) {
            wakeLock = await navigator.wakeLock.request('screen');
            wakeLockStatus.textContent = "Active";
            wakeLockStatus.className = "status-value success-text";
            console.log("[Wake Lock] Screen Wake Lock acquired.");
            
            wakeLock.addEventListener('release', () => {
                console.log("[Wake Lock] Screen Wake Lock released.");
            });
        } else {
            wakeLockStatus.textContent = "Unsupported";
        }
    } catch (err) {
        console.error("[Wake Lock Error]", err);
        wakeLockStatus.textContent = "Error";
        wakeLockStatus.className = "status-value warning-text";
    }
}

function releaseWakeLock() {
    if (wakeLock) {
        wakeLock.release();
        wakeLock = null;
        wakeLockStatus.textContent = "Disabled";
        wakeLockStatus.className = "status-value warning-text";
    }
}

// ==========================================
// 5. WEB SPEECH API & VOICE DAEMON
// ==========================================

function initializeSpeechEngine() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        transcriptDisplay.textContent = "Speech Recognition unsupported in this browser.";
        return;
    }

    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = "en-IN"; // Target Indian English accent

    recognition.onstart = () => {
        isListeningLoopActive = true;
        assistantSection.classList.add("listening");
        assistantPrompt.textContent = "Listening for Wake Word...";
        transcriptDisplay.textContent = 'Say "Alexa" or "Nova" followed by your command...';
    };

    recognition.onresult = async (event) => {
        // Suppress microphone input during speaker startup buffer to prevent acoustic feedback loops
        if (Date.now() < ignoreAudioUntil) {
            console.log("[Speech Engine] Ignoring transcript during speaker audio startup buffer.");
            return;
        }

        const lastResultIndex = event.results.length - 1;
        const text = event.results[lastResultIndex][0].transcript.trim();
        const textLower = text.toLowerCase();
        console.log(`[Heard]: "${text}" (Wake active: ${isWakeWordActive})`);
        
        // Visual feedback: show what the phone heard on screen
        transcriptDisplay.textContent = `Heard: "${text}"`;

        // Case A: Wake word is already active, this is the command
        if (isWakeWordActive) {
            clearTimeout(wakeWordTimeout);
            isWakeWordActive = false;
            
            transcriptDisplay.textContent = `Processing: "${text}"`;
            await parseAndExecuteVoiceCommand(textLower);
            
            // Restore playback if command wasn't pause or new play/navigation
            const isPauseCommand = /pause|stop|boss|freeze/.test(textLower);
            const isPlayOrNavigationCommand = /play|start|resume|next|skip|prev|back/.test(textLower);
            if (wasPlayingBeforeDucking && !isPauseCommand && !isPlayOrNavigationCommand) {
                const shouldRestore = wasPlayingBeforeDucking;
                wasPlayingBeforeDucking = false;
                setTimeout(async () => {
                    if (shouldRestore) {
                        console.log("[Voice Daemon] Restoring playback...");
                        suppressAcousticFeedback(2500);
                        await fetchFromSpotify("/v1/me/player/play", "PUT");
                        checkActiveDevice();
                    }
                }, 1000);
            } else {
                wasPlayingBeforeDucking = false;
            }
            
            setTimeout(() => {
                assistantPrompt.textContent = "Listening for Wake Word...";
                assistantPrompt.style.color = "var(--text-primary)";
            }, 3000);
            return;
        }

        // Case B: Listening for wake word trigger ("Alex", "Alexa", "Nova", "Alexis")
        const wordsArray = textLower.match(/\b\w+\b/g) || [];
        const wordsSet = new Set(wordsArray);
        
        const wakeWordList = ["alexa", "alex", "nova", "innova", "alexis"];
        let matchedWake = null;

        for (const w of wakeWordList) {
            if (wordsSet.has(w)) {
                matchedWake = w;
                break;
            }
        }

        // If no wake word was spoken in this phrase, ignore it completely! Music continues playing smoothly.
        if (!matchedWake) {
            return;
        }

        console.log(`[Wake Word] Detected trigger: "${matchedWake}" in phrase: "${text}"`);
        
        // Extract trailing command (what was spoken after the wake word in the same sentence)
        const parts = textLower.split(matchedWake);
        const trailingCommand = parts[parts.length - 1].trim();

        // Duck volume/pause active music ONLY when a legitimate wake word is matched!
        wasPlayingBeforeDucking = false;
        console.log("[Voice Daemon] Ducking active playback for listening environment...");
        const pauseRes = await fetchFromSpotify("/v1/me/player/pause", "PUT");
        if (pauseRes === true) {
            wasPlayingBeforeDucking = true;
        }

        if (trailingCommand && trailingCommand.length > 1) {
            // One-shot execution: User said "Alex play Starboy" or "Alexa next"
            transcriptDisplay.textContent = `Processing: "${trailingCommand}"`;
            await parseAndExecuteVoiceCommand(trailingCommand);
            
            const isPauseCommand = /pause|stop|boss|freeze/.test(trailingCommand);
            const isPlayOrNavigationCommand = /play|start|resume|next|skip|prev|back/.test(trailingCommand);
            if (wasPlayingBeforeDucking && !isPauseCommand && !isPlayOrNavigationCommand) {
                const shouldRestore = wasPlayingBeforeDucking;
                wasPlayingBeforeDucking = false;
                setTimeout(async () => {
                    if (shouldRestore) {
                        console.log("[Voice Daemon] Restoring playback...");
                        suppressAcousticFeedback(2500);
                        await fetchFromSpotify("/v1/me/player/play", "PUT");
                        checkActiveDevice();
                    }
                }, 1000);
            } else {
                wasPlayingBeforeDucking = false;
            }
        } else {
            // Two-step execution: User said "Alex" or "Alexa". Duck music, change UI state, and wait for command.
            isWakeWordActive = true;
            assistantPrompt.textContent = "Listening to Command...";
            assistantPrompt.style.color = "var(--neon-green)";
            transcriptDisplay.textContent = "Speak your command now...";
            
            // Timeout after 6 seconds if no command is spoken
            wakeWordTimeout = setTimeout(() => {
                isWakeWordActive = false;
                assistantPrompt.textContent = "Listening for Wake Word...";
                assistantPrompt.style.color = "var(--text-primary)";
                transcriptDisplay.textContent = "Wake word timed out. Say 'Alex' or 'Alexa'...";
                
                if (wasPlayingBeforeDucking) {
                    wasPlayingBeforeDucking = false;
                    suppressAcousticFeedback(2500);
                    fetchFromSpotify("/v1/me/player/play", "PUT");
                }
            }, 6000);
        }
    };

    recognition.onerror = (event) => {
        console.error("[Speech Error]", event.error);
        if (event.error === 'not-allowed') {
            transcriptDisplay.textContent = "Microphone access blocked. Enable permissions in settings.";
            stopListeningLoop();
        }
    };

    recognition.onend = () => {
        // Auto-restart loop for continuous hands-free operation
        if (isListeningLoopActive) {
            console.log("[Speech] Loop ended. Auto-restarting...");
            recognition.start();
        }
    };
}

async function parseAndExecuteVoiceCommand(command) {
    if (!command) return;

    const words = command.split(" ");
    
    // 1. Playback Resuming / General Resume
    if (words.includes("resume") || words.includes("start") || (words.includes("play") && words.length === 1)) {
        suppressAcousticFeedback(2500);
        await fetchFromSpotify("/v1/me/player/play", "PUT");
        checkActiveDevice();
        return;
    }

    // 2. Playback Pausing
    if (words.includes("pause") || words.includes("stop") || words.includes("boss")) {
        await fetchFromSpotify("/v1/me/player/pause", "PUT");
        checkActiveDevice();
        return;
    }

    // 3. Skip Next (Direct execution, no pre-resume lag)
    if (words.includes("next") || words.includes("skip")) {
        console.log("[Playback] Skipping next...");
        suppressAcousticFeedback(2500);
        await fetchFromSpotify("/v1/me/player/next", "POST");
        setTimeout(checkActiveDevice, 300);
        return;
    }

    // 4. Skip Previous (Direct execution, no pre-resume lag)
    if (words.includes("previous") || words.includes("prev") || words.includes("back")) {
        console.log("[Playback] Returning previous...");
        suppressAcousticFeedback(2500);
        await fetchFromSpotify("/v1/me/player/previous", "POST");
        setTimeout(checkActiveDevice, 300);
        return;
    }

    // 5. Volume Changes
    if (words.includes("volume")) {
        const numMatch = command.match(/\d+/);
        if (numMatch) {
            const level = Math.min(100, Math.max(0, parseInt(numMatch[0])));
            await fetchFromSpotify(`/v1/me/player/volume?volume_percent=${level}`, "PUT");
        }
        return;
    }

    // 6. What's Playing status query
    if (words.includes("playing") || words.includes("status")) {
        const state = await fetchFromSpotify("/v1/me/player");
        if (state && state.item) {
            const trackName = state.item.name;
            const artistName = state.item.artists[0].name;
            transcriptDisplay.textContent = `Song: "${trackName}" by ${artistName}.`;
        } else {
            transcriptDisplay.textContent = "No song loaded.";
        }
        return;
    }

    // 7. General song playing query (e.g. "play Softly")
    if (words.includes("play")) {
        const queryIndex = words.indexOf("play") + 1;
        const query = words.slice(queryIndex).join(" ").trim();
        if (query) {
            suppressAcousticFeedback(2500);
            await playSongWithAutoplayQueue(query);
        }
    } else {
        // Fallback: entire transcript is treated as song search
        suppressAcousticFeedback(2500);
        await playSongWithAutoplayQueue(command);
    }
}

// Fuzzy Match & Autoplay Queue Rotation
async function playSongWithAutoplayQueue(queryText) {
    console.log(`[Voice Search]: "${queryText}"`);
    let matchedTrackURI = null;
    let finalTrackName = "";

    // A. Fuzzy Match against cached Liked Songs first
    if (likedSongsCache.length > 0) {
        let bestMatch = null;
        let highestScore = 0;

        for (const t of likedSongsCache) {
            const score = similarity(queryText, t.name);
            if (score > highestScore && score > 0.65) {
                highestScore = score;
                bestMatch = t;
            }
        }

        if (bestMatch) {
            console.log(`[Fuzzy Match]: Found "${bestMatch.name}" in Liked Songs (confidence ${Math.round(highestScore * 100)}%)`);
            finalTrackName = bestMatch.name;
            
            // Rotate list: find index and rearrange cached liked tracks
            const index = likedSongsCache.findIndex(t => t.uri === bestMatch.uri);
            const rotated = [
                bestMatch.uri,
                ...likedSongsCache.slice(index + 1).map(t => t.uri),
                ...likedSongsCache.slice(0, index).map(t => t.uri)
            ].slice(0, 50); // limit to 50 tracks to keep it fast

            await fetchFromSpotify("/v1/me/player/play", "PUT", { uris: rotated });
            setTimeout(checkActiveDevice, 800);
            return;
        }
    }

    // B. Global Catalog Search fallback
    console.log(`[Fuzzy Match] Not found in library. Searching global catalog: "${queryText}"`);
    const results = await fetchFromSpotify(`/v1/search?q=${encodeURIComponent(queryText)}&type=track&limit=1`);
    if (results && results.tracks && results.tracks.items.length > 0) {
        const track = results.tracks.items[0];
        matchedTrackURI = track.uri;
        finalTrackName = track.name;
        
        // Grab up to 10 random liked songs from cache to inject as the autoplay context
        let autoplayList = [matchedTrackURI];
        if (likedSongsCache.length > 0) {
            const shuffledLiked = [...likedSongsCache].sort(() => 0.5 - Math.random());
            const sample = shuffledLiked.slice(0, 10).map(t => t.uri);
            autoplayList = autoplayList.concat(sample);
            console.log(`[Autoplay] Loaded ${sample.length} random liked songs into queue context.`);
        }

        console.log(`[Global Search] Found track: "${finalTrackName}"`);
        await fetchFromSpotify("/v1/me/player/play", "PUT", { uris: autoplayList });
        setTimeout(checkActiveDevice, 800);
    } else {
        transcriptDisplay.textContent = `No tracks found for: "${queryText}"`;
    }
}

// Levenshtein distance string similarity score
function similarity(s1, s2) {
    let longer = s1;
    let shorter = s2;
    if (s1.length < s2.length) {
        longer = s2;
        shorter = s1;
    }
    const longerLength = longer.length;
    if (longerLength === 0) return 1.0;
    return (longerLength - editDistance(longer, shorter)) / parseFloat(longerLength);
}

function editDistance(s1, s2) {
    s1 = s1.toLowerCase();
    s2 = s2.toLowerCase();
    const costs = new Array();
    for (let i = 0; i <= s1.length; i++) {
        let lastValue = i;
        for (let j = 0; j <= s2.length; j++) {
            if (i == 0) costs[j] = j;
            else {
                if (j > 0) {
                    let newValue = costs[j - 1];
                    if (s1.charAt(i - 1) != s2.charAt(j - 1))
                        newValue = Math.min(Math.min(newValue, lastValue), costs[j]) + 1;
                    costs[j - 1] = lastValue;
                    lastValue = newValue;
                }
            }
        }
        if (i > 0) costs[s2.length] = lastValue;
    }
    return costs[s2.length];
}

// ==========================================
// 6. UI ACTIONS & LOOP LIFECYCLES
// ==========================================

function toggleListeningLoop() {
    if (isListeningLoopActive) {
        stopListeningLoop();
    } else {
        startListeningLoop();
    }
}

async function startListeningLoop() {
    if (isListeningLoopActive) return;
    
    // Acquire Web Audio stream with hardware echo cancellation first so Mobile OS allows continuous playback!
    try {
        if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
            mediaStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }
            });
            console.log("[Web Audio] Stream acquired with echo cancellation enabled.");
        }
    } catch (e) {
        console.warn("[Web Audio] getUserMedia stream warning:", e);
    }

    if (recognition) {
        isListeningLoopActive = true;
        isWakeWordActive = false;
        wasPlayingBeforeDucking = false;
        if (wakeWordTimeout) clearTimeout(wakeWordTimeout);
        try {
            recognition.start();
        } catch (err) {
            console.warn("[Speech] Recognition start warning:", err);
        }
        requestWakeLock();
    }
}

function stopListeningLoop() {
    if (isListeningLoopActive) {
        isListeningLoopActive = false;
        isWakeWordActive = false;
        wasPlayingBeforeDucking = false;
        if (wakeWordTimeout) clearTimeout(wakeWordTimeout);
        
        if (recognition) {
            try {
                recognition.stop();
            } catch (e) {}
        }
        
        if (mediaStream) {
            try {
                mediaStream.getTracks().forEach(track => track.stop());
            } catch (e) {}
            mediaStream = null;
        }

        releaseWakeLock();
        assistantSection.classList.remove("listening");
        assistantPrompt.textContent = "Wake Word Off";
        transcriptDisplay.textContent = "Tap to start voice recognition loop...";
    }
}

async function initializeDashboard() {
    await loadUserProfile();
    await checkActiveDevice();
    await cacheLikedSongs();
    
    // Poll device active state every 8 seconds to reflect manual changes
    setInterval(checkActiveDevice, 8000);
}

// Event Listeners
loginBtn.addEventListener("click", redirectToSpotifyAuth);
logoutBtn.addEventListener("click", logout);
micTriggerBtn.addEventListener("click", toggleListeningLoop);

// Manual Controls Event Listeners
playBtn.addEventListener("click", async () => {
    await checkActiveDevice();
    const state = await fetchFromSpotify("/v1/me/player");
    if (state) {
        if (state.is_playing) {
            await fetchFromSpotify("/v1/me/player/pause", "PUT");
            playIcon.classList.remove("hidden");
            pauseIcon.classList.add("hidden");
        } else {
            await fetchFromSpotify("/v1/me/player/play", "PUT");
            playIcon.classList.add("hidden");
            pauseIcon.classList.remove("hidden");
        }
    }
});

prevBtn.addEventListener("click", async () => {
    await fetchFromSpotify("/v1/me/player/previous", "POST");
    setTimeout(checkActiveDevice, 500);
});

nextBtn.addEventListener("click", async () => {
    await fetchFromSpotify("/v1/me/player/next", "POST");
    setTimeout(checkActiveDevice, 500);
});

// App Startup Initializer
window.addEventListener("DOMContentLoaded", () => {
    // Populate Redirect URI input and saved Client ID
    const redirectUriInput = document.getElementById("redirect-uri-input");
    const clientIdInput = document.getElementById("client-id-input");
    const copyUriBtn = document.getElementById("copy-uri-btn");
    const copyFeedback = document.getElementById("copy-feedback");

    if (redirectUriInput) {
        redirectUriInput.value = REDIRECT_URI;
        redirectUriInput.addEventListener("change", () => {
            const val = redirectUriInput.value.trim();
            if (val) {
                localStorage.setItem("spotify_custom_redirect_uri", val);
                REDIRECT_URI = val;
            } else {
                localStorage.removeItem("spotify_custom_redirect_uri");
                REDIRECT_URI = getNormalizedRedirectURI();
                redirectUriInput.value = REDIRECT_URI;
            }
        });
    }

    if (clientIdInput && clientID) {
        clientIdInput.value = clientID;
    }

    if (copyUriBtn) {
        copyUriBtn.addEventListener("click", () => {
            const uriToCopy = redirectUriInput ? redirectUriInput.value.trim() : REDIRECT_URI;
            navigator.clipboard.writeText(uriToCopy).then(() => {
                if (copyFeedback) {
                    copyFeedback.classList.remove("hidden");
                    setTimeout(() => copyFeedback.classList.add("hidden"), 2500);
                }
            }).catch(() => {
                prompt("Copy your exact Redirect URI:", uriToCopy);
            });
        });
    }

    handleAuthRedirectCallback();
    initializeSpeechEngine();
    
    if (accessToken) {
        initializeDashboard();
    }
});
