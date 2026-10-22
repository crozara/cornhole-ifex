#include <Wire.h>
#include <Adafruit_VL53L0X.h>
#include <NewPing.h>
#include <HX711.h>
#include <ArduinoJson.h>

// --- Configurações dos Pinos ---

// Buraco Pequeno (Sensor Laser VL53L0X usa I2C: pinos SDA e SCL)
Adafruit_VL53L0X lox = Adafruit_VL53L0X();

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

// --- Variáveis de Controle (Debounce/Cooldown) ---
// Evita que a mesma sacola registre vários pontos enquanto atravessa o buraco
const unsigned long TEMPO_COOLDOWN_MS = 2000; // 2 segundos de intervalo por buraco
unsigned long ultimoAcertoPequeno = 0;
unsigned long ultimoAcertoMedio   = 0;
unsigned long ultimoAcertoGrande  = 0;

void setup() {
  // Baud rate alto para minimizar atraso na comunicação serial
  Serial.begin(115200);
  while (!Serial) { delay(1); }

  // 1. Inicializa Sensor Laser
  if (!lox.begin()) {
    // Em produção, você pode disparar um JSON de erro aqui
    // Serial.println("{\"erro\": \"VL53L0X nao encontrado\"}");
  }

  // 2. Inicializa Célula de Carga
  scale.begin(LOADCELL_DOUT_PIN, LOADCELL_SCK_PIN);
  // IMPORTANTE: Insira seu fator de calibração obtido previamente
  // scale.set_scale(2280.f); 
  scale.tare(); // Zera a balança na inicialização
}

void loop() {
  unsigned long tempoAtual = millis();
  
  bool pontoMarcado = false;
  String buraco = "";
  int pontuacao = 0;

  // --- LEITURA BURACO PEQUENO (VL53L0X) ---
  VL53L0X_RangingMeasurementData_t measure;
  lox.rangingTest(&measure, false);
  
  // Se o status for diferente de 4 (Out of Range) e a distância cruzar o limiar
  if (measure.RangeStatus != 4 && measure.RangeMilliMeter < LIMIAR_LASER_MM) {
    if (tempoAtual - ultimoAcertoPequeno > TEMPO_COOLDOWN_MS) {
      buraco = "pequeno";
      pontuacao = 50;
      ultimoAcertoPequeno = tempoAtual;
      pontoMarcado = true;
    }
  }

  // --- LEITURA BURACO MÉDIO (Ultrassônico) ---
  if (!pontoMarcado) { // Evita sobreposição no mesmo ciclo
    int distanciaCm = sonar.ping_cm();
    if (distanciaCm > 0 && distanciaCm < LIMIAR_SONAR_CM) {
      if (tempoAtual - ultimoAcertoMedio > TEMPO_COOLDOWN_MS) {
        buraco = "medio";
        pontuacao = 30;
        ultimoAcertoMedio = tempoAtual;
        pontoMarcado = true;
      }
    }
  }

  // --- LEITURA BURACO GRANDE (Célula de Carga) ---
  if (!pontoMarcado) {
    if (scale.is_ready()) {
      // Passar "1" no get_units evita que a biblioteca bloqueie o código tirando médias longas
      float pesoAtual = scale.get_units(1); 
      
      if (pesoAtual > LIMIAR_PESO_G) {
        if (tempoAtual - ultimoAcertoGrande > TEMPO_COOLDOWN_MS) {
          buraco = "grande";
          pontuacao = 10;
          ultimoAcertoGrande = tempoAtual;
          pontoMarcado = true;
          
          // Se os sacos caírem em uma rede e ficarem acumulados, 
          // comente a linha abaixo. Se eles caírem no chão e a balança esvaziar, 
          // ou se você quiser zerar o peso base sempre, pode deixar ativado.
          // scale.tare(); 
        }
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
  // {"evento":"acerto","buraco":"pequeno","pontos":50}
  serializeJson(doc, Serial);
  Serial.println(); // O '\n' final é vital para o Python usar .readline()
}
