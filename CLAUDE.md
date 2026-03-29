
# 楽曲制作ワークフロー（ai-music-player-tools）

```
musicGeneratePrompt/          # ① Suno用プロンプトCSVを生成
        ↓
      csv/                    # ② 生成されたCSVの置き場
        ↓
chromePlugin/                 # ③ SunoへCSVを一括流し込み（ダウンロードは手動）
        ↓
inputDB/                      # ④ ダウンロードしたMP3を処理・DBへ投入
```

## ① musicGeneratePrompt.py

- プレイリスト名を引数で指定する
- OpenAI (gpt-4o) を使って Suno 用プロンプトを50曲分生成（25曲×2バッチ）
- 出力形式: CSV（Title, Suno Prompt, Genre, BPM, vibe_tags）
- 生成した CSV は `csv/` フォルダに `{プレイリスト名}_prompt.csv` として保存
- Google スプレッドシートにも同名シートで保存
- タイトル重複時は自動でサフィックス付与（例: `Whispering Pines (2)`）

```bash
python musicGeneratePrompt.py 'Cafe BGM'
# → csv/Cafe BGM_prompt.csv を生成 + Google Sheets に保存
```

## ② csv/

- `musicGeneratePrompt/` が出力したCSVの置き場
- `chromePlugin/` がここのCSVを読み込む
- ファイル名はプレイリストのslugに合わせる（例: `cafe-bgm.csv`）

## ③ chromePlugin/

- Chrome拡張機能（`suno-extension/`）
- `csv/` のCSVを貼り付けて Suno に一括流し込む
- 生成間隔は60秒（設定可能）
- **ダウンロードは手動**で行う

## ④ inputDB/process.py

- ダウンロードした MP3 を `inputDB/{プレイリスト名}/` フォルダに置いて実行する
- 処理内容：
  1. MP3 から埋め込み画像（アルバムアート）を分離して抽出
  2. MP3 ファイルを Cloudflare R2 にアップロード（パス: `{slug}/{曲名}.mp3`）
  3. 画像ファイルを Cloudflare R2 にアップロード（パス: `{slug}/{曲名}.jpg`）
  4. R2 のパス・メタデータを Supabase の `tracks` テーブルに登録
  5. `playlists` テーブルに公式プレイリストとして取得 or 作成
  6. `playlist_tracks` テーブルに曲を追加（position は既存の続きから採番）

```bash
python inputDB/process.py 'EDM & Festival'
# → inputDB/EDM & Festival/*.mp3 を処理
```

## ⑤ backfill_metadata.py

- inputDB で登録済みのトラックに対して、CSVからメタデータを埋め戻す
- r2_key のパス（slug）でDBからトラックを取得し、タイトルでCSVとマッチング
- 処理内容：
  1. CSVから `suno_prompt`, `genre`, `bpm`, `vibe_tags` を埋める
  2. OpenAI (gpt-4o) で `use_case`（利用シーン配列）と `energy_level`（1-5整数）を生成
  3. Supabase の `tracks` テーブルを更新
- CSVヘッダーは `vibe_tags` / `Mood` どちらにも対応

```bash
python backfill_metadata.py 'Lo-Fi Hip Hop'
# → lo-fi-hip-hop/* のトラックを csv/Lo-Fi Hip Hop_prompt.csv で埋め戻し
```


## tracks（楽曲メタデータ）

カラム名,型,説明
id,uuid,PK (主キー)
title,text,曲名
artist,text,アーティスト名
album,text,アルバム名（プレイリスト名など）
r2_key,text,R2上のMP3ファイルパス
image_r2_key,text,R2上のジャケット画像パス
genre,text,ジャンル（例: Progressive Trance）
bpm,integer,テンポ（フィルタリング・ソート用）
energy_level,integer,1（静寂）〜5（激しい）の5段階評価
vibe_tags,text[],"特徴タグ（例: ['uplifting', 'cosmic']）"
use_case,text[],"用途（例: ['focus', 'coding', 'cafe']）"
is_instrumental,boolean,インスト曲フラグ（今回は基本 True）
duration_sec,integer,再生時間（秒）
suno_prompt,text,生成時のプロンプト（AI分析・再生成用）
created_at,timestamptz,レコード作成日時

## playlists（公式＋ユーザープレイリスト）

| カラム | 型 | 説明 |
|---|---|---|
| id | uuid | PK |
| name | text | プレイリスト名 |
| user_id | uuid | FK → auth.users（公式は NULL） |
| is_official | boolean | 公式: true / ユーザー: false |
| cover_image_url | text | カバー画像URL |
| created_at | timestamptz | |

## playlist_tracks（中間テーブル）

| カラム | 型 | 説明 |
|---|---|---|
| id | uuid | PK |
| playlist_id | uuid | FK → playlists |
| track_id | uuid | FK → tracks |
| position | int | 曲順 |

---
