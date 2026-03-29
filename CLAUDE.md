
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

## ① musicGeneratePrompt/

- プレイリスト名を引数で指定する
- Claude API を使って Suno 用プロンプトを生成
- 出力形式: CSV（1列目: タイトル、2列目: プロンプト）
- 生成した CSV は `csv/` フォルダに保存する

```bash
npx ts-node musicGeneratePrompt/index.ts --playlist "Cafe BGM"
# → csv/cafe-bgm.csv を生成
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

## ④ inputDB/

- ダウンロードした MP3 を `input/` フォルダに置いて実行する
- 処理内容：
  1. MP3 から埋め込み画像（アルバムアート）を分離して抽出
  2. MP3 ファイルを Cloudflare R2 にアップロード
  3. 画像ファイルを Cloudflare R2 にアップロード
  4. R2 のパス・メタデータを Supabase の `tracks` テーブルに登録
  5. `playlist` テーブルに公式プレイリストとして追加 `playlist_tracks` テーブルに曲を追加


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
