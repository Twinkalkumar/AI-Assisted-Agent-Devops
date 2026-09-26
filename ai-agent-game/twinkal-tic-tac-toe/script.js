const WIN_LINES = [
  [0, 1, 2],
  [3, 4, 5],
  [6, 7, 8],
  [0, 3, 6],
  [1, 4, 7],
  [2, 5, 8],
  [0, 4, 8],
  [2, 4, 6],
];

const HUMAN = "X";
const AI = "O";

const boardEl = document.getElementById("board");
const statusEl = document.getElementById("status");
const resetBtn = document.getElementById("reset");
const resetScoresBtn = document.getElementById("resetScores");
const modeSelect = document.getElementById("mode");
const difficultySelect = document.getElementById("difficulty");
const difficultyLabel = document.getElementById("difficultyLabel");
const scoreXEl = document.getElementById("scoreX");
const scoreOEl = document.getElementById("scoreO");
const scoreDrawEl = document.getElementById("scoreDraw");

let board = Array(9).fill(null);
let currentPlayer = HUMAN;
let gameOver = false;
let scores = { X: 0, O: 0, draw: 0 };

function isAiMode() {
  return modeSelect.value === "ai";
}

function render() {
  boardEl.innerHTML = "";
  const winInfo = getWinner();

  board.forEach((value, index) => {
    const cell = document.createElement("button");
    cell.className = "cell";
    cell.textContent = value ?? "";
    cell.disabled = Boolean(value) || gameOver || (isAiMode() && currentPlayer === AI);
    if (winInfo && winInfo.line.includes(index)) {
      cell.classList.add("winner");
    }
    cell.addEventListener("click", () => handleMove(index));
    boardEl.appendChild(cell);
  });

  if (winInfo) {
    statusEl.textContent = `Player ${winInfo.player} wins!`;
  } else if (board.every(Boolean)) {
    statusEl.textContent = "It's a draw!";
  } else {
    statusEl.textContent = isAiMode() && currentPlayer === AI
      ? "Computer is thinking..."
      : `Player ${currentPlayer}'s turn`;
  }
}

function handleMove(index) {
  if (gameOver || board[index]) return;
  if (isAiMode() && currentPlayer === AI) return;

  board[index] = currentPlayer;
  afterMove();

  if (!gameOver && isAiMode() && currentPlayer === AI) {
    render();
    setTimeout(aiMove, 350);
  }
}

function afterMove() {
  const winInfo = getWinner();
  if (winInfo) {
    gameOver = true;
    scores[winInfo.player] += 1;
    updateScoreboard();
  } else if (board.every(Boolean)) {
    gameOver = true;
    scores.draw += 1;
    updateScoreboard();
  } else {
    currentPlayer = currentPlayer === "X" ? "O" : "X";
  }
  render();
}

function aiMove() {
  if (gameOver) return;
  const index = chooseAiMove(difficultySelect.value);
  if (index === undefined) return;
  board[index] = AI;
  afterMove();
}

function chooseAiMove(difficulty) {
  const empty = board.reduce((acc, v, i) => (v ? acc : [...acc, i]), []);
  if (empty.length === 0) return undefined;

  if (difficulty === "easy") {
    return empty[Math.floor(Math.random() * empty.length)];
  }

  if (difficulty === "medium") {
    return Math.random() < 0.5
      ? empty[Math.floor(Math.random() * empty.length)]
      : bestMove(board, AI);
  }

  return bestMove(board, AI);
}

function bestMove(currentBoard, player) {
  let best = { score: -Infinity, index: undefined };
  const opponent = player === AI ? HUMAN : AI;

  for (let i = 0; i < 9; i++) {
    if (currentBoard[i]) continue;
    currentBoard[i] = player;
    const score = minimax(currentBoard, opponent, player, 0);
    currentBoard[i] = null;
    if (score > best.score) {
      best = { score, index: i };
    }
  }
  return best.index;
}

function minimax(currentBoard, turn, aiPlayer, depth) {
  const winInfo = getWinner(currentBoard);
  if (winInfo) {
    return winInfo.player === aiPlayer ? 10 - depth : depth - 10;
  }
  if (currentBoard.every(Boolean)) return 0;

  const opponent = turn === "X" ? "O" : "X";
  const isMaximizing = turn === aiPlayer;
  let best = isMaximizing ? -Infinity : Infinity;

  for (let i = 0; i < 9; i++) {
    if (currentBoard[i]) continue;
    currentBoard[i] = turn;
    const score = minimax(currentBoard, opponent, aiPlayer, depth + 1);
    currentBoard[i] = null;
    best = isMaximizing ? Math.max(best, score) : Math.min(best, score);
  }
  return best;
}

function getWinner(currentBoard = board) {
  for (const line of WIN_LINES) {
    const [a, b, c] = line;
    if (currentBoard[a] && currentBoard[a] === currentBoard[b] && currentBoard[a] === currentBoard[c]) {
      return { player: currentBoard[a], line };
    }
  }
  return null;
}

function updateScoreboard() {
  scoreXEl.textContent = scores.X;
  scoreOEl.textContent = scores.O;
  scoreDrawEl.textContent = scores.draw;
}

function resetGame() {
  board = Array(9).fill(null);
  currentPlayer = HUMAN;
  gameOver = false;
  render();
}

function resetScores() {
  scores = { X: 0, O: 0, draw: 0 };
  updateScoreboard();
}

resetBtn.addEventListener("click", resetGame);
resetScoresBtn.addEventListener("click", resetScores);
modeSelect.addEventListener("change", () => {
  difficultyLabel.classList.toggle("hidden", !isAiMode());
  resetGame();
});
difficultySelect.addEventListener("change", resetGame);

updateScoreboard();
render();
