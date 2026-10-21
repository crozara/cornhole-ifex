/**
 * =============================================================================
 * CORNHOLE INTELIGENTE - IFEx 2026
 * Arquivo: frontend/app.js
 * Função: Motor do Navegador (Client-side) - Interface do Fliperama
 * =============================================================================
 * O QUE ESTE ARQUIVO FAZ?
 * 1. Mantém a conexão WebSocket aberta em tempo real com o servidor Python.
 * 2. Controla o Cronômetro de Precisão a 60 quadros por segundo (60 FPS).
 * 3. Toca os sons nostálgicos 8-bit chamando o 'audio.js'.
 * 4. Renderiza na tela a tabela do Ranking Top 10 com pódio e tempos.
 * 5. Escuta as teclas do teclado ([ESPAÇO], [O], [B], [P], [F]) para jogar.
 * =============================================================================
 */

// -----------------------------------------------------------------------------
// 1. Mapeamento dos Elementos Visuais do HTML (DOM)
// -----------------------------------------------------------------------------
// Guardamos referências aos elementos da tela para atualizar textos e luzes rapidamente
const dom = {
    wsDot: document.getElementById('wsDot'),                   // Bolinha verde/vermelha de status da conexão
    wsStatus: document.getElementById('wsStatus'),             // Texto "ONLINE" ou "DESCONECTADO"
    playerName: document.getElementById('playerName'),         // Nome do jogador da vez na tela
    playerTag: document.getElementById('playerTag'),           // Turma ou curso do competidor
    displayTimer: document.getElementById('displayTimer'),     // Caixa do cronômetro gigante
    displayScore: document.getElementById('displayScore'),     // Caixa da pontuação gigante
    ammoCountLabel: document.getElementById('ammoCountLabel'), // Contador de saquinhos (ex: "3 / 5 LANÇADOS")
    bannerTitle: document.getElementById('bannerTitle'),       // Título do banner inferior de instruções
    bannerSubtitle: document.getElementById('bannerSubtitle'), // Subtítulo do banner de instruções
    rankingHeaderTitle: document.getElementById('rankingHeaderTitle'), // Título da tabela de ranking ("GLOBAL" ou "TURMA X")
    btnFilterGeral: document.getElementById('btnFilterGeral'), // Aba para ver o Placar Geral
    selectGroupFilter: document.getElementById('selectGroupFilter'), // Menu suspenso para filtrar por Turma/Grupo
    rankingTableBody: document.getElementById('rankingTableBody'), // Corpo da tabela do Ranking Top 10
    scorePopup: document.getElementById('scorePopup'),         // Efeito flutuante de "+3 BURACO" ou "+1 PRANCHA"
    operatorModal: document.getElementById('operatorModal'),   // Janela modal de cadastro do competidor
    btnOpenOperator: document.getElementById('btnOpenOperator'), // Botão superior que abre o painel do operador
    btnCloseModal: document.getElementById('btnCloseModal'),   // Botão 'X' para fechar a janela modal
    selectJogador: document.getElementById('selectJogador'),   // Menu suspenso com lista de alunos cadastrados
    labelSelectJogador: document.getElementById('labelSelectJogador'), // Rótulo com a contagem da fila
    btnSelectExisting: document.getElementById('btnSelectExisting'), // Botão para confirmar aluno selecionado
    inputNome: document.getElementById('inputNome'),           // Campo de texto para digitar novo nome
    inputApelido: document.getElementById('inputApelido'),     // Campo de texto para turma/curso
    btnCadastrarNovo: document.getElementById('btnCadastrarNovo'), // Botão para salvar novo cadastro e jogar agora
    btnAdicionarFila: document.getElementById('btnAdicionarFila'), // Botão para adicionar à fila de espera
    modalFeedback: document.getElementById('modalFeedback'),   // Mensagem de feedback de cadastro
    btnAudioToggle: document.getElementById('btnAudioToggle'), // Botão para ligar ou mutar o som
    btnActionEspaco: document.getElementById('btnActionEspaco'), // Botão principal de ação arcade (Espaço)
    btnActionIcon: document.getElementById('btnActionIcon'),   // Ícone do botão principal
    btnActionLabel: document.getElementById('btnActionLabel'), // Texto do botão principal
    btnSimHole: document.getElementById('btnSimHole'),         // Botão de simular buraco
    btnSimBoard: document.getElementById('btnSimBoard'),       // Botão de simular prancha
    btnSimMiss: document.getElementById('btnSimMiss'),         // Botão de simular fora
    btnSimReset: document.getElementById('btnSimReset'),        // Botão de resetar
    btnSalvarBackup: document.getElementById('btnSalvarBackup'), // Botão para salvar cópia de segurança
    btnRestaurarBackup: document.getElementById('btnRestaurarBackup'), // Botão para restaurar backup
    btnExportarCsv: document.getElementById('btnExportarCsv'),   // Botão para baixar planilhas CSV
    btnZerarBanco: document.getElementById('btnZerarBanco'),     // Botão perigoso para zerar banco com senha
    securityFeedback: document.getElementById('securityFeedback'), // Feedback visual de segurança
    backupNoticeLabel: document.getElementById('backupNoticeLabel') // Rótulo de status de backup
};

// -----------------------------------------------------------------------------
// 2. Variáveis de Estado Interno da Tela
// -----------------------------------------------------------------------------
let ws = null;                      // Conexão WebSocket com o Python
let timerAnimationFrameId = null;  // Identificador do loop de animação do cronômetro
let timerStartEpoch = null;        // Horário exato em que a partida foi iniciada
let currentState = "ESPERA";       // Estado atual do jogo (ESPERA, PRONTO, JOGANDO, FINALIZADA)
let activeMatchId = null;          // ID da partida que está rolando agora
let currentSaquinhos = [];         // Histórico dos saquinhos arremessados na rodada atual
let selectedGroup = "";            // Turma/grupo atualmente filtrado (vazio = GERAL)
let availableGroups = [];          // Lista de todas as turmas cadastradas no sistema

// -----------------------------------------------------------------------------
// 3. Funções do Cronômetro de Alta Fluidez (60 FPS)
// -----------------------------------------------------------------------------
/**
 * Converte milissegundos brutos em texto digital formatado: "00:14.320"
 */
function formatMs(ms) {
    if (ms === null || ms === undefined || ms < 0) return "00:00.000";
    const totalSecs = Math.floor(ms / 1000);
    const mins = Math.floor(totalSecs / 60);
    const secs = totalSecs % 60;
    const millis = ms % 1000;
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}.${String(millis).padStart(3, '0')}`;
}

/**
 * Loop do Cronômetro:
 * Usa 'requestAnimationFrame', que sincroniza a atualização do cronômetro
 * com a taxa de atualização do monitor (geralmente 60 vezes por segundo).
 * Isso faz com que os números corram suaves e macios na tela, sem travar o navegador.
 */
function startTimerLoop() {
    stopTimerLoop();
    function tick() {
        if (currentState === "JOGANDO" && timerStartEpoch) {
            const elapsed = Date.now() - timerStartEpoch;
            dom.displayTimer.textContent = formatMs(elapsed);
            timerAnimationFrameId = requestAnimationFrame(tick);
        }
    }
    timerAnimationFrameId = requestAnimationFrame(tick);
}

/**
 * Trava o cronômetro imediatamente.
 */
function stopTimerLoop() {
    if (timerAnimationFrameId) {
        cancelAnimationFrame(timerAnimationFrameId);
        timerAnimationFrameId = null;
    }
}

// -----------------------------------------------------------------------------
// 4. Animações e Efeitos Visuais
// -----------------------------------------------------------------------------
/**
 * Dispara um texto flutuante neon na tela quando o competidor acerta o alvo
 */
function triggerScorePopup(texto, cor) {
    dom.scorePopup.textContent = texto;
    dom.scorePopup.style.color = cor;
    dom.scorePopup.classList.remove('animate-popup');
    // Força o navegador a reiniciar a animação CSS
    void dom.scorePopup.offsetWidth;
    dom.scorePopup.classList.add('animate-popup');
}

/**
 * Desenha as linhas da Tabela do Ranking Top 10 com medalhas e tempos de desempate
 */
function renderRankingTable(ranking) {
    if (!ranking || ranking.length === 0) {
        dom.rankingTableBody.innerHTML = `
            <tr>
                <td colspan="5" style="text-align: center; color: var(--text-dim); padding: 30px;">
                    Nenhuma partida registrada hoje. Seja o primeiro a jogar!
                </td>
            </tr>`;
        return;
    }

    dom.rankingTableBody.innerHTML = ranking.map(r => {
        let medalha = `#${r.posicao}`;
        let rowClass = "";
        if (r.posicao === 1) {
            medalha = "🥇 1º";
            rowClass = "ranking-row-top1"; // Dourado
        } else if (r.posicao === 2) {
            medalha = "🥈 2º";
            rowClass = "ranking-row-top2"; // Prateado
        } else if (r.posicao === 3) {
            medalha = "🥉 3º";
            rowClass = "ranking-row-top3"; // Bronze
        }

        // Destaca a linha se for a partida que o competidor acabou de jogar
        const isCurrentMatch = (activeMatchId && r.partida_id === activeMatchId);
        const highlightStyle = isCurrentMatch ? "border-left: 4px solid var(--neon-yellow); background: rgba(255, 230, 0, 0.15);" : "";

        return `
            <tr class="${rowClass}" style="${highlightStyle}">
                <td><span class="pos-badge">${medalha}</span></td>
                <td><strong>${r.nome_jogador}</strong></td>
                <td><span style="color: var(--text-dim);">${r.apelido_jogador || 'IFEx'}</span></td>
                <td class="col-points">${r.pontuacao_total} pts</td>
                <td class="col-time">${r.tempo_formatado || (r.tempo_segundos + 's')}</td>
            </tr>
        `;
    }).join('');
}

/**
 * Preenche o menu suspenso do operador com os nomes dos jogadores cadastrados
 */
function populatePlayersSelect(jogadores) {
    if (!jogadores || !dom.selectJogador) return;
    const currentVal = dom.selectJogador.value;
    const total = jogadores.length;
    
    dom.selectJogador.innerHTML = `<option value="">-- Escolha um competidor (${total} na fila) --</option>` +
        jogadores.map(j => `<option value="${j.id}">${j.nome} (${j.apelido || 'IFEx'})</option>`).join('');
        
    if (currentVal) dom.selectJogador.value = currentVal;

    if (dom.labelSelectJogador) {
        dom.labelSelectJogador.textContent = `OU SELECIONE ALGUÉM DA FILA (${total} CADASTRADOS):`;
    }
}

/**
 * Exibe uma mensagem rápida de confirmação no modal do operador
 */
function showModalFeedback(texto, cor = "var(--neon-green)") {
    if (!dom.modalFeedback) return;
    dom.modalFeedback.textContent = texto;
    dom.modalFeedback.style.display = "block";
    dom.modalFeedback.style.color = cor;
    dom.modalFeedback.style.background = "rgba(0, 0, 0, 0.4)";
    dom.modalFeedback.style.border = `1px solid ${cor}`;
    setTimeout(() => {
        if (dom.modalFeedback) dom.modalFeedback.style.display = "none";
    }, 3500);
}

/**
 * Exibe status das operações de segurança e backup no modal do operador
 */
function showSecurityFeedback(texto, cor = "var(--neon-cyan)") {
    if (!dom.securityFeedback) return;
    dom.securityFeedback.textContent = texto;
    dom.securityFeedback.style.display = "block";
    dom.securityFeedback.style.color = cor;
    dom.securityFeedback.style.background = "rgba(0, 0, 0, 0.6)";
    dom.securityFeedback.style.border = `1px solid ${cor}`;
    if (dom.backupNoticeLabel) {
        dom.backupNoticeLabel.textContent = "Última ação: agora mesmo";
    }
    setTimeout(() => {
        if (dom.securityFeedback) dom.securityFeedback.style.display = "none";
    }, 5000);
}

// -----------------------------------------------------------------------------
// 5. Atualização da Interface conforme o Estado do Jogo
// -----------------------------------------------------------------------------
/**
 * Atualiza o HUD dos 5 saquinhos na tela do fliperama:
 * - Ícone e cor para BURACO (🎯 +3), PRANCHA (🪵 +1), FORA (💨 0)
 * - Realça o próximo arremesso ativo quando em jogo
 */
function renderBagSlots(saquinhos = []) {
    currentSaquinhos = saquinhos || [];
    const total = currentSaquinhos.length;

    if (dom.ammoCountLabel) {
        if (total >= 5) {
            dom.ammoCountLabel.textContent = "5 / 5 LANÇADOS (FINALIZADA)";
            dom.ammoCountLabel.style.color = "var(--neon-green)";
        } else {
            dom.ammoCountLabel.textContent = `${total} / 5 LANÇADOS`;
            dom.ammoCountLabel.style.color = "var(--text-dim)";
        }
    }

    for (let i = 1; i <= 5; i++) {
        const slot = document.getElementById(`bagSlot${i}`);
        if (!slot) continue;

        const iconEl = slot.querySelector('.bag-icon');
        const statusEl = slot.querySelector('.bag-status');
        const arremesso = currentSaquinhos[i - 1];

        // Reseta classes do slot
        slot.className = 'hud-pill';

        if (arremesso) {
            if (arremesso.sensor === 'BURACO') {
                slot.classList.add('scored-hole');
                if (iconEl) iconEl.textContent = '🎯';
                if (statusEl) statusEl.textContent = '+3 PTS';
            } else if (arremesso.sensor === 'PRANCHA') {
                slot.classList.add('scored-board');
                if (iconEl) iconEl.textContent = '🪵';
                if (statusEl) statusEl.textContent = '+1 PTO';
            } else {
                slot.classList.add('scored-miss');
                if (iconEl) iconEl.textContent = '💨';
                if (statusEl) statusEl.textContent = '0 PTS';
            }
        } else {
            // Se o jogo está rolando e este é o próximo saquinho a ser lançado
            if (currentState === 'JOGANDO' && i === total + 1) {
                slot.classList.add('active');
                if (iconEl) iconEl.textContent = '⏳';
                if (statusEl) statusEl.textContent = `${i}º SACO`;
            } else {
                if (iconEl) iconEl.textContent = '⚪';
                if (statusEl) statusEl.textContent = `${i}º SACO`;
            }
        }
    }
}

/**
 * Preenche o menu suspenso de filtro de turmas/grupos no Ranking
 */
function populateGroupFilter(grupos = []) {
    if (!dom.selectGroupFilter) return;
    availableGroups = grupos || [];
    const currentVal = dom.selectGroupFilter.value;

    let html = `<option value="">👥 TODAS AS TURMAS (${availableGroups.length}) ▾</option>`;
    availableGroups.forEach(g => {
        html += `<option value="${g}">${g}</option>`;
    });
    dom.selectGroupFilter.innerHTML = html;
    if (currentVal && availableGroups.includes(currentVal)) {
        dom.selectGroupFilter.value = currentVal;
    }
}

/**
 * Alterna a visualização da tabela de ranking entre Placar Geral e Placar da Turma
 */
function setRankingFilter(grupo) {
    selectedGroup = grupo ? grupo.trim() : "";
    if (!selectedGroup) {
        if (dom.btnFilterGeral) dom.btnFilterGeral.classList.add('active');
        if (dom.selectGroupFilter) dom.selectGroupFilter.value = "";
        if (dom.rankingHeaderTitle) dom.rankingHeaderTitle.textContent = "🏆 RANKING GLOBAL IFEx";
        sendWs({ tipo: "OBTER_RANKING", grupo: null });
        fetch('/api/ranking')
            .then(r => r.json())
            .then(data => renderRankingTable(data))
            .catch(() => {});
    } else {
        if (dom.btnFilterGeral) dom.btnFilterGeral.classList.remove('active');
        if (dom.selectGroupFilter) dom.selectGroupFilter.value = selectedGroup;
        if (dom.rankingHeaderTitle) dom.rankingHeaderTitle.textContent = `👥 RANKING: ${selectedGroup.toUpperCase()}`;
        sendWs({ tipo: "OBTER_RANKING", grupo: selectedGroup });
        fetch(`/api/ranking?grupo=${encodeURIComponent(selectedGroup)}`)
            .then(r => r.json())
            .then(data => renderRankingTable(data))
            .catch(() => {});
    }
}

function applyState(data) {
    currentState = data.estado || currentState;
    activeMatchId = data.partida_id || activeMatchId;

    // Atualiza nome do competidor
    if (data.jogador_atual) {
        dom.playerName.textContent = data.jogador_atual.nome;
        dom.playerTag.textContent = data.jogador_atual.apelido || "IFEx";
    } else if (currentState === "ESPERA") {
        dom.playerName.textContent = "Aguardando Seleção...";
        dom.playerTag.textContent = "---";
    }

    // Atualiza placar na tela
    dom.displayScore.textContent = String(data.pontuacao_atual || 0).padStart(2, '0');

    // Atualiza Ranking, turmas e lista de seleção
    if (data.ranking && !selectedGroup) renderRankingTable(data.ranking);
    if (data.jogadores_cadastrados) populatePlayersSelect(data.jogadores_cadastrados);
    if (data.grupos) populateGroupFilter(data.grupos);

    // Atualiza o rack visual com os 5 saquinhos
    if (data.saquinhos !== undefined) {
        renderBagSlots(data.saquinhos);
    } else if (data.ultimo_resultado && data.ultimo_resultado.saquinhos) {
        renderBagSlots(data.ultimo_resultado.saquinhos);
    } else if (currentState === "ESPERA" || currentState === "PRONTO") {
        renderBagSlots([]);
    }

    // Atualiza botão principal arcade conforme o estado
    if (dom.btnActionEspaco) {
        if (currentState === "ESPERA") {
            dom.btnActionEspaco.className = "arcade-btn btn-main-space";
            if (dom.btnActionIcon) dom.btnActionIcon.textContent = "▶️";
            if (dom.btnActionLabel) dom.btnActionLabel.textContent = "INICIAR RODADA";
        } else if (currentState === "PRONTO") {
            dom.btnActionEspaco.className = "arcade-btn btn-main-space";
            if (dom.btnActionIcon) dom.btnActionIcon.textContent = "🚀";
            if (dom.btnActionLabel) dom.btnActionLabel.textContent = "LARGAR CRONÔMETRO";
        } else if (currentState === "JOGANDO") {
            dom.btnActionEspaco.className = "arcade-btn btn-main-space running";
            if (dom.btnActionIcon) dom.btnActionIcon.textContent = "⏹️";
            if (dom.btnActionLabel) dom.btnActionLabel.textContent = "PARAR TEMPO MANUAL";
        } else if (currentState === "FINALIZADA") {
            dom.btnActionEspaco.className = "arcade-btn btn-main-space finished";
            if (dom.btnActionIcon) dom.btnActionIcon.textContent = "🔄";
            if (dom.btnActionLabel) dom.btnActionLabel.textContent = "PRÓXIMO COMPETIDOR";
        }
    }

    // Ajusta banners e cronômetro para cada um dos 4 estados
    if (currentState === "ESPERA") {
        stopTimerLoop();
        dom.displayTimer.textContent = "00:00.000";
        dom.bannerTitle.textContent = "CORNHOLE INTELIGENTE";
        dom.bannerSubtitle.textContent = "Aperte [ESPAÇO] para iniciar ou [O] para selecionar o jogador da vez.";
    } else if (currentState === "PRONTO") {
        stopTimerLoop();
        dom.displayTimer.textContent = "00:00.000";
        dom.bannerTitle.textContent = "JOGADOR NA LINHA DE TIRO!";
        dom.bannerSubtitle.textContent = "APERTE [ESPAÇO] PARA DISPARAR O CRONÔMETRO E COMEÇAR!";
    } else if (currentState === "JOGANDO") {
        dom.bannerTitle.textContent = "RODADA EM ANDAMENTO!";
        dom.bannerSubtitle.textContent = "LANCE OS 5 SAQUINHOS! O TEMPO TRAVA AUTOMATICAMENTE NO 5º ARREMESSO.";
        if (!timerAnimationFrameId) {
            timerStartEpoch = Date.now() - (data.tempo_decorrido_ms || 0);
            startTimerLoop();
        }
    } else if (currentState === "FINALIZADA") {
        stopTimerLoop();
        const tempoFinal = data.tempo_final_ms || (data.ultimo_resultado ? data.ultimo_resultado.tempo_final_ms : 0);
        dom.displayTimer.textContent = formatMs(tempoFinal);

        const recorde = data.ultimo_resultado && data.ultimo_resultado.bateu_recorde;
        if (recorde) {
            dom.bannerTitle.textContent = "🎉 NOVO RECORDE NO TOP 3 DO IFEx!";
            dom.bannerSubtitle.textContent = `Pontuação e tempo salvos no Postgres! Aperte [ESPAÇO] para o próximo competidor.`;
        } else {
            dom.bannerTitle.textContent = "🏁 RODADA FINALIZADA COM SUCESSO!";
            dom.bannerSubtitle.textContent = `Tempo cravado no PostgreSQL! Aperte [ESPAÇO] para o próximo competidor.`;
        }
    }
}

// -----------------------------------------------------------------------------
// 6. Gerenciador de Conexão WebSocket em Tempo Real (/ws)
// -----------------------------------------------------------------------------
let reconnectTimeout = null;
function connectWebSocket() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        return;
    }
    if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
        reconnectTimeout = null;
    }

    // Detecta se estamos rodando em http (ws://) ou https (wss://)
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host || 'localhost:8080';
    const wsUrl = `${protocol}//${host}/ws`;

    dom.wsStatus.textContent = "CONECTANDO...";
    dom.wsDot.className = "connection-dot";

    try {
        ws = new WebSocket(wsUrl);
    } catch (e) {
        dom.wsStatus.textContent = "DESCONECTADO (TENTANDO EM 2s...)";
        dom.wsDot.className = "connection-dot";
        reconnectTimeout = setTimeout(connectWebSocket, 2000);
        return;
    }

    // Conexão estabelecida com sucesso
    ws.onopen = () => {
        dom.wsStatus.textContent = "ONLINE (TEMPO REAL)";
        dom.wsDot.className = "connection-dot online";
    };

    // Mensagens recebidas do servidor Python
    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);

            // 1. Estado inicial ou sincronização
            if (msg.tipo === "ESTADO_ATUAL") {
                applyState(msg);
            } 
            // 2. Partida disparada (dispara cronômetro e toca som de largada)
            else if (msg.tipo === "PARTIDA_INICIADA") {
                window.arcadeAudio.playStart();
                timerStartEpoch = Date.now();
                currentSaquinhos = [];
                renderBagSlots([]);
                applyState({
                    estado: "JOGANDO",
                    partida_id: msg.partida_id,
                    jogador_atual: msg.jogador,
                    pontuacao_atual: 0,
                    saquinhos: []
                });
            } 
            // 3. Saquinho pontuou (toca o som correspondente e mostra popup neon)
            else if (msg.tipo === "SAQUINHO_PONTUOU") {
                if (msg.sensor === 'BURACO') {
                    window.arcadeAudio.playHole();
                    triggerScorePopup("+3 BURACO! 🎯", "#ff0055");
                } else if (msg.sensor === 'PRANCHA') {
                    window.arcadeAudio.playBoard();
                    triggerScorePopup("+1 PRANCHA! 🪵", "#00f0ff");
                } else {
                    window.arcadeAudio.playMiss();
                    triggerScorePopup("FORA! 💨", "#888888");
                }

                dom.displayScore.textContent = String(msg.pontuacao_total).padStart(2, '0');

                // Adiciona o arremesso ao rack visual
                currentSaquinhos.push({
                    numero: msg.numero_saquinho,
                    sensor: msg.sensor,
                    pontos: msg.pontos,
                    tempo_parcial_ms: msg.tempo_parcial_ms
                });
                renderBagSlots(currentSaquinhos);

                // TRAVA IMEDIATA NO FRONT-END NO 5º ARREMESSO:
                // O cronômetro para no exato milissegundo do 5º arremesso sem depender de nenhuma outra mensagem
                if (msg.numero_saquinho >= 5 || msg.finalizada) {
                    stopTimerLoop();
                    currentState = "FINALIZADA";
                    if (msg.tempo_parcial_ms) {
                        dom.displayTimer.textContent = formatMs(msg.tempo_parcial_ms);
                    }
                    if (dom.btnActionEspaco) {
                        dom.btnActionEspaco.className = "arcade-btn btn-main-space finished";
                        if (dom.btnActionIcon) dom.btnActionIcon.textContent = "🔄";
                        if (dom.btnActionLabel) dom.btnActionLabel.textContent = "PRÓXIMO COMPETIDOR";
                    }
                }
            } 
            // 4. Rodada finalizada (trava o tempo e toca fanfarra ou game over)
            else if (msg.tipo === "PARTIDA_FINALIZADA") {
                stopTimerLoop();
                const res = msg.resultado;
                // Aguarda 350ms para que o som do impacto do 5º arremesso seja ouvido antes da fanfarra
                setTimeout(() => {
                    if (res.bateu_recorde) {
                        window.arcadeAudio.playHighScore();
                    } else {
                        window.arcadeAudio.playGameOver();
                    }
                }, 350);

                if (msg.grupos) populateGroupFilter(msg.grupos);

                applyState({
                    estado: "FINALIZADA",
                    tempo_final_ms: res.tempo_final_ms,
                    pontuacao_atual: res.pontuacao_final,
                    ultimo_resultado: res,
                    ranking: selectedGroup ? null : msg.ranking,
                    saquinhos: res.saquinhos || currentSaquinhos,
                    grupos: msg.grupos
                });
            } 
            // 5. Reset ou cancelamento
            else if (msg.tipo === "RESET_ESPERA" || msg.tipo === "PARTIDA_CANCELADA") {
                currentSaquinhos = [];
                renderBagSlots([]);
                applyState({
                    estado: "ESPERA",
                    jogador_atual: null,
                    partida_id: null,
                    pontuacao_atual: 0,
                    saquinhos: [],
                    ranking: selectedGroup ? null : msg.ranking
                });
            } 
            // 6. Novo jogador selecionado
            else if (msg.tipo === "JOGADOR_SELECIONADO") {
                currentSaquinhos = [];
                renderBagSlots([]);
                if (msg.grupos) populateGroupFilter(msg.grupos);
                applyState({
                    estado: msg.estado,
                    jogador_atual: msg.jogador,
                    pontuacao_atual: 0,
                    saquinhos: [],
                    jogadores_cadastrados: msg.jogadores_cadastrados,
                    grupos: msg.grupos
                });
            }
            // 7. Jogador apenas adicionado à fila ou lista atualizada
            else if (msg.tipo === "JOGADOR_CADASTRADO_FILA" || msg.tipo === "LISTA_JOGADORES") {
                if (msg.jogadores_cadastrados) {
                    populatePlayersSelect(msg.jogadores_cadastrados);
                }
                if (msg.grupos) {
                    populateGroupFilter(msg.grupos);
                }
            }
            // 8. Ranking filtrado recebido (geral ou por turma específica)
            else if (msg.tipo === "RANKING_ATUALIZADO") {
                renderRankingTable(msg.ranking);
            }
            // 9. Lista de turmas/grupos recebida
            else if (msg.tipo === "LISTA_GRUPOS") {
                if (msg.grupos) populateGroupFilter(msg.grupos);
            }
            // 10. Mensagens de Segurança e Backup
            else if (msg.tipo === "BACKUP_CONCLUIDO") {
                showSecurityFeedback(msg.mensagem, msg.sucesso ? "var(--neon-green)" : "var(--neon-red)");
                if (msg.sucesso) playSound("RECORD");
            }
            else if (msg.tipo === "RESTAURACAO_CONCLUIDA") {
                showSecurityFeedback(msg.mensagem, msg.sucesso ? "var(--neon-green)" : "var(--neon-red)");
                if (msg.sucesso) playSound("CORNHOLIO");
            }
            else if (msg.tipo === "BANCO_ZERADO") {
                showSecurityFeedback(msg.mensagem, msg.sucesso ? "var(--neon-yellow)" : "var(--neon-red)");
                if (msg.sucesso) playSound("RESET");
            }
            else if (msg.tipo === "CSV_EXPORTADO") {
                showSecurityFeedback(msg.mensagem, msg.sucesso ? "var(--neon-green)" : "var(--neon-red)");
                if (msg.sucesso) playSound("RECORD");
            }
        } catch (e) {
            console.error("Erro ao tratar mensagem WebSocket:", e);
        }
    };

    // Se a conexão cair (ex: servidor reiniciou), tenta reconectar automaticamente a cada 2s
    ws.onclose = () => {
        dom.wsStatus.textContent = "DESCONECTADO (TENTANDO EM 2s...)";
        dom.wsDot.className = "connection-dot";
        if (!reconnectTimeout) {
            reconnectTimeout = setTimeout(connectWebSocket, 2000);
        }
    };

    ws.onerror = (err) => {
        console.warn("[WebSocket Erro]:", err);
    };
}

/**
 * Função utilitária para enviar pacotes JSON para o Back-end
 */
function sendWs(payload) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(payload));
    }
}

// -----------------------------------------------------------------------------
// 7. Controle da Janela do Operador (Modal [O])
// -----------------------------------------------------------------------------
function toggleOperatorModal(forceOpen) {
    const isCurrentlyActive = dom.operatorModal.classList.contains('active');
    const targetState = (forceOpen !== undefined) ? forceOpen : !isCurrentlyActive;
    if (targetState) {
        dom.operatorModal.classList.add('active');
        dom.inputNome.focus();
        if (dom.modalFeedback) dom.modalFeedback.style.display = "none";
        
        // Solicita imediatamente a lista atualizada de jogadores da fila
        sendWs({ tipo: "LISTAR_JOGADORES" });
        fetch('/api/jogadores')
            .then(r => r.json())
            .then(data => populatePlayersSelect(data))
            .catch(() => {});
    } else {
        dom.operatorModal.classList.remove('active');
    }
}

dom.btnOpenOperator.addEventListener('click', () => toggleOperatorModal(true));
dom.btnCloseModal.addEventListener('click', () => toggleOperatorModal(false));
dom.operatorModal.addEventListener('click', (e) => {
    if (e.target === dom.operatorModal) toggleOperatorModal(false);
});

// Seleção de competidor já existente
if (dom.btnSelectExisting && dom.selectJogador) {
    dom.btnSelectExisting.addEventListener('click', () => {
        const jogadorId = dom.selectJogador.value;
        if (!jogadorId) {
            alert("Por favor, selecione um jogador na lista!");
            return;
        }
        sendWs({ tipo: "SELECIONAR_JOGADOR", jogador_id: jogadorId });
        toggleOperatorModal(false);
    });
}

// Cadastro de novo competidor para JOGAR AGORA (Entra na linha de arremesso)
dom.btnCadastrarNovo.addEventListener('click', () => {
    const nome = dom.inputNome.value.trim();
    const apelido = dom.inputApelido.value.trim();
    if (!nome) {
        alert("Digite o nome completo do jogador!");
        return;
    }
    sendWs({ tipo: "CADASTRAR_JOGADOR", nome: nome, apelido: apelido, apenas_fila: false });
    dom.inputNome.value = "";
    dom.inputApelido.value = "";
    toggleOperatorModal(false);
});

// Cadastro de novo competidor APENAS NA FILA (Sem interromper a tela atual)
if (dom.btnAdicionarFila) {
    dom.btnAdicionarFila.addEventListener('click', () => {
        const nome = dom.inputNome.value.trim();
        const apelido = dom.inputApelido.value.trim();
        if (!nome) {
            alert("Digite o nome completo do jogador!");
            return;
        }
        sendWs({ tipo: "CADASTRAR_JOGADOR", nome: nome, apelido: apelido, apenas_fila: true });
        showModalFeedback(`✅ "${nome}" adicionado à fila com sucesso!`, "var(--neon-green)");
        dom.inputNome.value = "";
        dom.inputApelido.value = "";
        dom.inputNome.focus();
    });
}

// Navegação rápida por ENTER nos campos de cadastro
dom.inputNome.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        e.preventDefault();
        dom.inputApelido.focus();
    }
});

dom.inputApelido.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        e.preventDefault();
        dom.btnCadastrarNovo.click();
    }
});

// Alternar Áudio Mudo
dom.btnAudioToggle.addEventListener('click', () => {
    const isMuted = window.arcadeAudio.toggleMute();
    dom.btnAudioToggle.textContent = isMuted ? "🔇 SOM: OFF" : "🔊 SOM: ON";
    dom.btnAudioToggle.style.color = isMuted ? "var(--text-dim)" : "var(--neon-cyan)";
});

// Botão Principal Arcade [ESPAÇO]
if (dom.btnActionEspaco) {
    dom.btnActionEspaco.addEventListener('click', () => sendWs({ tipo: "ACAO_ESPACO" }));
}

// Botões de arremesso e reset do deck arcade
if (dom.btnSimHole) dom.btnSimHole.addEventListener('click', () => sendWs({ tipo: "SIMULAR_ARREMESSO", sensor: "BURACO" }));
if (dom.btnSimBoard) dom.btnSimBoard.addEventListener('click', () => sendWs({ tipo: "SIMULAR_ARREMESSO", sensor: "PRANCHA" }));
if (dom.btnSimMiss) dom.btnSimMiss.addEventListener('click', () => sendWs({ tipo: "SIMULAR_ARREMESSO", sensor: "FORA" }));
if (dom.btnSimReset) dom.btnSimReset.addEventListener('click', () => sendWs({ tipo: "RESET_ESPERA" }));

// Filtros do Ranking (Aba Geral vs Menu de Turmas)
if (dom.btnFilterGeral) {
    dom.btnFilterGeral.addEventListener('click', () => setRankingFilter(''));
}
if (dom.selectGroupFilter) {
    dom.selectGroupFilter.addEventListener('change', (e) => setRankingFilter(e.target.value));
}

// -----------------------------------------------------------------------------
// Controles da Zona de Segurança de Dados e Backups
// -----------------------------------------------------------------------------
// 1. Botão Salvar Backup
if (dom.btnSalvarBackup) {
    dom.btnSalvarBackup.addEventListener('click', () => {
        showSecurityFeedback("⏳ Gerando cópia de segurança física do banco...", "var(--neon-yellow)");
        sendWs({ tipo: "FAZER_BACKUP" });
    });
}

// 2. Botão Restaurar Backup Mais Recente
if (dom.btnRestaurarBackup) {
    dom.btnRestaurarBackup.addEventListener('click', () => {
        if (confirm("Deseja restaurar as partidas e rankings a partir do backup mais recente?")) {
            showSecurityFeedback("⏳ Restaurando banco de dados a partir do backup...", "var(--neon-yellow)");
            sendWs({ tipo: "RESTAURAR_BACKUP" });
        }
    });
}

// 3. Botão Exportar Planilhas CSV
if (dom.btnExportarCsv) {
    dom.btnExportarCsv.addEventListener('click', () => {
        showSecurityFeedback("⏳ Exportando planilhas CSV...", "var(--neon-yellow)");
        sendWs({ tipo: "EXPORTAR_CSV" });
        // Abre o download do ranking.csv
        window.open('/ranking.csv', '_blank');
    });
}

// 4. Botão Perigoso: Zerar Banco de Dados (Exige Senha: 'admin')
if (dom.btnZerarBanco) {
    dom.btnZerarBanco.addEventListener('click', () => {
        const senha = prompt("⚠️ ATENÇÃO: Isso apagará todas as partidas e o ranking para iniciar um novo evento!\n\nDigite a senha de administrador para confirmar:");
        if (senha === null) return; // cancelou
        if (senha.trim() !== "admin") {
            showSecurityFeedback("❌ Senha incorreta! Operação de limpeza cancelada.", "var(--neon-red)");
            alert("Senha incorreta! O banco não foi alterado.");
            return;
        }
        if (confirm("Última confirmação: Tem certeza absoluta que deseja zerar o placar agora?\n(Um backup pré-limpeza será salvo automaticamente).")) {
            showSecurityFeedback("⏳ Limpando banco e gerando backup de segurança...", "var(--neon-yellow)");
            sendWs({ tipo: "ZERAR_BANCO", senha: "admin" });
        }
    });
}


// -----------------------------------------------------------------------------
// 8. Atalhos de Teclado Universais do Fliperama
// -----------------------------------------------------------------------------
window.addEventListener('keydown', (e) => {
    // Se o operador estiver digitando no modal, não intercepta as teclas do jogo
    if (dom.operatorModal.classList.contains('active')) {
        if (e.key === 'Escape') toggleOperatorModal(false);
        return;
    }

    // Tecla ESPAÇO: Controle de Botão Único
    // 1. Inicia o cronômetro se estiver em ESPERA ou PRONTO
    // 2. Finaliza a rodada e crava o tempo se estiver em JOGANDO
    // 3. Limpa o placar para o próximo competidor se estiver em FINALIZADA
    if (e.code === 'Space') {
        e.preventDefault();
        sendWs({ tipo: "ACAO_ESPACO" });
    }

    // Tecla B: Simula acerto no BURACO (+3)
    else if (e.key.toLowerCase() === 'b') {
        e.preventDefault();
        sendWs({ tipo: "SIMULAR_ARREMESSO", sensor: "BURACO" });
    }

    // Tecla P: Simula acerto na PRANCHA (+1)
    else if (e.key.toLowerCase() === 'p') {
        e.preventDefault();
        sendWs({ tipo: "SIMULAR_ARREMESSO", sensor: "PRANCHA" });
    }

    // Tecla F: Simula saquinho FORA (0)
    else if (e.key.toLowerCase() === 'f') {
        e.preventDefault();
        sendWs({ tipo: "SIMULAR_ARREMESSO", sensor: "FORA" });
    }

    // Tecla O: Abre o Painel do Operador
    else if (e.key.toLowerCase() === 'o') {
        e.preventDefault();
        toggleOperatorModal();
    }

    // Tecla R: Reseta a tela para espera
    else if (e.key.toLowerCase() === 'r') {
        e.preventDefault();
        sendWs({ tipo: "RESET_ESPERA" });
    }

    // Tecla ESC: Fecha qualquer janela aberta
    else if (e.key === 'Escape') {
        toggleOperatorModal(false);
    }
});

// Inicialização: conecta o WebSocket e carrega as turmas existentes
window.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();
    const apiBase = window.location.host ? '' : 'http://localhost:8080';
    fetch(`${apiBase}/api/grupos`)
        .then(r => r.json())
        .then(data => populateGroupFilter(data))
        .catch(() => {});
});
