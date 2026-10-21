-- =============================================================================
-- CORNHOLE INTELIGENTE - IFEx 2026
-- Arquivo: database/triggers.sql
-- Função: Funções e Gatilhos (Triggers) em PL/pgSQL para Automação do Banco
-- =============================================================================
-- O QUE SÃO TRIGGERS?
-- Triggers (gatilhos) são robôs programados para rodar sozinhos dentro do banco.
-- Quando o Python insere um novo saquinho, essas triggers entram em ação
-- instantaneamente, calculando os pontos sem que ninguém precise somar na mão.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. TRIGGER: Busca Automática dos Pontos pelo Sensor
-- -----------------------------------------------------------------------------
-- Quando um arremesso chega com 'sensor_codigo = BURACO', esta função vai até
-- a tabela de sensores, descobre que 'BURACO' vale 3 pontos e preenche NEW.pontos = 3.
CREATE OR REPLACE FUNCTION fn_processar_arremesso()
RETURNS TRIGGER AS $$
DECLARE
    v_pontos_sensor INT;
    v_ativo BOOLEAN;
BEGIN
    -- 1. Procura o sensor na tabela de sensores
    SELECT pontos, ativo INTO v_pontos_sensor, v_ativo
    FROM sensores
    WHERE codigo = NEW.sensor_codigo;

    -- Se o sensor não existir, cancela a operação e avisa o erro
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Sensor "%" não cadastrado no sistema!', NEW.sensor_codigo;
    END IF;

    -- Se o sensor estiver desativado por manutenção
    IF NOT v_ativo THEN
        RAISE EXCEPTION 'Sensor "%" está desativado!', NEW.sensor_codigo;
    END IF;

    -- 2. Se a aplicação não passou a pontuação na mão, assume o valor do sensor
    IF NEW.pontos IS NULL THEN
        NEW.pontos := v_pontos_sensor;
    END IF;

    -- Permite que a inserção continue com os pontos preenchidos
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Associa a função acima à tabela 'arremessos' (dispara ANTES de salvar a linha)
DROP TRIGGER IF EXISTS trg_arremesso_before_insert ON arremessos;
CREATE TRIGGER trg_arremesso_before_insert
BEFORE INSERT OR UPDATE OF sensor_codigo ON arremessos
FOR EACH ROW
EXECUTE FUNCTION fn_processar_arremesso();

-- -----------------------------------------------------------------------------
-- 2. TRIGGER: Atualização da Pontuação Total da Rodada
-- -----------------------------------------------------------------------------
-- Sempre que um arremesso é inserido (ou modificado), esta função soma todos
-- os saquinhos daquela partida e atualiza a coluna 'pontuacao_total' na tabela 'partidas'.
CREATE OR REPLACE FUNCTION fn_atualizar_pontuacao_partida()
RETURNS TRIGGER AS $$
DECLARE
    v_partida_id INT;
    v_soma_pontos INT;
BEGIN
    -- Identifica qual é a partida do arremesso (funciona para INSERT, UPDATE ou DELETE)
    v_partida_id := COALESCE(NEW.partida_id, OLD.partida_id);

    -- Soma os pontos de todos os saquinhos já lançados nesta rodada
    SELECT COALESCE(SUM(pontos), 0) INTO v_soma_pontos
    FROM arremessos
    WHERE partida_id = v_partida_id;

    -- Atualiza o placar geral da partida na tabela 'partidas'
    UPDATE partidas
    SET pontuacao_total = v_soma_pontos
    WHERE id = v_partida_id;

    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- Associa a função acima à tabela 'arremessos' (dispara DEPOIS que o saquinho foi salvo)
DROP TRIGGER IF EXISTS trg_atualiza_pontuacao ON arremessos;
CREATE TRIGGER trg_atualiza_pontuacao
AFTER INSERT OR UPDATE OR DELETE ON arremessos
FOR EACH ROW
EXECUTE FUNCTION fn_atualizar_pontuacao_partida();
