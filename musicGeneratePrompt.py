import csv
import json
import os
import sys
import time

import gspread
import openai
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials

# .env.local から環境変数を読み込み
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env.local"))

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
SPREADSHEET_KEY = os.environ["SPREADSHEET_KEY"]
JSON_KEY_FILE = os.path.join(os.path.dirname(__file__), "aisoundproject-3d0397bfb4ff.json")

client = openai.OpenAI(api_key=OPENAI_API_KEY)


def generate_music_prompts(playlist_name: str, total_count: int = 50) -> list[dict]:
    """
    プレイリスト名に合わせた多様な音楽タイトルとSunoAI用プロンプトを生成する。
    BPM・楽器・雰囲気などをプレイリスト名の範疇で幅広く考えさせる。
    """
    # 1回のAPIコールで最大25曲（トークン制限を考慮して分割）
    batch_size = 25
    all_tracks: list[dict] = []

    for batch_idx in range(0, total_count, batch_size):
        count = min(batch_size, total_count - batch_idx)
        batch_num = batch_idx // batch_size + 1
        total_batches = (total_count + batch_size - 1) // batch_size
        print(f"Batch {batch_num}/{total_batches} generating ({count} tracks)...")

        prompt = f"""
You are a music producer creating a playlist called "{playlist_name}".
Generate {count} unique instrumental music tracks for this playlist.

Return a JSON object with a "tracks" key containing a list of objects.
Each object must have:
- "title": Creative and evocative track title (in English)
- "prompt": A detailed SunoAI generation prompt describing the sound. MUST include "no vocals, instrumental". Include specific details about instruments, tempo, mood, texture, and production style.
- "genre": Specific sub-genre that fits the playlist theme
- "bpm": Appropriate BPM as an integer
- "mood": 2-3 mood/atmosphere keywords separated by commas

Requirements:
- Every prompt MUST contain the phrase "no vocals, instrumental"
- All tracks must fit the "{playlist_name}" playlist theme
- Vary the BPM, instruments, mood, and sub-genres within the playlist's scope to create diversity
- Avoid repetitive or similar-sounding tracks
- Prompts should be detailed enough for SunoAI to produce distinct tracks (50-100 words each)
- If this is batch {batch_num} of {total_batches}, ensure variety from previous batches by exploring different tempos and textures
"""

        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            batch_json = json.loads(response.choices[0].message.content)
            items = batch_json.get("tracks", [])

            # "no vocals, instrumental" が含まれていない場合は補完
            for item in items:
                p = item.get("prompt", "")
                if "no vocals" not in p.lower():
                    item["prompt"] = p.rstrip(".") + ". No vocals, instrumental."

            all_tracks.extend(items)
            print(f"  -> Got {len(items)} tracks")
        except Exception as e:
            print(f"Error in batch {batch_num}: {e}")

        if batch_idx + batch_size < total_count:
            time.sleep(1)

    return all_tracks


def save_to_csv(tracks: list[dict], playlist_name: str) -> str:
    """csv/プレイリスト名_prompt.csv に保存"""
    csv_dir = os.path.join(os.path.dirname(__file__), "csv")
    os.makedirs(csv_dir, exist_ok=True)
    filepath = os.path.join(csv_dir, f"{playlist_name}_prompt.csv")

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Title", "Suno Prompt", "Genre", "BPM", "Mood"])
        for track in tracks:
            writer.writerow([
                track.get("title", ""),
                track.get("prompt", ""),
                track.get("genre", ""),
                track.get("bpm", 0),
                track.get("mood", ""),
            ])

    print(f"Saved {len(tracks)} tracks to {filepath}")
    return filepath


def save_to_sheets(tracks: list[dict], playlist_name: str) -> None:
    """Google スプレッドシートにも同様の内容を保存"""
    if not tracks:
        print("No data to save to sheets.")
        return

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEY_FILE, scope)
    client_gspread = gspread.authorize(creds)

    spreadsheet = client_gspread.open_by_key(SPREADSHEET_KEY)

    # プレイリスト名のシートを取得 or 作成
    try:
        sheet = spreadsheet.worksheet(playlist_name)
        sheet.clear()
    except gspread.exceptions.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title=playlist_name, rows=str(len(tracks) + 1), cols="5")

    headers = ["Title", "Suno Prompt", "Genre", "BPM", "Mood"]
    rows = [headers]
    for track in tracks:
        rows.append([
            track.get("title", ""),
            track.get("prompt", ""),
            track.get("genre", ""),
            track.get("bpm", 0),
            track.get("mood", ""),
        ])

    sheet.update(range_name=f"A1:E{len(rows)}", values=rows)
    print(f"Saved {len(tracks)} tracks to Google Sheets (sheet: {playlist_name})")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python musicGeneratePrompt.py <playlist_name>")
        print("Example: python musicGeneratePrompt.py 'Cafe BGM'")
        sys.exit(1)

    playlist_name = sys.argv[1]
    print(f"Generating 50 tracks for playlist: {playlist_name}")

    tracks = generate_music_prompts(playlist_name, total_count=50)

    # タイトルの重複チェック
    titles = [t.get("title", "") for t in tracks]
    seen: dict[str, int] = {}
    duplicates: list[str] = []
    for title in titles:
        key = title.strip().lower()
        if key in seen:
            duplicates.append(title)
        else:
            seen[key] = 1
    if duplicates:
        print(f"ERROR: Duplicate titles found: {duplicates}")
        sys.exit(1)

    save_to_csv(tracks, playlist_name)
    save_to_sheets(tracks, playlist_name)

    print(f"Done! Generated {len(tracks)} tracks.")
