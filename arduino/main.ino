#include <Wire.h>
#include <Adafruit_VL53L0X.h>
#include <NewPing.h>
#include <HX711.h>
#include <ArduinoJson.h>

// --- Configurações dos Pinos ---

// Buraco Pequeno:
// Suporta TANTO o Sensor Laser VL53L0X (I2C: SDA / SCL)
// QUANTO o Sensor Infravermelho Digital de Obstáculo comum (Pino Digital 4)
#define PINO_INFRA_DIGITAL 4 // Conecte o pino OUT do sensor infravermelho no Pino 4 (opcional)
Adafruit_VL53L0X lox = Adafruit_VL53L0X();
bool loxAtivo = false;

// Buraco Médio (Sensor Ultrassônico HC-SR04)
#define TRIGGER_PIN  5
#define ECHO_PIN     6
#define MAX_DISTANCE 40 // Distância máxima de leitura em cm
NewPing sonar(TRIGGER_PIN, ECHO_PIN, MAX_DISTANCE);

// Buraco Grande (Célula de Carga HX711)
#define LOADCELL_DOUT_PIN 3
#define LOADCELL_SCK_PIN  2
HX711 scale;

// --- Parâmetros de Detecção ---
// Ajuste esses valores de acordo com a mecânica física da sua mesa
const int LIMIAR_LASER_MM   = 100; // Dispara se algo passar a menos de 100mm
const int LIMIAR_SONAR_CM   = 15;  // Dispara se algo passar a menos de 15cm
const float LIMIAR_PESO_G   = 100.0; // Peso mínimo para registrar (sacos costumam ter ~400g)

// --- Constantes de Pontuação ---
const int pontosPequeno = 8;
const int pontosMedio   = 6;
const int pontosGrande  = 4;

// --- Variáveis de Controle (Debounce/Cooldown e Tempo de Retirada) ---
// Evita que a mesma sacola registre vários pontos enquanto atravessa o buraco ou é retirada
float tempoDeEspera = 2.0;          // Tempo de espera em segundos após retirar o objeto (otimizado para 2s)
String status = "LIVRE";            // Estados do sistema: "LIVRE", "DETECTADO", "ESPERANDO"
unsigned long inicioEspera = 0;     // Marca o momento (em ms) em que o objeto foi retirado
float pesoAtual = 0.0;              // Mantém a última leitura válida da célula de carga

void setup() {
  // Baud rate alto para sincronização com Python
  Serial.begin(115200);
  while (!Serial && millis() < 3000) { delay(10); }

  // Configura pino do sensor infravermelho digital (com pull-up interno)
  pinMode(PINO_INFRA_DIGITAL, INPUT_PULLUP);

  // 1. Inicializa Sensor Laser VL53L0X (I2C)
  loxAtivo = lox.begin();
  if (!loxAtivo) {
    Serial.println("{\"aviso\": \"VL53L0X nao encontrado no I2C (verifique se SDA=A4 e SCL=A5)\"}");
  } else {
    Serial.println("{\"info\": \"VL53L0X laser inicializado com sucesso\"}");
  }

  // 2. Inicializa Célula de Carga HX711 (protegido para NÃO travar se a célula não estiver conectada)
  scale.begin(LOADCELL_DOUT_PIN, LOADCELL_SCK_PIN);
  if (scale.is_ready() || scale.wait_ready_timeout(500)) {
    scale.tare(); // Zera a balança na inicialização
    Serial.println("{\"info\": \"HX711 tarado com sucesso\"}");
  } else {
    Serial.println("{\"info\": \"HX711 nao conectado no momento (ignorado para nao travar)\"}");
  }

  Serial.println("{\"evento\":\"boot\",\"status\":\"ARDUINO_ONLINE\",\"versao\":\"2026.1\"}");
}

void loop() {
  unsigned long tempoAtual = millis();
  
  bool pontoMarcado = false;
  String buraco = "";
  int pontuacao = 0;

  // --- LEITURA BURACO PEQUENO (VL53L0X Laser ToF ou Infravermelho Digital) ---
  bool detectouLaser = false;
  if (loxAtivo) {
    VL53L0X_RangingMeasurementData_t measure;
    lox.rangingTest(&measure, false);
    if (measure.RangeStatus != 4 && measure.RangeMilliMeter > 0 && measure.RangeMilliMeter < LIMIAR_LASER_MM) {
      detectouLaser = true;
    }
  }

  // Sensor infravermelho de obstáculo digital (Pino 4: normalmente LOW ao detectar reflexo/objeto)
  bool detectouInfraDigital = (digitalRead(PINO_INFRA_DIGITAL) == LOW);

  bool detectouPequeno = detectouLaser || detectouInfraDigital;

  // --- LEITURA BURACO MÉDIO (Ultrassônico) ---
  int distanciaCm = sonar.ping_cm();
  bool detectouMedio = (distanciaCm > 0 && distanciaCm < LIMIAR_SONAR_CM);

  // --- LEITURA BURACO GRANDE (Célula de Carga) ---
  if (scale.is_ready()) {
    // Passar "1" no get_units evita que a biblioteca bloqueie o código tirando médias longas
    pesoAtual = scale.get_units(1); 
  }
  bool detectouGrande = (pesoAtual > LIMIAR_PESO_G);

  // Verifica se algum dos sensores está detectando um objeto no momento
  bool objetoDetectado = detectouPequeno || detectouMedio || detectouGrande;

  // --- CONTROLE DE STATUS E PONTUAÇÃO (TEMPO DE RETIRADA) ---
  if (objetoDetectado) {
    if (status == "LIVRE") {
      // Computa o ponto apenas quando o sistema estava livre (sem objeto e fora do tempo de espera)
      if (detectouPequeno) {
        buraco = "pequeno";
        pontuacao = pontosPequeno;
      } else if (detectouMedio) {
        buraco = "medio";
        pontuacao = pontosMedio;
      } else if (detectouGrande) {
        buraco = "grande";
        pontuacao = pontosGrande;
        
        // Se os sacos caírem em uma rede e ficarem acumulados, 
        // comente a linha abaixo. Se eles caírem no chão e a balança esvaziar, 
        // ou se você quiser zerar o peso base sempre, pode deixar ativado.
        // scale.tare(); 
      }
      pontoMarcado = true;
      status = "DETECTADO";
    } else if (status == "ESPERANDO") {
      // Se um objeto for detectado durante a espera, nenhum ponto é computado
      // e o status volta para DETECTADO (o que fará o tempo de espera voltar a 100% ao retirar)
      status = "DETECTADO";
    }
  } else {
    // Nenhum sensor está detectando objeto no momento
    if (status == "DETECTADO") {
      // Assim que o objeto é retirado, entra em ESPERANDO e reinicia a contagem (100% de tempoDeEspera)
      status = "ESPERANDO";
      inicioEspera = tempoAtual;
    } else if (status == "ESPERANDO") {
      // Aguarda tempoDeEspera segundos (convertido para milissegundos) sem detecções para liberar o sistema
      if (tempoAtual - inicioEspera >= (unsigned long)(tempoDeEspera * 1000.0)) {
        status = "LIVRE";
      }
    }
  }

  // --- ENVIO DOS DADOS PARA O PYTHON ---
  if (pontoMarcado) {
    enviarParaPython(buraco, pontuacao);
  }

  delay(20); // Pequeno atraso para estabilidade do loop e do I2C
}

// Função para empacotar e enviar o JSON
void enviarParaPython(String nomeBuraco, int pontos) {
  // Criação do documento JSON (sintaxe do ArduinoJson v7)
  JsonDocument doc;
  
  doc["evento"] = "acerto";
  doc["buraco"] = nomeBuraco;
  doc["pontos"] = pontos;
  
  // Envia pela porta Serial. Vai imprimir algo como: 
  // {"evento":"acerto","buraco":"pequeno","pontos":8}
  serializeJson(doc, Serial);
  Serial.println(); // O '\n' final é vital para o Python usar .readline()
}
