"""
routes.py

Flask routes for the duelingbook recorder app.
"""

import threading

from flask import Blueprint, jsonify, render_template, request

from app.database import get_connection

bp = Blueprint("main", __name__)

VALID_STATUSES = ["pending", "recorded", "thumbnail_ready", "uploaded"]

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
    except Exception as e:
        update("pending")  # revert so user can retry
        print(f"[pipeline error] {e}")
    finally:
        _recording_in_progress.discard(replay_id)


@bp.route("/")
def index():
    return render_template("index.html")


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
                    (replay_id, deck1, deck2, title, description, tags, notes, scheduled_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                replay_id,
                data.get("deck1", ""),
                data.get("deck2", ""),
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
    fields = ["deck1", "deck2", "title", "description", "tags", "notes",
              "scheduled_date", "status", "video_path", "thumbnail_path", "youtube_url"]
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
