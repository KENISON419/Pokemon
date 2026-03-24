const WS_URL = `ws://${window.location.hostname || '127.0.0.1'}:8765`;
const POLL_INTERVAL_MS = 2000;

class PokechampIntegrationPanel {
    constructor() {
        this.socket = null;
        this.app = null;
        this.lastSnapshotHash = '';
        this.lastAnalysisAt = 0;
        this.root = this.createRoot();
        this.bindApp();
        this.connect();
        this.startPolling();
    }

    createRoot() {
        const root = document.createElement('aside');
        root.id = 'pokechamp-integration-root';
        root.innerHTML = `
            <div class="integration-grid">
                <section class="integration-card">
                    <div class="integration-badge">PokéChamp × battle-assistant-sv-main</div>
                    <h2>統合提案</h2>
                    <p id="integration-connection-status" class="integration-status-warn">接続中...</p>
                    <p id="integration-model-name">Ollama model: 確認中</p>
                    <div class="integration-actions">
                        <button id="integration-refresh-button" type="button">今すぐ解析</button>
                    </div>
                </section>
                <section class="integration-card">
                    <h3>推奨手</h3>
                    <div id="integration-recommendation">まだ提案はありません。</div>
                </section>
                <section class="integration-card">
                    <h3>候補手ランキング</h3>
                    <ul id="integration-candidates" class="integration-list"></ul>
                </section>
                <section class="integration-card">
                    <h3>PokéChamp予測</h3>
                    <div id="integration-predictor-summary">未解析</div>
                </section>
                <section class="integration-card">
                    <h3>統合ログ</h3>
                    <div id="integration-summary-log">待機中</div>
                </section>
            </div>
        `;
        document.body.appendChild(root);
        root.querySelector('#integration-refresh-button').addEventListener('click', () => {
            this.pushSnapshot(true);
        });
        return root;
    }

    bindApp() {
        if (window.pbaApp) {
            this.app = window.pbaApp;
        }
        window.addEventListener('pba-ready', (event) => {
            this.app = event.detail;
            this.setStatus('battle-assistant 接続完了', 'ok');
        });
    }

    connect() {
        this.socket = new WebSocket(WS_URL);
        this.socket.addEventListener('open', () => {
            this.setStatus('中間器接続済み', 'ok');
            this.socket.send(JSON.stringify({type: 'hello'}));
        });
        this.socket.addEventListener('close', () => {
            this.setStatus('中間器との接続が切断されました', 'error');
            window.setTimeout(() => this.connect(), 3000);
        });
        this.socket.addEventListener('error', () => {
            this.setStatus('中間器接続エラー', 'error');
        });
        this.socket.addEventListener('message', (event) => {
            this.handleMessage(event.data);
        });
    }

    startPolling() {
        window.setInterval(() => this.pushSnapshot(false), POLL_INTERVAL_MS);
    }

    pushSnapshot(force) {
        if (!this.app || !this.socket || this.socket.readyState !== WebSocket.OPEN) {
            return;
        }
        const snapshot = this.app.getIntegrationSnapshot();
        const hash = JSON.stringify({
            phase: snapshot.phase,
            self: snapshot.currentPokemon?.name,
            enemy: snapshot.currentEnemy?.name,
            hp: snapshot.enemyHPratio,
            attackRows: snapshot.ui?.attackRows,
            defenceRows: snapshot.ui?.defenceRows,
        });
        if (!force && hash === this.lastSnapshotHash) {
            return;
        }
        this.lastSnapshotHash = hash;
        this.lastAnalysisAt = Date.now();
        this.socket.send(JSON.stringify({
            type: 'state_update',
            payload: {snapshot},
        }));
        this.setStatus('解析中...', 'warn');
    }

    handleMessage(rawMessage) {
        const message = JSON.parse(rawMessage);
        if (message.type === 'hello') {
            const payload = message.payload || {};
            this.root.querySelector('#integration-model-name').textContent = `Ollama model: ${payload.ollama_model}`;
            this.setStatus('中間器接続済み', 'ok');
            return;
        }
        if (message.type === 'analysis') {
            this.renderAnalysis(message.payload || {});
            const latency = Date.now() - this.lastAnalysisAt;
            this.setStatus(`解析完了 (${latency}ms)`, 'ok');
            return;
        }
        if (message.type === 'error') {
            this.setStatus(message.payload?.message || 'エラー', 'error');
        }
    }

    renderAnalysis(payload) {
        const recommendation = payload.recommendation;
        const recommendationNode = this.root.querySelector('#integration-recommendation');
        if (recommendation) {
            recommendationNode.innerHTML = `
                <p><span class="integration-inline-label">提案</span>${recommendation.action_type}: ${recommendation.action_id}</p>
                <p><span class="integration-inline-label">根拠</span>${recommendation.reason}</p>
                <p><span class="integration-inline-label">信頼度</span>${Math.round((recommendation.confidence || 0) * 100)}%</p>
                <p><span class="integration-inline-label">生成元</span>${recommendation.source}</p>
            `;
        } else {
            recommendationNode.textContent = '提案なし';
        }

        const candidatesNode = this.root.querySelector('#integration-candidates');
        const candidates = payload.candidate_actions || [];
        candidatesNode.innerHTML = candidates.map((candidate) => `
            <li>
                <strong>${candidate.action_type}: ${candidate.action_id}</strong><br>
                score ${candidate.score}<br>
                ${candidate.rationale}
            </li>
        `).join('') || '<li>候補なし</li>';

        const predictorNode = this.root.querySelector('#integration-predictor-summary');
        const predictor = payload.predictor_summary || {};
        if (predictor.available) {
            predictorNode.innerHTML = `
                <p><span class="integration-inline-label">相手</span>${predictor.active_enemy}</p>
                <p><span class="integration-inline-label">持ち物</span>${predictor.predicted_item || '不明'}</p>
                <p><span class="integration-inline-label">特性</span>${predictor.predicted_ability || '不明'}</p>
                <p><span class="integration-inline-label">技</span>${(predictor.predicted_moves || []).join(', ') || '不明'}</p>
                <p><span class="integration-inline-label">テラ</span>${predictor.predicted_tera || '不明'}</p>
            `;
        } else {
            predictorNode.textContent = predictor.reason || 'Bayesian予測なし';
        }

        this.root.querySelector('#integration-summary-log').textContent = payload.summary || '要約なし';
    }

    setStatus(message, kind) {
        const node = this.root.querySelector('#integration-connection-status');
        node.textContent = message;
        node.className = '';
        node.classList.add(
            kind === 'ok' ? 'integration-status-ok' : kind === 'error' ? 'integration-status-error' : 'integration-status-warn'
        );
    }
}

window.addEventListener('DOMContentLoaded', () => {
    new PokechampIntegrationPanel();
});
