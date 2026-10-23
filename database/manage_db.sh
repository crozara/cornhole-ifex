#!/usr/bin/env bash
# =============================================================================
# CORNHOLE INTELIGENTE - IFEx 2026
# Arquivo: database/manage_db.sh
# Função: Script Utilitário para Controlar o Banco de Dados via Terminal
# =============================================================================
# Com este arquivo você não precisa decorar comandos difíceis do PostgreSQL.
# Basta rodar no terminal:
#   ./database/manage_db.sh ver   -> Mostra o Ranking e as Partidas formatadas
#   ./database/manage_db.sh csv   -> Exporta tudo para planilhas Excel (.csv)
#   ./database/manage_db.sh start -> Inicia o banco de dados
#   ./database/manage_db.sh stop  -> Desliga o banco de dados
#   ./database/manage_db.sh psql  -> Abre o terminal de comando do PostgreSQL
# =============================================================================

# 'set -e' faz o script parar imediatamente se algum comando der erro
set -e

# Descobre o caminho absoluto das pastas do projeto
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$DIR/.." && pwd)"

# Define onde os dados do banco ficam gravados (pasta local .pgdata)
PG_DATA="${PG_DATA:-$PROJECT_ROOT/.pgdata}"

# Define onde o arquivo de comunicação do banco fica (pasta local .pgrun)
PG_RUN="${PG_RUN:-$PROJECT_ROOT/.pgrun}"

DB_NAME="ifex_cornhole"

# Localização dinâmica dos executáveis do PostgreSQL no Linux (17, 16, 15, 14 ou PATH do sistema)
if ! command -v initdb >/dev/null 2>&1 || ! command -v psql >/dev/null 2>&1; then
    for v in 17 16 15 14; do
        if [ -d "/usr/lib/postgresql/$v/bin" ]; then
            export PATH="/usr/lib/postgresql/$v/bin:$PATH"
            break
        fi
    done
fi

# Garante que a pasta do socket de comunicação exista
mkdir -p "$PG_RUN"

# -----------------------------------------------------------------------------
# Função: Iniciar o PostgreSQL
# -----------------------------------------------------------------------------
start_pg() {
    # Se a pasta .pgdata ainda não existir, cria o cluster do banco do zero
    if [ ! -d "$PG_DATA" ]; then
        echo "==> Inicializando cluster PostgreSQL em $PG_DATA..."
        initdb -D "$PG_DATA" -E UTF8 --no-locale -U postgres >/dev/null
    fi

    # 'pg_isready' testa se o banco já está ligado e respondendo
    if pg_isready -h "$PG_RUN" -p 5432 >/dev/null 2>&1; then
        echo "==> PostgreSQL já está em execução."
    else
        # Se o computador foi desligado de repente, remove arquivos de trava antigos
        if [ -f "$PG_DATA/postmaster.pid" ]; then
            rm -f "$PG_DATA/postmaster.pid"
        fi
        echo "==> Iniciando PostgreSQL local..."
        pg_ctl -D "$PG_DATA" -o "-k $PG_RUN -c listen_addresses='' -p 5432" -l "$PG_RUN/postgresql.log" start
        echo "==> PostgreSQL iniciado com sucesso!"
    fi
}

# -----------------------------------------------------------------------------
# Função: Parar o PostgreSQL de forma segura
# -----------------------------------------------------------------------------
stop_pg() {
    if [ -d "$PG_DATA" ]; then
        echo "==> Parando PostgreSQL..."
        pg_ctl -D "$PG_DATA" stop -m fast || true
    fi
}

# -----------------------------------------------------------------------------
# Função: Criar Tabelas, Triggers e Views (Setup Não-Destrutivo)
# -----------------------------------------------------------------------------
init_db() {
    start_pg
    echo "==> Criando banco de dados $DB_NAME (se não existir)..."
    psql -h "$PG_RUN" -p 5432 -U postgres -tc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q 1 || \
    psql -h "$PG_RUN" -p 5432 -U postgres -c "CREATE DATABASE $DB_NAME;"

    echo "==> Aplicando schema.sql (Garante tabelas sem apagar dados existentes)..."
    psql -h "$PG_RUN" -p 5432 -U postgres -d "$DB_NAME" -f "$DIR/schema.sql"

    echo "==> Aplicando triggers.sql (Gatilhos automáticos de pontuação)..."
    psql -h "$PG_RUN" -p 5432 -U postgres -d "$DB_NAME" -f "$DIR/triggers.sql"

    echo "==> Aplicando views.sql (Ranking analítico com desempate)..."
    psql -h "$PG_RUN" -p 5432 -U postgres -d "$DB_NAME" -f "$DIR/views.sql"

    echo "==> Banco de dados configurado e verificado com sucesso!"
}

# -----------------------------------------------------------------------------
# Função: Fazer Backup Completo do Banco (SQL Dump)
# -----------------------------------------------------------------------------
backup_db() {
    start_pg
    local BACKUP_DIR="$PROJECT_ROOT/backups"
    mkdir -p "$BACKUP_DIR"
    local TIMESTAMP
    TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
    local OUT_FILE="${1:-$BACKUP_DIR/backup_$TIMESTAMP.sql}"

    echo "==> Gerando backup completo do banco de dados em $OUT_FILE..."
    pg_dump -h "$PG_RUN" -p 5432 -U postgres -d "$DB_NAME" --clean --if-exists -f "$OUT_FILE"
    
    # Também mantém uma cópia do último backup para restauração rápida
    cp "$OUT_FILE" "$BACKUP_DIR/backup_automatico_recente.sql"

    echo "✅ Backup realizado com sucesso! Tamanho: $(du -h "$OUT_FILE" | cut -f1)"
    echo "📁 Arquivo: $OUT_FILE"
}

# -----------------------------------------------------------------------------
# Função: Restaurar Banco a Partir de um Backup SQL
# -----------------------------------------------------------------------------
restore_db() {
    start_pg
    local BACKUP_DIR="$PROJECT_ROOT/backups"
    local IN_FILE="$1"

    if [ -z "$IN_FILE" ]; then
        # Se não especificou arquivo, procura o mais recente na pasta backups
        if [ -f "$BACKUP_DIR/backup_automatico_recente.sql" ]; then
            IN_FILE="$BACKUP_DIR/backup_automatico_recente.sql"
        else
            IN_FILE=$(ls -t "$BACKUP_DIR"/backup_*.sql 2>/dev/null | head -n 1 || true)
        fi
    fi

    if [ -z "$IN_FILE" ] || [ ! -f "$IN_FILE" ]; then
        echo "❌ Erro: Nenhum arquivo de backup válido foi encontrado."
        echo "   Uso: $0 restore [caminho_do_arquivo.sql]"
        exit 1
    fi

    echo "==> Restaurando banco de dados a partir de $IN_FILE..."
    psql -h "$PG_RUN" -p 5432 -U postgres -d "$DB_NAME" -f "$IN_FILE"

    # Re-aplica triggers e views para garantir consistência
    psql -h "$PG_RUN" -p 5432 -U postgres -d "$DB_NAME" -f "$DIR/triggers.sql" >/dev/null 2>&1 || true
    psql -h "$PG_RUN" -p 5432 -U postgres -d "$DB_NAME" -f "$DIR/views.sql" >/dev/null 2>&1 || true

    echo "✅ Banco de dados restaurado com sucesso a partir de $IN_FILE!"
}

# -----------------------------------------------------------------------------
# Função: Zerar/Resetar Banco de Dados (PROTEGIDO POR SENHA: 'admin')
# -----------------------------------------------------------------------------
reset_db() {
    local PASS_INPUT="$1"

    # Se a senha não foi passada como argumento, solicita no terminal
    if [ -z "$PASS_INPUT" ]; then
        echo -n "🔒 Digite a senha de administrador para zerar o banco de dados: "
        read -s PASS_INPUT
        echo ""
    fi

    if [ "$PASS_INPUT" != "admin" ]; then
        echo "❌ Senha incorreta! Operação de limpeza abortada."
        exit 1
    fi

    echo "⚠️ Senha correta confirmada ('admin')."
    
    # Gera um backup de emergência antes de apagar, caso alguém se arrependa
    start_pg
    local BACKUP_DIR="$PROJECT_ROOT/backups"
    mkdir -p "$BACKUP_DIR"
    local TIMESTAMP
    TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
    local SAFETY_BACKUP="$BACKUP_DIR/backup_pre_reset_$TIMESTAMP.sql"
    echo "==> Criando backup preventivo de segurança em $SAFETY_BACKUP..."
    pg_dump -h "$PG_RUN" -p 5432 -U postgres -d "$DB_NAME" --clean --if-exists -f "$SAFETY_BACKUP" >/dev/null 2>&1 || true

    echo "==> Apagando todas as tabelas e partidas antigas..."
    psql -h "$PG_RUN" -p 5432 -U postgres -d "$DB_NAME" -c "
        DROP TABLE IF EXISTS arremessos CASCADE;
        DROP TABLE IF EXISTS partidas CASCADE;
        DROP TABLE IF EXISTS sensores CASCADE;
        DROP TABLE IF EXISTS jogadores CASCADE;
    "

    # Recria a estrutura limpa
    init_db
    echo "🎉 Banco de dados zerado com sucesso! Um backup pré-limpeza foi salvo em $SAFETY_BACKUP."
}

# -----------------------------------------------------------------------------
# Função: Ver o Ranking e o Histórico formatados direto no Terminal
# -----------------------------------------------------------------------------
ver_tabelas() {
    start_pg
    echo "========================================================================"
    echo "🏆 RANKING GLOBAL IFEX (MELHOR RESULTADO POR JOGADOR)"
    echo "========================================================================"
    psql -h "$PG_RUN" -p 5432 -U postgres -d "$DB_NAME" -c "
        SELECT posicao, nome_jogador, apelido_jogador, pontuacao_total, tempo_formatado
        FROM view_ranking_global;
    "
    echo ""
    echo "========================================================================"
    echo "📋 HISTÓRICO DE TODAS AS PARTIDAS DISPUTADAS"
    echo "========================================================================"
    psql -h "$PG_RUN" -p 5432 -U postgres -d "$DB_NAME" -c "
        SELECT partida_id, nome_jogador, pontuacao_total, tempo_segundos || 's' AS tempo,
               saquinhos_buraco AS buracos, saquinhos_prancha AS pranchas, saquinhos_fora AS fora
        FROM view_historico_partidas
        LIMIT 15;
    "
}

# -----------------------------------------------------------------------------
# Função: Exportar os dados para arquivos Excel (.CSV)
# -----------------------------------------------------------------------------
export_csv() {
    start_pg
    echo "==> Exportando Ranking Global para $PROJECT_ROOT/ranking.csv..."
    psql -h "$PG_RUN" -p 5432 -U postgres -d "$DB_NAME" -c "\copy (SELECT * FROM view_ranking_global) TO '$PROJECT_ROOT/ranking.csv' WITH CSV HEADER"
    
    echo "==> Exportando Histórico de Partidas para $PROJECT_ROOT/historico_partidas.csv..."
    psql -h "$PG_RUN" -p 5432 -U postgres -d "$DB_NAME" -c "\copy (SELECT * FROM view_historico_partidas) TO '$PROJECT_ROOT/historico_partidas.csv' WITH CSV HEADER"

    echo "✅ Planilhas CSV geradas com sucesso na raiz do projeto!"
    ls -lh "$PROJECT_ROOT/ranking.csv" "$PROJECT_ROOT/historico_partidas.csv"
}

# -----------------------------------------------------------------------------
# Função: Importar Dados de Partidas a partir de um Arquivo CSV
# -----------------------------------------------------------------------------
import_csv() {
    local CSV_FILE="$1"
    if [ -z "$CSV_FILE" ]; then
        if [ -f "$PROJECT_ROOT/historico_partidas.csv" ]; then
            CSV_FILE="$PROJECT_ROOT/historico_partidas.csv"
        elif [ -f "$PROJECT_ROOT/ranking.csv" ]; then
            CSV_FILE="$PROJECT_ROOT/ranking.csv"
        fi
    fi

    if [ -z "$CSV_FILE" ] || [ ! -f "$CSV_FILE" ]; then
        echo "❌ Erro: Arquivo CSV não encontrado para importação."
        echo "   Uso: $0 import-csv [caminho_da_planilha.csv]"
        exit 1
    fi

    echo "==> Importando dados do CSV $CSV_FILE para o PostgreSQL..."
    python3 "$PROJECT_ROOT/database/db.py" --import-csv "$CSV_FILE"
}

# -----------------------------------------------------------------------------
# Função: Abrir o terminal interativo do PostgreSQL (psql)
# -----------------------------------------------------------------------------
cli_psql() {
    start_pg
    psql -h "$PG_RUN" -p 5432 -U postgres -d "$DB_NAME"
}

# -----------------------------------------------------------------------------
# Menu de Comandos (Interpreta o que você digitou depois do nome do arquivo)
# -----------------------------------------------------------------------------
case "$1" in
    start)
        start_pg
        ;;
    stop)
        stop_pg
        ;;
    setup)
        init_db
        ;;
    reset)
        reset_db "$2"
        ;;
    backup)
        backup_db "$2"
        ;;
    restore)
        restore_db "$2"
        ;;
    ver|planilha|tabelas)
        ver_tabelas
        ;;
    export|csv)
        export_csv
        ;;
    import-csv|importar)
        import_csv "$2"
        ;;
    psql)
        cli_psql
        ;;
    *)
        echo "Comandos disponíveis:"
        echo "  $0 start                -> Liga o banco PostgreSQL"
        echo "  $0 stop                 -> Desliga o banco PostgreSQL"
        echo "  $0 setup                -> Garante tabelas criadas SEM apagar dados existentes"
        echo "  $0 backup [arquivo.sql] -> Gera cópia de segurança completa do banco"
        echo "  $0 restore [arq.sql]    -> Restaura o banco a partir de um backup SQL"
        echo "  $0 reset [senha]        -> Zera o banco (exige senha: admin)"
        echo "  $0 ver                  -> Mostra o Ranking e partidas no terminal"
        echo "  $0 csv                  -> Exporta para planilhas Excel (ranking.csv e historico_partidas.csv)"
        echo "  $0 import-csv [arq.csv] -> Importa partidas a partir de planilha CSV"
        echo "  $0 psql                 -> Abre o terminal interativo do PostgreSQL"
        exit 1
        ;;
esac
