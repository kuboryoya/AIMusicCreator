"""
inputDB/process.py
MP3ファイルからアルバムアート画像を分離し、MP3・画像をR2にアップロード、
メタデータをSupabaseのtracksテーブルに登録する。

Usage:
    python inputDB/process.py <playlist_name>
    例: python inputDB/process.py "Cafe BGM"
"""

import os
import sys
import uuid
from pathlib import Path

import boto3
from dotenv import load_dotenv
from mutagen.mp3 import MP3
from supabase import create_client

# .env.local 読み込み
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env.local"))

# ── R2 設定 ──
R2_ACCOUNT_ID = os.environ["R2_ACCOUNT_ID"]
R2_ACCESS_KEY_ID = os.environ["R2_ACCESS_KEY_ID"]
R2_SECRET_ACCESS_KEY = os.environ["R2_SECRET_ACCESS_KEY"]
R2_BUCKET_NAME = os.environ["R2_BUCKET_NAME"]
R2_ENDPOINT = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

# ── Supabase 設定 ──
SUPABASE_URL = os.environ["NEXT_PUBLIC_SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

s3 = boto3.client(
    "s3",
    endpoint_url=R2_ENDPOINT,
    aws_access_key_id=R2_ACCESS_KEY_ID,
    aws_secret_access_key=R2_SECRET_ACCESS_KEY,
    region_name="auto",
)

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# 画像MIMEタイプ → 拡張子
MIME_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def extract_image(mp3_path: str, output_dir: str) -> str | None:
    """MP3からAPIC(アルバムアート)を抽出し、画像ファイルとして保存。パスを返す。"""
    tags = MP3(mp3_path).tags
    if not tags:
        return None

    for key in tags:
        if key.startswith("APIC"):
            apic = tags[key]
            ext = MIME_TO_EXT.get(apic.mime, ".jpg")
            stem = Path(mp3_path).stem
            img_path = os.path.join(output_dir, f"{stem}{ext}")
            with open(img_path, "wb") as f:
                f.write(apic.data)
            return img_path
    return None


def upload_to_r2(local_path: str, r2_key: str, content_type: str) -> None:
    """ファイルをR2にアップロード。"""
    with open(local_path, "rb") as f:
        s3.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=r2_key,
            Body=f,
            ContentType=content_type,
        )


def process_playlist(playlist_name: str) -> None:
    input_dir = os.path.join(os.path.dirname(__file__), playlist_name)
    if not os.path.isdir(input_dir):
        print(f"ERROR: Directory not found: {input_dir}")
        sys.exit(1)

    mp3_files = sorted(Path(input_dir).glob("*.mp3"))
    if not mp3_files:
        print(f"ERROR: No .mp3 files found in {input_dir}")
        sys.exit(1)

    # 画像出力用の一時ディレクトリ
    img_dir = os.path.join(input_dir, "_images")
    os.makedirs(img_dir, exist_ok=True)

    # プレイリスト名をR2パスに使う slug (スペース→ハイフン、小文字)
    slug = playlist_name.lower().replace(" ", "-")

    print(f"Processing {len(mp3_files)} MP3 files from: {input_dir}\n")

    # ── playlist の取得 or 作成 ──
    res = supabase.table("playlists").select("id").eq("name", playlist_name).execute()
    if res.data:
        playlist_id = res.data[0]["id"]
        print(f"Found existing playlist: {playlist_id}")
    else:
        playlist_id = str(uuid.uuid4())
        supabase.table("playlists").insert({
            "id": playlist_id,
            "name": playlist_name,
            "is_official": True,
        }).execute()
        print(f"Created playlist: {playlist_id}")

    # 既存 track 数 → position の開始値
    pos_res = (
        supabase.table("playlist_tracks")
        .select("position")
        .eq("playlist_id", playlist_id)
        .order("position", desc=True)
        .limit(1)
        .execute()
    )
    next_position = (pos_res.data[0]["position"] + 1) if pos_res.data else 0

    for i, mp3_path in enumerate(mp3_files):
        mp3_path_str = str(mp3_path)
        stem = mp3_path.stem
        print(f"[{i+1}/{len(mp3_files)}] {stem}")

        # メタデータ取得
        audio = MP3(mp3_path_str)
        tags = audio.tags or {}
        title = str(tags.get("TIT2", stem))
        artist = ""
        album = str(tags.get("TALB", ""))
        duration = int(audio.info.length)

        # 1. 画像抽出
        img_path = extract_image(mp3_path_str, img_dir)

        # 2. R2 アップロード（MP3）
        r2_mp3_key = f"{slug}/{stem}.mp3"
        print(f"  Uploading MP3 → {r2_mp3_key}")
        upload_to_r2(mp3_path_str, r2_mp3_key, "audio/mpeg")

        # 3. R2 アップロード（画像）
        r2_img_key = None
        if img_path:
            ext = Path(img_path).suffix
            r2_img_key = f"{slug}/{stem}{ext}"
            mime = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(ext, "image/jpeg")
            print(f"  Uploading image → {r2_img_key}")
            upload_to_r2(img_path, r2_img_key, mime)

        # 4. Supabase に track 登録
        track_id = str(uuid.uuid4())
        supabase.table("tracks").insert({
            "id": track_id,
            "title": title,
            "artist": artist,
            "album": album,
            "duration": duration,
            "r2_key": r2_mp3_key,
            "image_r2_key": r2_img_key,
        }).execute()

        # 5. playlist_tracks に紐付け
        supabase.table("playlist_tracks").insert({
            "id": str(uuid.uuid4()),
            "playlist_id": playlist_id,
            "track_id": track_id,
            "position": next_position + i,
        }).execute()

        print(f"  ✓ Registered (track_id={track_id})")

    print(f"\nDone! Processed {len(mp3_files)} tracks for '{playlist_name}'.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python inputDB/process.py <playlist_name>")
        print('Example: python inputDB/process.py "Cafe BGM"')
        sys.exit(1)

    process_playlist(sys.argv[1])
