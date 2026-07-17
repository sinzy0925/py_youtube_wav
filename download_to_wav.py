#!/usr/bin/env python3
"""YouTube URL一覧からMP4を取得し、WAVに変換する。"""

from __future__ import annotations

import argparse
import json
import platform
import re
import subprocess
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import random_user_agent, sanitize_filename

ROOT = Path(__file__).resolve().parent
URL_FILE = ROOT / "youtube_url.txt"
WAV_DIR = ROOT / "wav"
TEMP_DIR = ROOT / "tmp_mp4"
MAX_RETRIES = 2

VIDEO_ID_RE = re.compile(
    r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|embed/|shorts/))([A-Za-z0-9_-]{11})"
)


def fetch_latest_user_agent() -> str:
    """最新のChrome ユーザーエージェントを取得する。"""
    os_hint = "Windows NT 10.0" if platform.system() == "Windows" else "X11; Linux x86_64"
    try:
        with urllib.request.urlopen(
            "https://jnrbsn.github.io/user-agents/user-agents.json",
            timeout=15,
        ) as response:
            agents = json.load(response)
        for agent in agents:
            if os_hint in agent and "Chrome/" in agent and "Edg/" not in agent:
                return agent
    except Exception as exc:
        print(f"警告: 最新UAの取得に失敗しました ({exc})。yt-dlpのUAを使用します。")
    return random_user_agent()


def build_ydl_opts(user_agent: str, cookies: Path | None = None, *, quiet: bool = False) -> dict:
    opts: dict = {
        "http_headers": {"User-Agent": user_agent},
        "quiet": quiet,
        "no_warnings": quiet,
        "retries": 10,
        "fragment_retries": 10,
        "sleep_interval": 1,
        "max_sleep_interval": 5,
    }
    if cookies and cookies.exists():
        opts["cookiefile"] = str(cookies)
    return opts


def extract_video_id(url: str) -> str | None:
    match = VIDEO_ID_RE.search(url.strip())
    return match.group(1) if match else None


def extract_filename_title(title: str) -> str:
    """タイトルの区切り文字より左側をファイル名用に使う。"""
    for separator in ("|", "---"):
        if separator in title:
            return title.split(separator, 1)[0].strip()
    return title.strip()


def title_to_filename(title: str) -> str:
    display = extract_filename_title(title).replace("/", "／")
    name = sanitize_filename(display, restricted=False)
    return name or "untitled"


def fetch_playlist_entries(
    playlist_url: str,
    user_agent: str,
    cookies: Path | None = None,
) -> tuple[str, list[dict]]:
    """プレイリストのタイトルと動画一覧（プレイリスト順）を取得する。"""
    ydl_opts = {
        **build_ydl_opts(user_agent, cookies, quiet=True),
        "extract_flat": "in_playlist",
        "lazy_playlist": False,
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(playlist_url.strip(), download=False)

    playlist_title = info.get("title") or "playlist"
    entries: list[dict] = []
    for index, entry in enumerate(info.get("entries") or [], start=1):
        if not entry:
            continue
        video_id = entry.get("id")
        if not video_id:
            continue
        url = entry.get("url") or entry.get("webpage_url")
        if not url:
            url = f"https://www.youtube.com/watch?v={video_id}"
        title = entry.get("title") or video_id
        entries.append(
            {
                "index": index,
                "url": url,
                "title": title,
                "video_id": video_id,
            }
        )
    return playlist_title, entries


def numbered_wav_path(
    output_dir: Path,
    index: int,
    total: int,
    title: str,
    video_id: str,
) -> Path:
    width = max(2, len(str(total)))
    prefix = f"{index:0{width}d}"
    base = title_to_filename(title)
    primary = output_dir / f"{prefix} - {base}.wav"
    if not primary.exists():
        return primary
    return output_dir / f"{prefix} - {base}_{video_id}.wav"


def fetch_video_info(url: str, user_agent: str, cookies: Path | None = None) -> dict:
    ydl_opts = build_ydl_opts(user_agent, cookies, quiet=True)
    with YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)


def handle_existing_files(title: str, video_id: str, index: int, total: int) -> bool:
    """既存ファイルのスキップまたはリネーム。処理済みなら True。"""
    base = title_to_filename(title)
    legacy = WAV_DIR / f"{video_id}.wav"
    primary = WAV_DIR / f"{base}.wav"
    alt = WAV_DIR / f"{base}_{video_id}.wav"

    if legacy.exists():
        if not primary.exists():
            legacy.rename(primary)
            print(f"[{index}/{total}] リネーム: {legacy.name} → {primary.name}")
            return True
        if not alt.exists():
            legacy.rename(alt)
            print(f"[{index}/{total}] リネーム: {legacy.name} → {alt.name}")
            return True
        legacy.unlink()
        print(f"[{index}/{total}] スキップ: 同一内容の別名ファイルあり ({alt.name})")
        return True

    for path in (primary, alt):
        if path.exists():
            print(f"[{index}/{total}] スキップ: 既に存在します: {path.name}")
            return True
    return False


def new_wav_path(title: str, video_id: str) -> Path:
    base = title_to_filename(title)
    primary = WAV_DIR / f"{base}.wav"
    if not primary.exists():
        return primary
    return WAV_DIR / f"{base}_{video_id}.wav"


def parse_urls_from_text(text: str) -> list[str]:
    urls: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def load_urls(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"URLファイルが見つかりません: {path}")
    return parse_urls_from_text(path.read_text(encoding="utf-8"))


def resolve_urls(args: argparse.Namespace) -> list[str]:
    if args.stdin:
        return parse_urls_from_text(sys.stdin.read())

    urls: list[str] = []
    if args.urls:
        urls.extend(parse_urls_from_text(args.urls))
    if args.file:
        urls.extend(load_urls(Path(args.file)))
    elif not args.url and not args.urls and URL_FILE.exists():
        urls.extend(load_urls(URL_FILE))
    urls.extend(args.url)

    seen: set[str] = set()
    unique_urls: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    return unique_urls


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="YouTube URLからMP4を取得しWAVに変換する")
    parser.add_argument("url", nargs="*", help="YouTube URL")
    parser.add_argument("-f", "--file", help="URL一覧ファイル")
    parser.add_argument("-u", "--urls", help="改行区切りのURL文字列")
    parser.add_argument("--stdin", action="store_true", help="標準入力からURLを読み込む")
    parser.add_argument(
        "--cookies",
        help="YouTube cookies.txt（Netscape形式）。GitHub Actionsでは secrets から渡す",
    )
    parser.add_argument(
        "--playlist",
        help="YouTubeプレイリストURL（プレイリスト順に番号付きで専用フォルダへ出力）",
    )
    return parser


def download_mp4(
    url: str,
    video_id: str,
    user_agent: str,
    temp_dir: Path,
    cookies: Path | None = None,
) -> Path:
    output_template = str(temp_dir / f"{video_id}.%(ext)s")
    ydl_opts = {
        **build_ydl_opts(user_agent, cookies, quiet=False),
        "format": "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio/best",
        "outtmpl": output_template,
        "merge_output_format": "mp4",
    }

    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    mp4_path = temp_dir / f"{video_id}.mp4"
    if not mp4_path.exists():
        candidates = list(temp_dir.glob(f"{video_id}.*"))
        if not candidates:
            raise FileNotFoundError(f"MP4のダウンロードに失敗しました: {url}")
        mp4_path = candidates[0]
    return mp4_path


def convert_to_wav(mp4_path: Path, wav_path: Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(mp4_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "44100",
        "-ac",
        "2",
        str(wav_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg変換失敗:\n{result.stderr}")


def with_retries(
    label: str,
    fn: Callable[[], tuple[bool, str | None]],
) -> tuple[bool, str | None]:
    """失敗時に最大 MAX_RETRIES 回まで再試行する。"""
    result: tuple[bool, str | None] = (False, None)
    for attempt in range(MAX_RETRIES + 1):
        if attempt > 0:
            print(f"{label} リトライ {attempt}/{MAX_RETRIES}")
        result = fn()
        if result[0]:
            return result
    return result


def process_playlist_entry(
    entry: dict,
    total: int,
    user_agent: str,
    output_dir: Path,
    cookies: Path | None = None,
) -> tuple[bool, str | None]:
    index = entry["index"]
    url = entry["url"]
    video_id = entry["video_id"]
    title = entry["title"]

    width = max(2, len(str(total)))
    prefix = f"{index:0{width}d}"
    existing = sorted(output_dir.glob(f"{prefix} - *.wav"))
    if existing:
        print(f"[{index}/{total}] スキップ: 既に存在します: {existing[0].name}")
        return True, None

    try:
        info = fetch_video_info(url, user_agent, cookies)
        title = info.get("title") or title
    except Exception as exc:
        print(f"[{index}/{total}] エラー: {video_id} - タイトル取得失敗: {exc}", file=sys.stderr)
        return False, url

    wav_path = numbered_wav_path(output_dir, index, total, title, video_id)
    print(f"[{index}/{total}] 処理開始: {title} ({url})")

    mp4_path: Path | None = None
    try:
        mp4_path = download_mp4(url, video_id, user_agent, TEMP_DIR, cookies)
        convert_to_wav(mp4_path, wav_path)
        print(f"[{index}/{total}] 完了: {wav_path}")
        return True, None
    except Exception as exc:
        print(f"[{index}/{total}] エラー: {title} - {exc}", file=sys.stderr)
        if wav_path.exists():
            wav_path.unlink()
        return False, url
    finally:
        if mp4_path and mp4_path.exists():
            mp4_path.unlink()


def run_playlist(
    playlist_url: str,
    user_agent: str,
    cookies: Path | None = None,
) -> int:
    try:
        playlist_title, entries = fetch_playlist_entries(playlist_url, user_agent, cookies)
    except Exception as exc:
        print(f"プレイリスト取得失敗: {exc}", file=sys.stderr)
        return 1

    if not entries:
        print("プレイリストに動画がありません。", file=sys.stderr)
        return 1

    output_dir = WAV_DIR / title_to_filename(playlist_title)
    output_dir.mkdir(parents=True, exist_ok=True)

    total = len(entries)
    print(f"プレイリスト: {playlist_title}")
    print(f"出力先: {output_dir}")
    print(f"動画数: {total}（直列処理）\n")

    success = 0
    failed = 0
    failed_urls: list[str] = []
    for entry in entries:
        index = entry["index"]
        ok, failed_url = with_retries(
            f"[{index}/{total}]",
            lambda entry=entry: process_playlist_entry(
                entry, total, user_agent, output_dir, cookies
            ),
        )
        if ok:
            success += 1
        else:
            failed += 1
            if failed_url:
                failed_urls.append(failed_url)

    print(f"\n処理完了: 成功 {success} / 失敗 {failed} / 合計 {total}")
    if failed_urls:
        print("\n失敗したURL:")
        for failed_url in failed_urls:
            print(failed_url)
    return 0 if failed == 0 else 1


def process_url(
    url: str,
    index: int,
    total: int,
    user_agent: str,
    cookies: Path | None = None,
) -> tuple[bool, str | None]:
    video_id = extract_video_id(url)
    if not video_id:
        print(f"[{index}/{total}] スキップ: 動画IDを抽出できません: {url}")
        return False, url

    try:
        info = fetch_video_info(url, user_agent, cookies)
        title = info.get("title") or video_id
    except Exception as exc:
        print(f"[{index}/{total}] エラー: {video_id} - タイトル取得失敗: {exc}", file=sys.stderr)
        return False, url

    existing = handle_existing_files(title, video_id, index, total)
    if existing:
        return True, None

    wav_path = new_wav_path(title, video_id)
    print(f"[{index}/{total}] 処理開始: {title} ({url})")

    mp4_path: Path | None = None
    try:
        mp4_path = download_mp4(url, video_id, user_agent, TEMP_DIR, cookies)
        convert_to_wav(mp4_path, wav_path)
        print(f"[{index}/{total}] 完了: {wav_path.name}")
        return True, None
    except Exception as exc:
        print(f"[{index}/{total}] エラー: {title} - {exc}", file=sys.stderr)
        if wav_path.exists():
            wav_path.unlink()
        return False, url
    finally:
        if mp4_path and mp4_path.exists():
            mp4_path.unlink()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    WAV_DIR.mkdir(exist_ok=True)
    TEMP_DIR.mkdir(exist_ok=True)

    cookies = Path(args.cookies) if args.cookies else None
    if cookies and not cookies.exists():
        print(f"Cookieファイルが見つかりません: {cookies}", file=sys.stderr)
        return 1

    user_agent = fetch_latest_user_agent()
    print(f"User-Agent: {user_agent}")
    if cookies:
        print(f"Cookies: {cookies}")
    print()

    if args.playlist:
        return run_playlist(args.playlist, user_agent, cookies)

    try:
        urls = resolve_urls(args)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1

    if not urls:
        print("処理対象のURLがありません。", file=sys.stderr)
        return 1

    total = len(urls)
    print(f"URL数: {total}（直列処理）\n")

    success = 0
    failed = 0
    failed_urls: list[str] = []
    for index, url in enumerate(urls, start=1):
        ok, failed_url = with_retries(
            f"[{index}/{total}]",
            lambda url=url, index=index: process_url(
                url, index, total, user_agent, cookies
            ),
        )
        if ok:
            success += 1
        else:
            failed += 1
            if failed_url:
                failed_urls.append(failed_url)

    print(f"\n処理完了: 成功 {success} / 失敗 {failed} / 合計 {total}")
    if failed_urls:
        print("\n失敗したURL:")
        for failed_url in failed_urls:
            print(failed_url)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
