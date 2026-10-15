# RAG 知识库（项目内检索）

## 用来解决什么

Agent 每次规划都要"回忆"：这类故障以前怎么处理？有哪些硬件约束？评测阈值是多少？
这些答案本来就躺在仓库里（`docs/`、`prompts/`、`agents/`、`evals/log_rules/`、`examples/`），
靠模型记忆是不可靠的——`kb_search` 把仓库变成可检索的证据源，并且**每条结论都带引用**。

## 数据流

```
仓库文本 ──chunker(按标题/段落分块)──▶ 倒排索引(BM25, CJK bigram + ASCII token)
                                            │
                    任务/问题 ──▶ kb_search ─┴─▶ hits[{path, lines, citation, score, snippet}]
                                            │
                                            ▼
                        Planner 方案 / Tester 断言 / Trace 证据链
```

## 实现要点（全部标准库）

- **分块**：Markdown 按标题切、超长段按空行再切；非 Markdown 按固定行窗滑切。块保留
  `path#Lstart-Lend`，可回溯到原文件。
- **分词**：ASCII 词（小写）+ 中文单字与**二元组**——中文不依赖分词器也能召回，
  「采样窗口」既能被整词也能被「采样」「窗口」命中。
- **打分**：BM25（`k1=1.2, b=0.75`），并按字段加权：正文 + 标题路径 + 文件路径，
  文件名参与索引，所以「coding_rules」「planner」这类查询能直接命中对应文件。
- **索引持久化**：`rag/index/kb_index.json`（`python tools/kb_build.py` 重建）。

## 怎么用

```bash
python tools/kb_build.py                       # 重建索引（34 个文件 → 136 块）
python tools/kb_query.py --query "ADC 采样窗口 振铃" --k 3
python tools/kb_query.py --cases evals/rag_cases.yaml --k 3   # 检索质量评测
python tools/mcp_call.py --tool kb_search --args "{\"query\": \"评测 分层\"}"
```

编排器在规划前会自动检索（`--kb` / `--kb-k` 可调），把命中片段作为 `knowledge`
连同引用一起交给 Planner，并写进 `traces/<task>/trace.jsonl`——**方案里引用的每条经验都能查到出处**。

## 检索质量

| 指标 | 说明 |
|---|---|
| `recall_at_k` | 期望文档是否出现在前 k 条（默认 k=3） |
| `mrr` | 期望文档排名的倒数均值 |

用例在 `evals/rag_cases.yaml`，由 `tools/kb_query.py --cases` 打分，纳入八层评测的同一份报告。
