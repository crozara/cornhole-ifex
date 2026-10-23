# 🎯 Cornhole Inteligente — IFEx

Um jogo de **Cornhole (arremesso de saquinhos)** gamificado estilo *arcade/fliperama*. Os arremessos são detectados por sensores conectados ao Arduino, a pontuação é computada automaticamente em tempo real e um **Dashboard Web Arcade** exibe o placar neon, cronômetro de precisão e o **Ranking Global do IFEx** na tela do notebook voltada para o público.

---

## 🏗️ Arquitetura do Sistema

O projeto integra **hardware**, **comunicação serial**, **banco de dados relacional** e **front-end em tempo real**:

```
[ ARDUINO / SENSORES ] ──(USB / Serial)──> [ BACKEND PYTHON (server.py) ]
                                                   │
                         ┌─────────────────────────┴────────────────────────┐
                         ▼                                                  ▼
               [ POSTGRESQL 16 ]                               [ DASHBOARD WEB ARCADE ]
     • Triggers automáticas de pontuação              • Cronômetro de precisão (60 FPS)
     • Desempate analítico por tempo                  • Placar neon gigante & sons 8-bit
     • View com filtro da melhor rodada               • Ranking Global Top 10 em tempo real
```

---

## 🕹️ Dinâmica de Jogo & Regras

1. **Cadastro do Jogador:** O operador pressiona a tecla **`[O]`** e cadastra o competidor (nome e turma).
2. **Início da Rodada:** O jogador se posiciona e aperta a barra de **`[ESPAÇO]`**. O cronômetro gigante dispara e os LEDs acendem.
3. **Durante os Arremessos:** Conforme os saquinhos caem, os pontos sobem na tela com sons de fliperama:
   * **Buraco Pequeno (`pontosPequeno`):** `+8 pontos`
   * **Buraco Médio (`pontosMedio`):** `+6 pontos`
   * **Buraco Grande (`pontosGrande`):** `+4 pontos`
   * **Fora:** `0 pontos`
4. **Finalização Automática:** Ao registrar o **5º arremesso**, o cronômetro **trava imediatamente no exato milissegundo** do último impacto, os dados são persistidos no PostgreSQL e o Ranking Global é atualizado com a fanfarra de vitória!
   * Não é necessário apertar nenhum botão para encerrar a jogada;
   * O competidor pressiona **`[ESPAÇO]`** na tela de vitória apenas para limpar o placar para o próximo jogador;
   * Caso o competidor queira desistir ou encerrar antes dos 5 arremessos, a tecla **`[ESPAÇO]`** ainda funciona como parada manual antecipada.

---

## 🤖 Hardware e Firmware (Arduino)

O arquivo `arduino/main.ino` é responsável por monitorar os sensores físicos da prancha em tempo real e enviar os eventos de pontuação para o computador via porta Serial USB (`115200 bps`).

### 1. Sensores e Mapeamento de Pinos

| Alvo / Buraco | Sensor Utilizado | Pinos no Arduino | Limiar de Detecção | Constante (`main.ino`) | Pontuação |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **Buraco Pequeno** | Laser ToF `VL53L0X` | Barramento `I2C` (`SDA` / `SCL`) | `< 100 mm` (`LIMIAR_LASER_MM`) | `pontosPequeno` | `8 pts` |
| **Buraco Médio** | Ultrassônico `HC-SR04` | `TRIGGER`: Pino `5` / `ECHO`: Pino `6` | `< 15 cm` (`LIMIAR_SONAR_CM`) | `pontosMedio` | `6 pts` |
| **Buraco Grande** | Célula de Carga `HX711` | `DOUT`: Pino `3` / `SCK`: Pino `2` | `> 100.0 g` (`LIMIAR_PESO_G`) | `pontosGrande` | `4 pts` |

* **Bibliotecas necessárias na Arduino IDE:** `Wire.h`, `Adafruit_VL53L0X`, `NewPing`, `HX711` e `ArduinoJson` (v7).

### 2. Controle de Status e Tempo de Retirada (`tempoDeEspera`)

Como no Cornhole o saquinho pode permanecer sobre o sensor ou exigir que o jogador coloque a mão para retirá-lo, o firmware implementa uma máquina de estados com um tempo de retirada configurável (`tempoDeEspera = 3.0` segundos):

* **`LIVRE`:** Estado inicial em que nenhum sensor detecta objetos e o tempo de espera já expirou. Assim que qualquer sensor detecta um saquinho, o ponto correspondente é computado **uma única vez**, enviado via Serial em JSON (`{"evento":"acerto","buraco":"...","pontos":...}`) e o status muda imediatamente para **`DETECTADO`**.
* **`DETECTADO`:** Enquanto o saquinho (ou a mão do jogador) permanecer na área de leitura de qualquer sensor, o sistema mantém o status **`DETECTADO`** e bloqueia novas pontuações.
* **`ESPERANDO`:** No exato momento em que o objeto é retirado (todos os sensores livres), o sistema entra no status **`ESPERANDO`** e inicia a contagem regressiva de `tempoDeEspera` segundos (`3.0s`).
  * Durante **`ESPERANDO`**, **nenhum ponto é computado**.
  * Caso qualquer objeto seja detectado novamente enquanto estiver em **`ESPERANDO`** (por exemplo, o jogador esbarrando no sensor ao puxar o saquinho), **nenhum ponto é marcado**, o status retorna para **`DETECTADO`** e, quando o objeto for retirado outra vez, o tempo de espera é **reiniciado em 100%** (terá que aguardar os `3.0` segundos completos novamente).
  * Após transcorrerem os `tempoDeEspera` segundos ininterruptos sem detecções, o sistema retorna ao status **`LIVRE`** para o próximo lançamento.

---

## 🗄️ A Engenharia de Banco de Dados (PostgreSQL 16)

Como parte dos estudos avançados de banco de dados, as regras de negócio foram implementadas nativamente no PostgreSQL:

* **Triggers em PL/pgSQL:** Ao registrar um arremesso na tabela `arremessos`, uma trigger busca o valor do sensor na tabela `sensores` e outra trigger recalcula automaticamente o `pontuacao_total` na tabela `partidas`.
* **Critério de Desempate (A sacada do BD):** Em caso de empate de pontos, o PostgreSQL desempata ordenando pelo **menor tempo de execução da rodada** (`tempo_ms ASC`).
* **Deduplicação de Jogador:** A view analítica utiliza Funções de Janela (`ROW_NUMBER() OVER (PARTITION BY jogador_id ORDER BY pontuacao_total DESC, tempo_ms ASC)`) para garantir que **apenas a melhor tentativa de cada competidor** entre no Top 10, mesmo se a mesma pessoa jogar várias vezes.

---

## 📋 Pré-requisitos & Instalação

Para rodar este projeto em uma máquina Linux (Ubuntu / Debian / Raspberry Pi OS):

### 1. Pacotes do Sistema (PostgreSQL & Utilitários)
```bash
sudo apt update
sudo apt install -y python3 python3-pip postgresql postgresql-contrib psmisc
```

> **Nota para o Arduino:** Para que o Python consiga ler a porta USB (`/dev/ttyACM0` ou `/dev/ttyUSB0`) sem precisar de `sudo`, adicione seu usuário ao grupo de comunicação serial:
> ```bash
> sudo usermod -a -G dialout $USER
> ```
> *(Faça logoff e logon novamente para aplicar).*

### 2. Dependências do Python
Instale os pacotes necessários através do `requirements.txt`:
```bash
pip install -r requirements.txt
```
*(Ou instale via apt no Ubuntu: `sudo apt install python3-websockets python3-serial`)*

---

## 🚀 Como Executar o Projeto

### 1. Iniciar Tudo (PostgreSQL + Servidor Web)
No terminal do projeto (ou no terminal integrado do VS Code), execute:

```bash
./run_arcade.sh
```

Esse comando inicializa o PostgreSQL local e sobe o servidor web na porta `8080`.

### 2. Acessar o Jogo
Abra o navegador no notebook e acesse:
👉 **[http://localhost:8080](http://localhost:8080)**

> **Dica de Evento:** Pressione **`F11`** no navegador para colocar em tela cheia (modo arcade para o público).

### 3. Encerrar Tudo
Quando terminar o evento ou os testes, execute:

```bash
./parar_tudo.sh
```

---

## ⌨️ Controles e Atalhos do Teclado

| Tecla | Momento | Função |
| :---: | :--- | :--- |
| **`[ESPAÇO]`** | Antes de jogar | **Dispara o cronômetro** e inicia a rodada |
| **`5º Arremesso`** | Durante a rodada | **Trava o cronômetro automaticamente**, salva no PostgreSQL e atualiza o ranking |
| **`[ESPAÇO]`** | Durante a rodada | Parada manual antecipada (caso não vá arremessar os 5 saquinhos) |
| **`[ESPAÇO]`** | Na tela de resultado | **Limpa a tela** e prepara para o próximo competidor da fila |
| **`[O]`** | A qualquer momento | **Abre o Painel do Operador** para cadastrar ou escolher jogadores |
| **`[B]`** | A qualquer momento | *(Simulador)* Acerto no **Buraco (+3 pts)** |
| **`[P]`** | A qualquer momento | *(Simulador)* Acerto na **Prancha (+1 pt)** |
| **`[F]`** | A qualquer momento | *(Simulador)* Saquinho **Fora (0 pts)** |
| **`[R]`** | A qualquer momento | Reseta o display para a tela de espera |

---

## 📊 Visualização de Dados e Planilhas no Back-end

Você não precisa abrir a web para auditar ou ver os resultados:

* **Ver tabelas formatadas no terminal:**
  ```bash
  ./database/manage_db.sh ver
  ```
* **Exportar para arquivos Excel / Calc (`.csv`):**
  ```bash
  ./database/manage_db.sh csv
  ```
  *Gera os arquivos `ranking.csv` e `historico_partidas.csv` na raiz do projeto.*
* **Abrir o terminal interativo do PostgreSQL (`psql`):**
  ```bash
  ./database/manage_db.sh psql
  ```

---

## 📁 Estrutura do Repositório

```text
ifex/
├── arduino/
│   └── main.ino            # Firmware do Arduino (leitura de sensores e tempo de retirada)
├── backend/
│   ├── game_manager.py     # Máquina de estados, cronômetro de precisão e pontuação
│   ├── serial_handler.py   # Leitura serial do Arduino (USB) e modo simulador
│   └── server.py           # Servidor assíncrono HTTP e WebSockets (/ws)
├── database/
│   ├── db.py               # Camada de persistência Python com PostgreSQL
│   ├── manage_db.sh        # Utilitário CLI (ligar/parar banco, ver tabelas, exportar CSV)
│   ├── schema.sql          # DDL das tabelas (jogadores, partidas, arremessos, sensores)
│   ├── triggers.sql        # Funções PL/pgSQL e triggers de atualização automática
│   └── views.sql           # Views analíticas de Ranking Global com desempate
├── frontend/
│   ├── app.js              # Cliente WebSocket, controle do cronômetro (60fps) e atalhos
│   ├── audio.js            # Sintetizador Web Audio API de efeitos sonoros 8-bit
│   ├── index.html          # Dashboard visual com placar neon e ranking do IFEx
│   └── style.css           # Estilização arcade cyberpunk retrô
├── run_arcade.sh           # Script de inicialização completa
├── parar_tudo.sh           # Script de encerramento seguro
└── README.md               # Documentação técnica e operacional do projeto
```

---

## 🛠️ Tecnologias Utilizadas

* **Hardware & Firmware:** Arduino (C/C++), Sensores `VL53L0X` (Laser I2C), `HC-SR04` (Ultrassônico) e `HX711` (Célula de Carga)
* **Linguagem Back-end:** Python 3.12
* **Tempo Real:** WebSockets (protocolo `ws://`)
* **Banco de Dados:** PostgreSQL 16
* **Comunicação de Hardware:** PySerial / Porta Serial USB (`115200 bps`)
* **Front-end:** HTML5, CSS3 Moderno, JavaScript ES6+
* **Áudio:** Web Audio API (Sintetizador 8-bit nativo)
