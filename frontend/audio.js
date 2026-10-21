/**
 * =============================================================================
 * CORNHOLE INTELIGENTE - IFEx 2026
 * Arquivo: frontend/audio.js
 * Função: Sintetizador de Áudio Retro Arcade (Web Audio API)
 * =============================================================================
 * COMO FUNCIONA A SÍNTESE DE ÁUDIO?
 * Em vez de carregar arquivos de som externos (.mp3 ou .wav) que pesariam a página
 * e dependeriam de internet, este arquivo usa a 'Web Audio API' nativa do navegador.
 * 
 * Ele programa o próprio processador de som do computador para vibrar em ondas
 * sonoras eletrônicas (quadrada, dente de serra e senoidal), gerando aquele
 * som autêntico dos videogames e fliperamas dos anos 80/90.
 * =============================================================================
 */

class ArcadeAudio {
    constructor() {
        // Contexto de áudio do navegador (o motor de som)
        this.ctx = null;
        // Controle de mudo (pode ser ativado pelo botão no cabeçalho)
        this.muted = false;
    }

    /**
     * Inicializa o contexto de som no primeiro clique do usuário.
     * Os navegadores modernos bloqueiam sons automáticos antes de uma interação física.
     */
    _initContext() {
        if (!this.ctx) {
            const AudioContextClass = window.AudioContext || window.webkitAudioContext;
            this.ctx = new AudioContextClass();
        }
        // Se o navegador colocou o som para 'dormir', acorda o canal
        if (this.ctx.state === 'suspended') {
            this.ctx.resume();
        }
    }

    /**
     * Alterna entre som ligado e mudo.
     */
    toggleMute() {
        this.muted = !this.muted;
        return this.muted;
    }

    // -------------------------------------------------------------------------
    // 1. Som de Inserir Ficha / Start (Aperto da Barra de Espaço)
    // -------------------------------------------------------------------------
    // Cria dois bipes ascendentes rápidos (440Hz -> 880Hz) com onda quadrada
    playStart() {
        if (this.muted) return;
        this._initContext();
        const now = this.ctx.currentTime;

        // Cria o oscilador (quem gera a onda sonora) e o ganho (volume)
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();

        osc.type = 'square'; // Onda quadrada: dá o timbre clássico de 8-bit (estilo Nintendinho)
        osc.frequency.setValueAtTime(440, now);          // Começa na nota Lá (440Hz)
        osc.frequency.setValueAtTime(880, now + 0.08);   // Pula para Lá agudo (880Hz)

        // Fade-out do volume para não fazer estalo no alto-falante
        gain.gain.setValueAtTime(0.2, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);

        // Conecta o oscilador ao volume e o volume à saída de som
        osc.connect(gain);
        gain.connect(this.ctx.destination);

        osc.start(now);
        osc.stop(now + 0.35);
    }

    // -------------------------------------------------------------------------
    // 2. Acerto no BURACO (+3 Pontos!) - Fanfarra de Alta Energia
    // -------------------------------------------------------------------------
    // Toca uma sequência triunfante de 4 notas rápidas: Dó, Mi, Sol, Dó agudo
    playHole() {
        if (this.muted) return;
        this._initContext();
        const now = this.ctx.currentTime;

        const notes = [523.25, 659.25, 783.99, 1046.50]; // Frequências em Hz das notas C5, E5, G5, C6
        notes.forEach((freq, idx) => {
            const osc = this.ctx.createOscillator();
            const gain = this.ctx.createGain();

            osc.type = 'triangle'; // Onda triangular: som mais musical e suave
            osc.frequency.setValueAtTime(freq, now + idx * 0.06);

            gain.gain.setValueAtTime(0.3, now + idx * 0.06);
            gain.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.06 + 0.2);

            osc.connect(gain);
            gain.connect(this.ctx.destination);

            osc.start(now + idx * 0.06);
            osc.stop(now + idx * 0.06 + 0.2);
        });
    }

    // -------------------------------------------------------------------------
    // 3. Acerto na PRANCHA (+1 Ponto) - Som amadeirado de impacto
    // -------------------------------------------------------------------------
    // Usa onda senoidal caindo rapidamente de frequência (320Hz -> 140Hz) simulando o 'toc' na madeira
    playBoard() {
        if (this.muted) return;
        this._initContext();
        const now = this.ctx.currentTime;

        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();

        osc.type = 'sine'; // Onda senoidal pura: perfeita para impactos graves
        osc.frequency.setValueAtTime(320, now);
        osc.frequency.exponentialRampToValueAtTime(140, now + 0.15);

        gain.gain.setValueAtTime(0.3, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.18);

        osc.connect(gain);
        gain.connect(this.ctx.destination);

        osc.start(now);
        osc.stop(now + 0.18);
    }

    // -------------------------------------------------------------------------
    // 4. Errou / FORA (0 Pontos) - Som descendente de erro
    // -------------------------------------------------------------------------
    // Usa onda dente de serra (áspera) caindo para frequências graves
    playMiss() {
        if (this.muted) return;
        this._initContext();
        const now = this.ctx.currentTime;

        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();

        osc.type = 'sawtooth'; // Onda dente de serra: som cortante e áspero
        osc.frequency.setValueAtTime(220, now);
        osc.frequency.exponentialRampToValueAtTime(80, now + 0.25);

        gain.gain.setValueAtTime(0.15, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);

        osc.connect(gain);
        gain.connect(this.ctx.destination);

        osc.start(now);
        osc.stop(now + 0.25);
    }

    // -------------------------------------------------------------------------
    // 5. NOVO RECORDE / HIGH SCORE! (Entrou no Top 3 da competição)
    // -------------------------------------------------------------------------
    // Fanfarra completa de vitória
    playHighScore() {
        if (this.muted) return;
        this._initContext();
        const now = this.ctx.currentTime;

        const fanfare = [
            { f: 523.25, d: 0.12 }, // Dó
            { f: 659.25, d: 0.12 }, // Mi
            { f: 783.99, d: 0.12 }, // Sol
            { f: 1046.50, d: 0.35 } // Dó agudo sustentado
        ];

        let offset = 0;
        fanfare.forEach(item => {
            const osc = this.ctx.createOscillator();
            const gain = this.ctx.createGain();

            osc.type = 'square';
            osc.frequency.setValueAtTime(item.f, now + offset);

            gain.gain.setValueAtTime(0.25, now + offset);
            gain.gain.exponentialRampToValueAtTime(0.001, now + offset + item.d);

            osc.connect(gain);
            gain.connect(this.ctx.destination);

            osc.start(now + offset);
            osc.stop(now + offset + item.d);

            offset += item.d + 0.03;
        });
    }

    // -------------------------------------------------------------------------
    // 6. Fim da Rodada Normal (Game Over)
    // -------------------------------------------------------------------------
    // Escala descendente indicando que a partida terminou
    playGameOver() {
        if (this.muted) return;
        this._initContext();
        const now = this.ctx.currentTime;

        const notes = [
            { f: 440, d: 0.15 },
            { f: 415, d: 0.15 },
            { f: 392, d: 0.15 },
            { f: 349, d: 0.4 }
        ];

        let offset = 0;
        notes.forEach(item => {
            const osc = this.ctx.createOscillator();
            const gain = this.ctx.createGain();

            osc.type = 'sawtooth';
            osc.frequency.setValueAtTime(item.f, now + offset);

            gain.gain.setValueAtTime(0.2, now + offset);
            gain.gain.exponentialRampToValueAtTime(0.001, now + offset + item.d);

            osc.connect(gain);
            gain.connect(this.ctx.destination);

            osc.start(now + offset);
            osc.stop(now + offset + item.d);

            offset += item.d;
        });
    }
}

// Cria uma instância única acessível por todo o front-end
window.arcadeAudio = new ArcadeAudio();
