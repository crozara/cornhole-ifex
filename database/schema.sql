-- =============================================================================
-- CORNHOLE INTELIGENTE - IFEx 2026
-- Arquivo: database/schema.sql
-- Função: Criação das 4 Tabelas Relacionais, Chaves Estrangeiras e Índices
-- =============================================================================
-- Este arquivo define como os dados são guardados no PostgreSQL 16:
-- 1. jogadores: quem está competindo (nome, turma/curso).
-- 2. sensores: regras de pontuação dos 5 casos:
--    - PEQUENO = +8 pontos
--    - MEDIO   = +6 pontos
--    - GRANDE  = +4 pontos
--    - PRANCHA =  0 ponto
--    - FORA    = -4 pontos
-- 3. partidas: cada rodada jogada, seu tempo total e status.
-- 4. arremessos: o detalhe lance a lance dos 5 saquinhos jogados na rodada.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. TABELA DE JOGADORES (Competidores do IFEx)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS jogadores (
    id SERIAL PRIMARY KEY,                          -- Número de identificação único (auto-incremental)
    nome VARCHAR(100) NOT NULL,                     -- Nome completo ou de exibição do competidor
    apelido VARCHAR(50),                            -- Turma, curso ou gamertag (ex: "Info 3A", "Mecatrônica")
    criado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP -- Data e hora exata do cadastro
);

-- -----------------------------------------------------------------------------
-- 2. TABELA DE SENSORES (Mapeamento de Pontuação dos 5 Casos)
-- -----------------------------------------------------------------------------
-- Permite mudar a pontuação ou adicionar novos sensores sem precisar alterar código!
CREATE TABLE IF NOT EXISTS sensores (
    codigo VARCHAR(30) PRIMARY KEY,                 -- Código de texto (ex: 'PEQUENO', 'MEDIO', 'GRANDE', 'PRANCHA', 'FORA')
    pontos INT NOT NULL,                            -- Quantos pontos esse caso vale (pode ser positivo, zero ou negativo)
    descricao VARCHAR(100),                         -- Explicação humana do sensor
    ativo BOOLEAN NOT NULL DEFAULT TRUE             -- Permite desativar um sensor sem deletar o histórico
);

-- Remove restrição antiga de pontos >= 0 caso o banco já exista de versões anteriores
ALTER TABLE sensores DROP CONSTRAINT IF EXISTS sensores_pontos_check;

-- Inserção segura das regras oficiais dos 5 casos (não duplica nem apaga no reinício)
INSERT INTO sensores (codigo, pontos, descricao) VALUES
    ('PEQUENO', 8, '1. Buraco pequeno (+8 pontos)'),
    ('MEDIO', 6, '2. Buraco médio (+6 pontos)'),
    ('GRANDE', 4, '3. Buraco grande (+4 pontos)'),
    ('PRANCHA', 0, '4. Prancha (0 ponto)'),
    ('FORA', -4, '5. Fora (-4 pontos)'),
    ('BURACO', 8, 'Alias compatível para buraco pequeno (+8 pontos)')
ON CONFLICT (codigo) DO UPDATE 
SET pontos = EXCLUDED.pontos, descricao = EXCLUDED.descricao;

-- -----------------------------------------------------------------------------
-- 3. TABELA DE PARTIDAS (Cada rodada de jogo disputada)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS partidas (
    id SERIAL PRIMARY KEY,                          -- ID único da partida
    jogador_id INT NOT NULL REFERENCES jogadores(id) ON DELETE CASCADE, -- Vincula ao competidor que jogou
    status VARCHAR(20) NOT NULL DEFAULT 'em_andamento'
        CHECK (status IN ('em_andamento', 'finalizada', 'cancelada')), -- Garante apenas status válidos
    pontuacao_total INT NOT NULL DEFAULT 0,         -- Total de pontos (somado via Trigger, pode ser negativo)
    tempo_ms INT CHECK (tempo_ms IS NULL OR tempo_ms >= 0),              -- Tempo total da rodada em milissegundos
    iniciada_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,         -- Momento exato da largada
    finalizada_em TIMESTAMPTZ                                           -- Momento em que o cronômetro travou
);

-- Remove restrição antiga de pontuacao_total >= 0 caso o banco já exista
ALTER TABLE partidas DROP CONSTRAINT IF EXISTS partidas_pontuacao_total_check;

-- Índice para deixar a busca de partidas por jogador instantânea
CREATE INDEX IF NOT EXISTS idx_partidas_jogador ON partidas(jogador_id);

-- Índice especial para o Ranking: já deixa as partidas finalizadas pré-ordenadas por pontos e tempo
CREATE INDEX IF NOT EXISTS idx_partidas_ranking ON partidas (pontuacao_total DESC, tempo_ms ASC)
WHERE status = 'finalizada';

-- -----------------------------------------------------------------------------
-- 4. TABELA DE ARREMESSOS (Detalhamento dos 5 saquinhos lançados)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS arremessos (
    id SERIAL PRIMARY KEY,                          -- ID único do arremesso
    partida_id INT NOT NULL REFERENCES partidas(id) ON DELETE CASCADE, -- Qual partida esse arremesso pertence
    numero_saquinho INT NOT NULL CHECK (numero_saquinho BETWEEN 1 AND 5), -- Número do saquinho (1 ao 5)
    sensor_codigo VARCHAR(30) NOT NULL REFERENCES sensores(codigo),      -- Onde o saquinho caiu
    pontos INT NOT NULL,                            -- Pontos gerados (positivo, 0 ou negativo)
    tempo_parcial_ms INT CHECK (tempo_parcial_ms IS NULL OR tempo_parcial_ms >= 0), -- Tempo do arremesso
    registrado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Regra de integridade: em uma mesma rodada, só pode existir um saquinho número 1, número 2, etc.
    CONSTRAINT uq_partida_saquinho UNIQUE (partida_id, numero_saquinho)
);

-- Remove restrição antiga de pontos >= 0 caso o banco já exista
ALTER TABLE arremessos DROP CONSTRAINT IF EXISTS arremessos_pontos_check;

-- Índice para consultar rapidamente todos os 5 arremessos de qualquer partida
CREATE INDEX IF NOT EXISTS idx_arremessos_partida ON arremessos(partida_id);
