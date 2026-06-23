"""
Server-side position evaluation and game analysis.
Chess.com-style move classifications with efficient single-pass analysis.
"""

from __future__ import annotations

import os
import shutil
import chess

PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}

CLASSIFICATION_LABELS = {
    "book": "Book",
    "best": "Best",
    "excellent": "Great",
    "good": "Good",
    "inaccuracy": "Inaccuracy",
    "mistake": "Mistake",
    "blunder": "Blunder",
    "brilliant": "Brilliant",
    "miss": "Miss",
}

CLASSIFICATION_DIALOGUES = {
    "book": "A well-known opening move. You're following established theory.",
    "best": "Best move! The computer can't find anything better.",
    "excellent": "Great move! You found a strong continuation.",
    "good": "Good move. Your position remains solid.",
    "inaccuracy": "Inaccuracy. A small slip — try to stay focused.",
    "mistake": "Mistake. That move gave your opponent new chances.",
    "blunder": "Blunder! A serious error in this position.",
    "brilliant": "Brilliant!! A stunning move that changes the game.",
    "miss": "Missed opportunity. There was a much stronger move available.",
}


def material_evaluation(board: chess.Board) -> int:
    """Centipawn score from White's perspective."""
    score = 0
    for _square, piece in board.piece_map().items():
        val = PIECE_VALUES.get(piece.piece_type, 0)
        score += val if piece.color == chess.WHITE else -val
    return score


def _get_engine():
    stockfish_path = os.environ.get("STOCKFISH_PATH") or shutil.which("stockfish")
    if not stockfish_path:
        return None
    try:
        import chess.engine
        return chess.engine.SimpleEngine.popen_uci(stockfish_path)
    except Exception:
        return None


def _eval_cp(board: chess.Board, engine=None) -> int:
    if engine:
        try:
            import chess.engine
            info = engine.analyse(board, chess.engine.Limit(time=0.05))
            score = info.get("score")
            if score is not None:
                cp = score.white().score(mate_score=10000)
                if cp is not None:
                    return cp
        except Exception:
            pass
    return material_evaluation(board)


def _best_move_eval(board: chess.Board, engine=None) -> tuple[str | None, int]:
    if engine:
        try:
            import chess.engine
            info = engine.analyse(board, chess.engine.Limit(time=0.05))
            pv = info.get("pv") or []
            if pv:
                test = board.copy()
                test.push(pv[0])
                return pv[0].uci(), _eval_cp(test, engine)
            score = info.get("score")
            if score is not None:
                cp = score.white().score(mate_score=10000)
                if cp is not None:
                    return None, cp
        except Exception:
            pass
    return None, material_evaluation(board)


def _perspective_cp(cp: int, white_to_move: bool) -> int:
    return cp if white_to_move else -cp


def _cp_loss(eval_before: int, eval_after: int, best_eval: int, mover_is_white: bool) -> int:
    """Centipawn loss for the player who just moved."""
    before = _perspective_cp(eval_before, mover_is_white)
    after = _perspective_cp(eval_after, not mover_is_white)
    best = _perspective_cp(best_eval, mover_is_white)
    played_loss = before - after
    best_loss = before - best
    return max(0, played_loss - best_loss) if best_loss >= 0 else max(0, played_loss)


def _classify_move(cp_loss: int, move_index: int, eval_before: int, eval_after: int, mover_is_white: bool) -> str:
    if move_index < 12:
        return "book"
    if cp_loss <= 0:
        after = _perspective_cp(eval_after, not mover_is_white)
        before = _perspective_cp(eval_before, mover_is_white)
        if after - before > 150 and cp_loss == 0:
            return "brilliant"
        return "best"
    if cp_loss <= 10:
        return "excellent"
    if cp_loss <= 25:
        return "good"
    if cp_loss <= 50:
        return "inaccuracy"
    if cp_loss <= 100:
        return "mistake"
    return "blunder"


def _parse_move(board: chess.Board, move_data: dict) -> chess.Move | None:
    uci = move_data.get("san") or ""
    from_sq = move_data.get("from", "")
    to_sq = move_data.get("to", "")
    if from_sq and to_sq and len(from_sq) == 2 and len(to_sq) == 2:
        uci = from_sq + to_sq
    if not uci:
        return None
    try:
        if len(uci) >= 4 and uci[0] in "abcdefgh":
            move = chess.Move.from_uci(uci[:4])
        else:
            move = board.parse_san(uci)
        if move in board.legal_moves:
            return move
    except (ValueError, chess.InvalidMoveError):
        pass
    return None


def evaluate_position(fen: str) -> dict:
    board = chess.Board(fen)
    material = material_evaluation(board)

    result = {
        "fen": fen,
        "turn": "white" if board.turn == chess.WHITE else "black",
        "material_cp": material,
        "is_check": board.is_check(),
        "is_checkmate": board.is_checkmate(),
        "is_stalemate": board.is_stalemate(),
        "is_game_over": board.is_game_over(),
        "legal_moves": board.legal_moves.count(),
        "engine": "material",
    }

    engine = _get_engine()
    if engine:
        try:
            cp = _eval_cp(board, engine)
            result["evaluation_cp"] = cp
            result["engine"] = "stockfish"
            import chess.engine
            info = engine.analyse(board, chess.engine.Limit(time=0.08))
            pv = info.get("pv")
            if pv:
                result["best_line"] = [m.uci() for m in pv[:5]]
        except Exception:
            result["evaluation_cp"] = material
        finally:
            try:
                engine.quit()
            except Exception:
                pass
    else:
        result["evaluation_cp"] = material

    return result


def analyze_game(move_history: list, starting_fen: str | None = None) -> dict:
    """
    Analyze a full game with per-move classifications.
    Returns {positions: [...], moves: [...], summary: {...}}
    """
    board = chess.Board(starting_fen or chess.STARTING_FEN)
    positions = [evaluate_position(board.fen())]
    moves_out = []

    engine = _get_engine()
    engine_name = "stockfish" if engine else "material"

    try:
        for i, move_data in enumerate(move_history or []):
            move = _parse_move(board, move_data)
            if not move:
                continue

            mover_is_white = board.turn == chess.WHITE
            eval_before = _eval_cp(board, engine)
            _best_uci, best_eval = _best_move_eval(board, engine)

            san = move_data.get("san") or board.san(move)
            board.push(move)
            eval_after = _eval_cp(board, engine)
            cp_loss = _cp_loss(eval_before, eval_after, best_eval, mover_is_white)
            classification = _classify_move(cp_loss, i, eval_before, eval_after, mover_is_white)

            moves_out.append({
                "index": i,
                "san": san,
                "from": move_data.get("from", move.uci()[:2]),
                "to": move_data.get("to", move.uci()[2:4]),
                "fen": board.fen(),
                "cp_loss": cp_loss,
                "classification": classification,
                "label": CLASSIFICATION_LABELS.get(classification, classification.title()),
                "dialogue": CLASSIFICATION_DIALOGUES.get(classification, ""),
                "eval_before": eval_before,
                "eval_after": eval_after,
                "color": "white" if mover_is_white else "black",
            })
            positions.append({
                "fen": board.fen(),
                "evaluation_cp": eval_after,
                "material_cp": material_evaluation(board),
                "engine": engine_name,
            })
    finally:
        if engine:
            try:
                engine.quit()
            except Exception:
                pass

    counts = {}
    for m in moves_out:
        counts[m["classification"]] = counts.get(m["classification"], 0) + 1

    return {
        "positions": positions,
        "moves": moves_out,
        "summary": {
            "total_moves": len(moves_out),
            "classifications": counts,
            "engine": engine_name,
        },
    }
