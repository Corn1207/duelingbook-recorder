"""
routes.py

Flask routes for the duelingbook recorder app.
"""

import threading

from flask import Blueprint, jsonify, render_template, request

from app.database import get_connection

import logging
import time
from pathlib import Path

bp = Blueprint("main", __name__)
logger = logging.getLogger(__name__)

VALID_STATUSES = ["pending", "recorded", "thumbnail_ready", "uploaded"]
LOG_FILE = Path(__file__).parent.parent / "output" / "app.log"

# upload progress store: {row_id: {"pct": int, "done": bool, "error": str|None, "url": str|None}}
_upload_progress: dict = {}

# Tracks which replay IDs are currently being recorded
_recording_in_progress: set[str] = set()


def _run_pipeline(row_id: int, replay_id: str) -> None:
    """Runs the recording pipeline in a background thread."""
    from recorder.pipeline import RecordingPipeline

    def update(status, **kwargs):
        with get_connection() as conn:
            fields = {"status": status, **kwargs}
            set_clause = ", ".join(f"{k} = ?" for k in fields)
            conn.execute(
                f"UPDATE replays SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
                list(fields.values()) + [row_id],
            )
            conn.commit()

    try:
        pipeline = RecordingPipeline(obs_password="123456")
        final_path = pipeline.run(replay_id=replay_id)
        update("recorded", video_path=final_path)
        logging.getLogger(__name__).info(f"Recording finished: {final_path}")
    except Exception as e:
        update("pending")  # revert so user can retry
        logging.getLogger(__name__).error(f"Pipeline error for replay {replay_id}: {e}", exc_info=True)
    finally:
        _recording_in_progress.discard(replay_id)


@bp.route("/")
def index():
    return render_template("index.html")


@bp.route("/api/capture-replay", methods=["POST"])
def capture_replay():
    """Receives replay data from the Tampermonkey userscript."""
    data = request.json or {}
    replay_id = (data.get("replay_id") or "").strip()
    if not replay_id:
        return jsonify({"error": "replay_id is required"}), 400

    with get_connection() as conn:
        try:
            conn.execute("""
                INSERT INTO replays (replay_id, scheduled_date)
                VALUES (?, date('now'))
            """, (replay_id,))
            conn.commit()
            logger.info(f"Replay captured from browser: {replay_id}")
        except Exception as e:
            if "UNIQUE" in str(e):
                return jsonify({"error": "replay already exists"}), 409
            raise
    return jsonify({"ok": True}), 201


@bp.route("/api/logs", methods=["GET"])
def get_logs():
    lines = int(request.args.get("lines", 100))
    if not LOG_FILE.exists():
        return jsonify([])
    with open(LOG_FILE, encoding="utf-8") as f:
        all_lines = f.readlines()
    return jsonify([l.rstrip() for l in all_lines[-lines:]])


@bp.route("/api/logs", methods=["DELETE"])
def clear_logs():
    if LOG_FILE.exists():
        LOG_FILE.write_text("")
    return jsonify({"ok": True})


# ------------------------------------------------------------------
# Replays CRUD
# ------------------------------------------------------------------

@bp.route("/api/replays", methods=["GET"])
def list_replays():
    from_date = request.args.get("from")
    to_date   = request.args.get("to")
    with get_connection() as conn:
        if from_date and to_date:
            rows = conn.execute("""
                SELECT * FROM replays
                WHERE scheduled_date >= ? AND scheduled_date <= ?
                ORDER BY scheduled_date ASC, id ASC
            """, (from_date, to_date)).fetchall()
        elif from_date:
            rows = conn.execute("""
                SELECT * FROM replays
                WHERE scheduled_date >= ?
                ORDER BY scheduled_date ASC, id ASC
            """, (from_date,)).fetchall()
        elif to_date:
            rows = conn.execute("""
                SELECT * FROM replays
                WHERE scheduled_date <= ?
                ORDER BY scheduled_date ASC, id ASC
            """, (to_date,)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM replays ORDER BY scheduled_date ASC, id ASC"
            ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route("/api/replays", methods=["POST"])
def create_replay():
    data = request.json or {}
    replay_id = (data.get("replay_id") or "").strip()
    if not replay_id:
        return jsonify({"error": "replay_id is required"}), 400

    with get_connection() as conn:
        try:
            conn.execute("""
                INSERT INTO replays
                    (replay_id, deck1, deck2, label_left, label_right, title, description, tags, notes, scheduled_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                replay_id,
                data.get("deck1", ""),
                data.get("deck2", ""),
                data.get("label_left", "DUELINGBOOK"),
                data.get("label_right", "HIGH RATED"),
                data.get("title", ""),
                data.get("description", ""),
                data.get("tags", ""),
                data.get("notes", ""),
                data.get("scheduled_date") or None,
            ))
            conn.commit()
        except Exception as e:
            if "UNIQUE" in str(e):
                return jsonify({"error": "replay_id already exists"}), 409
            raise
    return jsonify({"ok": True}), 201


@bp.route("/api/replays/<int:row_id>", methods=["PUT"])
def update_replay(row_id: int):
    data = request.json or {}
    fields = ["deck1", "deck2", "label_left", "label_right", "title", "description",
              "tags", "notes", "scheduled_date", "publish_at", "status", "video_path", "thumbnail_path", "youtube_url"]
    updates = {k: data[k] for k in fields if k in data}
    if not updates:
        return jsonify({"error": "nothing to update"}), 400

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [row_id]

    with get_connection() as conn:
        conn.execute(
            f"UPDATE replays SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
            values,
        )
        conn.commit()
    return jsonify({"ok": True})


@bp.route("/api/replays/<int:row_id>/generate-metadata", methods=["POST"])
def generate_metadata(row_id: int):
    from postprocess.ai_metadata import generate_metadata as gen

    with get_connection() as conn:
        row = conn.execute("SELECT * FROM replays WHERE id = ?", (row_id,)).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404

    try:
        meta = gen(
            deck1=row["deck1"] or "",
            deck2=row["deck2"] or "",
            label_left=row["label_left"] or "DUELINGBOOK",
            label_right=row["label_right"] or "HIGH RATED",
            notes=row["notes"] or "",
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Save to DB
    with get_connection() as conn:
        conn.execute("""
            UPDATE replays SET title=?, description=?, tags=?, updated_at=datetime('now')
            WHERE id=?
        """, (meta["title"], meta["description"], meta["tags"], row_id))
        conn.commit()

    return jsonify({"ok": True, **meta})


@bp.route("/api/replays/<int:row_id>/record", methods=["POST"])
def record_replay(row_id: int):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM replays WHERE id = ?", (row_id,)).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    if row["status"] != "pending":
        return jsonify({"error": "only pending replays can be recorded"}), 400
    if _recording_in_progress:
        return jsonify({"error": "another recording is already in progress"}), 409

    replay_id = row["replay_id"]
    logger.info(f"Starting recording for replay {replay_id} (id={row_id})")
    _recording_in_progress.add(replay_id)

    # Mark as recording in the DB immediately
    with get_connection() as conn:
        conn.execute(
            "UPDATE replays SET status = 'recording', updated_at = datetime('now') WHERE id = ?",
            (row_id,),
        )
        conn.commit()

    thread = threading.Thread(target=_run_pipeline, args=(row_id, replay_id), daemon=True)
    thread.start()

    return jsonify({"ok": True, "message": "Recording started"})


@bp.route("/api/replays/<int:row_id>", methods=["DELETE"])
def delete_replay(row_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM replays WHERE id = ?", (row_id,))
        conn.commit()
    return jsonify({"ok": True})


def _cleanup_intermediates(final_video_path: str) -> None:
    """Deletes raw and outro intermediate files after a successful YouTube upload."""
    if not final_video_path:
        return
    final = Path(final_video_path)
    base = final.stem.replace("_final", "")

    candidates = [
        # Raw OBS recording
        Path("output/raw") / f"{base}.mp4",
        # Outro intermediate
        final.parent / f"{base}_outro.mp4",
    ]
    for p in candidates:
        if not p.is_absolute():
            p = Path(__file__).parent.parent / p
        try:
            if p.exists():
                p.unlink()
                logging.getLogger(__name__).info(f"Deleted intermediate: {p}")
        except Exception as e:
            logging.getLogger(__name__).warning(f"Could not delete {p}: {e}")


def _run_upload(row_id: int, row, privacy: str) -> None:
    from postprocess.youtube_uploader import upload_video

    _upload_progress[row_id] = {"pct": 0, "done": False, "error": None, "url": None}

    def on_progress(pct):
        _upload_progress[row_id]["pct"] = pct

    try:
        yt_url = upload_video(
            video_path=row["video_path"],
            title=row["title"] or "",
            description=row["description"] or "",
            tags=row["tags"] or "",
            thumbnail_path=row["thumbnail_path"] or None,
            privacy=privacy,
            publish_at=row["publish_at"] or None,
            progress_callback=on_progress,
        )
        _upload_progress[row_id].update({"pct": 100, "done": True, "url": yt_url})
        with get_connection() as conn:
            conn.execute(
                "UPDATE replays SET status='uploaded', youtube_url=?, updated_at=datetime('now') WHERE id=?",
                (yt_url, row_id),
            )
            conn.commit()
        logger.info(f"Upload complete for replay id={row_id}: {yt_url}")

        # Delete intermediate files now that the video is safely on YouTube
        _cleanup_intermediates(row["video_path"])
    except Exception as e:
        import traceback
        logger.error(f"Upload failed for replay id={row_id}: {e}", exc_info=True)
        _upload_progress[row_id].update({"done": True, "error": str(e)})


@bp.route("/api/replays/<int:row_id>/upload", methods=["POST"])
def upload_to_youtube(row_id: int):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM replays WHERE id = ?", (row_id,)).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    if row["status"] not in ("thumbnail_ready", "recorded"):
        return jsonify({"error": "replay must be recorded or have a thumbnail first"}), 400
    if not row["video_path"]:
        return jsonify({"error": "no video file found"}), 400
    if row_id in _upload_progress and not _upload_progress[row_id]["done"]:
        return jsonify({"error": "upload already in progress"}), 409

    data = request.json or {}
    privacy = data.get("privacy", "private")

    t = threading.Thread(target=_run_upload, args=(row_id, dict(row), privacy), daemon=True)
    t.start()

    return jsonify({"ok": True})


@bp.route("/api/replays/<int:row_id>/upload/progress")
def upload_progress_sse(row_id: int):
    from flask import Response

    def stream():
        while True:
            state = _upload_progress.get(row_id, {"pct": 0, "done": False, "error": None, "url": None})
            import json
            yield f"data: {json.dumps(state)}\n\n"
            if state["done"]:
                break
            time.sleep(1)

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ------------------------------------------------------------------
# Deck cards
# ------------------------------------------------------------------

@bp.route("/api/replays/<int:row_id>/thumbnail", methods=["POST"])
def generate_thumbnail(row_id: int):
    import random
    from postprocess.thumbnail import ThumbnailGenerator

    with get_connection() as conn:
        row = conn.execute("SELECT * FROM replays WHERE id = ?", (row_id,)).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    if row["status"] not in ("recorded", "thumbnail_ready"):
        return jsonify({"error": "replay must be recorded first"}), 400

    def pick_card(deck_name: str) -> str:
        with get_connection() as conn:
            cards = conn.execute(
                "SELECT card_name FROM deck_cards WHERE deck_name = ?", (deck_name,)
            ).fetchall()
        if not cards:
            return deck_name  # fallback: use deck name as card name
        return random.choice(cards)["card_name"]

    card1 = pick_card(row["deck1"] or "")
    card2 = pick_card(row["deck2"] or "")

    output_path = f"output/thumbnails/{row_id}_{row['replay_id']}.jpg"

    try:
        gen = ThumbnailGenerator()
        thumb_path = gen.generate(
            deck1=row["deck1"] or "",
            card1=card1,
            deck2=row["deck2"] or "",
            card2=card2,
            label_left=row["label_left"] or "DUELINGBOOK",
            label_right=row["label_right"] or "HIGH RATED",
            output_path=output_path,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    with get_connection() as conn:
        conn.execute(
            "UPDATE replays SET status='thumbnail_ready', thumbnail_path=?, updated_at=datetime('now') WHERE id=?",
            (thumb_path, row_id),
        )
        conn.commit()

    return jsonify({"ok": True, "thumbnail_path": thumb_path})


@bp.route("/api/replays/<int:row_id>/thumbnail", methods=["GET"])
def serve_thumbnail(row_id: int):
    from flask import send_file
    BASE = Path(__file__).parent.parent
    with get_connection() as conn:
        row = conn.execute("SELECT thumbnail_path FROM replays WHERE id = ?", (row_id,)).fetchone()
    if not row or not row["thumbnail_path"]:
        return jsonify({"error": "no thumbnail"}), 404
    path = Path(row["thumbnail_path"])
    if not path.is_absolute():
        path = BASE / path
    if not path.exists():
        return jsonify({"error": "file not found"}), 404
    return send_file(str(path), mimetype="image/jpeg")


@bp.route("/api/cards/search", methods=["GET"])
def search_cards():
    import requests as req
    query = request.args.get("q", "").strip()
    if len(query) < 2:
        return jsonify([])
    try:
        r = req.get(
            "https://db.ygoprodeck.com/api/v7/cardinfo.php",
            params={"fname": query, "num": 15, "offset": 0},
            timeout=5,
        )
        if r.status_code == 404:
            return jsonify([])
        names = [c["name"] for c in r.json().get("data", [])]
        return jsonify(names)
    except Exception:
        return jsonify([])


@bp.route("/api/decks", methods=["GET"])
def list_decks():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM deck_cards ORDER BY deck_name ASC, id ASC"
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route("/api/decks", methods=["POST"])
def create_deck_card():
    data = request.json or {}
    deck_name = (data.get("deck_name") or "").strip()
    card_name = (data.get("card_name") or "").strip()
    if not deck_name or not card_name:
        return jsonify({"error": "deck_name and card_name are required"}), 400
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO deck_cards (deck_name, card_name) VALUES (?, ?)",
            (deck_name, card_name),
        )
        conn.commit()
    return jsonify({"ok": True}), 201


@bp.route("/api/decks/<int:row_id>", methods=["PUT"])
def update_deck_card(row_id: int):
    data = request.json or {}
    deck_name = (data.get("deck_name") or "").strip()
    card_name = (data.get("card_name") or "").strip()
    if not deck_name or not card_name:
        return jsonify({"error": "deck_name and card_name are required"}), 400
    with get_connection() as conn:
        conn.execute(
            "UPDATE deck_cards SET deck_name=?, card_name=? WHERE id=?",
            (deck_name, card_name, row_id),
        )
        conn.commit()
    return jsonify({"ok": True})


@bp.route("/api/decks/<int:row_id>", methods=["DELETE"])
def delete_deck_card(row_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM deck_cards WHERE id = ?", (row_id,))
        conn.commit()
    return jsonify({"ok": True})
