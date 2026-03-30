"""Launches the duelingbook recorder web app."""
import webbrowser
import threading
from app import create_app

app = create_app()

def open_browser():
    webbrowser.get("safari").open("http://localhost:5001")

if __name__ == "__main__":
    threading.Timer(1.0, open_browser).start()
    app.run(debug=False, host="0.0.0.0", port=5001)
