"""
=============================================================================
CORNHOLE INTELIGENTE - IFEx 2026
Arquivo: backend/game_manager.py
Função: Gerenciador do Jogo e Árbitro de Regras (Game Manager)
=============================================================================
Este arquivo é o "CÉREBRO" do jogo. Ele controla:
1. A Máquina de Estados (se estamos esperando jogador, jogando ou finalizando).
2. O Cronômetro de Precisão (calculado em milissegundos).
3. A contagem dos 5 saquinhos arremessados e a pontuação acumulada.
4. O acionamento do banco PostgreSQL (via database.db) para salvar as partidas.
5. Os avisos para a tela web atualizar em tempo real via WebSockets.
=============================================================================
"""

import logging
import os
import sys
import time
from typing import Any, Callable, Dict, List, Optional

# Garante que o Python consiga encontrar a pasta do banco de dados na raiz do projeto
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database import db

PONTOS_PADRAO_SENSORES = {
    "PEQUENO": 8,
    "MEDIO": 6,
    "GRANDE": 4,
    "PRANCHA": 0,
    "FORA": -4,
    "BURACO": 8,
}


class EstadosJogo:
    """
    Os 4 Estados do Fliperama (Máquina de Estados):
    - ESPERA: Ninguém jogando. Tela aguarda operador selecionar/cadastrar jogador.
    - PRONTO: Jogador na linha de arremesso. Aperte ESPAÇO para largar.
    - JOGANDO: Cronômetro disparado! Sensores ativos recebendo os 5 saquinhos.
    - FINALIZADA: Rodada concluída! Tempo travado, salvo no banco e pódio na tela.
    """
    ESPERA = "ESPERA"
    PRONTO = "PRONTO"
    JOGANDO = "JOGANDO"
    FINALIZADA = "FINALIZADA"


class GameManager:
    """
    Controlador central de regras e dados da rodada.
    """

    def __init__(self, on_event: Optional[Callable[[Dict[str, Any]], None]] = None):
        # Callback para enviar eventos aos navegadores conectados via WebSockets
        self.on_event = on_event
        
        # Estado inicial do jogo
        self.estado = EstadosJogo.ESPERA
        
        # Dados do competidor atual (id, nome, apelido/turma)
        self.jogador_atual: Optional[Dict[str, Any]] = None
        
        # ID da partida registrado no PostgreSQL
        self.partida_id: Optional[int] = None
        
        # Marcador de tempo inicial de alta precisão (em segundos/frações)
        self.inicio_timestamp: Optional[float] = None
        
        # Duração total da rodada em milissegundos travada no final
        self.tempo_final_ms: int = 0
        
        # Pontos acumulados na rodada atual
        self.pontuacao_atual: int = 0
        
        # Lista com o histórico de cada um dos 5 arremessos da rodada
        self.saquinhos: List[Dict[str, Any]] = []
        
        # Guarda o resumo da última partida concluída para exibição
        self.ultimo_resultado: Optional[Dict[str, Any]] = None

        # Estatísticas e telemetria de sensores em tempo real (HUD Técnico)
        self.stats_sensores: Dict[str, Dict[str, Any]] = {
            "PEQUENO": {"total": 0, "ultimo_ts": None, "nome": "Laser VL53L0X (Pequeno)", "pinos": "I2C (SDA/SCL)", "pontos": PONTOS_PADRAO_SENSORES.get("PEQUENO", 8)},
            "MEDIO": {"total": 0, "ultimo_ts": None, "nome": "Ultrassônico HC-SR04 (Médio)", "pinos": "Trig 5 / Echo 6", "pontos": PONTOS_PADRAO_SENSORES.get("MEDIO", 6)},
            "GRANDE": {"total": 0, "ultimo_ts": None, "nome": "Célula Carga HX711 (Grande)", "pinos": "DOUT 3 / SCK 2", "pontos": PONTOS_PADRAO_SENSORES.get("GRANDE", 4)},
            "PRANCHA": {"total": 0, "ultimo_ts": None, "nome": "Prancha", "pinos": "Mesa", "pontos": PONTOS_PADRAO_SENSORES.get("PRANCHA", 0)},
            "FORA": {"total": 0, "ultimo_ts": None, "nome": "Fora", "pinos": "Solo", "pontos": PONTOS_PADRAO_SENSORES.get("FORA", -4)},
        }

    def _notificar(self, payload: Dict[str, Any]) -> None:
        """
        Dispara uma notificação para o servidor web enviar via WebSocket
        para todas as telas e navegadores conectados.
        """
        if self.on_event:
            self.on_event(payload)

    def selecionar_jogador(self, jogador_id: int) -> Dict[str, Any]:
        """
        Seleciona um jogador já existente na lista do banco e prepara
        a máquina para o estado 'PRONTO' (aguardando largada).
        """
        jogadores = db.listar_jogadores()
        jogador = next((j for j in jogadores if j["id"] == jogador_id), None)
        if not jogador:
            raise ValueError(f"Jogador ID {jogador_id} não encontrado!")

        self.jogador_atual = jogador
        self.estado = EstadosJogo.PRONTO
        self.partida_id = None
        self.inicio_timestamp = None
        self.tempo_final_ms = 0
        self.pontuacao_atual = 0
        self.saquinhos = []

        evento = {
            "tipo": "JOGADOR_SELECIONADO",
            "jogador": self.jogador_atual,
            "estado": self.estado,
            "jogadores_cadastrados": jogadores,
            "grupos": db.listar_grupos()
        }
        self._notificar(evento)
        return evento

    def cadastrar_e_selecionar_jogador(self, nome: str, apelido: Optional[str] = None) -> Dict[str, Any]:
        """
        Cadastra um novo competidor (nome + turma) no PostgreSQL e já
        o define automaticamente como o jogador da vez na linha de arremesso.
        """
        novo = db.cadastrar_ou_obter_jogador(nome, apelido)
        return self.selecionar_jogador(novo["id"])

    def cadastrar_jogador_na_fila(self, nome: str, apelido: Optional[str] = None) -> Dict[str, Any]:
        """
        Cadastra um novo competidor (nome + turma) no PostgreSQL apenas adicionando-o
        à lista/fila de espera, sem tirá-lo do banco e sem mexer no jogador atual da tela.
        """
        novo = db.cadastrar_ou_obter_jogador(nome, apelido)
        jogadores = db.listar_jogadores()
        grupos = db.listar_grupos()
        evento = {
            "tipo": "JOGADOR_CADASTRADO_FILA",
            "novo_jogador": novo,
            "jogadores_cadastrados": jogadores,
            "grupos": grupos
        }
        self._notificar(evento)
        return evento

    def acao_espaco(self) -> Dict[str, Any]:
        """
        A Mágica da Barra de ESPAÇO (Controle de Botão Único):
        1. Se estiver em ESPERA ou PRONTO: Inicia a rodada e dispara o cronômetro.
        2. Se estiver em JOGANDO: Trava o cronômetro na hora e finaliza a partida.
        3. Se estiver em FINALIZADA: Limpa o placar e volta para a tela de espera.
        """
        if self.estado in (EstadosJogo.PRONTO, EstadosJogo.ESPERA):
            return self.iniciar_partida()
        elif self.estado == EstadosJogo.JOGANDO:
            # Trava o cronômetro no exato milissegundo em que o botão foi pressionado
            tempo_final_ms = int((time.perf_counter() - self.inicio_timestamp) * 1000)
            self._finalizar_partida(tempo_final_ms)
            return {"tipo": "FINALIZADO_POR_ESPACO", "tempo_final_ms": tempo_final_ms}
        elif self.estado == EstadosJogo.FINALIZADA:
            return self.resetar_para_espera()
        return {}

    def iniciar_partida(self) -> Dict[str, Any]:
        """
        Inicia a rodada: cria a linha no PostgreSQL, zera contadores e
        dispara o cronômetro de precisão (time.perf_counter).
        """
        if self.estado not in (EstadosJogo.PRONTO, EstadosJogo.ESPERA):
            return {"erro": f"Não é possível iniciar partida no estado {self.estado}"}

        # Se nenhum jogador foi escolhido pelo painel, usa o perfil genérico
        if not self.jogador_atual:
            self.jogador_atual = db.cadastrar_ou_obter_jogador("Jogador Arcade", "IFEx")

        # Registra o início da partida no PostgreSQL (tabela 'partidas')
        partida = db.iniciar_partida(self.jogador_atual["id"])
        self.partida_id = partida["id"]
        self.saquinhos = []
        self.pontuacao_atual = 0
        self.tempo_final_ms = 0

        # Dispara o cronômetro de alta precisão
        self.inicio_timestamp = time.perf_counter()
        self.estado = EstadosJogo.JOGANDO

        evento = {
            "tipo": "PARTIDA_INICIADA",
            "partida_id": self.partida_id,
            "jogador": self.jogador_atual,
            "estado": self.estado,
            "inicio_epoch_ms": int(time.time() * 1000)
        }
        self._notificar(evento)
        return evento

    def registrar_arremesso(self, sensor_codigo: str, pontos: Optional[int] = None) -> Dict[str, Any]:
        """
        Chamado toda vez que um saquinho cai em um dos buracos (pequeno, medio, grande) ou fora.
        Recebe o código do buraco/sensor e a pontuação enviada pelo main.ino via SerialHandler,
        persiste no PostgreSQL e notifica a interface web em tempo real.
        """
        # Só aceita arremessos se a partida estiver rodando
        if self.estado != EstadosJogo.JOGANDO or self.partida_id is None:
            return {"aviso": "Jogo não está em andamento. Acerto ignorado."}

        num_saquinho = len(self.saquinhos) + 1
        if num_saquinho > 5:
            return {"aviso": "Limite de 5 saquinhos atingido. Partida já finalizada."}

        # Calcula quantos milissegundos se passaram desde o início até este arremesso
        tempo_parcial_ms = int((time.perf_counter() - self.inicio_timestamp) * 1000)

        # Padroniza o texto do sensor em maiúsculas (ex: "PEQUENO", "MEDIO", "GRANDE", "FORA")
        codigo = sensor_codigo.strip().upper().replace("MÉDIO", "MEDIO")
        pontos_informados = int(pontos) if pontos is not None else PONTOS_PADRAO_SENSORES.get(codigo, 0)

        # Salva no PostgreSQL com os pontos enviados pelo main.ino
        arremesso_db = db.registrar_arremesso(
            partida_id=self.partida_id,
            numero_saquinho=num_saquinho,
            sensor_codigo=codigo,
            tempo_parcial_ms=tempo_parcial_ms,
            pontos=pontos_informados
        )

        # Atualiza as variáveis em memória
        pontos_saquinho = int(arremesso_db.get("pontos", pontos_informados))
        self.pontuacao_atual += pontos_saquinho

        # Atualiza a telemetria do sensor
        chave_sensor = "PEQUENO" if codigo == "BURACO" else codigo
        if chave_sensor in self.stats_sensores:
            self.stats_sensores[chave_sensor]["total"] += 1
            self.stats_sensores[chave_sensor]["ultimo_ts"] = time.time()

        info_saquinho = {
            "numero": num_saquinho,
            "sensor": codigo,
            "buraco": codigo.lower(),
            "pontos": pontos_saquinho,
            "tempo_parcial_ms": tempo_parcial_ms
        }
        self.saquinhos.append(info_saquinho)

        # Envia aviso via WebSocket para a tela acender as luzes e tocar o som na hora
        evento_saquinho = {
            "tipo": "SAQUINHO_PONTUOU",
            "partida_id": self.partida_id,
            "numero_saquinho": num_saquinho,
            "sensor": codigo,
            "buraco": codigo.lower(),
            "pontos": pontos_saquinho,
            "pontuacao_total": self.pontuacao_atual,
            "tempo_parcial_ms": tempo_parcial_ms,
            "saquinhos_restantes": 5 - num_saquinho,
            "finalizada": (num_saquinho >= 5)
        }
        self._notificar(evento_saquinho)

        # REGRA OFICIAL IFEx 2026:
        # Sempre que atingir o 5º arremesso, o cronômetro para imediatamente no exato
        # milissegundo do impacto e a partida é finalizada e salva no PostgreSQL!
        if num_saquinho >= 5:
            self._finalizar_partida(tempo_parcial_ms)

        return evento_saquinho

    def _finalizar_partida(self, tempo_final_ms: int) -> None:
        """
        Encerra a partida:
        1. Atualiza a tabela 'partidas' com o tempo final e status 'finalizada'.
        2. Recalcula o Ranking Top 10 com a regra de desempate por tempo.
        3. Envia o resultado com fanfarra para a tela.
        """
        self.tempo_final_ms = tempo_final_ms
        self.estado = EstadosJogo.FINALIZADA

        # Salva o tempo e finaliza no PostgreSQL
        db.finalizar_partida(self.partida_id, self.tempo_final_ms)

        # Backup automático em tempo real:
        # Garante que um snapshot físico e as planilhas CSV estejam sempre salvos em disco
        try:
            db.fazer_backup()
            db.exportar_csv()
        except Exception as e:
            logging.warning(f"[Backup Automático] Erro ao salvar snapshot da partida: {e}")

        # Puxa a view do Ranking atualizada
        ranking = db.obter_ranking_global(10)

        # Descobre qual posição o competidor conquistou
        posicao_jogador = None
        for r in ranking:
            if r.get("partida_id") == self.partida_id:
                posicao_jogador = r.get("posicao")
                break

        resultado = {
            "partida_id": self.partida_id,
            "jogador": self.jogador_atual,
            "pontuacao_final": self.pontuacao_atual,
            "tempo_final_ms": self.tempo_final_ms,
            "tempo_segundos": round(self.tempo_final_ms / 1000.0, 2),
            "posicao_ranking": posicao_jogador,
            "bateu_recorde": (posicao_jogador is not None and posicao_jogador <= 3),
            "saquinhos": self.saquinhos
        }
        self.ultimo_resultado = resultado

        # Transmite o resultado final para a interface web
        evento = {
            "tipo": "PARTIDA_FINALIZADA",
            "resultado": resultado,
            "ranking": ranking,
            "grupos": db.listar_grupos(),
            "estado": self.estado
        }
        self._notificar(evento)

    def cancelar_partida(self) -> Dict[str, Any]:
        """
        Cancela a partida atual sem salvar e volta para a tela de espera.
        """
        self.estado = EstadosJogo.ESPERA
        self.partida_id = None
        self.inicio_timestamp = None
        self.saquinhos = []
        self.pontuacao_atual = 0

        evento = {
            "tipo": "PARTIDA_CANCELADA",
            "estado": self.estado
        }
        self._notificar(evento)
        return evento

    def resetar_para_espera(self) -> Dict[str, Any]:
        """
        Limpa a tela após uma partida concluída e aguarda o próximo participante.
        """
        self.estado = EstadosJogo.ESPERA
        self.jogador_atual = None
        self.partida_id = None
        self.saquinhos = []
        self.pontuacao_atual = 0

        evento = {
            "tipo": "RESET_ESPERA",
            "estado": self.estado,
            "ranking": db.obter_ranking_global(10)
        }
        self._notificar(evento)
        return evento

    def obter_estado_atual(self) -> Dict[str, Any]:
        """
        Gera uma 'foto' completa do estado do jogo. Usado para sincronizar
        imediatamente qualquer navegador que acabe de abrir a página.
        """
        tempo_decorrido_ms = 0
        if self.estado == EstadosJogo.JOGANDO and self.inicio_timestamp:
            tempo_decorrido_ms = int((time.perf_counter() - self.inicio_timestamp) * 1000)
        elif self.estado == EstadosJogo.FINALIZADA:
            tempo_decorrido_ms = self.tempo_final_ms

        return {
            "tipo": "ESTADO_ATUAL",
            "estado": self.estado,
            "jogador_atual": self.jogador_atual,
            "partida_id": self.partida_id,
            "pontuacao_atual": self.pontuacao_atual,
            "saquinhos": self.saquinhos,
            "tempo_decorrido_ms": tempo_decorrido_ms,
            "ultimo_resultado": self.ultimo_resultado,
            "ranking": db.obter_ranking_global(10),
            "grupos": db.listar_grupos(),
            "jogadores_cadastrados": db.listar_jogadores(),
            "sensores": db.listar_sensores(),
            "stats_sensores": self.stats_sensores
        }

    def obter_telemetria_sensores(self) -> Dict[str, Any]:
        """
        Retorna o relatório completo de telemetria e estado de todos os sensores.
        """
        return {
            "tipo": "TELEMETRIA_SENSORES",
            "stats": self.stats_sensores,
            "saquinhos_rodada": len(self.saquinhos),
            "estado": self.estado
        }
