# Raspberry Pi 5 음성 대화·양방향 통역 CLI

ALSA의 `arecord`/`aplay`와 OpenAI API를 이용하는 push-to-talk MVP입니다.
기본값은 마이크 `plughw:CARD=Device,DEV=0`, 스피커
`plughw:CARD=Audio,DEV=0`, 16 kHz·16비트·모노입니다. 카드 이름을 사용하므로
재부팅 후 ALSA 카드 번호가 바뀌어도 동일한 USB 장치를 찾습니다.

## 토론·인물 인터뷰

선택 화면은 다음 2×2 메뉴와 키보드 단축키를 제공합니다.

```text
[대화하기 D] [통역하기 T]
[토론하기 C] [인터뷰하기 I]
```

토론하기는 Supabase의 `textbooks` 토론 자료를 우선 사용하며, 등록 자료가
없거나 네트워크가 끊기면 국어 교과서 기본 토론 주제로 동작합니다. 인터뷰하기는
`textbooks`와 `personas`를 연결해 교과서 속 인물과 음성 인터뷰를 진행합니다.
Supabase 주소와 공개 anon 키는 코드가 아닌 `.env`에 설정합니다.

```dotenv
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-supabase-anon-key
```

## 준비

- Raspberry Pi OS와 Python 3.10 이상
- ALSA 도구
- OpenAI API 키와 인터넷 연결

```bash
sudo apt update
sudo apt install -y python3-venv python3-tk alsa-utils fonts-noto-cjk

cd /home/chungwhoong/interpreter-bot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
nano .env
chmod +x run.sh
```

`.env`의 `OPENAI_API_KEY`를 실제 키로 변경합니다. `.env`는 Git에서 제외됩니다.

## 장치 확인

```bash
arecord -l
aplay -l
arecord -D plughw:CARD=Device,DEV=0 -f S16_LE -r 16000 -c 1 -d 3 test.wav
aplay -D plughw:CARD=Audio,DEV=0 test.wav
```

장치 번호가 다르면 `.env`의 `ALSA_MIC_DEVICE`와
`ALSA_SPEAKER_DEVICE`만 바꾸면 됩니다.

## 실행과 키 조작

### 터치스크린 GUI

```bash
./run_touchscreen.sh
```

ILI9488 SPI LCD(`/dev/fb0`)에 직접 표시하려면 다음을 실행합니다.

```bash
chmod +x run_touchscreen_lcd.sh
./run_touchscreen_lcd.sh
```

ILI9488 전용 화면은 키보드만으로 조작할 수 있습니다.

- 시작 화면: `S` 선택 화면, `W` Wi-Fi 선택 창
- 선택 화면: `D` 언어 선택, `T` 통역 화면
- 언어 선택: `K` 한국어, `C` 중국어, `V` 베트남어, `R` 러시아어,
  `Enter` 선택 확정
- 대화 화면: `Space` 녹음 시작/종료
- 통역 화면: `O` 원본 언어, `T` 통역 언어, `↑/↓` 후보 이동,
  `Enter` 확정, `Space` 녹음 시작/종료
- 모든 하위 화면: `Backspace` 이전 화면
- 프로그램 종료: `ESC`

화면 버튼은 마우스나 정상적인 터치 장치로도 선택할 수 있습니다. 시작,
선택, 언어 선택, 대화, 통역 안내는 스피커로 동시에 출력됩니다.
시작 화면의 `Wi-Fi` 버튼을 누르면 주변 네트워크를 선택할 수 있습니다.
비밀번호 입력칸을 터치하면 영문·숫자·특수문자 가상 키보드가 표시됩니다.

### 터미널 화면 UI

```bash
./run.sh
```

`run.sh`는 터치스크린 GUI 서비스를 자동으로 확인하고 로컬 Unix 소켓을 통해
같은 프로그램을 공유 제어합니다. CLI에서 누른 키가 터치스크린의 실제 화면을
전환하며, 녹음·AI 처리·결과·언어 선택 상태도 CLI 화면에 동기화됩니다. 마이크,
스피커, 대화 기록은 GUI 프로세스 하나만 소유하므로 ALSA 충돌이 없습니다.
`Q` 또는 `ESC`는 CLI 컨트롤러만 종료하고 터치스크린은 계속 실행합니다.

GUI 없이 독립적인 터미널 프로그램으로 실행하려면 다음을 사용합니다.

```bash
sudo systemctl stop dahamkke-touchscreen.service
./run_standalone_tui.sh
```

기존의 한 줄 상태 방식 단순 CLI가 필요하면 다음을 실행합니다.

```bash
.venv/bin/python main.py
```

기본 AI 대화 모드는 최근 대화 기록을 유지합니다. 통역 모드는 발화 언어를
판별하여 한국어이면 선택 언어로, 선택 언어이면 한국어로 번역하고 읽습니다.
녹음 중 `s`, `q`, `ESC`도 즉시 처리합니다.
프로그램 시작 시 출력 음성이 AI 생성 음성임을 안내합니다.

## 구조

- `interpreter_bot/audio.py`: push-to-talk 녹음과 재생
- `interpreter_bot/keyboard.py`: 비동기 키 입력
- `interpreter_bot/controller.py`: 터치스크린 공유 제어 CLI
- `interpreter_bot/tui.py`: 독립 실행 터미널 UI
- `interpreter_bot/openai_service.py`: STT, 대화, 번역, TTS
- `interpreter_bot/app.py`: 모드와 생명주기 관리
- `interpreter_bot/touchscreen.py`: 전체화면 터치 UI와 로봇 애니메이션
- `assets/dahamkke_robot.png`: 다함께 봇 홈 화면 이미지

자동 무음 감지를 추가할 때는 `AudioRecorder`와 같은 `start/stop/abort`
인터페이스를 구현하는 별도 recorder로 교체하면 나머지 계층을 유지할 수 있습니다.

## 문제 해결

- `arecord: main: ... audio open error`: `.env`의 마이크 장치와 `arecord -l`을 확인합니다.
- 소리가 안 남: `aplay -l`, 볼륨(`alsamixer`), 스피커 장치를 확인합니다.
- API 오류: API 키, 인터넷 연결, 계정의 모델 사용 권한을 확인합니다.
- SSH에서 키가 동작하지 않음: 대화형 TTY로 접속했는지 확인합니다(`ssh -t`).
