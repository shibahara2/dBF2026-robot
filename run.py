from app import create_app
import socket

app = create_app()

def find_available_port(start_port=5000, max_port=5100):
    for port in range(start_port, max_port + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("0.0.0.0", port))
            return port
        except OSError:
            continue

    raise RuntimeError("利用可能なポートが見つかりません")

if __name__ == "__main__":
    port = find_available_port()
    print(f"Starting server on port {port}")
    app.run(host="0.0.0.0", port=port, threaded=True)