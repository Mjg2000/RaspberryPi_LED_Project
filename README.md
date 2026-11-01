# RaspberryPi_LED_Project V1.0

## Overview

The goal of this project is to display live camera data on a 64x64 RGB LED matrix. A Raspberry Pi 5 captures and processes video from a camera module, then streams it over the local network to a Raspberry Pi Zero 2 W that drives the panel.

**Current effects:** edge detection with motion trails (Canny edges drawn in color, fading over time).

## Architecture

The Pi 5 captures, processes, and sends raw 64×64×3-byte RGB frames (12,288 bytes) over TCP port 5005 to the Zero 2 W, which blits them to the panel.

```
[Pi 5 + Camera Module 3]                     [Pi Zero 2 W + Active-3 Bonnet]
  capture frame                                receive 12,288-byte frame
  resize to 64x64                 TCP :5005    SetImage() onto offscreen canvas
  edge detection + motion trail  ----------->  SwapOnVSync()
  send raw RGB bytes                           64x64 HUB75 panel
```

## Next Steps

- Implement a gesture-sensing setting to modify display output.

## Additional Tips

- Start `display_server.py` on the Zero 2 W first. `camera_sender.py` on the Pi 5 retries every 2 seconds if the server isn't up yet.
- Tailscale isn't part of the build, but it interfered with local SSH from my computer. Make sure it is turned OFF when interfacing with the Pis.
- See [Troubleshooting](#troubleshooting) at the end of this README for additional requirements and fixes.

## Hardware

| Component | Role |
|---|---|
| Raspberry Pi Zero 2 W ("GrantPi") | Display node that drives the LED matrix |
| Raspberry Pi 5 ("GrantPi5") | Vision node that captures and processes the camera feed |
| Raspberry Pi Camera Module 3 (IMX708) | Video source, attached to the Pi 5 |
| 64×64 RGB LED matrix panel (HUB75) | Output display |
| Triple-output HUB75 RGB Matrix Active-3 Bonnet | Interface between the Pi's GPIO and the panel |
| Facmogu 5V 4A DC power supply | Powers the panel |
| HUB75 ribbon cable | Bonnet to panel (IN port) |
| microSD cards (one per Pi) | OS storage |
| Camera ribbon cable | Camera to Pi 5 CSI port |

## Software

### OS and system

- Raspberry Pi OS (Debian 13 "Trixie"), 64-bit, on both Pis
- Raspberry Pi Imager for flashing and pre-configuring hostname, user, and Wi-Fi
- SSH for remote access
- Raspberry Pi Connect for remote shell access
- tmux to keep long builds alive over dropped SSH sessions
- zram plus a 1 GB swapfile so the Zero 2 W could finish compiling the matrix bindings

### Display node (Raspberry Pi Zero 2 W)

- [hzeller/rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix) as the matrix driver library, with its Python bindings installed via `pip install .`
- Python 3.13
- Cython 3 (to build the bindings)
- Pillow (frame handling, `SetImage`)
- Python `socket` module (TCP frame receiver)
- Config: `--led-gpio-mapping=regular`, `gpio_slowdown=4`, audio module (`snd_bcm2835`) blacklisted

### Vision node (Raspberry Pi 5)

- Picamera2 / libcamera / rpicam-apps for camera capture
- OpenCV (`python3-opencv`) for resizing, Canny edge detection, and Gaussian blur
- NumPy for the motion-trail buffer and frame math
- Python `socket` module (TCP frame sender)

### Dev workflow

- Git and GitHub for version control
- `scp` for moving scripts between the Pis

## Troubleshooting

Issues hit while building this project, with the symptom, cause, and fix for each. Items 1-4 cost the most time, so check them first if the panel isn't working.

| # | Symptom | Cause | Fix |
|---|---------|-------|-----|
| 1 | Demo runs and prints "Press CTRL-C to exit," but the panel stays dark | The Active-3 bonnet isn't wired like an Adafruit HAT, so the `adafruit-hat` mapping drives the wrong pins | Use `--led-gpio-mapping=regular` (CLI) or `options.hardware_mapping = 'regular'` (Python) |
| 2 | Demo exits with `snd_bcm2835: found that the Pi sound module is loaded` | Onboard audio and the matrix library share the same hardware PWM timer | Disable audio and blacklist the module (see [details](#2-onboard-audio-conflict)) |
| 3 | `ModuleNotFoundError: No module named 'rgbmatrix'`, or `make: No rule to make target 'build-python'` | The bindings now build via `pyproject.toml`; the old `make build-python` targets no longer exist | `sudo pip install . --break-system-packages` from the repo root (see [details](#3-python-bindings-install)) |
| 4 | Build hangs, then SSH drops with `Connection reset` | The Zero 2 W has 512 MB RAM, which isn't enough to compile the bindings with zram swap alone | Add a 1 GB swapfile and build inside `tmux` (see [details](#4-out-of-memory-during-build)) |
| 5 | `sudo: ./demo: command not found` | Top-level `make` only builds the core library | Run `make` inside `examples-api-use/` |
| 6 | `ping`/SSH to a Pi on the same LAN times out | Tailscale on the host computer captures local routing | Disable Tailscale while working locally, or connect by LAN IP |
| 7 | `WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!` | The Pi was reflashed and generated new SSH host keys | `ssh-keygen -R <hostname>.local`, then reconnect |
| 8 | `rpicam-hello` detects the IMX708 but fails with `Camera frontend has timed out` | The Zero 2 W has a smaller CSI connector and needs the Zero-specific camera cable | Use the correct cable, or run the camera on the Pi 5 |
| 9 | Flicker, dim rows, or random resets | Panel is drawing more current than the supply can deliver, or a marginal connection | Cap brightness and check voltage under load (see [details](#9-power-budget)) |

---

### 1. GPIO mapping

The Active-3 bonnet requires the `regular` mapping.

```bash
sudo ./demo -D0 --led-rows=64 --led-cols=64 --led-chain=1 \
  --led-gpio-mapping=regular --led-slowdown-gpio=4
```

The Zero 2 W also needs `--led-slowdown-gpio=4` (`options.gpio_slowdown = 4` in Python) to avoid flicker and ghosting. If you still see flicker, try adding `--led-pwm-lsb-nanoseconds=130`.

### 2. Onboard audio conflict

Comment out `dtparam=audio=on` in `/boot/firmware/config.txt`, then blacklist the module:

```bash
echo "blacklist snd_bcm2835" | sudo tee /etc/modprobe.d/blacklist-rgb-matrix.conf
sudo update-initramfs -u
sudo reboot
```

Verify after reboot (should print nothing):

```bash
lsmod | grep snd_bcm2835
```

The reboot is required: blacklisting doesn't unload a module that's already running.

### 3. Python bindings install

```bash
sudo apt install -y python3-dev cython3
cd ~/rpi-rgb-led-matrix
sudo pip install . --break-system-packages
```

- **Why `sudo`:** the display script runs as root, so the package must be installed system-wide. A plain `pip install` lands in `~/.local`, which root can't see.
- **Why `--break-system-packages`:** Raspberry Pi OS Trixie enforces PEP 668 and blocks system-wide pip installs without it.

Verify under `sudo`:

```bash
sudo python3 -c "import rgbmatrix; print(rgbmatrix.__file__)"
```

### 4. Out of memory during build

Compiling the Cython/C++ bindings on a 512 MB Zero 2 W can take 10-20 minutes and may drop your SSH session. `dmesg` often shows no OOM entry, so this is easy to misdiagnose.

Add a disk-backed swapfile on top of the default zram swap:

```bash
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
cat /proc/swaps        # should list both zram0 and /swapfile
```

Run the build inside `tmux` so it survives a dropped connection:

```bash
sudo apt install -y tmux
tmux new -s build
# run the pip install inside this session
# if SSH drops: reconnect, then `tmux attach -t build`
```

Note: current Raspberry Pi OS uses zram by default, so `dphys-swapfile` instructions found in older guides don't apply.

### 5. Example binaries

```bash
cd ~/rpi-rgb-led-matrix/examples-api-use
make
```

### 6. Tailscale interference

Tailscale on the host computer can capture traffic meant for the local network, so SSH and ping to a Pi on the same LAN fail even though the Pi is fine. Disable Tailscale on the host while doing local Pi work, or connect by the Pi's LAN IP.

Also note that `.local` hostnames rely on mDNS. Windows may need [Bonjour](https://support.apple.com/kb/DL999) installed for `hostname.local` to resolve.

### 7. Host key warning after reflashing

Expected behavior when reusing a hostname on a freshly flashed Pi:

```bash
ssh-keygen -R <hostname>.local
```

Then reconnect and accept the new fingerprint.

### 8. Camera on the Zero 2 W

If `rpicam-hello` identifies the sensor but reports `Camera frontend has timed out`, the control channel (I2C) is working but the high-speed data lanes aren't. On the Zero 2 W this usually means the wrong ribbon cable. The Zero's CSI port is smaller than a full-size Pi's and needs the Zero-specific camera cable (22-pin to 15-pin). This project moved the camera to the Pi 5 to avoid the issue.

### 9. Power budget

A 64x64 panel can draw well over 4 A at full white, so a 5 V / 4 A supply is tight.

- Cap brightness (roughly 40-60%), e.g. `--led-brightness=50`.
- Power the panel directly from the 5 V supply, not through the Pi.
- Diagnose by probing voltage at the panel under load while flexing the cables; visual inspection alone won't catch a marginal connection.

### Runtime notes

- **Run as root:** the matrix library needs root for full performance (`sudo python3 display_server.py`). It drops privileges to the `daemon` user after initializing the matrix; set `options.drop_privileges = False` if your script needs file access afterward.
- **Color channels:** Picamera2's `RGB888` format is BGR in memory, so the sender converts with `cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)`. If red and blue look swapped on the panel, remove or add that conversion.
- **Start order:** start `display_server.py` on the Zero 2 W first. `camera_sender.py` on the Pi 5 retries every 2 seconds if the server isn't up yet.
