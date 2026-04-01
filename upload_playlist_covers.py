"""
playlists/ フォルダの画像を R2 にアップロードし、
Supabase の playlists テーブルの cover_image_url を更新する。

Usage:
    python upload_playlist_covers.py
"""

import os
import sys
from pathlib import Path

import boto3
from dotenv import load_dotenv
from supabase import create_client

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env.local"))

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

MIME_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

PLAYLISTS_DIR = os.path.join(os.path.dirname(__file__), "playlists")


def upload_to_r2(local_path: str, r2_key: str, content_type: str) -> None:
    with open(local_path, "rb") as f:
        s3.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=r2_key,
            Body=f,
            ContentType=content_type,
        )


def main():
    if not os.path.isdir(PLAYLISTS_DIR):
        print(f"ERROR: Directory not found: {PLAYLISTS_DIR}")
        sys.exit(1)

    image_files = [
        p for p in Path(PLAYLISTS_DIR).iterdir()
        if p.suffix.lower() in MIME_MAP
    ]

    if not image_files:
        print("No image files found in playlists/")
        sys.exit(1)

    print(f"Found {len(image_files)} images\n")

    for img_path in sorted(image_files):
        playlist_name = img_path.stem  # ファイル名（拡張子なし）= プレイリスト名
        ext = img_path.suffix.lower()
        mime = MIME_MAP[ext]

        # R2 キー: playlists/{ファイル名}
        r2_key = f"playlists/{img_path.name}"

        # 1. R2 にアップロード
        print(f"[{playlist_name}]")
        print(f"  Uploading → {r2_key}")
        upload_to_r2(str(img_path), r2_key, mime)

        # 2. Supabase の playlists テーブルを更新
        res = supabase.table("playlists").select("id").eq("name", playlist_name).execute()
        if res.data:
            playlist_id = res.data[0]["id"]
            supabase.table("playlists").update({
                "cover_image_url": r2_key,
            }).eq("id", playlist_id).execute()
            print(f"  ✓ Updated playlist (id={playlist_id})")
        else:
            print(f"  ⚠ Playlist '{playlist_name}' not found in DB — skipped DB update")

    print("\nDone!")


if __name__ == "__main__":
    main()
