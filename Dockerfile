# Reproducible harness image: stdlib only, so one layer is enough.
FROM python:3.11-slim

WORKDIR /repo
COPY . .

# Build the knowledge base (lexical + hashed-vector indexes) at image time so the
# container can answer retrieval queries without a writable checkout.
RUN python tools/kb_build.py \
 && python tools/vector_eval.py --cases evals/rag_cases.yaml --k 3 > /dev/null \
 && python tools/mcp_call.py --check > /dev/null

CMD ["python", "tools/eval_runner.py", "--cases", "evals/test_cases.yaml", \
     "--expected", "evals/expected_results.yaml"]
