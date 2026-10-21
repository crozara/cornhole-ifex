"""
=============================================================================
CORNHOLE INTELIGENTE - IFEx 2026
Arquivo: backend/server.py
Função: Servidor Web HTTP, Conexão WebSocket e Roteador Central
=============================================================================
Este arquivo é o "CENTRO DE TRANSMISSÃO" do sistema.
Ele desempenha três papéis fundamentais:
1. Servidor Web (HTTP): Entrega a página web do fliperama (HTML, CSS, JS e sons)
   para quem abrir no navegador em http://localhost:8080.
2. Servidor de Tempo Real (WebSockets): Mantém uma conexão contínua e ultrarrápida
   com o navegador. Quando o Arduino lê um ponto, o server.py avisa a tela
   em menos de 5 milissegundos sem precisar recarregar a página.
3. Rotas de API REST: Disponibiliza endpoints (/api/ranking, /api/jogadores) para
   quem quiser consultar os dados em formato JSON.
=============================================================================
"""

import asyncio
import http
import json
import logging
import mimetypes
import os
import sys
import urllib.parse
from typing import Set

# Configura caminhos absolutos para encontrar o diretório frontend/ e a raiz do projeto
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import websockets
from backend.game_manager import GameManager, EstadosJogo
from backend.serial_handler import SerialHandler
from database import db

# Formatação das mensagens no terminal
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")

# Guarda todas as conexões de navegadores abertos no momento (ex: tela do notebook, TV externa)
CLIENTES_CONECTADOS: Set[websockets.WebSocketServerProtocol] = set()
LOOP: asyncio.AbstractEventLoop = None


def broadcast_evento_threadsafe(evento: dict) -> None:
    """
    Função 'ponte' para envio seguro entre threads:
    Como o Arduino roda em uma thread paralela, usamos esta função para
    passar os eventos para o loop assíncrono do WebSocket sem gerar conflitos.
    """
    global LOOP
    if LOOP and LOOP.is_running() and CLIENTES_CONECTADOS:
        mensagem = json.dumps(evento)
        asyncio.run_coroutine_threadsafe(broadcast_evento(mensagem), LOOP)


async def broadcast_evento(mensagem: str) -> None:
    """
    BROADCAST (Transmissão Simultânea):
    Dispara a mesma mensagem JSON para todas as telas e navegadores conectados de uma só vez.
    Se algum navegador tiver sido fechado, ele é removido da lista automaticamente.
    """
    if not CLIENTES_CONECTADOS:
        return
    desconectados = set()
    for ws in list(CLIENTES_CONECTADOS):
        try:
            await ws.send(mensagem)
        except Exception:
            desconectados.add(ws)
    CLIENTES_CONECTADOS.difference_update(desconectados)


# Inicializa o árbitro do jogo (GameManager), passando a função de broadcast para notificações
game_manager = GameManager(on_event=broadcast_evento_threadsafe)


def tratar_mensagem_serial(mensagem: str) -> None:
    """
    Roteador de Mensagens do Arduino:
    Chamado sempre que o Arduino envia um texto via USB.
    Traduz a mensagem da placa física em uma ação dentro do jogo.
    """
    msg = mensagem.strip().upper()
    logging.info(f"[Serial Router] Processando: '{msg}'")

    # Botão de largada / parada física (ou tecla espaço)
    if msg in ("START", "ESPACO", "ESPAÇO", "BOTAO_START"):
        game_manager.acao_espaco()
        if game_manager.estado == EstadosJogo.JOGANDO:
            serial_handler.enviar_comando_arduino("LEDS_ON")
        elif game_manager.estado == EstadosJogo.FINALIZADA:
            serial_handler.enviar_comando_arduino("GAME_OVER")

    # Sensores da prancha e buraco
    elif msg in ("BURACO", "PRANCHA", "FORA"):
        res = game_manager.registrar_arremesso(msg)
        pts = res.get("pontos", 0)
        # Devolve sinal para o Arduino piscar luzes conforme a pontuação do saquinho
        serial_handler.enviar_comando_arduino(f"ACERTO_{pts}")
        # Se com esse 5º arremesso a partida finalizou automaticamente, avisa o Arduino imediatamente
        if game_manager.estado == EstadosJogo.FINALIZADA:
            serial_handler.enviar_comando_arduino("GAME_OVER")

    # Comando de reset de emergência
    elif msg in ("RESET", "CANCELAR"):
        game_manager.resetar_para_espera()
        serial_handler.enviar_comando_arduino("LEDS_OFF")


# Inicializa o leitor da porta USB com o Arduino
serial_handler = SerialHandler(callback_mensagem=tratar_mensagem_serial)


# -----------------------------------------------------------------------------
# Roteamento HTTP (Entrega dos Arquivos Visuais e Endpoints da API REST)
# -----------------------------------------------------------------------------
async def process_http_request(path: str, request_headers: dict):
    """
    Intercepta as requisições HTTP normais que chegam na porta 8080:
    - Se a URL for '/ws', deixa passar para o canal WebSocket de tempo real.
    - Se for rota de API (/api/...), retorna os dados em formato JSON.
    - Se for arquivo estático (HTML, CSS, JS), entrega o arquivo da pasta frontend/.
    """
    # Extrai o caminho e os parâmetros de busca (query string)
    url_parsed = urllib.parse.urlparse(path)
    path_sem_query = url_parsed.path
    query_params = urllib.parse.parse_qs(url_parsed.query)

    # 1. Se for uma conexão WebSocket (cabeçalho Upgrade: websocket ou rota /ws),
    # devolve None imediatamente para o websockets fazer o handshake sem interferência!
    upgrade_header = request_headers.get("Upgrade", "").lower() if request_headers else ""
    if upgrade_header == "websocket" or path_sem_query.rstrip("/") == "/ws":
        return None

    # Silencia requisições de favicon do navegador
    if path_sem_query == "/favicon.ico":
        return (http.HTTPStatus.NO_CONTENT, [("Content-Length", "0")], b"")

    # Log da requisição HTTP recebida
    logging.info(f"[HTTP] {path_sem_query}")

    # --- ENDPOINTS DA API REST ---
    
    # 1. Retorna o estado atual da rodada em JSON
    if path_sem_query == "/api/estado":
        corpo = json.dumps(game_manager.obter_estado_atual()).encode("utf-8")
        headers = [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Access-Control-Allow-Origin", "*"),
            ("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0"),
            ("Content-Length", str(len(corpo)))
        ]
        return (http.HTTPStatus.OK, headers, corpo)

    # 2. Retorna a lista dos 10 melhores colocados (Geral ou filtrado por Turma/Grupo)
    if path_sem_query == "/api/ranking":
        grupo = query_params.get("grupo", [None])[0]
        ranking = db.obter_ranking_por_grupo(grupo, 10)
        corpo = json.dumps(ranking).encode("utf-8")
        headers = [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Access-Control-Allow-Origin", "*"),
            ("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0"),
            ("Content-Length", str(len(corpo)))
        ]
        return (http.HTTPStatus.OK, headers, corpo)

    # 3. Retorna a lista de todas as turmas/grupos cadastrados em JSON
    if path_sem_query == "/api/grupos":
        corpo = json.dumps(db.listar_grupos()).encode("utf-8")
        headers = [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Access-Control-Allow-Origin", "*"),
            ("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0"),
            ("Content-Length", str(len(corpo)))
        ]
        return (http.HTTPStatus.OK, headers, corpo)

    # 4. Retorna a lista de todos os competidores cadastrados no banco em JSON
    if path_sem_query == "/api/jogadores":
        corpo = json.dumps(db.listar_jogadores()).encode("utf-8")
        headers = [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Access-Control-Allow-Origin", "*"),
            ("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0"),
            ("Content-Length", str(len(corpo)))
        ]
        return (http.HTTPStatus.OK, headers, corpo)

    # 5. Rota para Gerar Backup Manual via HTTP
    if path_sem_query == "/api/backup":
        try:
            arq = db.fazer_backup()
            res = {"sucesso": True, "mensagem": "Backup realizado com sucesso!", "arquivo": os.path.basename(arq)}
        except Exception as e:
            res = {"sucesso": False, "mensagem": str(e)}
        corpo = json.dumps(res).encode("utf-8")
        headers = [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Access-Control-Allow-Origin", "*"),
            ("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0"),
            ("Content-Length", str(len(corpo)))
        ]
        return (http.HTTPStatus.OK, headers, corpo)

    # 6. Rota para Restaurar o Último Backup via HTTP
    if path_sem_query == "/api/restore":
        try:
            arq = db.restaurar_backup()
            res = {"sucesso": True, "mensagem": "Backup restaurado com sucesso!", "arquivo": os.path.basename(arq)}
            # Transmite para todas as telas abertas o ranking e dados atualizados
            broadcast_evento_threadsafe({
                "tipo": "RANKING_ATUALIZADO",
                "ranking": db.obter_ranking_global(10),
                "grupos": db.listar_grupos()
            })
            broadcast_evento_threadsafe({
                "tipo": "LISTA_JOGADORES",
                "jogadores_cadastrados": db.listar_jogadores()
            })
        except Exception as e:
            res = {"sucesso": False, "mensagem": str(e)}
        corpo = json.dumps(res).encode("utf-8")
        headers = [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Access-Control-Allow-Origin", "*"),
            ("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0"),
            ("Content-Length", str(len(corpo)))
        ]
        return (http.HTTPStatus.OK, headers, corpo)

    # 7. Rota para Zerar o Banco de Dados (PROTEGIDO POR SENHA: 'admin')
    if path_sem_query == "/api/reset":
        senha = query_params.get("senha", [""])[0]
        res = db.zerar_banco_dados(senha)
        if res.get("sucesso"):
            game_manager.resetar_para_espera()
            broadcast_evento_threadsafe(game_manager.obter_estado_atual())
            broadcast_evento_threadsafe({
                "tipo": "RANKING_ATUALIZADO",
                "ranking": db.obter_ranking_global(10),
                "grupos": db.listar_grupos()
            })
            broadcast_evento_threadsafe({
                "tipo": "LISTA_JOGADORES",
                "jogadores_cadastrados": db.listar_jogadores()
            })
        corpo = json.dumps(res).encode("utf-8")
        headers = [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Access-Control-Allow-Origin", "*"),
            ("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0"),
            ("Content-Length", str(len(corpo)))
        ]
        return (http.HTTPStatus.OK, headers, corpo)

    # 8. Rota para Exportar Planilhas CSV
    if path_sem_query == "/api/exportar-csv":
        try:
            res_csv = db.exportar_csv()
            res = {"sucesso": True, "arquivos": res_csv}
        except Exception as e:
            res = {"sucesso": False, "mensagem": str(e)}
        corpo = json.dumps(res).encode("utf-8")
        headers = [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Access-Control-Allow-Origin", "*"),
            ("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0"),
            ("Content-Length", str(len(corpo)))
        ]
        return (http.HTTPStatus.OK, headers, corpo)

    # 9. Download direto de ranking.csv e historico_partidas.csv
    if path_sem_query in ("/ranking.csv", "/historico_partidas.csv"):
        arq_csv = os.path.join(PROJECT_ROOT, path_sem_query.lstrip("/"))
        if os.path.isfile(arq_csv):
            with open(arq_csv, "rb") as f:
                conteudo_csv = f.read()
            headers = [
                ("Content-Type", "text/csv; charset=utf-8"),
                ("Content-Disposition", f'attachment; filename="{os.path.basename(arq_csv)}"'),
                ("Cache-Control", "no-store, no-cache, must-revalidate"),
                ("Content-Length", str(len(conteudo_csv)))
            ]
            return (http.HTTPStatus.OK, headers, conteudo_csv)

    # --- SERVIDOR DE ARQUIVOS ESTÁTICOS (frontend/) ---
    if path_sem_query in ("/", "/index.html"):
        arquivo_alvo = os.path.join(FRONTEND_DIR, "index.html")
    else:
        rel_path = path_sem_query.lstrip("/")
        arquivo_alvo = os.path.join(FRONTEND_DIR, rel_path)

    # Proteção de segurança contra invasão de pastas (path traversal)
    arquivo_alvo = os.path.abspath(arquivo_alvo)
    if not arquivo_alvo.startswith(FRONTEND_DIR) or not os.path.isfile(arquivo_alvo):
        corpo = b"404 Not Found"
        return (http.HTTPStatus.NOT_FOUND, [("Content-Type", "text/plain")], corpo)

    # Descobre o formato do arquivo (HTML, CSS, JS, etc.)
    tipo_mime, _ = mimetypes.guess_type(arquivo_alvo)
    if not tipo_mime:
        tipo_mime = "application/octet-stream"
    if tipo_mime.startswith("text/") or tipo_mime in ("application/javascript", "application/json"):
        tipo_mime += "; charset=utf-8"

    # Lê o arquivo do disco e devolve para o navegador com regras rígidas anti-cache
    try:
        with open(arquivo_alvo, "rb") as f:
            conteudo = f.read()
        headers = [
            ("Content-Type", tipo_mime),
            ("Content-Length", str(len(conteudo))),
            ("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0"),
            ("Pragma", "no-cache")
        ]
        return (http.HTTPStatus.OK, headers, conteudo)
    except Exception as e:
        corpo = f"500 Internal Error: {e}".encode("utf-8")
        return (http.HTTPStatus.INTERNAL_SERVER_ERROR, [("Content-Type", "text/plain")], corpo)


# -----------------------------------------------------------------------------
# Handler do Canal WebSocket em Tempo Real (/ws)
# -----------------------------------------------------------------------------
async def websocket_handler(websocket, path):
    """
    Gerencia a conexão persistente e bidirecional com o navegador do fliperama:
    - Assim que a página abre, recebe o estado atual completo e o Top 10.
    - Fica escutando comandos do navegador (tecla espaço, cadastro de jogadores).
    """
    CLIENTES_CONECTADOS.add(websocket)
    logging.info(f"[WebSocket] Novo cliente conectado ({len(CLIENTES_CONECTADOS)} online)")

    try:
        # Envia o estado completo assim que o navegador se conecta
        estado_inicial = game_manager.obter_estado_atual()
        await websocket.send(json.dumps(estado_inicial))

        # Loop de escuta: fica aguardando mensagens enviadas pelo JavaScript do navegador
        async for mensagem_str in websocket:
            try:
                dados = json.loads(mensagem_str)
                tipo = dados.get("tipo")
                logging.info(f"[WebSocket Recebido] Tipo: {tipo}")

                # 1. Pressionou barra de espaço (Iniciar ou Parar)
                if tipo in ("ACAO_ESPACO", "INICIAR_PARTIDA"):
                    game_manager.acao_espaco()
                    if game_manager.estado == EstadosJogo.JOGANDO:
                        serial_handler.enviar_comando_arduino("LEDS_ON")
                    elif game_manager.estado == EstadosJogo.FINALIZADA:
                        serial_handler.enviar_comando_arduino("GAME_OVER")

                elif tipo == "FINALIZAR_PARTIDA":
                    game_manager.acao_espaco()
                    serial_handler.enviar_comando_arduino("GAME_OVER")

                # 2. Operador escolheu um jogador da lista
                elif tipo == "SELECIONAR_JOGADOR":
                    jogador_id = dados.get("jogador_id")
                    if jogador_id:
                        game_manager.selecionar_jogador(int(jogador_id))

                # 3. Operador cadastrou um novo competidor (nome + turma)
                elif tipo in ("CADASTRAR_JOGADOR", "CADASTRAR_FILA"):
                    nome = dados.get("nome", "").strip()
                    apelido = dados.get("apelido", "").strip()
                    apenas_fila = dados.get("apenas_fila", False) or (tipo == "CADASTRAR_FILA")
                    if nome:
                        if apenas_fila:
                            game_manager.cadastrar_jogador_na_fila(nome, apelido)
                        else:
                            game_manager.cadastrar_e_selecionar_jogador(nome, apelido)

                # 4. Requisição para atualizar lista de competidores cadastrados
                elif tipo == "LISTAR_JOGADORES":
                    await websocket.send(json.dumps({
                        "tipo": "LISTA_JOGADORES",
                        "jogadores_cadastrados": db.listar_jogadores()
                    }))

                # 5. Arremesso simulado pelo teclado do PC ([B], [P], [F])
                elif tipo == "SIMULAR_ARREMESSO":
                    sensor = dados.get("sensor", "BURACO")
                    tratar_mensagem_serial(sensor)

                # 6. Cancelamento ou reset manual
                elif tipo == "CANCELAR_PARTIDA":
                    game_manager.cancelar_partida()
                    serial_handler.enviar_comando_arduino("LEDS_OFF")

                elif tipo == "RESET_ESPERA":
                    game_manager.resetar_para_espera()
                    serial_handler.enviar_comando_arduino("LEDS_OFF")

                elif tipo == "OBTER_ESTADO":
                    await websocket.send(json.dumps(game_manager.obter_estado_atual()))

                # 7. Consulta de Ranking filtrado por turma/grupo ou geral
                elif tipo == "OBTER_RANKING":
                    grupo = dados.get("grupo")
                    ranking_filtrado = db.obter_ranking_por_grupo(grupo, 10)
                    await websocket.send(json.dumps({
                        "tipo": "RANKING_ATUALIZADO",
                        "grupo": grupo,
                        "ranking": ranking_filtrado
                    }))

                # 8. Consulta da lista de turmas/grupos cadastrados
                elif tipo == "LISTAR_GRUPOS":
                    await websocket.send(json.dumps({
                        "tipo": "LISTA_GRUPOS",
                        "grupos": db.listar_grupos()
                    }))

                # 9. Backup Manual via WebSocket
                elif tipo == "FAZER_BACKUP":
                    try:
                        arq = db.fazer_backup()
                        await websocket.send(json.dumps({
                            "tipo": "BACKUP_CONCLUIDO",
                            "sucesso": True,
                            "mensagem": f"Backup salvo com sucesso: {os.path.basename(arq)}"
                        }))
                    except Exception as e:
                        await websocket.send(json.dumps({
                            "tipo": "BACKUP_CONCLUIDO",
                            "sucesso": False,
                            "mensagem": f"Erro ao gerar backup: {e}"
                        }))

                # 10. Restaurar Backup via WebSocket
                elif tipo == "RESTAURAR_BACKUP":
                    try:
                        arq = db.restaurar_backup()
                        # Atualiza todas as telas
                        await broadcast_evento(json.dumps({
                            "tipo": "RANKING_ATUALIZADO",
                            "ranking": db.obter_ranking_global(10),
                            "grupos": db.listar_grupos()
                        }))
                        await broadcast_evento(json.dumps({
                            "tipo": "LISTA_JOGADORES",
                            "jogadores_cadastrados": db.listar_jogadores()
                        }))
                        await websocket.send(json.dumps({
                            "tipo": "RESTAURACAO_CONCLUIDA",
                            "sucesso": True,
                            "mensagem": f"Banco restaurado a partir de {os.path.basename(arq)}!"
                        }))
                    except Exception as e:
                        await websocket.send(json.dumps({
                            "tipo": "RESTAURACAO_CONCLUIDA",
                            "sucesso": False,
                            "mensagem": f"Erro na restauração: {e}"
                        }))

                # 11. Zerar Banco de Dados (PROTEGIDO POR SENHA: 'admin')
                elif tipo == "ZERAR_BANCO":
                    senha = dados.get("senha", "")
                    res = db.zerar_banco_dados(senha)
                    if res.get("sucesso"):
                        game_manager.resetar_para_espera()
                        await broadcast_evento(json.dumps(game_manager.obter_estado_atual()))
                        await broadcast_evento(json.dumps({
                            "tipo": "RANKING_ATUALIZADO",
                            "ranking": db.obter_ranking_global(10),
                            "grupos": db.listar_grupos()
                        }))
                        await broadcast_evento(json.dumps({
                            "tipo": "LISTA_JOGADORES",
                            "jogadores_cadastrados": db.listar_jogadores()
                        }))
                        await websocket.send(json.dumps({
                            "tipo": "BANCO_ZERADO",
                            "sucesso": True,
                            "mensagem": res.get("mensagem")
                        }))
                    else:
                        await websocket.send(json.dumps({
                            "tipo": "BANCO_ZERADO",
                            "sucesso": False,
                            "mensagem": res.get("mensagem")
                        }))

                # 12. Exportar Planilhas CSV via WebSocket
                elif tipo == "EXPORTAR_CSV":
                    try:
                        res_csv = db.exportar_csv()
                        await websocket.send(json.dumps({
                            "tipo": "CSV_EXPORTADO",
                            "sucesso": True,
                            "mensagem": "Planilhas CSV geradas com sucesso na raiz do projeto!",
                            "arquivos": res_csv
                        }))
                    except Exception as e:
                        await websocket.send(json.dumps({
                            "tipo": "CSV_EXPORTADO",
                            "sucesso": False,
                            "mensagem": f"Erro ao exportar CSV: {e}"
                        }))

            except json.JSONDecodeError:
                logging.warning(f"[WebSocket] Mensagem JSON inválida: {mensagem_str}")
            except Exception as e:
                logging.error(f"[WebSocket] Erro ao processar mensagem: {e}")

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        # Quando a aba do navegador é fechada, remove da lista
        CLIENTES_CONECTADOS.discard(websocket)
        logging.info(f"[WebSocket] Cliente desconectado ({len(CLIENTES_CONECTADOS)} restantes)")


# -----------------------------------------------------------------------------
# Ponto de Partida do Servidor
# -----------------------------------------------------------------------------
async def main():
    """
    Função principal que inicia a escuta do Arduino e liga o servidor web na porta 8080.
    """
    global LOOP
    LOOP = asyncio.get_running_loop()

    # Inicia a escuta da porta USB em segundo plano
    serial_handler.iniciar()

    host = "0.0.0.0"
    porta_preferencial = int(os.environ.get("PORT", "8080"))
    portas_candidatas = [porta_preferencial] + [p for p in [8081, 8082, 8088, 8000] if p != porta_preferencial]

    server = None
    porta = porta_preferencial
    for p in portas_candidatas:
        try:
            server = await websockets.serve(
                websocket_handler,
                host,
                p,
                process_request=process_http_request
            )
            porta = p
            break
        except OSError as e:
            if p == portas_candidatas[-1]:
                raise
            logging.warning(f"Porta {p} indisponível ({e}). Tentando próxima porta...")

    logging.info("=" * 60)
    logging.info("🎮 CORNHOLE INTELIGENTE - IFEx")
    logging.info(f"🌐 Servidor Web & WebSocket rodando em: http://localhost:{porta}")
    logging.info("🕹️ Modo Simulador ativo pelo teclado: [ESPAÇO], [B], [P], [F], [O]")
    logging.info("=" * 60)

    async with server:
        await asyncio.Future()  # Mantém o servidor ligado continuamente


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Servidor encerrado pelo usuário.")
        serial_handler.parar()

