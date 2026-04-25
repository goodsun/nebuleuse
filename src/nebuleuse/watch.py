"""raw/ を監視して自動で ingest を呼ぶ。

watchdog による poll/native event。複数イベントが立て続けに来てもデバウンスで
1 ingest にまとめる。
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from . import db, ingest

DEBOUNCE_SECONDS = 1.0


class _Handler(FileSystemEventHandler):
    def __init__(self, trigger):
        self._trigger = trigger

    def _should_handle(self, path: str) -> bool:
        return path.endswith(".md")

    def on_created(self, event):
        if not event.is_directory and self._should_handle(event.src_path):
            self._trigger()

    def on_modified(self, event):
        if not event.is_directory and self._should_handle(event.src_path):
            self._trigger()

    def on_deleted(self, event):
        if not event.is_directory and self._should_handle(event.src_path):
            self._trigger()

    def on_moved(self, event):
        if not event.is_directory and (
            self._should_handle(event.src_path) or self._should_handle(event.dest_path)
        ):
            self._trigger()


class _Debouncer:
    def __init__(self, delay: float, fn):
        self._delay = delay
        self._fn = fn
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def trigger(self):
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._delay, self._run)
            self._timer.daemon = True
            self._timer.start()

    def _run(self):
        try:
            self._fn()
        except Exception as e:  # 監視ループは絶対殺さない
            print(f"[watch] ingest failed: {e}", flush=True)


def _do_ingest():
    stats = ingest.ingest_all()
    print(f"[watch] {time.strftime('%H:%M:%S')} ingested: {stats}", flush=True)


def run(raw_root: Path | None = None, debounce: float = DEBOUNCE_SECONDS) -> None:
    raw_root = raw_root or (db.data_dir() / "raw")
    raw_root.mkdir(parents=True, exist_ok=True)
    print(f"[watch] watching {raw_root}", flush=True)

    debouncer = _Debouncer(debounce, _do_ingest)
    handler = _Handler(debouncer.trigger)
    observer = Observer()
    observer.schedule(handler, str(raw_root), recursive=True)
    observer.start()
    try:
        # 起動時に一度フル ingest
        debouncer.trigger()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[watch] stopping", flush=True)
    finally:
        observer.stop()
        observer.join()
