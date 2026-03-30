// ==UserScript==
// @name         Duelingbook Replay Capture
// @namespace    http://tampermonkey.net/
// @version      4.0
// @description  Adds a button to capture the replay ID at any time
// @author       Yugioh Pro Games
// @match        https://www.duelingbook.com/*
// @grant        GM_xmlhttpRequest
// @connect      localhost
// ==/UserScript==

(function () {
    'use strict';

    const APP_URL = 'http://localhost:5001/api/capture-replay';

    // Press Alt+C to capture the replay at any time
    // capture:true intercepts before the game canvas handles the event
    window.addEventListener('keydown', function (e) {
        // Alt/Option + C (e.code works on Mac where e.key produces 'ç')
        if (e.altKey && e.code === 'KeyC') {
            e.preventDefault();
            e.stopPropagation();
            captureReplay();
        }
    }, true);

    function captureReplay() {
        const btn = document.querySelector('#draw_btn');
        if (!btn) {
            showNotification('❌ draw_btn no encontrado');
            return;
        }

        btn.style.opacity = '1';
        btn.style.display = 'block';
        btn.click();

        setTimeout(function () {
            const url = window.location.href;
            const match = url.match(/[?&]id=([^\s&]+)/);
            if (!match) {
                showNotification('❌ ID no encontrado en URL:\n' + url);
                return;
            }
            sendToApp(match[1], url);
        }, 1500);
    }

    function sendToApp(replayId, replayUrl) {
        showNotification('⏳ Enviando replay ' + replayId + '...');
        GM_xmlhttpRequest({
            method: 'POST',
            url: APP_URL,
            headers: { 'Content-Type': 'application/json' },
            data: JSON.stringify({ replay_id: replayId, replay_url: replayUrl }),
            onload: function (res) {
                if (res.status === 200 || res.status === 201) {
                    showNotification('✅ Replay ' + replayId + ' agregado!');
                } else {
                    showNotification('⚠️ Error: ' + res.responseText);
                }
            },
            onerror: function () {
                showNotification('📋 Replay ID: ' + replayId + '\n(App no disponible)');
            }
        });
    }

    function showNotification(msg) {
        const div = document.createElement('div');
        div.textContent = msg;
        div.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #1a1d27;
            color: #e0e0e0;
            border: 1px solid #3b82f6;
            border-radius: 8px;
            padding: 14px 18px;
            font-size: 14px;
            font-family: sans-serif;
            z-index: 99999;
            max-width: 320px;
            white-space: pre-line;
            box-shadow: 0 4px 20px rgba(0,0,0,0.5);
        `;
        document.body.appendChild(div);
        setTimeout(function () { div.remove(); }, 8000);
    }

})();
