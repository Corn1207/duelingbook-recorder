"""Launches the duelingbook recorder web app."""
import socket
import webbrowser
import threading
from app import create_app

app = create_app()

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"

def open_browser():
    webbrowser.get("safari").open("http://localhost:5001")

if __name__ == "__main__":
    local_ip = get_local_ip()
    print(f"\n  Local:   http://localhost:5001")
    print(f"  Celular: http://{local_ip}:5001\n")
    threading.Timer(1.0, open_browser).start()
    app.run(debug=False, host="0.0.0.0", port=5001)
