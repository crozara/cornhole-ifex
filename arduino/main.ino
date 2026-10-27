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

// --- Calibração e Parâmetros de Detecção ---
float fatorCalibracao       = 84.0;  // Fator de conversão para gramas
const int LIMIAR_LASER_MM   = 100;   // Acerto se objeto cruzar a menos de 100mm (10cm)
const int LIMIAR_SONAR_CM   = 15;    // Acerto se objeto cruzar a menos de 15cm
const float LIMIAR_PESO_G   = 45.0;  // Sensibilidade aumentada (dispara a partir de 45g)

// --- Pontuações Oficiais IFEx 2026 ---
const int PONTOS_PEQUENO = 8;
const int PONTOS_MEDIO   = 6;
const int PONTOS_GRANDE  = 4;

// --- Cooldown Independente por Sensor ---
const unsigned long COOLDOWN_MS      = 1000; // 1s para laser e ultrassônico
const unsigned long COOLDOWN_BALANCA = 1500; // 1.5s para estabilização da balança
unsigned long ultimoAcertoPequeno = 0;
unsigned long ultimoAcertoMedio   = 0;
unsigned long ultimoAcertoGrande  = 0;

float ultimoPesoBase = 0.0;
int leiturasPesoConsecutivas = 0; // Confirmação contra batidas/vibração na mesa

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

  // 2. Inicialização e Calibração da Célula de Carga HX711
  scale.begin(LOADCELL_DOUT_PIN, LOADCELL_SCK_PIN);
  if (scale.wait_ready_timeout(1000)) {
    balancaDisponivel = true;
    scale.set_scale(fatorCalibracao); // Converte leitura bruta para gramas
    scale.tare(10);                   // Zera a balança na inicialização
    ultimoPesoBase = 0.0;
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
      if (measure.RangeStatus == 0 && measure.RangeMilliMeter > 10 && measure.RangeMilliMeter < LIMIAR_LASER_MM) {
        detectouLaser = true;
      }
    }

    bool detectouInfra = (digitalRead(PINO_INFRA_DIGITAL) == LOW);

    if (detectouLaser || detectouInfra) {
      ultimoAcertoPequeno = agora;
      enviarParaPython("pequeno", PONTOS_PEQUENO);
    }
  }

  // -------------------------------------------------------------
  // 2. BURACO MÉDIO (Célula de Carga HX711 - Leitura Não-Bloqueante)
  // -------------------------------------------------------------
  if (balancaDisponivel && scale.is_ready()) {
    // IMPORTANTE: get_units(1) NÃO bloqueia o loop (leva < 1ms),
    // permitindo que o sensor ultrassônico continue lendo sem atraso!
    // fabs() garante funcionamento mesmo se a célula estiver montada invertida.
    float pesoGramas = fabs(scale.get_units(1));

    if (agora - ultimoAcertoGrande > COOLDOWN_BALANCA) {
      float diferencaGramas = pesoGramas - ultimoPesoBase;

      // Exige 2 amostras consecutivas (>= 100g) para ignorar vibrações/batidas na mesa
      if (diferencaGramas >= LIMIAR_PESO_G) {
        leiturasPesoConsecutivas++;
        if (leiturasPesoConsecutivas >= 2) {
          ultimoAcertoGrande = agora;
          ultimoPesoBase = pesoGramas; // Atualiza a base para suportar sacos acumulados
          leiturasPesoConsecutivas = 0;
          enviarParaPython("medio", PONTOS_MEDIO);
        }
      } else {
        leiturasPesoConsecutivas = 0;
        // Se os saquinhos forem retirados da balança, reajusta a base
        if (diferencaGramas < -25.0) {
          ultimoPesoBase = pesoGramas;
        }
      }
    }
  }

  // -------------------------------------------------------------
  // 3. BURACO GRANDE (Sensor Ultrassônico HC-SR04)
  // -------------------------------------------------------------
  if (agora - ultimoAcertoMedio > COOLDOWN_MS) {
    int distanciaCm = sonar.ping_cm();
    if (distanciaCm > 0 && distanciaCm < LIMIAR_SONAR_CM) {
      ultimoAcertoMedio = agora;
      enviarParaPython("grande", PONTOS_GRANDE);
    }
  }

  delay(20);
}
