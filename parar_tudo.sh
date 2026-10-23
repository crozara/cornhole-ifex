#!/usr/bin/env bash
# =============================================================================
# CORNHOLE INTELIGENTE - IFEx 2026
# Arquivo: parar_tudo.sh
# Função: Script para Encerrar Tudo com Segurança (Servidor Web e Banco de Dados)
# =============================================================================
# Use este script sempre que terminar o evento ou quiser fechar o jogo.
# Ele desliga o servidor web da porta 8080 e encerra o processo do PostgreSQL,
# evitando que fiquem processos 'fantasmas' rodando em segundo plano.
# =============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PG_RUN="${PG_RUN:-$DIR/.pgrun}"

# 1. Encerra o Servidor Web e WebSockets na porta 8080
echo "==> Encerrando Servidor Web na porta 8080..."
fuser -k 8080/tcp 2>/dev/null || pkill -f "backend/server.py" 2>/dev/null || true

# 2. Desliga o PostgreSQL local de forma rápida e segura
echo "==> Encerrando PostgreSQL..."
"$DIR/database/manage_db.sh" stop 2>/dev/null || true

echo "✅ Tudo desligado e memória limpa com sucesso!"
