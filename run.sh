#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ─────────────────────────────────────────────
# Helper: print the welcome banner
# ─────────────────────────────────────────────
show_help() {
    echo ""
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║        Schema Intelligence Assistant — run.sh        ║"
    echo "╚══════════════════════════════════════════════════════╝"
    echo ""
    echo "  Usage:  ./run.sh <command> [args]"
    echo ""
    echo "  Commands:"
    echo "    chat              Start the interactive assistant (default)"
    echo "    test              Run all test suites (PII, RAG, agent)"
    echo "    ingest            Refresh RAG corpus chunks/metadata from markdown docs"
    echo "    detect '<json>'   Detect PII in a single column descriptor"
    echo "    mcp               Launch MCP server (stdio transport, for IDE/CLI clients)"
    echo "    mcp --sse         Launch MCP server (SSE transport on http://localhost:8000)"
    echo ""
    echo "  Examples:"
    echo "    ./run.sh"
    echo "    ./run.sh chat"
    echo "    ./run.sh test"
    echo "    ./run.sh ingest"
    echo "    ./run.sh mcp"
    echo "    ./run.sh detect '{\"column_name\":\"email\",\"data_type\":\"VARCHAR\",\"sample_values\":[\"a@b.com\"]}'"
    echo ""
}

# ─────────────────────────────────────────────
# Validate virtualenv
# ─────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo ""
    echo "  ERROR: .venv not found."
    echo ""
    echo "  To set up the environment, run:"
    echo "    python -m venv .venv"
    echo "    source .venv/bin/activate"
    echo "    pip install -r requirements.txt"
    echo "    ./run.sh ingest     # validate corpus chunks/metadata"
    echo "    ./run.sh            # start chatting"
    echo ""
    exit 1
fi

source .venv/bin/activate

# Optional: force HuggingFace to use cached models only.
# Set FORCE_HF_OFFLINE=1 in restricted corporate networks.
if [ "${FORCE_HF_OFFLINE:-0}" = "1" ]; then
    export HF_HUB_OFFLINE=1
fi

# ─────────────────────────────────────────────
# Route command
# ─────────────────────────────────────────────
case "${1:-chat}" in
    chat)
        echo ""
        echo "  Starting Schema Intelligence Assistant..."
        echo "  Type your question (e.g. 'How do I mask an email column?')"
        echo "  Type 'exit' or press Ctrl-C to quit."
        echo ""
        python chat.py
        echo ""
        echo "  Session ended. Run './run.sh chat' to start a new session."
        echo ""
        ;;
    test)
        echo ""
        echo "  Running all test suites..."
        echo "  (PII detector → Masking generator → Agent quality)"
        echo ""
        python -m pytest pii-detector/tests/ masking-generator/tests/ agent/tests/ -v
        echo ""
        echo "  Running RAG Recall@3 quality gate (threshold: >= 0.70)..."
        python - <<'PY'
from rag.retrieve import evaluate_recall_at_k

report = evaluate_recall_at_k()
top_k = int(report.get("top_k", 3))
recall = float(report.get("recall_at_k", 0.0))

print(f"  Recall@{top_k}: {recall:.2f}")
if recall < 0.70:
    raise SystemExit(f"RAG recall gate failed: {recall:.2f} < 0.70")
print("  RAG recall gate passed.")
PY
        echo ""
        echo "  All tests complete. Check output above for any failures."
        echo "  Next: './run.sh chat' to start the assistant."
        echo ""
        ;;
    ingest)
        echo ""
        echo "  Refreshing RAG corpus chunks/metadata from markdown docs..."
        python -m rag.ingest
        echo ""
        echo "  Corpus refresh complete. Retrieval builds an in-memory FAISS index at query time."
        echo "  Next: './run.sh chat' to start chatting."
        echo ""
        ;;
    detect)
        if [ -z "${2}" ]; then
            echo ""
            echo "  ERROR: No column JSON provided."
            echo ""
            echo "  Usage:"
            echo "    ./run.sh detect '<column-json>'"
            echo ""
            echo "  Example:"
            echo "    ./run.sh detect '{\"column_name\":\"email\",\"data_type\":\"VARCHAR\",\"sample_values\":[\"a@b.com\"]}'"
            echo ""
            exit 1
        fi
        echo ""
        echo "  Running PII detection..."
        echo ""
        python -c "
import sys, json
sys.path.insert(0, 'pii-detector')
from detector import HybridPiiDetector
print(HybridPiiDetector().detect(json.loads('${2}')))
"
        echo ""
        echo "  Done. 'is_pii=True' means the column should be masked."
        echo "  Run './run.sh chat' to get masking recommendations."
        echo ""
        ;;
    mcp)
        TRANSPORT_ARG=""
        if [ "${2}" = "--sse" ]; then
            TRANSPORT_ARG="--sse"
            echo ""
            echo "  Starting MCP server (SSE transport)..."
            echo "  Listening on http://localhost:8000"
            echo "  Press Ctrl-C to stop."
        else
            echo ""
            echo "  Starting MCP server (stdio transport)..."
            echo "  Connect using any MCP-compatible client (Claude Desktop, VS Code, Cursor)."
            echo "  Press Ctrl-C to stop."
        fi
        echo ""
        python agent/mcp_server.py $TRANSPORT_ARG
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo ""
        echo "  Unknown command: '${1}'"
        show_help
        exit 1
        ;;
esac
