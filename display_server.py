"""Used to display images captured from 
   raspberry pi 5. This is the driver script for the
   LED matrix running on the Pi Zero 2 W"""

import socket
from PIL import Image #Image from pi5
from rgbmatrix import RGBMatrix, RGBMatrixOptions

#64 x 64 matrix specs
WIDTH = 64 
HEIGHT = 64
FRAME_BYTES = WIDTH * HEIGHT * 3
PORT = 5005 #server port


options = RGBMatrixOptions()
options.rows = HEIGHT
options.cols = WIDTH
options.chain_length = 1
options.parallel = 1
options.hardware_mapping = 'regular'   # confirmed working mapping for your Active-3 bonnet
options.gpio_slowdown = 4

matrix = RGBMatrix(options=options)
canvas = matrix.CreateFrameCanvas()


def recv_exact(conn, n):
    buf = b''
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def main():
    global canvas
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', PORT))
        s.listen(1)
        print(f"Listening on port {PORT}...")

        while True:
            conn, addr = s.accept()
            print(f"Connected: {addr}")
            try:
                while True:
                    data = recv_exact(conn, FRAME_BYTES)
                    if data is None:
                        print("Sender disconnected.")
                        break
                    img = Image.frombytes('RGB', (WIDTH, HEIGHT), data)
                    canvas.SetImage(img)
                    canvas = matrix.SwapOnVSync(canvas)
            finally:
                conn.close()


if __name__ == '__main__':
    main()