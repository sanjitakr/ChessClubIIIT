// Multiplayer Chess JavaScript - WebSocket Integration

class ChessMatch {
  constructor(matchId, playerColor, matchStatus) {
    this.matchId = matchId;
    this.playerColor = playerColor;
    this.matchStatus = matchStatus || 'LIVE';
    this.game = new Chess();
    this.selectedSquare = null;
    this.isFlipped = playerColor === 'black';
    this.moveHistory = [];
    this.websocket = null;
    this.isConnected = false;
    this.opponentConnected = false;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.pendingMove = null;
    this.startFen = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
    this.whitePlayer = null;
    this.blackPlayer = null;
    this.endReason = '';
    this.endResult = '*';
    this.disconnectGraceUntil = null;

    this.whiteTimeMs = parseInt(document.body.dataset.whiteTime || '600000', 10);
    this.blackTimeMs = parseInt(document.body.dataset.blackTime || '600000', 10);
    this.incrementMs = parseInt(document.body.dataset.increment || '0', 10);
    this.lastTick = Date.now();
    this._flagSent = false;
    this.clockInterval = setInterval(() => this.tickClock(), 100);

    this.init();
  }

  init() {
    this.createBoard();
    this.updateDisplay();
    this.setupEventListeners();
    this.connectWebSocket();
    console.log(`Chess match initialized - Playing as ${this.playerColor}`);
  }

  isGameOver() {
    return this.matchStatus === 'END' || this.game.game_over();
  }

  clearEvalDisplay() {
    const scoreEl = document.getElementById('eval-score');
    const engineEl = document.getElementById('eval-engine');
    const fillEl = document.getElementById('eval-fill');
    const lineEl = document.getElementById('eval-line');
    if (scoreEl) scoreEl.textContent = '—';
    if (engineEl) engineEl.textContent = 'Request analysis';
    if (lineEl) lineEl.textContent = '—';
    if (fillEl) {
      fillEl.style.width = '50%';
      fillEl.style.background = 'linear-gradient(90deg, #1a1a1a 50%, #f0f0f0 50%)';
    }
  }

  connectWebSocket() {
    // Construct WebSocket URL
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/match/${this.matchId}/`;

    console.log('Connecting to WebSocket:', wsUrl);

    try {
      this.websocket = new WebSocket(wsUrl);

      this.websocket.onopen = (e) => {
        console.log('WebSocket connected');
        this.isConnected = true;
        this.reconnectAttempts = 0;
        this.updateConnectionStatus();
        this.requestGameState();
      };

      this.websocket.onmessage = (e) => {
        this.handleWebSocketMessage(e);
      };

      this.websocket.onerror = (e) => {
        console.error('WebSocket error:', e);
        this.isConnected = false;
        this.updateConnectionStatus();
      };

      this.websocket.onclose = (e) => {
        console.log('WebSocket closed:', e.code, e.reason);
        this.isConnected = false;
        this.updateConnectionStatus();

        // Attempt reconnection
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
          this.reconnectAttempts++;
          console.log(`Reconnecting... Attempt ${this.reconnectAttempts}`);
          setTimeout(() => this.connectWebSocket(), 2000 * this.reconnectAttempts);
        } else {
          this.showError('Connection lost. Please refresh the page.');
        }
      };

    } catch (error) {
      console.error('Failed to create WebSocket:', error);
      this.showError('Failed to connect to game server');
    }
  }

  handleWebSocketMessage(event) {
    try {
      const data = JSON.parse(event.data);
      console.log('Received message:', data);

      switch (data.type) {
        case 'game_state':
          this.handleGameState(data);
          break;
        case 'move':
          this.handleOpponentMove(data);
          break;
        case 'player_connected':
          this.handlePlayerConnected(data);
          break;
        case 'player_disconnected':
          this.handlePlayerDisconnected(data);
          break;
        case 'draw_offered':
          this.handleDrawOffer(data);
          break;
        case 'draw_declined':
          this.handleDrawDeclined(data);
          break;
        case 'game_ended':
          this.handleGameEnd(data);
          break;
        case 'error':
          this.showError(data.message);
          // ADDED: Revert any pending move on error
          if (this.pendingMove) {
            this.game.undo();
            this.pendingMove = null;
            this.updateDisplay();
          }
          break;
      }
    } catch (error) {
      console.error('Error handling WebSocket message:', error);
    }
  }

  handleGameState(data) {
    this.game.load(data.fen);
    this.moveHistory = data.move_history || [];
    if (data.status) {
      this.matchStatus = data.status;
    }

    if (data.white_time_ms != null) {
      this.whiteTimeMs = data.white_time_ms;
      this.blackTimeMs = data.black_time_ms;
      this.lastTick = Date.now();
      if (this.whiteTimeMs > 0 && this.blackTimeMs > 0) {
        this._flagSent = false;
      }
    }

    if (this.playerColor === 'white') {
      this.opponentConnected = data.black_connected;
    } else if (this.playerColor === 'black') {
      this.opponentConnected = data.white_connected;
    }

    this.pendingMove = null;
    this.updateDisplay();
    this.updateConnectionStatus();
    this.renderClocks();
  }

  handleOpponentMove(data) {
    // ADDED: Check if this is our own move echo (prevents double-move bug)
    if (this.pendingMove &&
      this.pendingMove.from === data.move.from &&
      this.pendingMove.to === data.move.to) {
      console.log('Received echo of our own move, clearing pending');
      if (data.white_time_ms != null) {
        this.whiteTimeMs = data.white_time_ms;
        this.blackTimeMs = data.black_time_ms;
        this.lastTick = Date.now();
        this.renderClocks();
      }
      this.pendingMove = null;
      return;
    }

    // ADDED: Undo our pending move if it exists (shouldn't happen but safety check)
    if (this.pendingMove) {
      this.game.undo();
      this.pendingMove = null;
    }

    // Apply move from opponent
    const move = this.game.move({
      from: data.move.from,
      to: data.move.to,
      promotion: data.move.promotion || 'q'
    });

    if (move) {
      this.selectedSquare = null;
      if (data.white_time_ms != null) {
        this.whiteTimeMs = data.white_time_ms;
        this.blackTimeMs = data.black_time_ms;
        this.lastTick = Date.now();
      }
      this.updateDisplay();

      // Check for game end
      if (data.game_status && data.game_status.game_over) {
        this.matchStatus = 'END';
        this.endReason = data.game_status.reason || 'Game ended';
        this.endResult = data.game_status.result || '*';
        setTimeout(() => {
          this.showGameOverModal(data.game_status);
        }, 500);
      }

      console.log('Opponent move applied:', data.move);
    } else {
      console.error('Failed to apply opponent move:', data.move);
      // ADDED: Request fresh game state if move fails
      this.requestGameState();
    }
  }

  handlePlayerConnected(data) {
    console.log('Player connected:', data);

    if (data.color !== this.playerColor) {
      this.opponentConnected = true;
      this.showNotification(`${data.username} connected`);
    }

    this.updateConnectionStatus();
  }

  handlePlayerDisconnected(data) {
    console.log('Player disconnected:', data);

    if (data.color !== this.playerColor) {
      this.opponentConnected = false;
      this.disconnectGraceUntil = Date.now() + ((data.grace_seconds || 30) * 1000);
      this.showNotification(`${data.username} disconnected. Forfeit in ${data.grace_seconds || 30}s if they do not return.`);
    }

    this.updateConnectionStatus();
  }

  handleDrawOffer(data) {
    if (data.by !== this.playerColor) {
      const accept = confirm('Your opponent offers a draw. Do you accept?');
      this.sendMessage({
        type: 'respond_draw',
        accept: accept
      });
    }
  }

  handleDrawDeclined(data) {
    if (data.by !== this.playerColor) {
      this.showNotification('Draw offer declined');
    }
  }

  handleGameEnd(data) {
    this.matchStatus = 'END';
    this.endReason = data.reason || 'Game ended';
    this.endResult = data.result || '*';
    this.disconnectGraceUntil = null;

    setTimeout(() => {
      this.showGameOverModal({
        game_over: true,
        result: data.result,
        reason: data.reason
      });
    }, 500);
  }

  sendMessage(message) {
    if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
      this.websocket.send(JSON.stringify(message));
    } else {
      console.error('WebSocket not connected');
      this.showError('Not connected to server');
    }
  }

  requestGameState() {
    this.sendMessage({ type: 'request_sync' });
  }

  createBoard() {
    const board = document.getElementById('chessboard');
    board.innerHTML = '';

    const ranks = this.isFlipped ? [1, 2, 3, 4, 5, 6, 7, 8] : [8, 7, 6, 5, 4, 3, 2, 1];
    const files = this.isFlipped ? [7, 6, 5, 4, 3, 2, 1, 0] : [0, 1, 2, 3, 4, 5, 6, 7];

    for (let rank of ranks) {
      for (let file of files) {
        const square = document.createElement('div');
        const fileChar = String.fromCharCode(97 + file);
        const squareName = fileChar + rank;

        square.className = `square ${(rank + file) % 2 === 0 ? 'dark' : 'light'}`;
        square.dataset.square = squareName;
        square.addEventListener('click', (e) => this.handleSquareClick(e));

        board.appendChild(square);
      }
    }
  }

  updateDisplay() {
    this.updateBoard();
    this.updateGameStatus();
    this.updateMoveHistory();
    this.updateGameInfo();
  }

  updateBoard() {
    const squares = document.querySelectorAll('.square');

    squares.forEach(square => {
      const squareName = square.dataset.square;
      const piece = this.game.get(squareName);

      square.innerHTML = '';
      square.classList.remove('has-piece', 'selected', 'legal-move', 'last-move', 'in-check');

      if (piece) {
        const pieceElement = document.createElement('div');
        const colorClass = piece.color === 'w' ? 'white' : 'black';
        const typeMap = { p: 'pawn', r: 'rook', n: 'knight', b: 'bishop', q: 'queen', k: 'king' };
        const typeClass = typeMap[piece.type];
        pieceElement.className = `piece ${colorClass} ${typeClass}`;
        square.appendChild(pieceElement);
        square.classList.add('has-piece');
      }

      if (this.selectedSquare === squareName) {
        square.classList.add('selected');
      }

      if (this.selectedSquare) {
        const moves = this.game.moves({ square: this.selectedSquare, verbose: true });
        if (moves.some(move => move.to === squareName)) {
          square.classList.add('legal-move');
        }
      }

      const history = this.game.history({ verbose: true });
      if (history.length > 0) {
        const lastMove = history[history.length - 1];
        if (squareName === lastMove.from || squareName === lastMove.to) {
          square.classList.add('last-move');
        }
      }

      if (this.game.in_check()) {
        const kingSquare = this.findKingSquare(this.game.turn());
        if (squareName === kingSquare) {
          square.classList.add('in-check');
        }
      }
    });
  }

  findKingSquare(color) {
    const board = this.game.board();
    for (let rank = 0; rank < 8; rank++) {
      for (let file = 0; file < 8; file++) {
        const piece = board[rank][file];
        if (piece && piece.type === 'k' && piece.color === color) {
          return String.fromCharCode(97 + file) + (8 - rank);
        }
      }
    }
    return null;
  }

  handleSquareClick(event) {
    if (this.isGameOver()) {
      return;
    }
    if (this.pendingMove) {
      this.showNotification('Move in progress, please wait...');
      return;
    }

    // Only allow moves if it's the player's turn and they're not a spectator
    if (this.playerColor === 'spectator') {
      this.showNotification('You are spectating this game');
      return;
    }

    const currentTurn = this.game.turn() === 'w' ? 'white' : 'black';
    if (this.playerColor !== currentTurn) {
      this.showNotification('Wait for your turn');
      return;
    }

    const square = event.currentTarget;
    const squareName = square.dataset.square;
    const piece = this.game.get(squareName);

    if (!this.selectedSquare) {
      if (piece && piece.color === this.game.turn()) {
        this.selectedSquare = squareName;
        this.updateDisplay();
      }
      return;
    }

    if (this.selectedSquare === squareName) {
      this.selectedSquare = null;
      this.updateDisplay();
      return;
    }

    if (piece && piece.color === this.game.turn()) {
      this.selectedSquare = squareName;
      this.updateDisplay();
      return;
    }

    this.attemptMove(this.selectedSquare, squareName);
  }

  attemptMove(from, to) {
    const piece = this.game.get(from);
    const isPromotion = piece && piece.type === 'p' &&
      ((piece.color === 'w' && to[1] === '8') ||
        (piece.color === 'b' && to[1] === '1'));

    if (isPromotion) {
      this.showPromotionModal(from, to);
      return;
    }

    this.makeMove(from, to);
  }

  makeMove(from, to, promotion = null) {
    // ADDED: Prevent double-moves
    if (this.pendingMove) {
      console.log('Move already in progress');
      return;
    }

    // Try to make the move locally first
    const move = this.game.move({ from, to, promotion: promotion || 'q' });

    if (move) {
      // ADDED: Mark move as pending
      this.pendingMove = { from, to, promotion };

      // Send move to server
      this.sendMessage({
        type: 'move',
        from: from,
        to: to,
        promotion: promotion
      });

      this.selectedSquare = null;
      this.updateDisplay();

      console.log(`Move made: ${move.san} (${from} → ${to})`);

      // ADDED: Clear pending move after timeout (safety net)
      setTimeout(() => {
        if (this.pendingMove) {
          console.log('Clearing stale pending move');
          this.pendingMove = null;
        }
      }, 5000);
    } else {
      // Invalid move - revert
      this.selectedSquare = null;
      this.updateDisplay();
      this.showNotification('Invalid move');
    }
  }

  showPromotionModal(from, to) {
    const modal = document.createElement('div');
    modal.className = 'promotion-modal';
    modal.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0, 0, 0, 0.7);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 1000;
    `;

    const content = document.createElement('div');
    content.className = 'promotion-content';
    content.style.cssText = `
      background: var(--surface);
      padding: 2rem;
      border-radius: 8px;
      text-align: center;
    `;

    const title = document.createElement('h3');
    title.textContent = 'Choose promotion piece:';
    title.style.marginBottom = '1rem';
    content.appendChild(title);

    const pieces = document.createElement('div');
    pieces.className = 'promotion-pieces';
    pieces.style.cssText = `
      display: flex;
      gap: 1rem;
      justify-content: center;
    `;

    const promotionOptions = ['q', 'r', 'b', 'n'];
    const currentPlayer = this.game.turn();

    promotionOptions.forEach(pieceType => {
      const pieceButton = document.createElement('div');
      const typeMap = { q: 'queen', r: 'rook', b: 'bishop', n: 'knight' };
      pieceButton.className = `promotion-piece piece ${currentPlayer === 'w' ? 'white' : 'black'} ${typeMap[pieceType]}`;
      pieceButton.style.cssText = `
        width: 80px;
        height: 80px;
        cursor: pointer;
        border: 2px solid var(--border);
        border-radius: 4px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 3rem;
      `;
      pieceButton.addEventListener('click', () => {
        this.makeMove(from, to, pieceType);
        document.body.removeChild(modal);
      });
      pieces.appendChild(pieceButton);
    });

    content.appendChild(pieces);
    modal.appendChild(content);
    document.body.appendChild(modal);

    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        document.body.removeChild(modal);
        this.selectedSquare = null;
        this.updateDisplay();
      }
    });
  }

  updateGameStatus() {
    const turnDisplay = document.getElementById('current-turn');
    const gameStatus = document.getElementById('game-status');

    if (this.isGameOver()) {
      const forfeitBtn = document.getElementById('forfeit-btn');
      const drawBtn = document.getElementById('offer-draw-btn');
      if (forfeitBtn) {
        forfeitBtn.disabled = true;
        forfeitBtn.style.opacity = '0.5';
        forfeitBtn.style.cursor = 'not-allowed';
      }
      if (drawBtn) {
        drawBtn.disabled = true;
        drawBtn.style.opacity = '0.5';
        drawBtn.style.cursor = 'not-allowed';
      }

      if (this.game.in_checkmate()) {
        const winner = this.game.turn() === 'w' ? 'Black' : 'White';
        turnDisplay.textContent = `Checkmate! ${winner} wins`;
        gameStatus.textContent = `${winner} wins by checkmate`;
      } else if (this.game.in_draw()) {
        turnDisplay.textContent = 'Game drawn';
        gameStatus.textContent = 'Draw';
      } else if (this.game.in_stalemate()) {
        turnDisplay.textContent = 'Stalemate';
        gameStatus.textContent = 'Draw by stalemate';
      } else {
        turnDisplay.textContent = 'Game ended';
        gameStatus.textContent = this.endReason || (this.endResult !== '*' ? `Result: ${this.endResult}` : 'Finished');
      }
    } else {
      const currentPlayer = this.game.turn() === 'w' ? 'White' : 'Black';
      const checkText = this.game.in_check() ? ' (in check)' : '';
      const yourTurn = (this.game.turn() === 'w' && this.playerColor === 'white') ||
        (this.game.turn() === 'b' && this.playerColor === 'black');

      if (this.playerColor === 'spectator') {
        turnDisplay.textContent = `${currentPlayer} to move${checkText}`;
      } else {
        turnDisplay.textContent = yourTurn ?
          `Your turn${checkText}` :
          `Opponent's turn${checkText}`;
      }

      gameStatus.textContent = 'In Progress';

      const forfeitBtn = document.getElementById('forfeit-btn');
      const drawBtn = document.getElementById('offer-draw-btn');
      if (forfeitBtn) {
        forfeitBtn.disabled = false;
        forfeitBtn.style.opacity = '1';
        forfeitBtn.style.cursor = 'pointer';
      }
      if (drawBtn) {
        drawBtn.disabled = false;
        drawBtn.style.opacity = '1';
        drawBtn.style.cursor = 'pointer';
      }
    }
  }

  tickClock() {
    if (this.isGameOver() || this.matchStatus === 'WAIT') return;

    const now = Date.now();
    const elapsed = now - this.lastTick;
    this.lastTick = now;

    if (this.game.turn() === 'w') {
      this.whiteTimeMs = Math.max(0, this.whiteTimeMs - elapsed);
    } else {
      this.blackTimeMs = Math.max(0, this.blackTimeMs - elapsed);
    }
    this.renderClocks();
    this.updateConnectionStatus();

    if (this.whiteTimeMs <= 0 && this.game.turn() === 'w') {
      if (!this._flagSent) {
        this._flagSent = true;
        this.sendMessage({ type: 'flag' });
      }
    } else if (this.blackTimeMs <= 0 && this.game.turn() === 'b') {
      if (!this._flagSent) {
        this._flagSent = true;
        this.sendMessage({ type: 'flag' });
      }
    }
  }

  renderClocks() {
    const whiteClock = document.getElementById('white-clock');
    const blackClock = document.getElementById('black-clock');

    const formatTime = (ms) => {
      const totalSeconds = Math.max(0, Math.floor(ms / 1000));
      const m = Math.floor(totalSeconds / 60).toString().padStart(2, '0');
      const s = (totalSeconds % 60).toString().padStart(2, '0');
      if (ms < 10000 && ms > 0) {
        const dec = Math.floor((ms % 1000) / 100);
        return `${m}:${s}.${dec}`;
      }
      return `${m}:${s}`;
    };

    if (whiteClock) {
      whiteClock.textContent = formatTime(this.whiteTimeMs);
      if (this.game.turn() === 'w' && this.matchStatus === 'LIVE') {
        whiteClock.style.background = '#0f172a';
        whiteClock.style.border = '2px solid #d8b457';
      } else {
        whiteClock.style.background = '#1e293b';
        whiteClock.style.border = '2px solid var(--border)';
      }
    }
    if (blackClock) {
      blackClock.textContent = formatTime(this.blackTimeMs);
      if (this.game.turn() === 'b' && this.matchStatus === 'LIVE') {
        blackClock.style.background = '#0f172a';
        blackClock.style.border = '2px solid #d8b457';
      } else {
        blackClock.style.background = '#1e293b';
        blackClock.style.border = '2px solid var(--border)';
      }
    }
  }

  updateMoveHistory() {
    const historyElement = document.getElementById('move-history');
    const moves = this.game.history();

    if (moves.length === 0) {
      historyElement.innerHTML = '<p class="text-muted">No moves yet...</p>';
      return;
    }

    let historyHTML = '';
    for (let i = 0; i < moves.length; i += 2) {
      const moveNumber = Math.floor(i / 2) + 1;
      const whiteMove = this.formatMoveLabel(moves[i]);
      const blackMove = moves[i + 1] ? this.formatMoveLabel(moves[i + 1]) : '';

      historyHTML += `
        <div class="move-pair">
          <span class="move-number">${moveNumber}.</span>
          <span class="move">${whiteMove}</span>
          ${blackMove ? `<span class="move">${blackMove}</span>` : ''}
        </div>
      `;
    }

    historyElement.innerHTML = historyHTML;
    historyElement.scrollTop = historyElement.scrollHeight;
  }

  formatMoveLabel(move) {
    if (!move) return '';
    if (typeof move === 'string') return move;
    return move.san || move.uci || `${move.from || ''}${move.to || ''}` || '...';
  }

  updateGameInfo() {
    const moveCount = document.getElementById('move-count');
    if (!moveCount) return;
    moveCount.textContent = this.game.history().length;
  }

  updateConnectionStatus() {
    const statusElement = document.getElementById('connection-status');
    if (!statusElement) return;

    if (this.isGameOver()) {
      statusElement.textContent = 'Game ended';
      statusElement.className = 'connection-status connected';
    } else if (!this.isConnected) {
      statusElement.textContent = 'Disconnected';
      statusElement.className = 'connection-status disconnected';
    } else if (!this.opponentConnected && this.playerColor !== 'spectator') {
      if (this.disconnectGraceUntil) {
        const seconds = Math.max(0, Math.ceil((this.disconnectGraceUntil - Date.now()) / 1000));
        statusElement.textContent = `Opponent disconnected. Forfeit in ${seconds}s`;
      } else {
        statusElement.textContent = 'Waiting for opponent...';
      }
      statusElement.className = 'connection-status waiting';
    } else {
      statusElement.textContent = 'Connected';
      statusElement.className = 'connection-status connected';
    }
  }

  showGameOverModal(gameStatus) {
    const modal = document.createElement('div');
    modal.className = 'game-over-overlay';
    modal.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0, 0, 0, 0.8);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 1000;
    `;

    const content = document.createElement('div');
    content.className = 'game-over-content';
    content.style.cssText = `
      background: var(--surface);
      padding: 3rem;
      border-radius: 8px;
      text-align: center;
      max-width: 400px;
    `;

    content.innerHTML = `
      <h2 style="margin-bottom: 1rem;">${gameStatus.reason}</h2>
      <p style="font-size: 1.5rem; margin-bottom: 2rem;">Result: ${gameStatus.result}</p>
      <div style="display:flex;gap:1rem;justify-content:center;">
        <button class="btn btn-secondary" onclick="alert('Rematch request sent!'); this.disabled=true;" style="display:inline-flex;align-items:center;gap:0.4rem;">
          <i data-lucide="refresh-cw" style="width:16px;height:16px;"></i> Offer Rematch
        </button>
        <button class="btn btn-primary" onclick="window.location.href='/match/lobby/'" style="display:inline-flex;align-items:center;gap:0.4rem;">
          <i data-lucide="layout-grid" style="width:16px;height:16px;"></i> Back to Lobby
        </button>
      </div>
    `;

    modal.appendChild(content);
    document.body.appendChild(modal);
  }

  showNotification(message) {
    const notification = document.createElement('div');
    notification.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      background: var(--surface);
      border: 1px solid var(--border);
      padding: 1rem;
      border-radius: 8px;
      box-shadow: 0 4px 12px var(--shadow-lg);
      z-index: 1000;
      max-width: 300px;
    `;
    notification.textContent = message;
    document.body.appendChild(notification);

    setTimeout(() => {
      if (document.body.contains(notification)) {
        document.body.removeChild(notification);
      }
    }, 3000);
  }

  showError(message) {
    console.error(message);
    this.showNotification('Error: ' + message);
  }

  resetGame() {
    if (confirm('Are you sure you want to start a new game? This will end the current match.')) {
      window.location.href = '/match/lobby/';
    }
  }

  flipBoard() {
    this.isFlipped = !this.isFlipped;
    this.createBoard();
    this.updateDisplay();
  }

  offerDraw() {
    if (this.playerColor === 'spectator') {
      this.showNotification('Spectators cannot offer draws');
      return;
    }

    if (confirm('Offer a draw to your opponent?')) {
      this.sendMessage({ type: 'offer_draw' });
      this.showNotification('Draw offer sent');
    }
  }

  forfeit() {
    if (this.playerColor === 'spectator') {
      this.showNotification('Spectators cannot forfeit');
      return;
    }

    if (confirm('Are you sure you want to forfeit this game?')) {
      this.sendMessage({ type: 'forfeit' });
    }
  }

  copyFEN() {
    const fen = this.game.fen();

    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(fen).then(() => {
        this.showNotification('FEN copied to clipboard!');
      });
    } else {
      const textArea = document.createElement('textarea');
      textArea.value = fen;
      textArea.style.position = 'fixed';
      textArea.style.opacity = '0';
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      this.showNotification('FEN copied to clipboard!');
    }
  }

  async runFullAnalysis() {
    const btn = document.getElementById('analyze-btn');
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i data-lucide="loader" style="width:14px;height:14px;"></i> Analyzing...';
    }
    try {
      const resp = await fetch(`/match/api/${this.matchId}/analyze/`);
      const data = await resp.json();
      if (data.success) {
        this.analysisRequested = true;
        this.gameAnalysis = data.analysis;
        const vertEvalBar = document.getElementById('vertical-eval-bar');
        if (vertEvalBar) vertEvalBar.style.display = 'flex';
        this.showNotification(
          data.cached ? 'Analysis loaded' : `Analysis complete — ${data.analysis.moves?.length || 0} moves reviewed`
        );
        if (data.analysis.positions?.length) {
          const last = data.analysis.positions[data.analysis.positions.length - 1];
          this.updateEvalDisplay(last.evaluation_cp ?? last.material_cp, last.engine || 'analysis');
        }
        this.updateMoveHistory();
        this.showAnalysisSummary(data.analysis.summary);
      } else {
        this.showNotification('Analysis failed');
      }
    } catch (e) {
      this.showNotification('Analysis failed');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i data-lucide="scan-search" style="width:14px;height:14px;"></i> Re-run Analysis';
        if (typeof lucide !== 'undefined') lucide.createIcons();
      }
    }
  }

  showAnalysisSummary(summary) {
    if (!summary?.classifications) return;
    const counts = summary.classifications;
    const parts = [];
    if (counts.brilliant) parts.push(`${counts.brilliant} Brilliant`);
    if (counts.excellent) parts.push(`${counts.excellent} Excellent`);
    if (counts.good) parts.push(`${counts.good} Good`);
    if (counts.best) parts.push(`${counts.best} Best`);
    if (counts.book) parts.push(`${counts.book} Book`);
    if (counts.inaccuracy) parts.push(`${counts.inaccuracy} Inaccurac${counts.inaccuracy > 1 ? 'ies' : 'y'}`);
    if (counts.mistake) parts.push(`${counts.mistake} Mistake${counts.mistake > 1 ? 's' : ''}`);
    if (counts.blunder) parts.push(`${counts.blunder} Blunder${counts.blunder > 1 ? 's' : ''}`);
    if (parts.length) {
      this.showNotification(parts.join(' · '));
    }
  }

  setupEventListeners() {
    document.getElementById('reset-game')?.addEventListener('click', () => {
      this.resetGame();
    });

    document.getElementById('flip-board')?.addEventListener('click', () => {
      this.flipBoard();
    });

    document.getElementById('copy-fen')?.addEventListener('click', () => {
      this.copyFEN();
    });

    document.getElementById('offer-draw-btn')?.addEventListener('click', () => {
      this.offerDraw();
    });

    document.getElementById('forfeit-btn')?.addEventListener('click', () => {
      this.forfeit();
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        this.selectedSquare = null;
        this.updateDisplay();
      }
    });

    // Cleanup on page unload
    window.addEventListener('beforeunload', () => {
      if (this.websocket) {
        this.websocket.close();
      }
    });
  }
}

// Initialize the chess match when the page loads
let chessMatch;

document.addEventListener('DOMContentLoaded', function () {
  const matchId = document.body.dataset.matchId;
  const playerColor = document.body.dataset.playerColor;
  const matchStatus = document.body.dataset.matchStatus || 'LIVE';

  if (matchId && typeof Chess !== 'undefined') {
    chessMatch = new ChessMatch(matchId, playerColor, matchStatus);
  } else {
    console.error('Missing match ID or Chess.js library');
  }
});
