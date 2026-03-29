"""
backfill_metadata.py
DBの既存トラックに対して、CSVからメタデータ(suno_prompt, genre, bpm, vibe_tags)を埋め、
OpenAIで use_case, energy_level を生成して更新する。

Usage:
    python backfill_metadata.py "Lo-Fi Hip Hop"
"""

import csv
import json
import os
import sys

import openai
from dotenv import load_dotenv
from supabase import create_client

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env.local"))

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
SUPABASE_URL = os.environ["NEXT_PUBLIC_SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

oai = openai.OpenAI(api_key=OPENAI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def load_csv(playlist_name: str) -> dict[str, dict]:
    """CSVを読み込み、title→メタデータの辞書を返す。"""
    csv_path = os.path.join(os.path.dirname(__file__), "csv", f"{playlist_name}_prompt.csv")
    if not os.path.exists(csv_path):
        print(f"ERROR: CSV not found: {csv_path}")
        sys.exit(1)

    result = {}
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = row["Title"].strip()
            result[title] = {
                "suno_prompt": row["Suno Prompt"].strip(),
                "genre": row["Genre"].strip(),
                "bpm": int(row["BPM"]) if row["BPM"].strip().isdigit() else None,
                "vibe_tags": [v.strip() for v in row.get("vibe_tags", row.get("Mood", "")).split(",") if v.strip()],
            }
    return result


def generate_use_case_energy(tracks_meta: list[dict]) -> dict[str, dict]:
    """
    OpenAI に一括で use_case と energy_level を生成させる。
    tracks_meta: [{"title": ..., "genre": ..., "bpm": ..., "vibe_tags": ..., "suno_prompt": ...}, ...]
    戻り値: {title: {"use_case": [...], "energy_level": "..."}}
    """
    # 25曲ずつバッチ処理
    batch_size = 25
    all_results: dict[str, dict] = {}

    for i in range(0, len(tracks_meta), batch_size):
        batch = tracks_meta[i : i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(tracks_meta) + batch_size - 1) // batch_size
        print(f"  OpenAI batch {batch_num}/{total_batches} ({len(batch)} tracks)...")

        tracks_info = json.dumps(
            [{"title": t["title"], "genre": t["genre"], "bpm": t["bpm"],
              "vibe_tags": t["vibe_tags"], "suno_prompt": t["suno_prompt"]}
             for t in batch],
            ensure_ascii=False,
        )

        prompt = f"""Given these music tracks, generate use_case and energy_level for each.

Tracks:
{tracks_info}

For each track, return:
- "use_case": list of 2-4 usage scenarios (e.g. "studying", "cooking", "morning routine", "meditation", "work focus", "relaxation", "driving", "party", "workout", "reading", "cafe background", "sleep")
- "energy_level": integer from 1 to 5 (1=very calm/chill, 2=low energy, 3=medium, 4=high energy, 5=very high energy/intense)

Base your choices on the genre, BPM, vibe_tags, and suno_prompt.

Return a JSON object with a "tracks" key containing a list of objects, each with "title", "use_case", and "energy_level".
"""

        response = oai.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        for item in result.get("tracks", []):
            all_results[item["title"]] = {
                "use_case": item["use_case"],
                "energy_level": item["energy_level"],
            }

    return all_results


def main(playlist_name: str) -> None:
    # R2パスのslug
    slug = playlist_name.lower().replace(" ", "-")

    # 1. DBからトラック取得
    print(f"Fetching tracks with r2_key like '{slug}/%' ...")
    res = supabase.table("tracks").select("id, title, r2_key").like("r2_key", f"{slug}/%").execute()
    db_tracks = res.data
    if not db_tracks:
        print("ERROR: No tracks found in DB.")
        sys.exit(1)
    print(f"  Found {len(db_tracks)} tracks in DB.")

    # 2. CSV読み込み
    print(f"Loading CSV: csv/{playlist_name}_prompt.csv ...")
    csv_data = load_csv(playlist_name)
    print(f"  Loaded {len(csv_data)} entries from CSV.")

    # 3. タイトルでマッチング
    matched = []
    unmatched_db = []
    for track in db_tracks:
        title = track["title"]
        if title in csv_data:
            matched.append({**track, **csv_data[title]})
        else:
            unmatched_db.append(title)

    print(f"  Matched: {len(matched)}, Unmatched in DB: {len(unmatched_db)}")
    if unmatched_db:
        print(f"  Unmatched titles: {unmatched_db[:5]}...")

    if not matched:
        print("ERROR: No matches found.")
        sys.exit(1)

    # 4. OpenAI で use_case, energy_level 生成
    print("Generating use_case & energy_level via OpenAI...")
    ai_results = generate_use_case_energy(matched)

    # 5. DB更新
    print("Updating DB...")
    updated = 0
    for track in matched:
        title = track["title"]
        ai = ai_results.get(title, {})

        update_data = {
            "suno_prompt": track["suno_prompt"],
            "genre": track["genre"],
            "bpm": track["bpm"],
            "vibe_tags": track["vibe_tags"],
            "use_case": ai.get("use_case", []),
            "energy_level": ai.get("energy_level"),
        }

        supabase.table("tracks").update(update_data).eq("id", track["id"]).execute()
        updated += 1
        print(f"  [{updated}/{len(matched)}] {title} ✓")

    print(f"\nDone! Updated {updated} tracks for '{playlist_name}'.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python backfill_metadata.py "Lo-Fi Hip Hop"')
        sys.exit(1)

    main(sys.argv[1])
