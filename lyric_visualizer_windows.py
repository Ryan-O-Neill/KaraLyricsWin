#!/usr/bin/env python3
"""
Lyric visualizer synced to the Spotify desktop app on Windows.

No Spotify API, credentials, or Premium needed. It reads what Spotify reports
to the Windows media session (the same info shown in the volume flyout), then
fetches time-stamped lyrics at runtime from LRCLIB and animates them with pygame.

Install (PowerShell):
    pip install pygame requests winrt-runtime winrt-Windows.Media.Control winrt-Windows.Foundation winrt-Windows.Foundation.Collections

Run:
    1. Open the Spotify desktop app and play a song (e.g. Virtual Insanity).
    2. python lyric_visualizer_windows.py

Controls:  SPACE = pause/resume   LEFT/RIGHT = nudge sync by 100 ms   ESC = quit
"""

import asyncio
import bisect
import colorsys
import math
import re
import sys
import threading
import time
from datetime import datetime, timezone
from functools import lru_cache

import pygame
import requests
from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
)

POLL_SECONDS = 0.4
LRCLIB_URL = "https://lrclib.net/api"
USER_AGENT = "lyric-visualizer/1.0 (personal project)"
LRC_TIME = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")


# --------------------------------------------------------------------------- #
# Windows media session
# --------------------------------------------------------------------------- #
class NowPlaying:
    """Thread-safe snapshot of what Spotify is playing, with interpolation."""

    def __init__(self):
        self.lock = threading.Lock()
        self.found = False
        self.title = self.artist = self.album = ""
        self.duration_ms = 0.0
        self.base_pos_ms = 0.0
        self.playing = False
        self.stamp = time.perf_counter()
        self.toggle_requested = False

    def update(self, title, artist, album, duration_ms, pos_ms, playing):
        with self.lock:
            self.found = True
            self.title, self.artist, self.album = title, artist, album
            self.duration_ms = duration_ms
            self.base_pos_ms = pos_ms
            self.playing = playing
            self.stamp = time.perf_counter()

    def mark_missing(self):
        with self.lock:
            self.found = False

    def position_ms(self):
        with self.lock:
            if self.playing:
                return self.base_pos_ms + (time.perf_counter() - self.stamp) * 1000
            return self.base_pos_ms

    def snapshot(self):
        with self.lock:
            return self.found, self.title, self.artist, self.album, self.duration_ms, self.playing


async def poll_media_session(state: NowPlaying, stop: threading.Event):
    manager = await MediaManager.request_async()
    while not stop.is_set():
        try:
            session = next(
                (s for s in manager.get_sessions()
                 if "spotify" in s.source_app_user_model_id.lower()),
                None,
            )
            if session is None:
                state.mark_missing()
            else:
                if state.toggle_requested:
                    state.toggle_requested = False
                    await session.try_toggle_play_pause_async()

                props = await session.try_get_media_properties_async()
                timeline = session.get_timeline_properties()
                info = session.get_playback_info()
                playing = info.playback_status == PlaybackStatus.PLAYING

                pos_ms = timeline.position.total_seconds() * 1000
                if playing:
                    # Position is as of last_updated_time; add the time since then
                    last = timeline.last_updated_time
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=timezone.utc)
                    pos_ms += max(0.0, (datetime.now(timezone.utc) - last).total_seconds() * 1000)

                duration_ms = (timeline.end_time - timeline.start_time).total_seconds() * 1000
                state.update(props.title or "", props.artist or "", props.album_title or "",
                             duration_ms, pos_ms, playing)
        except Exception as exc:
            print(f"[media] {exc}", file=sys.stderr)
        await asyncio.sleep(POLL_SECONDS)


def start_poller(state: NowPlaying, stop: threading.Event):
    threading.Thread(
        target=lambda: asyncio.run(poll_media_session(state, stop)), daemon=True
    ).start()


# --------------------------------------------------------------------------- #
# Lyrics (fetched at runtime, nothing bundled)
# --------------------------------------------------------------------------- #
def parse_lrc(text):
    lines = []
    for raw in text.splitlines():
        stamps = LRC_TIME.findall(raw)
        if not stamps:
            continue
        content = LRC_TIME.sub("", raw).strip()
        for mins, secs in stamps:
            lines.append((int((int(mins) * 60 + float(secs)) * 1000), content))
    lines.sort(key=lambda x: x[0])
    return lines


def fetch_synced_lyrics(title, artist, album, duration_ms):
    headers = {"User-Agent": USER_AGENT}
    duration = round(duration_ms / 1000)
    try:
        r = requests.get(f"{LRCLIB_URL}/get",
                         params={"track_name": title, "artist_name": artist,
                                 "album_name": album, "duration": duration},
                         headers=headers, timeout=10)
        if r.ok and r.json().get("syncedLyrics"):
            return parse_lrc(r.json()["syncedLyrics"])
    except requests.RequestException:
        pass
    try:
        r = requests.get(f"{LRCLIB_URL}/search",
                         params={"track_name": title, "artist_name": artist},
                         headers=headers, timeout=10)
        r.raise_for_status()
        cands = [c for c in r.json() if c.get("syncedLyrics")]
        if cands:
            best = min(cands, key=lambda c: abs((c.get("duration") or 0) - duration))
            return parse_lrc(best["syncedLyrics"])
    except requests.RequestException as exc:
        print(f"[lyrics] {exc}", file=sys.stderr)
    return []


class LyricsStore:
    """Loads lyrics in the background whenever the track changes."""

    def __init__(self):
        self.key = None
        self.lines = []
        self.status = "idle"  # idle | loading | ready | none

    def request(self, title, artist, album, duration_ms):
        key = (title, artist)
        if key == self.key:
            return
        self.key, self.lines, self.status = key, [], "loading"

        def work():
            lines = fetch_synced_lyrics(title, artist, album, duration_ms)
            if self.key == key:  # ignore stale results if the track changed again
                self.lines = lines
                self.status = "ready" if lines else "none"

        threading.Thread(target=work, daemon=True).start()


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=64)
def get_font(size, bold=False):
    return pygame.font.SysFont("segoeui,helvetica,arial", size, bold=bold)


def hsv(h, s, v):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


def wrap_text(font, text, max_width):
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if font.size(trial)[0] <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [""]


def draw_background(screen, t, pulse):
    w, h = screen.get_size()
    top = hsv(0.62 + 0.05 * math.sin(t * 0.1), 0.65, 0.18 + 0.10 * pulse)
    bottom = hsv(0.80 + 0.05 * math.cos(t * 0.13), 0.70, 0.10 + 0.08 * pulse)
    for y in range(0, h, 4):
        k = y / h
        pygame.draw.rect(screen, tuple(int(top[i] * (1 - k) + bottom[i] * k) for i in range(3)),
                         (0, y, w, 4))
    overlay = pygame.Surface((w, h), pygame.SRCALPHA)
    for i in range(7):
        phase = t * 0.25 + i * 0.9
        cx = w * (0.5 + 0.42 * math.sin(phase + i))
        cy = h * (0.5 + 0.38 * math.cos(phase * 0.8 + i * 1.7))
        r = int(min(w, h) * (0.12 + 0.05 * pulse + 0.03 * math.sin(phase * 2)))
        pygame.draw.circle(overlay, (*hsv(0.55 + i * 0.07 + t * 0.01, 0.6, 1.0), 28), (cx, cy), r)
    screen.blit(overlay, (0, 0))


def draw_line(screen, font, text, center_y, color, alpha, max_width, fill_frac=None, fill_color=None):
    w, _ = screen.get_size()
    lines = wrap_text(font, text, max_width)
    lh = font.get_linesize()
    y = center_y - (lh * len(lines)) // 2
    widths = [font.size(l)[0] for l in lines]
    filled_px = (fill_frac or 0) * (sum(widths) or 1)
    for ln, lw in zip(lines, widths):
        x = (w - lw) // 2
        base = font.render(ln, True, color)
        base.set_alpha(alpha)
        screen.blit(base, (x, y))
        if fill_frac is not None and filled_px > 0:
            lit = font.render(ln, True, fill_color)
            lit.set_alpha(alpha)
            screen.blit(lit, (x, y), area=pygame.Rect(0, 0, int(min(lw, filled_px)), lit.get_height()))
        filled_px = max(0, filled_px - lw)
        y += lh


def centered_message(screen, text, color=(230, 230, 245)):
    w, h = screen.get_size()
    surf = get_font(max(22, int(h * 0.04))).render(text, True, color)
    screen.blit(surf, ((w - surf.get_width()) // 2, h // 2))


def main():
    state = NowPlaying()
    lyrics = LyricsStore()
    stop = threading.Event()
    start_poller(state, stop)

    pygame.init()
    pygame.display.set_caption("Lyric Visualizer")
    screen = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
    clock = pygame.time.Clock()

    offset_ms, smooth_idx, running = 0, 0.0, True
    t0 = time.perf_counter()

    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False
                elif ev.key == pygame.K_LEFT:
                    offset_ms -= 100
                elif ev.key == pygame.K_RIGHT:
                    offset_ms += 100
                elif ev.key == pygame.K_SPACE:
                    state.toggle_requested = True

        t = time.perf_counter() - t0
        w, h = screen.get_size()
        found, title, artist, album, duration_ms, playing = state.snapshot()

        if found and title:
            lyrics.request(title, artist, album, duration_ms)

        pos = state.position_ms() + offset_ms
        lines = lyrics.lines
        starts = [ms for ms, _ in lines]
        idx = bisect.bisect_right(starts, pos) - 1 if lines else -1

        progress = 0.0
        if idx >= 0:
            start = starts[idx]
            end = starts[idx + 1] if idx + 1 < len(starts) else start + 4000
            progress = max(0.0, min(1.0, (pos - start) / max(1, end - start)))
        pulse = (1 - progress) ** 3 if idx >= 0 else 0.0
        smooth_idx += (idx - smooth_idx) * 0.18

        draw_background(screen, t, pulse)

        if not found:
            centered_message(screen, "Open the Spotify desktop app and press play...")
        else:
            head = get_font(26, True).render(f"{title}  -  {artist}", True, (240, 240, 255))
            screen.blit(head, (30, 22))

            font_size = max(28, int(h * 0.075))
            main_font = get_font(int(font_size * (1 + 0.03 * pulse)), True)
            side_font = get_font(int(font_size * 0.62))
            max_w, cy = int(w * 0.85), h // 2

            if lyrics.status == "loading":
                centered_message(screen, "Fetching lyrics...")
            elif lyrics.status == "none":
                centered_message(screen, "No synced lyrics found for this track.", (255, 200, 200))
            else:
                for rel in (-2, -1, 1, 2):
                    j = idx + rel
                    if 0 <= j < len(lines) and lines[j][1]:
                        alpha = max(0, int(150 - 55 * abs(j - smooth_idx)))
                        y = cy + int((j - smooth_idx) * h * 0.14) + int(h * 0.04) * (1 if rel > 0 else -1)
                        draw_line(screen, side_font, lines[j][1], y, (200, 200, 230), alpha, max_w)

                if idx >= 0 and lines[idx][1]:
                    lit = hsv(t * 0.05 + idx * 0.04, 0.35, 1.0)
                    draw_line(screen, main_font, lines[idx][1], cy, (150, 150, 185), 255, max_w,
                              fill_frac=min(1.0, progress * 1.15), fill_color=lit)
                elif idx >= 0 or (lines and pos < starts[0]):
                    for b in range(9):  # instrumental / intro: equalizer bars
                        bh = int(12 + 38 * abs(math.sin(t * 3 + b * 0.7)))
                        pygame.draw.rect(screen, hsv(0.55 + b * 0.04, 0.5, 1.0),
                                         (w // 2 - 90 + b * 20, cy - bh // 2, 12, bh), border_radius=4)

            if duration_ms > 0:
                frac = max(0.0, min(1.0, pos / duration_ms))
                pygame.draw.rect(screen, (90, 90, 120), (30, h - 40, w - 60, 6), border_radius=3)
                pygame.draw.rect(screen, hsv(t * 0.05, 0.4, 1.0),
                                 (30, h - 40, int((w - 60) * frac), 6), border_radius=3)

            hint = get_font(16).render(
                f"SPACE pause/play   LEFT/RIGHT sync trim ({offset_ms:+d} ms)   ESC quit",
                True, (200, 200, 220))
            screen.blit(hint, (30, h - 30))

        pygame.display.flip()
        clock.tick(60)

    stop.set()
    pygame.quit()


if __name__ == "__main__":
    main()
