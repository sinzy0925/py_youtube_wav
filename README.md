# py_youtube_wav

YouTube の URL から MP4 をダウンロードし、WAV（PCM 44.1kHz / 16bit / ステレオ）に変換するツールです。

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) で動画を取得
- [ffmpeg](https://ffmpeg.org/) で音声を WAV に変換
- 複数 URL は **1件ずつ直列処理**
- 失敗時は **最大2回リトライ**（合計3回試行）
- 失敗した URL はログ末尾に一覧表示

## 必要なもの

| ツール | 用途 |
|--------|------|
| Python 3.10+ | スクリプト実行 |
| ffmpeg | WAV 変換 |
| yt-dlp | `pip install -r requirements.txt` |

任意: [Deno](https://deno.land/) を入れると yt-dlp の YouTube 対応が安定しやすくなります。

## セットアップ

```powershell
pip install -r requirements.txt
```

ffmpeg が PATH に通っていることを確認してください。

```powershell
ffmpeg -version
```

## 使い方

### URL ファイルから（デフォルト）

`youtube_url.txt` に1行1URLで記載し、実行します。

```powershell
python download_to_wav.py
```

別ファイルを指定する場合:

```powershell
python download_to_wav.py -f youtube_url_祭り.txt
```

### URL を直接指定

```powershell
python download_to_wav.py "https://www.youtube.com/watch?v=xxxxxxxxxxx"
```

### 標準入力から

```powershell
@"
https://youtu.be/xxxxx
https://youtu.be/yyyyy
"@ | python download_to_wav.py --stdin
```

### プレイリスト

プレイリスト順に番号付きファイルを専用フォルダへ出力します。

```powershell
python download_to_wav.py --playlist "https://www.youtube.com/playlist?list=xxxxxxxxxxx"
```

出力例:

```
wav/KATANA/
  01 - 疾風.wav
  02 - 刃.wav
  03 - 炎.wav
  ...
```

### クッキーを使う（ボット判定回避）

YouTube にブロックされた場合は、ログイン済みブラウザのクッキーを使います。

```powershell
yt-dlp --cookies-from-browser chrome --cookies cookies.txt --skip-download "https://www.youtube.com"
python download_to_wav.py -f youtube_url.txt --cookies cookies.txt
```

## ファイル名のルール

- 動画タイトルの `|` より**左側**をファイル名に使用
- `/` は `／`（全角スラッシュ）に置換
- 同名が衝突する場合は `_{動画ID}` を付加
- プレイリストは `01 - タイトル.wav` 形式（曲数に応じて桁数を調整）

## 出力先

| モード | 出力先 |
|--------|--------|
| 通常 | `wav/` |
| プレイリスト | `wav/{プレイリスト名}/` |

既に同名の WAV がある場合はスキップします（中断後の再開に対応）。

## GitHub Actions

GitHub 上から手動実行し、生成した WAV を Artifact としてダウンロードできます。

### 初回設定

1. リポジトリの **Settings → Secrets and variables → Actions**
2. `YOUTUBE_COOKIES` を追加（`cookies.txt` の中身を貼り付け）
3. **Actions** タブ → **Download YouTube to WAV** → **Run workflow**
4. `urls` 欄に URL を1行ずつ入力して実行
5. 完了後、実行結果ページの **Artifacts** から `wav-{番号}` をダウンロード

> GitHub Actions のサーバー IP は YouTube にボット判定されやすいため、`YOUTUBE_COOKIES` の設定を推奨します。クッキーは期限切れになることがあるので、失敗時は再エクスポートして Secret を更新してください。

参考: [yt-dlp FAQ - cookies](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp)

## オプション一覧

```
usage: download_to_wav.py [-h] [-f FILE] [-u URLS] [--stdin]
                          [--cookies COOKIES] [--playlist PLAYLIST]
                          [url ...]

  url                   YouTube URL
  -f, --file FILE       URL一覧ファイル
  -u, --urls URLS       改行区切りのURL文字列
  --stdin               標準入力からURLを読み込む
  --cookies COOKIES     YouTube cookies.txt（Netscape形式）
  --playlist PLAYLIST   プレイリストURL（番号付きで専用フォルダへ出力）
```

## ライセンス

このリポジトリのコードは自由に利用できます。ダウンロードする YouTube コンテンツの利用は、各動画の権利者と YouTube の利用規約に従ってください。
