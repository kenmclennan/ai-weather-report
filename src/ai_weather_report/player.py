"""Audio player using mpv with IPC socket for playback control."""

import json
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path


class MpvPlayer:
    """Controls mpv via its JSON IPC socket."""

    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None
        self._socket_path = os.path.join(tempfile.gettempdir(), f"awr-mpv-{os.getpid()}")
        self._sock: socket.socket | None = None

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def play(self, audio_path: Path) -> None:
        """Start playback of an audio file."""
        self.stop()

        # Clean up old socket
        if os.path.exists(self._socket_path):
            os.unlink(self._socket_path)

        self._process = subprocess.Popen(
            [
                "mpv",
                "--no-video",
                "--no-terminal",
                f"--input-ipc-server={self._socket_path}",
                str(audio_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Wait for socket to appear
        for _ in range(20):
            if os.path.exists(self._socket_path):
                break
            time.sleep(0.1)

    def stop(self) -> None:
        """Stop playback."""
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

        if self._process and self._process.poll() is None:
            try:
                self._send_command(["quit"])
            except Exception:
                self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()

        self._process = None

        if os.path.exists(self._socket_path):
            try:
                os.unlink(self._socket_path)
            except OSError:
                pass

    def toggle_pause(self) -> None:
        """Toggle pause/resume."""
        if not self.is_running:
            return
        paused = self.get_property("pause")
        if paused is not None:
            self._send_command(["set_property", "pause", not paused])

    def seek(self, seconds: float) -> None:
        """Seek relative by seconds (positive = forward, negative = back)."""
        if not self.is_running:
            return
        self._send_command(["seek", seconds, "relative"])

    def get_position(self) -> float | None:
        """Get current playback position in seconds."""
        return self.get_property("time-pos")

    def get_duration(self) -> float | None:
        """Get total duration in seconds."""
        return self.get_property("duration")

    def is_paused(self) -> bool:
        """Check if playback is paused."""
        result = self.get_property("pause")
        return bool(result) if result is not None else False

    def get_property(self, name: str):
        """Get an mpv property value."""
        if not self.is_running:
            return None
        try:
            response = self._send_command(["get_property", name])
            if response and "data" in response:
                return response["data"]
        except Exception:
            pass
        return None

    def _send_command(self, command: list) -> dict | None:
        """Send a JSON IPC command to mpv and return the response."""
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            sock.connect(self._socket_path)

            msg = json.dumps({"command": command}) + "\n"
            sock.sendall(msg.encode())

            data = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break

            sock.close()

            if data:
                return json.loads(data.split(b"\n")[0])
        except (OSError, json.JSONDecodeError, ConnectionRefusedError):
            pass
        return None

    def __del__(self):
        self.stop()


def format_time(seconds: float | None) -> str:
    """Format seconds as M:SS."""
    if seconds is None or seconds < 0:
        return "-:--"
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}:{secs:02d}"
