#include <Wire.h>
#include <Adafruit_VL53L0X.h>
#include <NewPing.h>
#include <HX711.h>

// --- Configurações dos Pinos ---

// Buraco Pequeno:
// Suporta TANTO o Sensor Laser VL53L0X (I2C: SDA / SCL)
// QUANTO o Sensor Infravermelho Digital de Obstáculo comum (Pino Digital 4)
#define PINO_INFRA_DIGITAL 4 // Conecte o pino OUT do sensor infravermelho no Pino 4 (opcional)
Adafruit_VL53L0X lox = Adafruit_VL53L0X();
bool laserDisponivel = false;

// Buraco Médio (Sensor Ultrassônico HC-SR04)
#define TRIGGER_PIN  5
#define ECHO_PIN     6
#define MAX_DISTANCE 40 // Distância máxima em cm
NewPing sonar(TRIGGER_PIN, ECHO_PIN, MAX_DISTANCE);

// Buraco Grande (Célula de Carga HX711)
#define LOADCELL_DOUT_PIN 3
#define LOADCELL_SCK_PIN  2
HX711 scale;
bool balancaDisponivel = false;

// --- Parâmetros de Detecção e Limiares ---
const int LIMIAR_LASER_MM   = 100;   // Acerto se objeto cruzar a menos de 100mm (10cm)
const int LIMIAR_SONAR_CM   = 15;    // Acerto se objeto cruzar a menos de 15cm
const float LIMIAR_PESO_G   = 100.0; // Variação mínima de peso para registrar acerto (g)

// --- Pontuações Oficiais IFEx 2026 ---
const int PONTOS_PEQUENO = 8;
const int PONTOS_MEDIO   = 6;
const int PONTOS_GRANDE  = 4;

// --- Cooldown Independente por Sensor (Debounce de 2.5s) ---
const unsigned long COOLDOWN_MS = 2500;
unsigned long ultimoAcertoPequeno = 0;
unsigned long ultimoAcertoMedio   = 0;
unsigned long ultimoAcertoGrande  = 0;

float ultimoPesoBase = 0.0;

void enviarParaPython(const char* nomeBuraco, int pontos) {
  // Envia JSON formatado diretamente pela Serial com quebra de linha (\n)
  Serial.print("{\"evento\":\"acerto\",\"buraco\":\"");
  Serial.print(nomeBuraco);
  Serial.print("\",\"pontos\":");
  Serial.print(pontos);
  Serial.println("}");
}

void setup() {
  Serial.begin(115200);
  // Aguarda conexão Serial por até 3 segundos (não bloqueia em placas com USB nativo)
  while (!Serial && millis() < 3000) { delay(10); }

  // Configura pino do sensor infravermelho digital (com pull-up interno)
  pinMode(PINO_INFRA_DIGITAL, INPUT_PULLUP);

  // 1. Inicialização segura do VL53L0X (não trava sem o sensor)
  Wire.begin();
  if (lox.begin()) {
    laserDisponivel = true;
    Serial.println("{\"status\":\"info\",\"sensor\":\"VL53L0X_OK\"}");
  } else {
    Serial.println("{\"status\":\"aviso\",\"sensor\":\"VL53L0X_NAO_ENCONTRADO\"}");
  }

  // 2. Inicialização segura do HX711 com timeout de 1 segundo (evita travamento do boot)
  scale.begin(LOADCELL_DOUT_PIN, LOADCELL_SCK_PIN);
  if (scale.wait_ready_timeout(1000)) {
    balancaDisponivel = true;
    // Ajuste o fator de calibração da sua balança:
    // scale.set_scale(2280.f);
    scale.tare();
    ultimoPesoBase = scale.get_units(1);
    Serial.println("{\"status\":\"info\",\"sensor\":\"HX711_OK\"}");
  } else {
    Serial.println("{\"status\":\"aviso\",\"sensor\":\"HX711_NAO_ENCONTRADO\"}");
  }

  Serial.println("{\"evento\":\"boot\",\"status\":\"ARDUINO_ONLINE\",\"versao\":\"2026.1\"}");
}

void loop() {
  unsigned long agora = millis();

  // -------------------------------------------------------------
  // 1. BURACO PEQUENO (Laser VL53L0X ou Infravermelho Digital Pino 4)
  // -------------------------------------------------------------
  if (agora - ultimoAcertoPequeno > COOLDOWN_MS) {
    bool detectouLaser = false;
    if (laserDisponivel) {
      VL53L0X_RangingMeasurementData_t measure;
      lox.rangingTest(&measure, false);
      // RangeStatus == 0 garante leitura válida e estável
      if (measure.RangeStatus == 0 && measure.RangeMilliMeter > 10 && measure.RangeMilliMeter < LIMIAR_LASER_MM) {
        detectouLaser = true;
      }
    }

    // Sensor infravermelho de obstáculo digital (Pino 4: normalmente LOW ao detectar reflexo/objeto)
    bool detectouInfra = (digitalRead(PINO_INFRA_DIGITAL) == LOW);

    if (detectouLaser || detectouInfra) {
      ultimoAcertoPequeno = agora;
      enviarParaPython("pequeno", PONTOS_PEQUENO);
    }
  }

  // -------------------------------------------------------------
  // 2. BURACO MÉDIO (Ultrassônico HC-SR04)
  // -------------------------------------------------------------
  if (agora - ultimoAcertoMedio > COOLDOWN_MS) {
    int distanciaCm = sonar.ping_cm();
    if (distanciaCm > 0 && distanciaCm < LIMIAR_SONAR_CM) {
      ultimoAcertoMedio = agora;
      enviarParaPython("medio", PONTOS_MEDIO);
    }
  }

  // -------------------------------------------------------------
  // 3. BURACO GRANDE (Célula de Carga HX711)
  // -------------------------------------------------------------
  if (balancaDisponivel && (agora - ultimoAcertoGrande > COOLDOWN_MS)) {
    if (scale.is_ready()) {
      float pesoLeitura = scale.get_units(1);
      // Detecta aumento relativo de peso (suporta múltiplos sacos acumulados na rede)
      if ((pesoLeitura - ultimoPesoBase) > LIMIAR_PESO_G) {
        ultimoAcertoGrande = agora;
        ultimoPesoBase = pesoLeitura; // Atualiza a base para o próximo arremesso
        enviarParaPython("grande", PONTOS_GRANDE);
      } else if (pesoLeitura < ultimoPesoBase - 50.0) {
        // Se os sacos forem retirados do buraco, reseta a base
        ultimoPesoBase = pesoLeitura;
      }
    }
  }

  delay(20);
}