#include <errno.h>
#include <fcntl.h>
#include <linux/spi/spidev.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

static int read_axis(int fd, uint8_t command, uint32_t speed_hz)
{
    uint8_t tx[3] = {command, 0, 0};
    uint8_t rx[3] = {0, 0, 0};
    struct spi_ioc_transfer transfer = {
        .tx_buf = (uintptr_t)tx,
        .rx_buf = (uintptr_t)rx,
        .len = sizeof(tx),
        .speed_hz = speed_hz,
        .bits_per_word = 8,
    };

    if (ioctl(fd, SPI_IOC_MESSAGE(1), &transfer) < 0) {
        return -1;
    }
    return ((rx[1] << 8) | rx[2]) >> 3;
}

int main(void)
{
    const char *device = "/dev/spidev0.1";
    uint8_t mode = SPI_MODE_0;
    uint8_t bits = 8;
    uint32_t speed_hz = 2000000;
    int fd = open(device, O_RDWR);

    if (fd < 0) {
        fprintf(stderr, "open %s: %s\n", device, strerror(errno));
        return 1;
    }
    if (ioctl(fd, SPI_IOC_WR_MODE, &mode) < 0 ||
        ioctl(fd, SPI_IOC_WR_BITS_PER_WORD, &bits) < 0 ||
        ioctl(fd, SPI_IOC_WR_MAX_SPEED_HZ, &speed_hz) < 0) {
        fprintf(stderr, "SPI setup: %s\n", strerror(errno));
        close(fd);
        return 1;
    }

    puts("Touch and hold the panel while samples are read:");
    for (int i = 0; i < 50; ++i) {
        int x = read_axis(fd, 0xD0, speed_hz);
        int y = read_axis(fd, 0x90, speed_hz);
        if (x < 0 || y < 0) {
            fprintf(stderr, "SPI transfer: %s\n", strerror(errno));
            close(fd);
            return 1;
        }
        printf("%02d X=%4d Y=%4d\n", i + 1, x, y);
        fflush(stdout);
        usleep(200000);
    }
    close(fd);
    return 0;
}
