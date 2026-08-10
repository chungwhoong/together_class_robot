#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DISPLAY_NUMBER="${TOUCH_DISPLAY:-:1}"
XORG_CONFIG_TEMPLATE="$SCRIPT_DIR/hardware/ili9488/xorg-ili9488.conf"
XORG_CONFIG="${XORG_CONFIG:-/tmp/dahamkke-xorg-ili9488.conf}"
XORG_LOG="${XORG_LOG:-/tmp/dahamkke-xorg.log}"
TOUCH_DISPLAY_TYPE="${TOUCH_DISPLAY_TYPE:-dsi}"

cd "$SCRIPT_DIR"

if [[ ! -x .venv/bin/python ]]; then
    echo "가상환경이 없습니다. README의 설치 절차를 먼저 실행하세요." >&2
    exit 1
fi

# DRM card numbers are not stable. Prefer the new 5-inch DSI panel and retain
# the old SPI panel as an environment-selectable fallback.
DISPLAY_DRM_CARD="${DISPLAY_DRM_CARD:-}"
DISPLAY_MODE="${DISPLAY_MODE:-}"
if [[ -z "$DISPLAY_DRM_CARD" && "$TOUCH_DISPLAY_TYPE" == "dsi" ]]; then
    for connector in /sys/class/drm/card*-DSI-*/status; do
        if [[ -e "$connector" && "$(cat "$connector")" == "connected" ]]; then
            connector_name="$(basename "$(dirname "$connector")")"
            DISPLAY_DRM_CARD="${connector_name%%-*}"
            modes_file="$(dirname "$connector")/modes"
            if [[ -z "$DISPLAY_MODE" && -s "$modes_file" ]]; then
                DISPLAY_MODE="$(head -n 1 "$modes_file")"
            fi
            break
        fi
    done
fi
if [[ -z "$DISPLAY_DRM_CARD" && "$TOUCH_DISPLAY_TYPE" == "spi" ]]; then
    for card_path in /sys/bus/spi/devices/spi0.0/drm/card*; do
        if [[ -e "$card_path" ]]; then
            DISPLAY_DRM_CARD="$(basename "$card_path")"
            DISPLAY_MODE="${DISPLAY_MODE:-480x320}"
            break
        fi
    done
fi
if [[ -z "$DISPLAY_DRM_CARD" || ! -e "/dev/dri/$DISPLAY_DRM_CARD" ]]; then
    echo "$TOUCH_DISPLAY_TYPE 화면의 DRM 장치를 찾지 못했습니다." >&2
    exit 1
fi
DISPLAY_MODE="${DISPLAY_MODE:-800x480}"

sed \
    -e "s|@DISPLAY_KMSDEV@|/dev/dri/$DISPLAY_DRM_CARD|g" \
    -e "s|@DISPLAY_MODE@|$DISPLAY_MODE|g" \
    "$XORG_CONFIG_TEMPLATE" > "$XORG_CONFIG"
echo "$TOUCH_DISPLAY_TYPE 화면 장치: /dev/dri/$DISPLAY_DRM_CARD ($DISPLAY_MODE)"

cleanup() {
    if [[ -n "${XORG_PID:-}" ]] && kill -0 "$XORG_PID" 2>/dev/null; then
        sudo kill "$XORG_PID" 2>/dev/null || true
        wait "$XORG_PID" 2>/dev/null || true
    fi
    rm -f "$XORG_CONFIG"
}
trap cleanup EXIT INT TERM

sudo /usr/lib/xorg/Xorg "$DISPLAY_NUMBER" \
    vt2 \
    -config "$XORG_CONFIG" \
    -logfile "$XORG_LOG" \
    -ac \
    -nolisten tcp \
    -noreset &
XORG_PID=$!

for _ in {1..50}; do
    [[ -S "/tmp/.X11-unix/X${DISPLAY_NUMBER#:}" ]] && break
    sleep 0.1
done

if [[ ! -S "/tmp/.X11-unix/X${DISPLAY_NUMBER#:}" ]]; then
    echo "ILI9488용 Xorg 시작 실패: $XORG_LOG를 확인하세요." >&2
    exit 1
fi

# A system service has no foreground console session, so the kernel may leave
# the SPI panel on tty1 even though Xorg is ready on tty2.
sudo chvt 2
DISPLAY="$DISPLAY_NUMBER" "$SCRIPT_DIR/.venv/bin/python" touchscreen.py
