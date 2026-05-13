#include <Wire.h>
#include <Adafruit_INA219.h>

// 센서 3개 (3, 4, 5번 부하)
Adafruit_INA219 ina219_3(0x40); 
Adafruit_INA219 ina219_4(0x41); 
Adafruit_INA219 ina219_5(0x44); 

// LED 핀 세팅 (위쪽 보드의 9번, 10번 구멍)
const int PIN_BLUE = 9;   
const int PIN_RED = 10;   
const int PIN_GREEN = 11; 

void setup() {
  Serial.begin(9600);
  pinMode(PIN_BLUE, OUTPUT);
  pinMode(PIN_RED, OUTPUT);
  pinMode(PIN_GREEN, OUTPUT);

  ina219_3.begin();
  ina219_4.begin();
  ina219_5.begin();
}

void loop() {
  // 센서 데이터 읽기
  float c3 = ina219_3.getCurrent_mA();
  float c4 = ina219_4.getCurrent_mA();
  float c5 = ina219_5.getCurrent_mA();
  
  // 'A' 이름표 달고 전송
  Serial.print("A:");
  Serial.print(c3); Serial.print(",");
  Serial.print(c4); Serial.print(",");
  Serial.println(c5);

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