# Raspberry Pi 5 ↔ ILI9488 터치 LCD 배선 안내

대상 모듈:

- 3.5인치 IPS TFT LCD
- 해상도 480×320
- LCD 드라이버 ILI9488
- 4선 저항식 터치 패널
- 14핀 SPI 인터페이스

> 반드시 Raspberry Pi를 종료하고 USB-C 전원까지 분리한 상태에서 배선하세요.
> 이 문서의 Raspberry Pi 핀 번호는 40핀 커넥터의 **물리 핀 번호**입니다.

## LCD 핀 순서별 연결표

| LCD 핀 | LCD 표기 | 기능 | Raspberry Pi 연결 | 물리 핀 |
|---:|---|---|---|---:|
| 1 | VCC | 전원 입력 | 3.3V | **1** |
| 2 | GND | 전원 접지 | GND | **6** |
| 3 | CS | LCD 칩 선택 | GPIO8 / SPI0 CE0 | **24** |
| 4 | RESET | LCD 재설정 | GPIO25 | **22** |
| 5 | DC | 명령/데이터 선택 | GPIO24 | **18** |
| 6 | SDI(MOSI) | LCD 데이터 입력 | GPIO10 / SPI0 MOSI | **19** |
| 7 | SCK | LCD SPI 클럭 | GPIO11 / SPI0 SCLK | **23** |
| 8 | LED | LCD 백라이트 | 3.3V | **17** |
| 9 | SDO(MISO) | LCD 데이터 출력 | GPIO9 / SPI0 MISO | **21** |
| 10 | T_CLK | 터치 SPI 클럭 | GPIO11 / SPI0 SCLK | **23** |
| 11 | T_CS | 터치 칩 선택 | GPIO7 / SPI0 CE1 | **26** |
| 12 | T_DIN | 터치 데이터 입력 | GPIO10 / SPI0 MOSI | **19** |
| 13 | T_DO | 터치 데이터 출력 | GPIO9 / SPI0 MISO | **21** |
| 14 | T_IRQ | 터치 인터럽트 | GPIO17 | **11** |

## 1번부터 14번까지 순서대로 연결

```text
LCD 1  VCC       → Raspberry Pi 물리 핀 1  (3.3V)
LCD 2  GND       → Raspberry Pi 물리 핀 6  (GND)
LCD 3  CS        → Raspberry Pi 물리 핀 24 (GPIO8 / CE0)
LCD 4  RESET     → Raspberry Pi 물리 핀 22 (GPIO25)
LCD 5  DC        → Raspberry Pi 물리 핀 18 (GPIO24)
LCD 6  SDI/MOSI  → Raspberry Pi 물리 핀 19 (GPIO10 / MOSI)
LCD 7  SCK       → Raspberry Pi 물리 핀 23 (GPIO11 / SCLK)
LCD 8  LED       → Raspberry Pi 물리 핀 17 (3.3V)
LCD 9  SDO/MISO  → Raspberry Pi 물리 핀 21 (GPIO9 / MISO)
LCD 10 T_CLK     → Raspberry Pi 물리 핀 23 (GPIO11 / SCLK)
LCD 11 T_CS      → Raspberry Pi 물리 핀 26 (GPIO7 / CE1)
LCD 12 T_DIN     → Raspberry Pi 물리 핀 19 (GPIO10 / MOSI)
LCD 13 T_DO      → Raspberry Pi 물리 핀 21 (GPIO9 / MISO)
LCD 14 T_IRQ     → Raspberry Pi 물리 핀 11 (GPIO17)
```

## 공유해야 하는 SPI 배선

LCD와 터치 컨트롤러는 MOSI, MISO, SCLK를 공유합니다.

| Raspberry Pi 물리 핀 | 함께 연결할 LCD 핀 |
|---:|---|
| **19** | LCD 6번 `SDI(MOSI)` + LCD 12번 `T_DIN` |
| **21** | LCD 9번 `SDO(MISO)` + LCD 13번 `T_DO` |
| **23** | LCD 7번 `SCK` + LCD 10번 `T_CLK` |

한 물리 핀에 두 점퍼선을 바로 꽂기 어렵다면 브레드보드에서 분기합니다.

```text
Raspberry Pi 핀 19 ──┬── LCD 6  SDI(MOSI)
                     └── LCD 12 T_DIN

Raspberry Pi 핀 21 ──┬── LCD 9  SDO(MISO)
                     └── LCD 13 T_DO

Raspberry Pi 핀 23 ──┬── LCD 7  SCK
                     └── LCD 10 T_CLK
```

## 전체 연결 구조

```text
Raspberry Pi 5                       ILI9488 LCD

3.3V   물리 핀 1  ───────────────── LCD 1  VCC
GND    물리 핀 6  ───────────────── LCD 2  GND
GPIO8  물리 핀 24 ───────────────── LCD 3  CS
GPIO25 물리 핀 22 ───────────────── LCD 4  RESET
GPIO24 물리 핀 18 ───────────────── LCD 5  DC
GPIO10 물리 핀 19 ────────┬──────── LCD 6  SDI(MOSI)
                           └──────── LCD 12 T_DIN
GPIO11 물리 핀 23 ────────┬──────── LCD 7  SCK
                           └──────── LCD 10 T_CLK
3.3V   물리 핀 17 ───────────────── LCD 8  LED
GPIO9  물리 핀 21 ────────┬──────── LCD 9  SDO(MISO)
                           └──────── LCD 13 T_DO
GPIO7  물리 핀 26 ───────────────── LCD 11 T_CS
GPIO17 물리 핀 11 ───────────────── LCD 14 T_IRQ
```

## 전원을 끄기 전 준비

- 이 문서를 휴대폰 또는 다른 컴퓨터에 열어 둡니다.
- 필요한 점퍼선과 브레드보드를 준비합니다.
- LCD 기판에 인쇄된 1번 핀 방향을 확인합니다.
- Raspberry Pi에서 `sudo poweroff`를 실행합니다.
- 상태 LED가 꺼진 뒤 USB-C 전원 케이블을 분리합니다.

## 전원을 다시 켜기 전 점검표

- [ ] LCD 1번 VCC가 Raspberry Pi **물리 핀 1(3.3V)**에 연결됨
- [ ] LCD 2번 GND가 Raspberry Pi **물리 핀 6(GND)**에 연결됨
- [ ] LCD 8번 LED가 Raspberry Pi **물리 핀 17(3.3V)**에 연결됨
- [ ] Raspberry Pi 5V 핀 2와 4에는 연결하지 않음
- [ ] LCD CS는 CE0, 터치 T_CS는 CE1에 연결됨
- [ ] MOSI 공유 배선이 물리 핀 19에 연결됨
- [ ] MISO 공유 배선이 물리 핀 21에 연결됨
- [ ] SCLK 공유 배선이 물리 핀 23에 연결됨
- [ ] 점퍼선이 한 칸씩 밀리지 않음
- [ ] 3.3V와 GND 사이에 잘못 연결된 선이나 합선이 없음

## 주의사항

- 화면 설명에 VCC 3.3~5V라고 표시되어 있어도 최초 시험은 3.3V를 사용합니다.
- Raspberry Pi GPIO 신호는 3.3V 전용입니다. GPIO에 5V가 들어가면 손상될 수 있습니다.
- LED를 GPIO 신호 핀에 직접 연결하지 않습니다. 항상 켜려면 위 표처럼 3.3V에 연결합니다.
- 드라이버를 설치하기 전에는 백라이트만 켜지거나 흰색/검은색 화면이 나올 수 있습니다.
- 발열, 냄새, 연기 또는 비정상적으로 뜨거운 부품이 있으면 즉시 전원을 분리합니다.
