-- =============================================================================
-- CORNHOLE INTELIGENTE - IFEx 2026
-- Arquivo: database/views.sql
-- Função: Views Analíticas para Ranking Global com Desempate e Relatórios
-- =============================================================================
-- O QUE É UMA VIEW?
-- Uma View é uma consulta SQL salva dentro do banco que funciona como uma
-- "tabela virtual". Toda vez que alguém consulta 'view_ranking_global', o
-- PostgreSQL roda esta fórmula em milissegundos e entrega os dados atualizados.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. VIEW DO RANKING GLOBAL (Critério Oficial do IFEx)
-- -----------------------------------------------------------------------------
-- Regras de Negócio Implementadas nesta Consulta:
--   1. Deduplicação: se o mesmo competidor jogou 5 vezes, apenas a sua MELHOR
--      partida entra no ranking (usando PARTITION BY jogador_id).
--   2. Critério 1: Maior pontuação total (DESC) - quem fez mais pontos fica na frente.
--   3. Critério 2 (Desempate): Menor tempo em milissegundos (tempo_ms ASC).
--   4. Formatação: Já converte milissegundos para o formato digital bonito (MM:SS.MS).
-- =============================================================================
CREATE OR REPLACE VIEW view_ranking_global AS
WITH melhor_partida_por_jogador AS (
    -- Etapa 1: Numera as partidas de cada jogador da melhor para a pior
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
                p.pontuacao_total DESC,        -- Maior pontuação primeiro
                p.tempo_ms ASC NULLS LAST,     -- Menor tempo desempata
                p.finalizada_em ASC            -- Se empatar até no tempo, quem jogou primeiro leva
        ) AS ranking_pessoal
    FROM partidas p
    WHERE p.status = 'finalizada'
)
-- Etapa 2: Pega apenas a melhor tentativa de cada um (ranking_pessoal = 1) e monta o ranking geral
SELECT 
    DENSE_RANK() OVER (
        ORDER BY 
            m.pontuacao_total DESC, 
            m.tempo_ms ASC NULLS LAST, 
            m.finalizada_em ASC
    ) AS posicao,                               -- 1º, 2º, 3º lugar geral
    j.id AS jogador_id,
    j.nome AS nome_jogador,
    COALESCE(j.apelido, 'Anônimo') AS apelido_jogador,
    m.partida_id,
    m.pontuacao_total,
    m.tempo_ms,
    ROUND(m.tempo_ms / 1000.0, 2) AS tempo_segundos, -- Ex: 14.32 segundos
    TO_CHAR(
        INTERVAL '1 millisecond' * m.tempo_ms, 
        'MI:SS.MS'
    ) AS tempo_formatado,                       -- Ex: "00:14.320" para a tela do fliperama
    m.finalizada_em
FROM melhor_partida_por_jogador m
JOIN jogadores j ON m.jogador_id = j.id
WHERE m.ranking_pessoal = 1                     -- Filtra apenas a melhor rodada de cada pessoa
ORDER BY posicao ASC;

-- -----------------------------------------------------------------------------
-- 2. VIEW DE HISTÓRICO COMPLETO (Auditoria e Relatório em Planilha)
-- -----------------------------------------------------------------------------
-- Agrupa todas as partidas e contabiliza os arremessos nos buracos, prancha e fora.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW view_historico_partidas AS
SELECT 
    p.id AS partida_id,
    j.id AS jogador_id,
    j.nome AS nome_jogador,
    j.apelido AS apelido_jogador,
    p.status,
    p.pontuacao_total,
    ROUND(p.tempo_ms / 1000.0, 2) AS tempo_segundos,
    p.iniciada_em,
    p.finalizada_em,
    COUNT(a.id) AS total_saquinhos_computados,
    -- Contagem condicional por tipo de acerto usando o recurso FILTER do PostgreSQL
    COUNT(a.id) FILTER (WHERE a.sensor_codigo IN ('PEQUENO', 'MEDIO', 'GRANDE', 'BURACO')) AS saquinhos_buraco,
    COUNT(a.id) FILTER (WHERE a.sensor_codigo = 'PRANCHA') AS saquinhos_prancha,
    COUNT(a.id) FILTER (WHERE a.sensor_codigo = 'FORA') AS saquinhos_fora
FROM partidas p
JOIN jogadores j ON p.jogador_id = j.id
LEFT JOIN arremessos a ON p.id = a.partida_id
GROUP BY p.id, j.id, j.nome, j.apelido, p.status, p.pontuacao_total, p.tempo_ms, p.iniciada_em, p.finalizada_em
ORDER BY p.iniciada_em DESC;
