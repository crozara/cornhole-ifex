"""
=============================================================================
CORNHOLE INTELIGENTE - IFEx 2026
Arquivo: backend/serial_handler.py
Função: Comunicação com o Hardware (Arduino) via Porta Serial USB
=============================================================================
Este arquivo é o "OUVIDO" do nosso sistema. Ele fica escutando a porta USB
onde o Arduino está conectado. Toda vez que um saquinho cai em algum dos
buracos, o Arduino envia um pacote JSON (ex: {"evento":"acerto","buraco":"pequeno","pontos":8})
ou um texto simples, e este arquivo recebe essa mensagem e a repassa para o
motor do jogo.

Se o Arduino NÃO estiver conectado (por exemplo, ao testar no quarto ou na sala),
ele ativa automaticamente o "Modo Simulador", permitindo jogar usando o teclado.
=============================================================================
"""

import glob
import logging
import threading
import time
from typing import Callable, Optional

# Configura as mensagens de log (mensagens informativas que aparecem no terminal)
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")


class SerialHandler:
    """
    Classe responsável por:
    1. Achar a porta USB onde o Arduino está conectado.
    2. Ler as mensagens que o Arduino manda em tempo real (JSON ou texto).
    3. Enviar comandos do PC de volta para o Arduino (ex: ligar luzes).
    4. Ativar o modo simulador caso o Arduino não esteja plugado.
    """

    def __init__(self, callback_mensagem: Callable[[str], None], baudrate: int = 115200):
        # Função que será chamada sempre que uma nova mensagem chegar do Arduino
        self.callback_mensagem = callback_mensagem
        
        # Velocidade da comunicação serial (115200 bits por segundo é o padrão rápido do Arduino)
        self.baudrate = baudrate
        
        # Guarda o nome da porta USB conectada (ex: '/dev/ttyUSB0' ou 'COM3')
        self.porta_ativa: Optional[str] = None
        
        # Objeto da conexão serial com a placa
        self.conexao = None
        
        # Controla se a escuta em segundo plano está ativa
        self.rodando = False
        
        # Thread (tarefa em segundo plano) para escutar a porta sem travar o restante do jogo
        self.thread: Optional[threading.Thread] = None
        
        # Indica se estamos no modo simulador (quando não há placa física plugada)
        self.modo_simulador = True

        # Telemetria e diagnóstico em tempo real
        self.ultima_linha: str = ""
        self.ultimo_ts: Optional[float] = None
        self.total_leituras: int = 0
        self.historico_telemetria: list = []
        self.ultimo_erro: Optional[str] = None

    def encontrar_porta_arduino(self) -> Optional[str]:
        """
        Varre o sistema operacional procurando onde o Arduino foi plugado.
        No Linux, placas Arduino costumam aparecer como /dev/ttyUSB0 ou /dev/ttyACM0.
        No Windows, aparecem como COM3, COM4, etc.
        Retorna o caminho da primeira porta encontrada ou None se não achar nenhuma.
        """
        portas = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
        if portas:
            return portas[0]  # Retorna a porta encontrada (ex: '/dev/ttyACM0')

        # Suporte multiplataforma (Windows COM* / macOS / Linux via list_ports)
        try:
            from serial.tools import list_ports
            for p in list_ports.comports():
                desc = f"{p.device} {p.description or ''} {p.manufacturer or ''}".lower()
                if any(k in desc for k in ("arduino", "ch340", "cp210", "ftdi", "usb", "acm")):
                    return p.device
        except Exception:
            pass

        return None

    def iniciar(self) -> None:
        """
        Inicia a escuta da porta serial em uma 'Thread' separada.
        O que é Thread? É uma linha de execução em paralelo. Usamos isso para
        que o computador possa 'ficar esperando' o Arduino sem congelar a tela do jogo.
        """
        self.rodando = True
        self.thread = threading.Thread(target=self._loop_leitura, daemon=True)
        self.thread.start()

    def parar(self) -> None:
        """
        Encerra com segurança a escuta da porta USB e desliga a conexão.
        """
        self.rodando = False
        if self.conexao:
            try:
                self.conexao.close()
            except Exception:
                pass

    def _loop_leitura(self) -> None:
        """
        Loop contínuo que roda em segundo plano.
        Ele tenta se conectar ao Arduino e fica lendo linha por linha o que a placa envia.
        """
        # Verifica se a biblioteca 'pyserial' está instalada no Python
        pyserial_disponivel = False
        try:
            import serial
            pyserial_disponivel = True
        except ImportError:
            logging.info("[Serial] Biblioteca 'pyserial' não encontrada. Modo Simulador ativado.")

        while self.rodando:
            # Se não tem a biblioteca serial, permanece em modo simulador
            if not pyserial_disponivel:
                time.sleep(2)
                continue

            # Tenta encontrar o Arduino plugado na USB
            porta = self.encontrar_porta_arduino()
            if not porta:
                if not self.modo_simulador:
                    logging.info("[Serial] Arduino desconectado. Aguardando conexão ou simulador...")
                    self.modo_simulador = True
                time.sleep(1)  # Aguarda 1 segundo antes de procurar novamente
                continue

            # Se encontrou uma porta, tenta abrir a conexão com a placa
            try:
                import serial
                logging.info(f"[Serial] Conectando ao Arduino em {porta} ({self.baudrate} bps)...")
                self.conexao = serial.Serial(porta, self.baudrate, timeout=1)
                self.porta_ativa = porta
                self.modo_simulador = False
                self.ultimo_erro = None
                logging.info(f"[Serial] ✅ Conectado com sucesso em {porta}!")

                # Limpa qualquer dado velho que tenha ficado acumulado na memória da porta
                self.conexao.reset_input_buffer()

                # Loop de leitura: enquanto estiver conectado, lê o que o Arduino manda
                while self.rodando:
                    # Lê uma linha enviada pelo Arduino (ex: '{"evento":"acerto","buraco":"pequeno","pontos":8}\n')
                    linha = self.conexao.readline().decode("utf-8", errors="ignore").strip()
                    
                    # Se chegou uma mensagem válida, registra a telemetria e encaminha para o jogo
                    if linha:
                        agora_ts = time.time()
                        self.ultima_linha = linha
                        self.ultimo_ts = agora_ts
                        self.total_leituras += 1
                        self.historico_telemetria.append({
                            "timestamp": agora_ts,
                            "linha": linha,
                            "origem": "hardware"
                        })
                        if len(self.historico_telemetria) > 20:
                            self.historico_telemetria.pop(0)

                        logging.info(f"[Serial Recebido] -> '{linha}'")
                        self.callback_mensagem(linha)

            except Exception as e:
                # Se der algum erro (ex: permissão negada, cabo desconectado), registra e tenta novamente
                err_msg = str(e)
                if "Permission denied" in err_msg:
                    self.ultimo_erro = f"Permissão negada em {porta}. Execute: sudo usermod -a -G dialout $USER"
                else:
                    self.ultimo_erro = err_msg
                logging.warning(f"[Serial] Erro na conexão ({e}). Tentando reconectar em 2s...")
                self.modo_simulador = True
                if self.conexao:
                    try:
                        self.conexao.close()
                    except Exception:
                        pass
                time.sleep(2)

    def enviar_comando_arduino(self, comando: str) -> None:
        """
        Envia comandos de texto do computador para o Arduino através da USB.
        Exemplo: se o jogo acabar, o PC envia 'GAME_OVER' para o Arduino piscar LEDs.
        """
        if self.conexao and self.conexao.is_open:
            try:
                msg = (comando.strip() + "\n").encode("utf-8")
                self.conexao.write(msg)
                self.conexao.flush()
                logging.info(f"[Serial Enviado] <- '{comando}'")
            except Exception as e:
                logging.error(f"[Serial] Falha ao enviar comando para o Arduino: {e}")

    def simular_entrada(self, mensagem: str) -> None:
        """
        Função de teste para o Modo Simulador:
        Permite disparar um evento (JSON ou texto do sensor) usando
        as teclas do teclado sem precisar do Arduino físico conectado.
        """
        agora_ts = time.time()
        self.ultima_linha = mensagem
        self.ultimo_ts = agora_ts
        self.total_leituras += 1
        self.historico_telemetria.append({
            "timestamp": agora_ts,
            "linha": mensagem,
            "origem": "simulador"
        })
        if len(self.historico_telemetria) > 20:
            self.historico_telemetria.pop(0)

        logging.info(f"[Simulador Entrada] -> '{mensagem}'")
        self.callback_mensagem(mensagem)

    def obter_telemetria(self) -> dict:
        """
        Retorna o estado técnico atual da comunicação serial e do hardware Arduino.
        """
        return {
            "conectado": not self.modo_simulador and self.conexao is not None and getattr(self.conexao, "is_open", False),
            "porta": self.porta_ativa if not self.modo_simulador else "Simulador Teclado",
            "modo_simulador": self.modo_simulador,
            "ultimo_erro": self.ultimo_erro,
            "baudrate": self.baudrate,
            "total_leituras": self.total_leituras,
            "ultima_linha": self.ultima_linha,
            "ultimo_ts": self.ultimo_ts,
            "historico": self.historico_telemetria[-10:]
        }
