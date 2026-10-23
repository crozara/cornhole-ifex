"""
=============================================================================
CORNHOLE INTELIGENTE - IFEx 2026
Arquivo: database/db.py
Função: Camada de Acesso e Persistência de Dados (PostgreSQL)
=============================================================================
Este arquivo é o "GARÇOM / PONTE" entre o código Python e o banco de dados.
Ele reúne todas as funções que salvam e buscam informações no PostgreSQL:
- Cadastro e busca de competidores (jogadores)
- Abertura de novas rodadas (partidas)
- Registro lance a lance dos 5 arremessos
- Consulta do Ranking Top 10 com desempate por tempo

Como a conexão é feita:
Ele usa o cliente oficial 'psql' através do socket Unix local (.pgrun).
Dessa forma, o banco funciona 100% offline, seguro e sem depender de internet.
=============================================================================
"""

import json
import os
import subprocess
from typing import Any, Dict, List, Optional

# Configurações dinâmicas de caminhos absolutos baseados no diretório do projeto
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
DEFAULT_PG_RUN = os.path.join(PROJECT_ROOT, ".pgrun")

# Configurações de Conexão com o PostgreSQL local
# O 'PG_RUN' aponta para a pasta onde o PostgreSQL cria seu arquivo de comunicação (socket)
PG_RUN = os.environ.get("PG_RUN", DEFAULT_PG_RUN)
PG_PORT = os.environ.get("PG_PORT", "5432")
PG_USER = os.environ.get("PG_USER", "postgres")
DB_NAME = os.environ.get("DB_NAME", "ifex_cornhole")

PONTOS_PADRAO_SENSORES = {
    "PEQUENO": 8,
    "MEDIO": 6,
    "GRANDE": 4,
    "PRANCHA": 0,
    "FORA": -4,
    "BURACO": 8,
}


def _execute_sql(sql: str, params: Optional[List[Any]] = None) -> None:
    """
    Executa comandos SQL simples que não precisam retornar dados (como DELETE ou UPDATE em lote).
    Se o comando falhar, ele interrompe e avisa o erro exato retornado pelo banco.
    """
    cmd = [
        "psql",
        "-h", PG_RUN,
        "-p", PG_PORT,
        "-U", PG_USER,
        "-d", DB_NAME,
        "-v", "ON_ERROR_STOP=1",
        "-c", sql
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Erro ao executar SQL: {res.stderr.strip()}")


def _query_json(sql: str) -> List[Dict[str, Any]]:
    """
    Função Inteligente de Consulta:
    Em vez de converter manualmente as linhas do banco para Python, nós pedimos
    para o próprio PostgreSQL agrupar os resultados diretamente em formato JSON 
    usando a função nativa 'json_agg()'.
    
    Isso é extremamente rápido e já entrega os dados prontos como dicionários Python!
    """
    clean_sql = sql.strip().rstrip(";")
    first_word = clean_sql.split()[0].upper()
    
    # Se for INSERT/UPDATE com RETURNING, usamos CTE (WITH) para transformar em JSON
    if first_word in ("INSERT", "UPDATE", "DELETE", "WITH"):
        wrapped_sql = f"WITH dml_rows AS ({clean_sql}) SELECT COALESCE(json_agg(dml_rows), '[]'::json) FROM dml_rows;"
    else:
        # Se for um SELECT normal
        wrapped_sql = f"SELECT COALESCE(json_agg(t), '[]'::json) FROM ({clean_sql}) t;"
        
    cmd = [
        "psql",
        "-h", PG_RUN,
        "-p", PG_PORT,
        "-U", PG_USER,
        "-d", DB_NAME,
        "-t",  # Apenas o texto puro (sem cabeçalhos decorativos de tabela)
        "-A",  # Sem espaços em branco extras
        "-v", "ON_ERROR_STOP=1",
        "-c", wrapped_sql
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Erro na query SQL: {res.stderr.strip()}")
    
    out = res.stdout.strip()
    if not out:
        return []
    # Converte o texto JSON que o PostgreSQL gerou de volta para lista do Python
    return json.loads(out)


# -----------------------------------------------------------------------------
# 1. Operações com Jogadores (Competidores)
# -----------------------------------------------------------------------------
def cadastrar_ou_obter_jogador(nome: str, apelido: Optional[str] = None) -> Dict[str, Any]:
    """
    Cadastra um novo competidor (nome e turma/apelido).
    Se já existir um jogador com o mesmo nome, ele não duplica: apenas reutiliza o cadastro existente.
    """
    nome = nome.strip()
    apelido = apelido.strip() if apelido else None

    # Verifica primeiro se já existe alguém com esse nome (sem diferenciar maiúsculas/minúsculas)
    query = f"""
        SELECT id, nome, apelido, criado_em 
        FROM jogadores 
        WHERE LOWER(nome) = LOWER('{nome.replace("'", "''")}')
        LIMIT 1;
    """
    existente = _query_json(query)
    if existente:
        return existente[0]

    # Se não existe, insere o novo competidor na tabela 'jogadores'
    insert_sql = f"""
        INSERT INTO jogadores (nome, apelido) 
        VALUES ('{nome.replace("'", "''")}', {f"'{apelido.replace("'", "''")}'" if apelido else 'NULL'})
        RETURNING id, nome, apelido, criado_em;
    """
    res = _query_json(insert_sql)
    return res[0]


def listar_jogadores() -> List[Dict[str, Any]]:
    """
    Retorna a lista completa de competidores cadastrados em ordem alfabética.
    Utilizada para preencher a caixa de seleção no Painel do Operador [O].
    """
    return _query_json("SELECT id, nome, apelido, criado_em FROM jogadores ORDER BY nome ASC;")


# -----------------------------------------------------------------------------
# 2. Operações com a Tabela de Sensores
# -----------------------------------------------------------------------------
def listar_sensores() -> List[Dict[str, Any]]:
    """
    Retorna os sensores ativos cadastrados no banco e seus valores de pontuação:
    - PEQUENO: 8 pontos
    - MEDIO: 6 pontos
    - GRANDE: 4 pontos
    - FORA: 0 pontos
    """
    return _query_json("SELECT codigo, pontos, descricao, ativo FROM sensores WHERE ativo = TRUE;")


# -----------------------------------------------------------------------------
# 3. Operações com Partidas e Arremessos
# -----------------------------------------------------------------------------
def iniciar_partida(jogador_id: int) -> Dict[str, Any]:
    """
    Cria uma nova linha na tabela 'partidas' com o status 'em_andamento'.
    Retorna o ID gerado para que os arremessos fiquem vinculados a essa rodada.
    """
    sql = f"""
        INSERT INTO partidas (jogador_id, status, pontuacao_total, iniciada_em)
        VALUES ({jogador_id}, 'em_andamento', 0, NOW())
        RETURNING id, jogador_id, status, pontuacao_total, iniciada_em;
    """
    res = _query_json(sql)
    return res[0]


def registrar_arremesso(
    partida_id: int, 
    numero_saquinho: int, 
    sensor_codigo: str, 
    tempo_parcial_ms: Optional[int] = None,
    pontos: Optional[int] = None
) -> Dict[str, Any]:
    """
    Registra um dos 5 arremessos de uma rodada na tabela 'arremessos'.
    
    Se 'pontos' for enviado pelo Arduino (main.ino), grava exatamente esse valor
    e garante que o sensor esteja cadastrado na tabela 'sensores'.
    A trigger 'trg_atualiza_pontuacao' no PostgreSQL recalcula a soma na tabela 'partidas'.
    """
    codigo_limpo = sensor_codigo.strip().upper().replace("'", "''")
    pontos_padrao = PONTOS_PADRAO_SENSORES.get(codigo_limpo, 0)
    pontos_efetivos = int(pontos) if pontos is not None else pontos_padrao

    # Garante que restrições antigas de pontos >= 0 sejam removidas (para aceitar FORA = -4)
    # e que o sensor esteja cadastrado na tabela 'sensores' com a pontuação correspondente
    _execute_sql(f"""
        ALTER TABLE sensores DROP CONSTRAINT IF EXISTS sensores_pontos_check;
        ALTER TABLE partidas DROP CONSTRAINT IF EXISTS partidas_pontuacao_total_check;
        ALTER TABLE arremessos DROP CONSTRAINT IF EXISTS arremessos_pontos_check;
        INSERT INTO sensores (codigo, pontos, descricao, ativo)
        VALUES ('{codigo_limpo}', {pontos_efetivos}, 'Sensor {codigo_limpo}', TRUE)
        ON CONFLICT (codigo) DO UPDATE SET pontos = EXCLUDED.pontos;
    """)

    tempo_val = tempo_parcial_ms if tempo_parcial_ms is not None else "NULL"
    pontos_val = int(pontos) if pontos is not None else "NULL"
    sql = f"""
        INSERT INTO arremessos (partida_id, numero_saquinho, sensor_codigo, pontos, tempo_parcial_ms)
        VALUES ({partida_id}, {numero_saquinho}, '{codigo_limpo}', {pontos_val}, {tempo_val})
        RETURNING id, partida_id, numero_saquinho, sensor_codigo, pontos, tempo_parcial_ms, registrado_em;
    """
    res = _query_json(sql)
    return res[0]


def finalizar_partida(partida_id: int, tempo_ms: int) -> Dict[str, Any]:
    """
    Encerra a rodada no PostgreSQL:
    1. Muda o status para 'finalizada';
    2. Grava o tempo_ms exato travado na barra de espaço;
    3. Carimba a data/hora exata de término (NOW()).
    """
    sql = f"""
        UPDATE partidas
        SET status = 'finalizada',
            tempo_ms = {tempo_ms},
            finalizada_em = NOW()
        WHERE id = {partida_id}
        RETURNING id, jogador_id, status, pontuacao_total, tempo_ms, finalizada_em;
    """
    res = _query_json(sql)
    return res[0]


def obter_detalhes_partida(partida_id: int) -> Optional[Dict[str, Any]]:
    """
    Busca o raio-X completo de uma partida: dados do competidor e o histórico
    detalhado de cada um dos 5 saquinhos lançados.
    """
    sql_partida = f"""
        SELECT p.id, p.jogador_id, j.nome AS nome_jogador, j.apelido AS apelido_jogador,
               p.status, p.pontuacao_total, p.tempo_ms, p.iniciada_em, p.finalizada_em
        FROM partidas p
        JOIN jogadores j ON p.jogador_id = j.id
        WHERE p.id = {partida_id};
    """
    partida = _query_json(sql_partida)
    if not partida:
        return None

    dados = partida[0]
    sql_arremessos = f"""
        SELECT numero_saquinho, sensor_codigo, pontos, tempo_parcial_ms, registrado_em
        FROM arremessos
        WHERE partida_id = {partida_id}
        ORDER BY numero_saquinho ASC;
    """
    dados["arremessos"] = _query_json(sql_arremessos)
    return dados


# -----------------------------------------------------------------------------
# 4. Consulta do Ranking Global (View Analítica do IFEx)
# -----------------------------------------------------------------------------
def obter_ranking_global(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Consulta a VIEW analítica 'view_ranking_global' criada no PostgreSQL.
    Ela devolve os melhores competidores já ordenados pelas regras do IFEx:
    1º: Maior pontuação total;
    2º (Critério de Desempate): Menor tempo em milissegundos;
    3º: Apenas a MELHOR rodada de cada participante (sem nomes repetidos no pódio).
    """
    sql = f"""
        SELECT 
            posicao,
            jogador_id,
            nome_jogador,
            apelido_jogador,
            partida_id,
            pontuacao_total,
            tempo_ms,
            tempo_segundos,
            tempo_formatado,
            finalizada_em
        FROM view_ranking_global
        LIMIT {limit};
    """
    return _query_json(sql)


def listar_grupos() -> List[str]:
    """
    Retorna a lista de turmas/grupos distintos cadastrados pelos competidores.
    Utilizada para alimentar o seletor de turmas no placar do fliperama.
    """
    sql = """
        SELECT DISTINCT TRIM(apelido) AS grupo
        FROM jogadores
        WHERE apelido IS NOT NULL AND TRIM(apelido) != ''
        ORDER BY grupo ASC;
    """
    resultados = _query_json(sql)
    return [r["grupo"] for r in resultados if r.get("grupo")]


def obter_ranking_por_grupo(grupo: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Retorna o Ranking filtrado para uma turma/grupo específico ou geral.
    - Se grupo for None, vazio ou 'GERAL'/'TODOS': retorna o ranking global.
    - Se for uma turma específica: filtra os competidores daquela turma e calcula
      as posições (1º, 2º, 3º...) internamente para aquele grupo, mantendo o critério
      oficial de pontuação e desempate por tempo.
    """
    if not grupo or grupo.strip().upper() in ("TODOS", "GERAL", "TODAS"):
        return obter_ranking_global(limit)

    grupo_escapado = grupo.strip().replace("'", "''")
    sql = f"""
        WITH melhor_partida_por_jogador AS (
            SELECT 
                p.id AS partida_id,
                p.jogador_id,
                p.pontuacao_total,
                p.tempo_ms,
                p.iniciada_em,
                p.finalizada_em,
                ROW_NUMBER() OVER (
                    PARTITION BY p.jogador_id 
                    ORDER BY 
                        p.pontuacao_total DESC,
                        p.tempo_ms ASC NULLS LAST,
                        p.finalizada_em ASC
                ) AS ranking_pessoal
            FROM partidas p
            JOIN jogadores j ON p.jogador_id = j.id
            WHERE p.status = 'finalizada'
              AND LOWER(TRIM(j.apelido)) = LOWER(TRIM('{grupo_escapado}'))
        )
        SELECT 
            DENSE_RANK() OVER (
                ORDER BY 
                    m.pontuacao_total DESC, 
                    m.tempo_ms ASC NULLS LAST, 
                    m.finalizada_em ASC
            ) AS posicao,
            j.id AS jogador_id,
            j.nome AS nome_jogador,
            COALESCE(j.apelido, '{grupo_escapado}') AS apelido_jogador,
            m.partida_id,
            m.pontuacao_total,
            m.tempo_ms,
            ROUND(m.tempo_ms / 1000.0, 2) AS tempo_segundos,
            TO_CHAR(INTERVAL '1 millisecond' * m.tempo_ms, 'MI:SS.MS') AS tempo_formatado,
            m.finalizada_em
        FROM melhor_partida_por_jogador m
        JOIN jogadores j ON j.id = m.jogador_id
        WHERE m.ranking_pessoal = 1
        ORDER BY posicao ASC
        LIMIT {limit};
    """
    return _query_json(sql)


# -----------------------------------------------------------------------------
# 5. Backup, Restauração e Segurança de Dados
# -----------------------------------------------------------------------------
def fazer_backup(caminho_arquivo: Optional[str] = None) -> str:
    """
    Gera um backup SQL completo e consistente do banco de dados PostgreSQL.
    Retorna o caminho absoluto do arquivo .sql gerado.
    """
    backup_dir = os.path.join(PROJECT_ROOT, "backups")
    os.makedirs(backup_dir, exist_ok=True)

    if not caminho_arquivo:
        import datetime
        agora = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        caminho_arquivo = os.path.join(backup_dir, f"backup_{agora}.sql")

    cmd = [
        "pg_dump",
        "-h", PG_RUN,
        "-p", PG_PORT,
        "-U", PG_USER,
        "-d", DB_NAME,
        "--clean",
        "--if-exists",
        "-f", caminho_arquivo
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Erro ao gerar backup: {res.stderr.strip()}")

    # Mantém também uma cópia como backup_automatico_recente.sql para restauração rápida
    copia_recente = os.path.join(backup_dir, "backup_automatico_recente.sql")
    try:
        import shutil
        shutil.copyfile(caminho_arquivo, copia_recente)
    except Exception:
        pass

    return caminho_arquivo


def restaurar_backup(caminho_arquivo: Optional[str] = None) -> str:
    """
    Restaura o banco a partir de um arquivo SQL de backup.
    Se nenhum arquivo for especificado, utiliza o backup mais recente.
    """
    backup_dir = os.path.join(PROJECT_ROOT, "backups")

    if not caminho_arquivo:
        copia_recente = os.path.join(backup_dir, "backup_automatico_recente.sql")
        if os.path.isfile(copia_recente):
            caminho_arquivo = copia_recente
        else:
            # Pega o arquivo .sql mais recente da pasta
            import glob
            arquivos = sorted(glob.glob(os.path.join(backup_dir, "backup_*.sql")), key=os.path.getmtime, reverse=True)
            if arquivos:
                caminho_arquivo = arquivos[0]

    if not caminho_arquivo or not os.path.isfile(caminho_arquivo):
        raise FileNotFoundError("Nenhum arquivo de backup encontrado para restauração.")

    cmd = [
        "psql",
        "-h", PG_RUN,
        "-p", PG_PORT,
        "-U", PG_USER,
        "-d", DB_NAME,
        "-v", "ON_ERROR_STOP=1",
        "-f", caminho_arquivo
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Erro ao restaurar backup: {res.stderr.strip()}")

    # Re-aplica triggers e views para assegurar consistência
    dir_db = os.path.dirname(os.path.abspath(__file__))
    _execute_sql(open(os.path.join(dir_db, "triggers.sql")).read())
    _execute_sql(open(os.path.join(dir_db, "views.sql")).read())

    return caminho_arquivo


def zerar_banco_dados(senha: str) -> Dict[str, Any]:
    """
    Limpa completamente todas as partidas e jogadores, reiniciando o placar.
    EXIGE SENHA: 'admin'.
    Por segurança, gera automaticamente um backup pré-reset antes de apagar.
    """
    if senha.strip() != "admin":
        return {"sucesso": False, "mensagem": "Senha incorreta! Operação cancelada."}

    # 1. Gera backup de emergência
    backup_dir = os.path.join(PROJECT_ROOT, "backups")
    os.makedirs(backup_dir, exist_ok=True)
    import datetime
    agora = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safety_backup = os.path.join(backup_dir, f"backup_pre_reset_{agora}.sql")
    try:
        fazer_backup(safety_backup)
    except Exception as e:
        pass

    # 2. Apaga as tabelas
    sql_drop = """
        DROP TABLE IF EXISTS arremessos CASCADE;
        DROP TABLE IF EXISTS partidas CASCADE;
        DROP TABLE IF EXISTS sensores CASCADE;
        DROP TABLE IF EXISTS jogadores CASCADE;
    """
    _execute_sql(sql_drop)

    # 3. Recria estrutura limpa
    dir_db = os.path.dirname(os.path.abspath(__file__))
    _execute_sql(open(os.path.join(dir_db, "schema.sql")).read())
    _execute_sql(open(os.path.join(dir_db, "triggers.sql")).read())
    _execute_sql(open(os.path.join(dir_db, "views.sql")).read())

    return {
        "sucesso": True,
        "mensagem": "Banco de dados zerado com sucesso! Um backup de segurança foi criado.",
        "backup_seguranca": safety_backup
    }


def exportar_csv() -> Dict[str, str]:
    """
    Exporta o Ranking Global e o Histórico de Partidas para planilhas CSV na raiz do projeto.
    """
    ranking_csv = os.path.join(PROJECT_ROOT, "ranking.csv")
    historico_csv = os.path.join(PROJECT_ROOT, "historico_partidas.csv")

    cmd1 = [
        "psql", "-h", PG_RUN, "-p", PG_PORT, "-U", PG_USER, "-d", DB_NAME,
        "-c", f"\\copy (SELECT * FROM view_ranking_global) TO '{ranking_csv}' WITH CSV HEADER"
    ]
    subprocess.run(cmd1, capture_output=True, text=True, check=True)

    cmd2 = [
        "psql", "-h", PG_RUN, "-p", PG_PORT, "-U", PG_USER, "-d", DB_NAME,
        "-c", f"\\copy (SELECT * FROM view_historico_partidas) TO '{historico_csv}' WITH CSV HEADER"
    ]
    subprocess.run(cmd2, capture_output=True, text=True, check=True)

    return {"ranking_csv": ranking_csv, "historico_csv": historico_csv}


def importar_partidas_csv(caminho_csv: str) -> int:
    """
    Importa competidores e partidas finalizadas a partir de um arquivo CSV
    (seja ranking.csv ou historico_partidas.csv).
    Retorna o número de partidas importadas com sucesso.
    """
    import csv

    if not os.path.isfile(caminho_csv):
        raise FileNotFoundError(f"Arquivo CSV não encontrado: {caminho_csv}")

    total_importados = 0
    with open(caminho_csv, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            nome = (row.get("nome_jogador") or "").strip()
            apelido = (row.get("apelido_jogador") or "").strip()
            if not nome:
                continue

            # Pontuação total
            try:
                pontos = int(row.get("pontuacao_total") or 0)
            except ValueError:
                pontos = 0

            # Tempo em milissegundos
            tempo_ms = None
            if "tempo_ms" in row and row["tempo_ms"]:
                try:
                    tempo_ms = int(row["tempo_ms"])
                except ValueError:
                    tempo_ms = None
            elif "tempo_segundos" in row and row["tempo_segundos"]:
                try:
                    tempo_ms = int(float(row["tempo_segundos"]) * 1000)
                except ValueError:
                    tempo_ms = None

            jogador = cadastrar_ou_obter_jogador(nome, apelido)
            jogador_id = jogador["id"]

            # Insere a partida diretamente como finalizada
            sql_partida = f"""
                INSERT INTO partidas (jogador_id, status, pontuacao_total, tempo_ms, iniciada_em, finalizada_em)
                VALUES ({jogador_id}, 'finalizada', {pontos}, {tempo_ms if tempo_ms is not None else 'NULL'}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id;
            """
            res_partida = _query_json(sql_partida)
            if res_partida:
                nova_partida_id = res_partida[0]["id"]
                
                # Se tiver detalhe dos saquinhos (buracos, pranchas, fora), insere os arremessos
                buracos = int(row.get("saquinhos_buraco") or 0)
                pranchas = int(row.get("saquinhos_prancha") or 0)
                fora = int(row.get("saquinhos_fora") or 0)
                
                # Gera até 5 saquinhos proporcionais
                seq = 1
                for _ in range(buracos):
                    if seq <= 5:
                        registrar_arremesso(nova_partida_id, seq, "BURACO", tempo_ms or 0)
                        seq += 1
                for _ in range(pranchas):
                    if seq <= 5:
                        registrar_arremesso(nova_partida_id, seq, "PRANCHA", tempo_ms or 0)
                        seq += 1
                for _ in range(fora):
                    if seq <= 5:
                        registrar_arremesso(nova_partida_id, seq, "FORA", tempo_ms or 0)
                        seq += 1

                total_importados += 1

    return total_importados


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == "--import-csv":
        arquivo = sys.argv[2]
        qtd = importar_partidas_csv(arquivo)
        print(f"✅ {qtd} partidas importadas com sucesso de '{arquivo}'!")
