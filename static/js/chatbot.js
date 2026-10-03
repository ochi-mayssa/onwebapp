/* OnWebApp chat runtime: shared by the fixed widget and the /chatbot/ full page.
 *
 * One implementation, two surfaces. Every element is found through data-chat-*
 * attributes inside a [data-chat-root] container, so the same code drives the
 * panel widget and the inline page. Behaviour that the two copies previously
 * disagreed on (or lacked entirely) lives here once:
 *
 *   - a busy guard, so a double tap or a second Enter cannot fire two requests
 *   - the typed question is given back on failure, with a Try again button
 *   - Escape closes the panel and focus returns to the trigger; Tab is trapped
 *   - auto-scroll only when the reader is already at the bottom
 *   - answers render as paragraphs or a real list, via textContent only
 *   - the typing indicator is a held reference, not a global id, and stays up
 *     long enough to be read
 *   - "talk to a person" is one click away whenever the turn calls for it, both
 *     as a footer button and as channel buttons (call / WhatsApp / message)
 *     rendered under the answer
 *   - once the bot hands over, the widget polls for the agent's replies so the
 *     escalation is a two-way conversation, not a dead end
 */
(function (window, document) {
    'use strict';

    var MIN_TYPING_MS = 450;
    var STICK_THRESHOLD_PX = 60;
    var MAX_INPUT_CHARS = 500;
    var SESSION_KEY = 'chatbot_session_id';
    var NUDGE_KEY = 'chatbot_nudge_seen';

    function getCookie(name) {
        var value = null;
        document.cookie.split(';').forEach(function (part) {
            part = part.trim();
            if (part.indexOf(name + '=') === 0) {
                value = decodeURIComponent(part.substring(name.length + 1));
            }
        });
        return value;
    }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) { node.className = className; }
        if (text != null) { node.textContent = text; }
        return node;
    }

    function readSessionId() {
        try { return window.localStorage.getItem(SESSION_KEY) || null; } catch (e) { return null; }
    }

    function writeSessionId(id) {
        try { window.localStorage.setItem(SESSION_KEY, id); } catch (e) { /* private mode */ }
    }

    function init(root) {
        if (!root || root.dataset.chatReady === '1') { return; }
        root.dataset.chatReady = '1';

        var body = root.querySelector('[data-chat-body]');
        var input = root.querySelector('[data-chat-input]');
        var sendBtn = root.querySelector('[data-chat-send]');
        if (!body || !input || !sendBtn) { return; }

        var panel = root.querySelector('[data-chat-panel]');
        var trigger = root.querySelector('[data-chat-open]');
        var closeBtn = root.querySelector('[data-chat-close]');
        var nudge = root.querySelector('[data-chat-nudge]');
        var handoffBtn = root.querySelector('[data-chat-handoff]');
        var offerRow = root.querySelector('[data-chat-offer]');

        var cfg = {
            endpoint: root.dataset.chatEndpoint || '/chatbot/suggestions/',
            statusEndpoint: root.dataset.chatStatusEndpoint || '',
            waiting: root.dataset.chatWaiting || 'Someone from the team will join this chat shortly.',
            greeting: root.dataset.chatGreeting || '',
            deferGreeting: root.dataset.chatDefer === '1',
            refPrefix: root.dataset.chatRefPrefix || 'For more information, visit the',
            refPage: root.dataset.chatRefPage || 'page.',
            refPages: root.dataset.chatRefPages || 'pages.',
            errorHttp: root.dataset.chatErrorHttp || 'Sorry, something went wrong. Please try again.',
            errorNetwork: root.dataset.chatErrorNetwork || 'Network error. Please check your connection and try again.',
            retry: root.dataset.chatRetry || 'Try again',
            empty: root.dataset.chatEmpty || "I'm not sure how to help with that.",
            handoff: root.dataset.chatHandoff || ''
        };

        var sessionId = readSessionId();
        var busy = false;
        var typingNode = null;
        var typingShownAt = 0;
        var typingTimer = null;
        var greetingShown = false;
        var resumed = false;

        /* ---------- scrolling ---------- */

        function atBottom() {
            return body.scrollHeight - body.scrollTop - body.clientHeight < STICK_THRESHOLD_PX;
        }

        function append(node, forceStick) {
            // Yanking the reader to the bottom every time a node arrives is the
            // single most annoying thing a chat log can do to someone re-reading
            // an earlier answer, so only follow along when they are already there.
            var stick = forceStick === true || atBottom();
            body.appendChild(node);
            if (stick) { body.scrollTop = body.scrollHeight; }
        }

        /* ---------- messages ---------- */

        function addUserMessage(text) {
            var node = el('div', 'owa-chat-msg user');
            node.appendChild(el('strong', null, 'You:'));
            node.appendChild(document.createTextNode(' ' + text));
            append(node, true);
        }

        function renderParts(host, parts, format) {
            host.textContent = '';
            var wrap = el('div', 'owa-chat-parts');
            if (format === 'bullets') {
                var ul = el('ul');
                parts.forEach(function (text) { ul.appendChild(el('li', null, text)); });
                wrap.appendChild(ul);
            } else {
                parts.forEach(function (text) { wrap.appendChild(el('p', null, text)); });
            }
            host.appendChild(wrap);
        }

        function addBotMessage(text) {
            var node = el('div', 'owa-chat-msg bot', text || cfg.empty);
            append(node);
            return node;
        }

        function addBotParts(parts, format, fallbackText) {
            var node = el('div', 'owa-chat-msg bot');
            if (parts && parts.length) {
                renderParts(node, parts, format);
            } else {
                node.textContent = fallbackText || cfg.empty;
            }
            append(node);
            return node;
        }

        function addSystemMessage(text) {
            append(el('div', 'owa-chat-msg system', text));
        }

        // The widget defers its greeting until the panel is opened, but a
        // returning visitor's agent replies are already waiting, so the greeting
        // has to be able to appear after them without being shown twice.
        function showGreetingOnce() {
            if (greetingShown || !cfg.greeting) { return; }
            greetingShown = true;
            addBotMessage(cfg.greeting);
        }

        // A reply typed by a human in the call centre dashboard. Deliberately a
        // different colour from the bot's bubble so the visitor always knows
        // they have stopped talking to the bot.
        function addAgentMessage(text, who) {
            var node = el('div', 'owa-chat-msg agent');
            node.appendChild(el('strong', null, (who || 'Support') + ':'));
            node.appendChild(document.createTextNode(' ' + text));
            append(node, true);
        }

        function addErrorMessage(message, question) {
            var node = el('div', 'owa-chat-msg bot');
            node.appendChild(document.createTextNode(message));
            var retry = el('button', 'owa-chat-retry', cfg.retry);
            retry.type = 'button';
            retry.addEventListener('click', function () {
                node.remove();
                input.value = question;
                input.focus();
                send({ alreadyShown: true });
            });
            node.appendChild(retry);
            append(node);
        }

        function showTyping() {
            if (typingNode) { return; }
            var node = el('div', 'owa-chat-typing');
            node.setAttribute('role', 'status');
            node.setAttribute('aria-label', 'Typing');
            node.appendChild(el('span'));
            node.appendChild(el('span'));
            node.appendChild(el('span'));
            typingNode = node;
            typingShownAt = Date.now();
            append(node);
        }

        function hideTyping() {
            if (!typingNode) { return; }
            var node = typingNode;
            var wait = MIN_TYPING_MS - (Date.now() - typingShownAt);
            typingNode = null;
            if (wait <= 0) {
                node.remove();
                return;
            }
            // A fast reply would otherwise flash the dots for a few frames.
            typingTimer = setTimeout(function () {
                typingTimer = null;
                if (node.parentNode) { node.remove(); }
            }, wait);
        }

        function flushTyping() {
            if (typingTimer) { clearTimeout(typingTimer); typingTimer = null; }
            if (typingNode) { typingNode.remove(); typingNode = null; }
        }

        function addSuggestions(suggestions) {
            if (!suggestions || !suggestions.length) { return; }
            var container = el('div', 'owa-chat-chips');
            suggestions.forEach(function (suggestion) {
                var title = (suggestion && suggestion.title) || '';
                if (!title) { return; }
                var chip = el(suggestion.url ? 'a' : 'button', 'owa-chat-chip');
                chip.type = 'button';
                if (suggestion.url) {
                    chip.href = suggestion.url;
                } else {
                    chip.addEventListener('click', function () {
                        input.value = title;
                        send();
                    });
                }
                if (suggestion.content) { chip.title = suggestion.content; }
                if (suggestion.url) {
                    chip.appendChild(el('i', 'fas fa-arrow-up-right-from-square'));
                }
                chip.appendChild(document.createTextNode(title));
                container.appendChild(chip);
            });
            if (container.childNodes.length) { append(container); }
        }

        function addPageReference(links) {
            if (!links || !links.length) { return; }
            var node = el('div', 'owa-chat-ref');
            node.appendChild(document.createTextNode(cfg.refPrefix + ' '));
            links.forEach(function (link, i) {
                var a = el('a', null, '"' + link.title + '"');
                a.href = link.url;
                a.target = '_blank';
                a.rel = 'noopener';
                node.appendChild(a);
                if (i < links.length - 1) {
                    var joiner = (links.length === 2 || i === links.length - 2) ? ' or ' : ', ';
                    node.appendChild(document.createTextNode(joiner));
                }
            });
            node.appendChild(document.createTextNode(
                ' ' + (links.length > 1 ? cfg.refPages : cfg.refPage)
            ));
            append(node);
        }

        /* ---------- live-agent handoff ---------- */

        // The way to reach a person is shown only when it is relevant to what
        // was just asked: a person or details were requested, or the bot could
        // not answer. The server decides, because it is the only side that knows
        // whether the answer was confident. A "Call" button under every reply
        // gets ignored exactly when it is needed.
        function setCallOffer(visible) {
            if (!offerRow || !cfg.handoff) { return; }
            offerRow.hidden = visible !== true;
            if (offerRow.hidden) {
                offerRow.classList.remove('show');
            } else {
                offerRow.classList.add('show');
            }
        }

        // Channel buttons ("Call us now", "WhatsApp us", "Send a message").
        // Built with textContent like every other node here, so a reply can
        // never inject markup. tel: and wa.me links must not open in a new tab:
        // a phone link that does nothing is worse than no phone link.
        function addActions(actions) {
            if (!actions || !actions.length) { return; }
            var row = el('div', 'owa-chat-actions');
            actions.forEach(function (action) {
                if (!action || !action.url || !action.label) { return; }
                var a = el('a', 'owa-chat-action');
                a.href = action.url;
                if (action.kind !== 'form') {
                    a.target = '_blank';
                    a.rel = 'noopener';
                }
                if (action.icon) {
                    a.appendChild(el('i', action.icon));
                }
                var label = el('span', null, action.label);
                a.appendChild(label);
                if (action.detail) {
                    a.appendChild(el('small', null, action.detail));
                }
                row.appendChild(a);
            });
            if (row.childNodes.length) { append(row, true); }
        }

        /* ---------- network ---------- */

        function setBusy(state) {
            busy = state;
            sendBtn.disabled = state;
            input.disabled = state;
            if (handoffBtn) { handoffBtn.disabled = state; }
            sendBtn.setAttribute('aria-busy', state ? 'true' : 'false');
        }

        function send(options) {
            if (busy) { return; }
            var alreadyShown = !!(options && options.alreadyShown);
            var text = input.value ? input.value.trim() : '';
            if (!text) { return; }
            if (text.length > MAX_INPUT_CHARS) {
                text = text.slice(0, MAX_INPUT_CHARS);
                input.value = text;
            }

            setBusy(true);
            if (!alreadyShown) { addUserMessage(text); }
            input.value = '';
            showTyping();

            var payload = { message: text };
            if (sessionId) { payload.session_id = sessionId; }

            var failed = false;

            window.fetch(cfg.endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken') || ''
                },
                body: JSON.stringify(payload)
            }).then(function (res) {
                if (!res.ok) {
                    var httpError = new Error('http ' + res.status);
                    httpError.owaHttp = true;
                    throw httpError;
                }
                return res.json();
            }).then(function (data) {
                if (data && data.session_id) {
                    sessionId = data.session_id;
                    writeSessionId(sessionId);
                }
                hideTyping();
                var reply = (data && data.reply) || '';
                addBotParts(data && data.reply_parts, data && data.reply_format, reply);
                addPageReference(data && data.links);
                addSuggestions(data && data.suggestions);
                addActions(data && data.actions);
                setCallOffer(data && data.offer_call);
                beginLiveAgent(data && data.call);
            }).catch(function (error) {
                hideTyping();
                failed = true;
                addErrorMessage(
                    error && error.owaHttp ? cfg.errorHttp : cfg.errorNetwork, text
                );
                // Hand the question back so it is not lost, and let them edit it.
                input.value = text;
            }).then(function () {
                setBusy(false);
                // Only now that the input is enabled again, so focus really lands.
                if (failed) { input.focus(); }
            });
        }

        // The persistent "talk to a person" escape hatch. It goes through the
        // normal send path rather than calling the endpoint directly, so the
        // escalation lands in the same session log the team would read.
        function requestHandoff() {
            if (!cfg.handoff || busy) { return; }
            input.value = cfg.handoff;
            send();
        }

        /* ---------- live agent ---------- */

        var pollTimer = null;
        var lastSeen = 0;
        var pollAttempts = 0;
        var MAX_POLL_ATTEMPTS = 120; // 10 minutes at 5s, then stop bothering the server
        var POLL_MS = 5000;

        function stopPolling() {
            if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
        }

        function schedulePoll() {
            if (pollTimer || !cfg.statusEndpoint) { return; }
            pollTimer = setInterval(pollOnce, POLL_MS);
        }

        function pollOnce() {
            if (!sessionId || pollAttempts >= MAX_POLL_ATTEMPTS) {
                stopPolling();
                return;
            }
            pollAttempts += 1;

            window.fetch(cfg.statusEndpoint + '?session_id=' + encodeURIComponent(sessionId) +
                '&since=' + encodeURIComponent(lastSeen), {
                credentials: 'same-origin'
            }).then(function (res) {
                return res.ok ? res.json() : null;
            }).then(function (data) {
                if (!data) { return; }
                if (data.now) { lastSeen = new Date(data.now).getTime() / 1000; }
                (data.messages || []).forEach(function (message) {
                    addAgentMessage(message.content, message.agent);
                });
                if (data.status === 'RESOLVED') {
                    stopPolling();
                }
            }).catch(function () { /* keep trying; a dropped poll is not fatal */ });
        }

        // Called once the bot has handed the conversation over. The visitor is
        // told to wait, then hears from the agent through the same log.
        function beginLiveAgent(call) {
            if (!call || !call.escalated) { return; }
            if (cfg.waiting) { addSystemMessage(cfg.waiting); }
            lastSeen = 0;
            pollAttempts = 0;
            schedulePoll();
        }

        // Someone who reloads or navigates away mid-conversation is still in the
        // queue, and must not have to ask again to find that out. The session id
        // outlives the page in local storage, so the agent's side of the
        // conversation can be picked back up with one request.
        function resumeIfWaiting() {
            if (resumed || !sessionId || !cfg.statusEndpoint) { return; }
            window.fetch(cfg.statusEndpoint + '?session_id=' + encodeURIComponent(sessionId) +
                '&since=0', { credentials: 'same-origin' }).then(function (res) {
                return res.ok ? res.json() : null;
            }).then(function (data) {
                if (!data || !data.escalated) { return; }
                resumed = true;
                showGreetingOnce();
                setCallOffer(true);
                if (data.status === 'RESOLVED') { return; }
                (data.messages || []).forEach(function (message) {
                    addAgentMessage(message.content, message.agent);
                });
                if (cfg.waiting) { addSystemMessage(cfg.waiting); }
                if (data.now) { lastSeen = new Date(data.now).getTime() / 1000; }
                pollAttempts = 0;
                schedulePoll();
            }).catch(function () { /* not waiting after all */ });
        }

        /* ---------- open / close / focus ---------- */
        function focusableNodes() {
            if (!panel) { return []; }
            return Array.prototype.slice.call(panel.querySelectorAll(
                'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'
            )).filter(function (node) {
                return node.offsetParent !== null || node === document.activeElement;
            });
        }

        function openPanel() {
            if (!panel) { return; }
            dismissNudge();
            panel.classList.add('open');
            panel.setAttribute('aria-hidden', 'false');
            if (trigger) { trigger.setAttribute('aria-expanded', 'true'); }
            showGreetingOnce();
            // The page may have loaded before the queue request came back.
            resumeIfWaiting();
            input.focus();
        }

        function closePanel() {
            if (!panel) { return; }
            panel.classList.remove('open');
            panel.setAttribute('aria-hidden', 'true');
            if (trigger) {
                trigger.setAttribute('aria-expanded', 'false');
                trigger.focus();
            }
        }

        function trapTab(event) {
            var nodes = focusableNodes();
            if (!nodes.length) { return; }
            var first = nodes[0];
            var last = nodes[nodes.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        }

        /* ---------- nudge ---------- */

        var nudgeTimer = null;

        function stopNudge() {
            if (nudgeTimer) { clearTimeout(nudgeTimer); nudgeTimer = null; }
            if (nudge) { nudge.classList.remove('show'); }
        }

        function dismissNudge() {
            if (!nudge) { return; }
            stopNudge();
            try { window.sessionStorage.setItem(NUDGE_KEY, '1'); } catch (e) { /* private mode */ }
        }

        function startNudge() {
            if (!nudge) { return; }
            var seen = false;
            try { seen = window.sessionStorage.getItem(NUDGE_KEY) === '1'; } catch (e) { seen = false; }
            if (seen) { return; }
            nudgeTimer = setTimeout(function () {
                nudgeTimer = null;
                if (panel && panel.classList.contains('open')) { return; }
                nudge.classList.add('show');
            }, 0);
        }

        /* ---------- wiring ---------- */

        sendBtn.addEventListener('click', function () { send(); });
        input.addEventListener('keydown', function (event) {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                send();
            }
        });
        input.addEventListener('input', function () {
            if (input.value.length > MAX_INPUT_CHARS) {
                input.value = input.value.slice(0, MAX_INPUT_CHARS);
            }
        });

        if (trigger) {
            trigger.addEventListener('click', openPanel);
        }
        if (closeBtn) {
            closeBtn.addEventListener('click', closePanel);
        }
        // No configured handoff means no button, rather than one that lies.
        if (handoffBtn && cfg.handoff) {
            handoffBtn.addEventListener('click', requestHandoff);
        } else if (handoffBtn) {
            handoffBtn.remove();
            if (offerRow) { offerRow.remove(); offerRow = null; }
        }
        // Hidden until a turn earns it, including for any surface whose markup
        // was hand-written without the hidden attribute.
        setCallOffer(false);
        if (panel) {
            panel.addEventListener('keydown', function (event) {
                if (event.key === 'Escape') {
                    event.preventDefault();
                    closePanel();
                    return;
                }
                if (event.key === 'Tab') { trapTab(event); }
            });
        }

        window.addEventListener('pagehide', flushTyping);
        // A poll left running after the tab is hidden is pure waste.
        document.addEventListener('visibilitychange', function () {
            if (document.hidden) { stopPolling(); }
        });

        if (!cfg.deferGreeting) { showGreetingOnce(); }
        resumeIfWaiting();
        startNudge();

        root.owaChat = {
            send: send,
            open: openPanel,
            close: closePanel,
            handoff: requestHandoff,
            setCallOffer: setCallOffer,
            stopPolling: stopPolling
        };
    }

    function initAll() {
        var roots = document.querySelectorAll('[data-chat-root]');
        Array.prototype.forEach.call(roots, init);
    }

    window.OnWebAppChat = { init: init, initAll: initAll };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAll);
    } else {
        initAll();
    }
})(window, document);
