#include <Wire.h>
#include <Adafruit_INA219.h>

// 센서 2개 (1, 2번 부하)
Adafruit_INA219 ina219_1(0x40); 
Adafruit_INA219 ina219_2(0x41); 

// LED 핀 세팅 (아래쪽 보드의 9번, 10번 구멍)
const int PIN_BLUE = 9;   
const int PIN_RED = 10;   
const int PIN_GREEN = 11; 

void setup() {
  Serial.begin(9600);
  pinMode(PIN_BLUE, OUTPUT);
  pinMode(PIN_RED, OUTPUT);
  pinMode(PIN_GREEN, OUTPUT);

  ina219_1.begin();
  ina219_2.begin();
}

void loop() {
  float c1 = ina219_1.getCurrent_mA();
  float c2 = ina219_2.getCurrent_mA();
  
  // 'B' 이름표 달고 전송
  Serial.print("B:");
  Serial.print(c1); Serial.print(",");
  Serial.println(c2);

  // 파이 명령 받아서 LED 제어
  if (Serial.available() > 0) {
    char cmd = Serial.read();
    if (cmd == 'B' || cmd == 'b') {      
      digitalWrite(PIN_BLUE, HIGH); digitalWrite(PIN_RED, LOW);  digitalWrite(PIN_GREEN, LOW);
    } else if (cmd == 'R' || cmd == 'r') { 
      digitalWrite(PIN_BLUE, LOW);  digitalWrite(PIN_RED, HIGH); digitalWrite(PIN_GREEN, LOW);
    } else if (cmd == 'G' || cmd == 'g') { 
      digitalWrite(PIN_BLUE, LOW);  digitalWrite(PIN_RED, LOW);  digitalWrite(PIN_GREEN, HIGH);
    } else if (cmd == 'O' || cmd == 'o') { 
      digitalWrite(PIN_BLUE, LOW);  digitalWrite(PIN_RED, LOW);  digitalWrite(PIN_GREEN, LOW);
    }
  }
  delay(1000); 
}