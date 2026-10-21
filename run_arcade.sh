#!/usr/bin/env bash
# =============================================================================
# CORNHOLE INTELIGENTE - IFEx 2026
# Arquivo: run_arcade.sh
# Função: Script Mestre de Inicialização (Lança o Sistema Completo)
# =============================================================================
# O QUE ESTE SCRIPT FAZ?
# 1. Inicia o banco de dados PostgreSQL 16 no diretório local.
# 2. Garante que as tabelas, triggers e views estejam configuradas.
# 3. Limpa a porta 8080 se ela tiver ficado presa por uma execução anterior.
# 4. Inicia o Servidor Python (Web + WebSockets) e conecta ao Arduino.
# =============================================================================

# 'set -e' interrompe o script imediatamente se qualquer comando falhar
set -e

# Descobre a pasta onde o projeto está localizado no computador
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$DIR:$PYTHONPATH"

echo "=========================================================="
echo "🎯 INICIANDO O CORNHOLE INTELIGENTE - IFEx"
echo "=========================================================="

# 1. Garante que o PostgreSQL local está ligado e pronto para receber dados
"$DIR/database/manage_db.sh" start

# 2. Cria as tabelas e regras do jogo no banco (se ainda não existirem)
"$DIR/database/manage_db.sh" setup >/dev/null 2>&1 || true

# 3. Libera as portas caso algum processo anterior tenha ficado aberto em segundo plano
echo "==> Verificando e liberando processos anteriores..."
fuser -k -9 8080/tcp >/dev/null 2>&1 || true
fuser -k -9 8081/tcp >/dev/null 2>&1 || true
pkill -9 -f "backend/server.py" >/dev/null 2>&1 || true
sleep 0.4

# 4. Executa o servidor Python central (mantém o terminal aberto exibindo logs)
echo "==> Iniciando Servidor Web e WebSocket..."
exec python3 "$DIR/backend/server.py"
