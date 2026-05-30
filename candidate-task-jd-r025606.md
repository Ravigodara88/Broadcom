# 3-Day Candidate Task
## Product Architect — GenAI / AI-ML Engineering (JD R025606)

**Issued:** 2026-05-27
**Due:** 2026-05-30 at 9:00 IST
**Submission:** GitHub repository link sent to abderrahmane.zahrir@broadcom.com

---

## What This Task Is Evaluating

The JD for this role is explicit: we are looking for engineers who solve **real customer problems** with AI, write **production-quality tests** for AI systems, and think about **business value** — not engineers who integrate AI for technology's sake.

This task is designed so that someone who builds first and tests later will score significantly lower than someone who defines quality criteria upfront. **Your test strategy is as important as your implementation.**

---

## Implementation Language — Choose One

You must choose **one** implementation language and use it consistently throughout all three days. Mixed-language implementations will not be evaluated.

| Option | Language | AI Framework | Test Framework |
|---|---|---|---|
| **A — Python** | Python 3.10+ | LangChain / LangGraph / raw API | pytest |
| **B — Spring AI** | Java 21 + Spring Boot 3.5 | Spring AI 1.0 | JUnit 5 + Spring Boot Test |

**Declare your choice** as the first line of your root `README.md`:
```
Implementation: Python   (or)   Implementation: Spring AI
```

Both options are evaluated against identical criteria. Choose the one where you can demonstrate the deepest engineering judgment — not the one you can complete fastest.

### Framework Reference

**Python (Option A)**
- Agent: LangChain `AgentExecutor` / LangGraph `StateGraph` / raw Anthropic or OpenAI function-calling
- Vector store: (to be decided by you)
- Embeddings: `sentence-transformers` or OpenAI `text-embedding-3-small`
- BM25: `rank_bm25` library
- RAG: (to be decided by you)
- MCP: `mcp` Python SDK (`pip install mcp`)

**Spring AI (Option B)**
- Agent: `ChatClient` with `ToolCallback` + advisor chain; or `spring-ai-mcp-server-spring-boot-starter` for MCP
- Vector store: (to be decided by you)
- Embeddings: `OpenAiEmbeddingModel` or `OllamaEmbeddingModel`
- BM25: implement manually or use Apache Lucene's `BM25Similarity`
- RAG: (to be decided by you)
- MCP: `spring-ai-mcp-server-spring-boot-starter`

---

## Scenario

A product manager at an enterprise data management company hands you the following customer feedback aggregated from 6 months of support tickets:

> **"Setting up masking rules is the most time-consuming part of onboarding. Customers connect their database, see hundreds of columns, and have no idea which ones contain PII or what masking function to apply. Our professional services team spends 3–4 days per customer manually reviewing schemas and writing masking configurations."**

Your task is to build an AI-powered **Schema Intelligence Assistant** — a standalone tool that:

1. Analyses a database schema and automatically identifies columns that likely contain PII
2. Suggests appropriate masking rules for each detected PII column
3. Answers natural language questions about data masking capabilities using a documentation RAG
4. Does all of this with a test suite that gives the team confidence to ship it

> **Note:** This is a self-contained engineering task. You are not given access to any production system. All schemas, data, and documentation are created by you as part of the task.

---

## Day 1 — Problem Analysis + PII Detection Engine (8 hours)

### Goal
Before writing a single line of AI code, define quality criteria. Then build the PII detection engine.

### Part 1A — Quality Criteria Document (1 hour, required)

Create `QUALITY_CRITERIA.md` **before** implementing anything. It must define:

**Detection thresholds:**
- What precision and recall targets are acceptable? (Hint: think about the cost asymmetry — a missed PII column is a compliance incident; a false positive just adds a masking review)
- At what confidence score should the system auto-tag vs. route to human review?

**Test data plan:**
- How will you create a labelled test dataset of column schemas? (column name, table name, sample data patterns → is_pii, pii_category)
- What edge cases must the test set include? (obfuscated column names, non-English names, numeric PII like SSN vs account numbers)

**Success metric for Day 1:**
- Define the minimum Recall@PII score your implementation must hit before you would consider it shippable

---

### Part 1B — PII Detection Engine

Build a PII column classifier that takes a column descriptor as input and outputs a detection result.

**Input per column (language-independent JSON contract):**
```json
{
  "table_name": "CUSTOMERS",
  "column_name": "cust_acct_no",
  "data_type": "VARCHAR(20)",
  "sample_values": ["****1234", "ACC-98765", "null"],
  "nullable": true
}
```

**Output:**
```json
{
  "is_pii": true,
  "confidence": 0.91,
  "pii_category": "ACCOUNT_NUMBER",
  "recommended_masking_function": "ACCOUNT_MASK",
  "review_required": false,
  "reasoning": "Column name pattern matches account identifier; sample values match account number format"
}
```

**PII categories to detect** (minimum):
`FULL_NAME`, `EMAIL`, `PHONE`, `SSN`, `CREDIT_CARD`, `ACCOUNT_NUMBER`, `DATE_OF_BIRTH`, `ADDRESS`, `IP_ADDRESS`, `NATIONAL_ID`

**Masking function mapping** (use exactly as specified):

| PII Category | Recommended Masking Function |
|---|---|
| FULL_NAME | NAME_RANDOMIZE |
| EMAIL | EMAIL_MASK |
| PHONE | PHONE_MASK |
| SSN | SSN_MASK |
| CREDIT_CARD | CREDIT_CARD_MASK |
| ACCOUNT_NUMBER | ACCOUNT_MASK |
| DATE_OF_BIRTH | DATE_SHIFT |
| ADDRESS | ADDRESS_RANDOMIZE |
| IP_ADDRESS | IP_MASK |
| NATIONAL_ID | NATIONAL_ID_MASK |

**Implementation approach — your choice, justify it in comments:**
- Option A: Embedding similarity against a PII pattern library (no LLM API call per column — fast, cheap)
- Option B: LLM classification with structured output (higher accuracy, API cost per column)
- Option C: Hybrid — embedding for high-confidence cases, LLM for uncertain ones (recommended)

**Test dataset:**
Create `pii-detector/tests/schema_test_cases.json` with **30 labelled column descriptors** — 15 PII, 15 non-PII, covering at least 8 of the 10 PII categories and including deliberately tricky cases (e.g., `transaction_id` is NOT PII; `national_insurance_number` IS PII with an unusual name).

---

**Tests — Python (pytest):**
```python
# pii-detector/tests/test_detector.py
import pytest
from detector import PiiDetector

detector = PiiDetector()

def test_email_column_detected():
    result = detector.detect({
        "table_name": "USERS", "column_name": "email_address",
        "data_type": "VARCHAR(255)", "sample_values": ["user@example.com"], "nullable": True
    })
    assert result["is_pii"] is True
    assert result["pii_category"] == "EMAIL"
    assert result["recommended_masking_function"] == "EMAIL_MASK"

def test_non_pii_column_not_flagged():
    result = detector.detect({
        "table_name": "ORDERS", "column_name": "transaction_id",
        "data_type": "BIGINT", "sample_values": ["100001", "100002"], "nullable": False
    })
    assert result["is_pii"] is False

def test_low_confidence_sets_review_required():
    result = detector.detect({
        "table_name": "CONTRACTS", "column_name": "ref_code",
        "data_type": "VARCHAR(20)", "sample_values": ["C-2024-001"], "nullable": True
    })
    if result["confidence"] < 0.80:
        assert result["review_required"] is True

def test_recall_on_golden_set():
    import json
    with open("tests/schema_test_cases.json") as f:
        cases = json.load(f)
    pii_cases = [c for c in cases if c["expected"]["is_pii"]]
    detected = sum(1 for c in pii_cases
                   if detector.detect(c["input"])["is_pii"])
    recall = detected / len(pii_cases)
    assert recall >= 0.80, f"Recall {recall:.2f} below threshold"
```

**Tests — Spring AI / JUnit 5:**
```java
// pii-detector/src/test/java/com/example/PiiDetectorTest.java
@SpringBootTest
class PiiDetectorTest {

    @Autowired PiiDetector detector;

    @Test
    void emailColumnIsDetected() {
        ColumnDescriptor col = new ColumnDescriptor(
            "USERS", "email_address", "VARCHAR(255)",
            List.of("user@example.com"), true);
        DetectionResult result = detector.detect(col);
        assertThat(result.isPii()).isTrue();
        assertThat(result.piiCategory()).isEqualTo(PiiCategory.EMAIL);
        assertThat(result.recommendedMaskingFunction()).isEqualTo("EMAIL_MASK");
    }

    @Test
    void nonPiiColumnNotFlagged() {
        ColumnDescriptor col = new ColumnDescriptor(
            "ORDERS", "transaction_id", "BIGINT",
            List.of("100001", "100002"), false);
        DetectionResult result = detector.detect(col);
        assertThat(result.isPii()).isFalse();
    }

    @Test
    void lowConfidenceSetsReviewRequired() {
        ColumnDescriptor col = new ColumnDescriptor(
            "CONTRACTS", "ref_code", "VARCHAR(20)",
            List.of("C-2024-001"), true);
        DetectionResult result = detector.detect(col);
        if (result.confidence() < 0.80) {
            assertThat(result.reviewRequired()).isTrue();
        }
    }

    @Test
    void recallOnGoldenSet() {
        List<TestCase> cases = TestCaseLoader.load("schema_test_cases.json");
        List<TestCase> piiCases = cases.stream()
            .filter(c -> c.expected().isPii()).toList();
        long detected = piiCases.stream()
            .filter(c -> detector.detect(c.input()).isPii()).count();
        double recall = (double) detected / piiCases.size();
        assertThat(recall).isGreaterThanOrEqualTo(0.80);
    }
}
```

**Deliverables for Day 1:**

_Python:_
```
pii-detector/
├── detector.py
├── pii_patterns.py
└── tests/
    ├── schema_test_cases.json
    ├── test_detector.py
    └── eval_report.md
QUALITY_CRITERIA.md
```

_Spring AI:_
```
pii-detector/
├── src/main/java/com/example/
│   ├── PiiDetector.java
│   ├── ColumnDescriptor.java
│   ├── DetectionResult.java
│   └── PiiPatternLibrary.java
└── src/test/java/com/example/
    ├── PiiDetectorTest.java
    ├── schema_test_cases.json
    └── eval_report.md
QUALITY_CRITERIA.md
```

**Definition of done:** All tests pass. `eval_report.md` shows Recall ≥ your stated target in `QUALITY_CRITERIA.md`.

---

## Day 2 — Documentation RAG + Masking Rule Generator (8 hours)

### Goal
Build a RAG system over data masking documentation, and a masking rule generator that combines PII detection results with RAG-retrieved context.

### Part 2A — Documentation Corpus

Create **12 markdown documents** in `rag/corpus/` covering these data masking topics. Write fictional-but-plausible documentation for a generic enterprise data masking tool — content accuracy is not evaluated, only retrieval quality is.

1. What is data masking and why enterprises use it
2. Overview of masking functions and when to use each
3. NAME_RANDOMIZE — usage, parameters, examples
4. EMAIL_MASK — usage, parameters, examples
5. PHONE_MASK, SSN_MASK — usage, parameters, examples
6. CREDIT_CARD_MASK, ACCOUNT_MASK — usage, parameters, examples
7. DATE_SHIFT — usage, parameters, examples
8. ADDRESS_RANDOMIZE, IP_MASK, NATIONAL_ID_MASK — usage, examples
9. How to configure and run a masking job
10. GDPR and CCPA compliance in data masking workflows
11. Common masking errors and troubleshooting
12. Masking performance tuning for large tables

### Part 2B — RAG Pipeline

Implement **hybrid retrieval** — combining vector similarity with BM25 keyword search, fused via Reciprocal Rank Fusion (RRF). Pure vector search only scores partial marks.

Every retrieved chunk must carry a `pii_category` metadata field (set at index time) so the agent can filter by category at query time.

**Retrieval must support filtered queries:**

_Python:_
```python
retrieve(query="how to mask email addresses", pii_category_filter="EMAIL")
```

_Spring AI:_
```java
SearchRequest request = SearchRequest.query("how to mask email addresses")
    .withFilterExpression("pii_category == 'EMAIL'")
    .withTopK(3);
List<Document> results = vectorStore.similaritySearch(request);
```

**Evaluation (required):**
- `rag/eval/masking_queries.json` — 10 test queries, each with the expected source document title
- Report **Recall@3** — target ≥ 0.70
- Include results in `rag/eval/recall_report.md`

### Part 2C — Masking Configuration Generator

Build a module that takes a list of PII detection results and produces a masking configuration document in JSON.

**Output schema:**
```json
{
  "masking_job_name": "AUTO_GENERATED_2026-05-21",
  "generated_by": "SchemaIntelligenceAssistant",
  "confidence_summary": {
    "auto_configured": 8,
    "requires_review": 2,
    "not_pii": 15
  },
  "masking_rules": [
    {
      "table": "CUSTOMERS",
      "column": "cust_acct_no",
      "masking_function": "ACCOUNT_MASK",
      "parameters": {},
      "confidence": 0.91,
      "requires_review": false,
      "documentation_reference": "account_mask.md#usage"
    }
  ],
  "review_queue": [
    {
      "table": "ORDERS",
      "column": "ref_code",
      "reason": "Low confidence (0.62) — column name ambiguous",
      "suggested_function": "ACCOUNT_MASK",
      "alternatives": ["SSN_MASK", "NATIONAL_ID_MASK"]
    }
  ]
}
```

**Tests — Python (pytest):**
```python
def test_low_confidence_goes_to_review_queue():
    detections = [DetectionResult(column="ref_code", table="ORDERS",
                                   is_pii=True, confidence=0.62,
                                   pii_category="ACCOUNT_NUMBER",
                                   recommended_masking_function="ACCOUNT_MASK",
                                   review_required=True)]
    config = generator.generate(detections)
    assert any(r["column"] == "ref_code" for r in config["review_queue"])
    assert not any(r["column"] == "ref_code" for r in config["masking_rules"])

def test_documentation_references_exist():
    config = generator.generate(sample_detections())
    corpus_files = {f.name for f in Path("rag/corpus").glob("*.md")}
    for rule in config["masking_rules"]:
        doc_file = rule["documentation_reference"].split("#")[0]
        assert doc_file in corpus_files
```

**Tests — Spring AI / JUnit 5:**
```java
@Test
void lowConfidenceGoesToReviewQueue() {
    DetectionResult detection = DetectionResult.builder()
        .column("ref_code").table("ORDERS")
        .isPii(true).confidence(0.62)
        .piiCategory(PiiCategory.ACCOUNT_NUMBER)
        .reviewRequired(true).build();
    MaskingConfig config = generator.generate(List.of(detection));
    assertThat(config.reviewQueue())
        .anyMatch(r -> r.column().equals("ref_code"));
    assertThat(config.maskingRules())
        .noneMatch(r -> r.column().equals("ref_code"));
}

@Test
void documentationReferencesExist() {
    MaskingConfig config = generator.generate(sampleDetections());
    Set<String> corpusFiles = loadCorpusFileNames();
    config.maskingRules().forEach(rule -> {
        String docFile = rule.documentationReference().split("#")[0];
        assertThat(corpusFiles).contains(docFile);
    });
}
```

**Deliverables for Day 2:**

_Python:_
```
rag/
├── ingest.py
├── retrieve.py
├── corpus/               ← 12 markdown documents
└── eval/
    ├── masking_queries.json
    └── recall_report.md
masking-generator/
├── generator.py
└── tests/
    ├── test_generator.py
    └── test_integration_pipeline.py
```

_Spring AI:_
```
rag/
├── src/main/java/com/example/rag/
│   ├── DocumentIngestionService.java
│   └── HybridRetrievalService.java
├── corpus/               ← 12 markdown documents
└── eval/
    ├── masking_queries.json
    └── recall_report.md
masking-generator/
└── src/
    ├── main/java/com/example/MaskingConfigGenerator.java
    └── test/java/com/example/
        ├── MaskingConfigGeneratorTest.java
        └── IntegrationPipelineTest.java
```

---

## Day 3 — AI Agent + Testing + Write-ups (8 hours)

### Goal
Build the conversational agent, complete the AI output quality test suite, and produce the write-ups.

### Part 3A — Schema Intelligence Agent

Wire the PII detector, masking config generator, and RAG retrieval into a conversational agent.

**The agent must handle these 7 interaction types correctly:**

| User Input | Expected Behaviour |
|---|---|
| `"Analyse this schema for PII"` + schema JSON | Runs detector, returns results with confidence scores |
| `"Generate a masking configuration for these results"` | Calls generator, returns masking config JSON |
| `"What does DATE_SHIFT do and what parameters does it accept?"` | Retrieves from RAG, answers with document citation |
| `"Is column ref_code in table ORDERS PII?"` | Runs detector on single column, returns result with reasoning |
| `"How do I comply with GDPR when masking customer data?"` | Retrieves compliance doc, answers grounded in it |
| `"What is the weather in Hyderabad?"` | Refuses gracefully — out of scope |
| `"Mask this column: [no schema provided]"` | Asks for schema — does not hallucinate |

**Tools available to the agent:**
- `detect_pii_columns(schema)` — calls your Day 1 detector
- `generate_masking_config(detections)` — calls your Day 2 generator
- `search_masking_docs(query, pii_category_filter?)` — calls your Day 2 RAG

**Grounding rule:** The agent must never answer a documentation question without first calling `search_masking_docs`.

---

**Agent implementation — Python (LangGraph example skeleton):**
```python
# agent/agent.py
from langgraph.graph import StateGraph, END
from tools import detect_pii_columns, generate_masking_config, search_masking_docs

tools = [detect_pii_columns, generate_masking_config, search_masking_docs]

def build_agent():
    graph = StateGraph(AgentState)
    graph.add_node("reason", reasoning_node)
    graph.add_node("call_tool", tool_node)
    graph.add_edge("reason", "call_tool")
    graph.add_conditional_edges("call_tool",
                                 should_continue,
                                 {"continue": "reason", "end": END})
    graph.set_entry_point("reason")
    return graph.compile()
```

**Agent implementation — Spring AI example skeleton:**
```java
// agent/src/main/java/com/example/SchemaIntelligenceAgent.java
@Service
public class SchemaIntelligenceAgent {

    private final ChatClient chatClient;

    public SchemaIntelligenceAgent(ChatClient.Builder builder,
                                    PiiDetectorTool piiTool,
                                    MaskingConfigTool maskingTool,
                                    DocumentSearchTool searchTool) {
        this.chatClient = builder
            .defaultSystem("""
                You are a Schema Intelligence Assistant for data masking.
                Only answer questions about PII detection and data masking.
                Always call search_masking_docs before answering documentation questions.
                """)
            .defaultTools(piiTool, maskingTool, searchTool)
            .build();
    }

    public String chat(String userMessage) {
        return chatClient.prompt()
            .user(userMessage)
            .call()
            .content();
    }
}
```

---

### Part 3B — AI Output Quality Test Suite

This is **the most important deliverable**. Create the quality test file for your chosen language.

**Required test types (implement all 6):**

---

**1. Semantic correctness (keyword assertion — not string matching)**

_Python:_
```python
def test_date_shift_answer_is_grounded():
    response = agent.chat("What does DATE_SHIFT do?")
    assert any(kw in response.lower()
               for kw in ["shift", "offset", "date", "preserve", "format"])
    assert response_cites_source(response)
```

_Spring AI:_
```java
@Test
void dateShiftAnswerIsGrounded() {
    String response = agent.chat("What does DATE_SHIFT do?");
    assertThat(response.toLowerCase())
        .containsAnyOf("shift", "offset", "date", "preserve", "format");
    assertThat(responseUtil.citesSource(response)).isTrue();
}
```

---

**2. Grounding enforcement (tool call interception)**

_Python:_
```python
def test_doc_question_triggers_retrieval():
    with tool_call_tracker() as tracker:
        agent.chat("What parameters does EMAIL_MASK accept?")
    assert "search_masking_docs" in tracker.called_tools
```

_Spring AI:_
```java
@Test
void docQuestionTriggersRetrieval() {
    // Use a mock/spy on DocumentSearchTool to verify invocation
    agent.chat("What parameters does EMAIL_MASK accept?");
    verify(documentSearchTool, atLeastOnce()).search(anyString(), any());
}
```

---

**3. Out-of-scope rejection**

_Python:_
```python
def test_out_of_scope_query_rejected():
    response = agent.chat("What is the capital of France?")
    assert_no_hallucination(response)
    assert any(phrase in response.lower()
               for phrase in ["out of scope", "can't help", "masking", "data"])
```

_Spring AI:_
```java
@Test
void outOfScopeQueryRejected() {
    String response = agent.chat("What is the capital of France?");
    assertThat(response.toLowerCase())
        .containsAnyOf("out of scope", "can't help", "masking", "data");
    assertThat(responseUtil.appearsToAnswerQuestion(response, "France")).isFalse();
}
```

---

**4. PII detection accuracy regression**

_Python:_
```python
def test_pii_detector_recall_regression():
    results = run_detector_on_golden_set()
    recall = compute_recall(results)
    assert recall >= 0.80, f"PII recall regression: {recall:.2f} < 0.80"
```

_Spring AI:_
```java
@Test
void piiDetectorRecallRegression() {
    List<TestCase> goldenSet = TestCaseLoader.load("schema_test_cases.json");
    long correct = goldenSet.stream()
        .filter(tc -> tc.expected().isPii())
        .filter(tc -> piiDetector.detect(tc.input()).isPii())
        .count();
    long total = goldenSet.stream().filter(tc -> tc.expected().isPii()).count();
    double recall = (double) correct / total;
    assertThat(recall).isGreaterThanOrEqualTo(0.80);
}
```

---

**5. Masking config completeness**

_Python:_
```python
def test_masking_config_covers_high_confidence_detections():
    schema = load_test_schema("10_column_schema.json")
    detections = detector.detect_all(schema)
    config = generator.generate(detections)
    high_conf = [d for d in detections if d.confidence >= 0.80 and d.is_pii]
    configured = {r["column"] for r in config["masking_rules"]}
    for d in high_conf:
        assert d.column_name in configured
```

_Spring AI:_
```java
@Test
void maskingConfigCoversHighConfidenceDetections() {
    List<ColumnDescriptor> schema = SchemaLoader.load("10_column_schema.json");
    List<DetectionResult> detections = detector.detectAll(schema);
    MaskingConfig config = generator.generate(detections);
    Set<String> configured = config.maskingRules().stream()
        .map(MaskingRule::column).collect(Collectors.toSet());
    detections.stream()
        .filter(d -> d.isPii() && d.confidence() >= 0.80)
        .forEach(d -> assertThat(configured).contains(d.columnName()));
}
```

---

**6. A/B baseline (model comparison)**

Create a separate script / test class that runs 5 standard queries, scores response quality against a rubric you define, and outputs a comparison table establishing the baseline for future model version comparisons.

_Python:_ `agent/tests/ab_comparison.py` → outputs `ab_baseline_results.md`

_Spring AI:_ `agent/src/test/java/com/example/AbBaselineTest.java` → outputs `ab_baseline_results.md`

---

### Part 3C — Customer Value Write-up

Create `CUSTOMER_VALUE.md` (max 400 words) answering:

1. **Baseline problem:** What specific customer pain does this tool address?
2. **Measurable outcome:** How would you measure success in a 30-day pilot with 3 customers? Name specific metrics.
3. **Risk and limitations:** What can this tool get wrong, and what guardrails did you build?
4. **What you would NOT automate:** What parts of the process should stay human, and why?

### Part 3D — Scalability Write-up

Create `SCALABILITY.md` (max 400 words) answering:

1. **PII detection at scale:** Customer has a schema with 5,000 columns. How do you keep detection time under 30 seconds?
2. **RAG freshness:** The product team releases a new masking function. How does the RAG corpus stay current automatically?
3. **Cost control:** At 500 customers each running schema analysis weekly, what is your estimated LLM API cost per month and how would you optimise it?
4. **Quality monitoring in production:** What metrics would you alert on, and at what thresholds?

---

## Final Repository Structure

_Python (Option A):_
```
/
├── README.md                    ← First line: "Implementation: Python"
├── QUALITY_CRITERIA.md          ← First commit
├── CUSTOMER_VALUE.md
├── SCALABILITY.md
├── .env.example
├── requirements.txt
├── pii-detector/
│   ├── detector.py
│   ├── pii_patterns.py
│   └── tests/
│       ├── schema_test_cases.json
│       ├── test_detector.py
│       └── eval_report.md
├── rag/
│   ├── ingest.py
│   ├── retrieve.py
│   ├── corpus/
│   └── eval/
├── masking-generator/
│   ├── generator.py
│   └── tests/
└── agent/
    ├── agent.py
    ├── tools.py
    └── tests/
        ├── quality_tests.py
        ├── ab_comparison.py
        └── ab_baseline_results.md
```

_Spring AI (Option B):_
```
/
├── README.md                    ← First line: "Implementation: Spring AI"
├── QUALITY_CRITERIA.md          ← First commit
├── CUSTOMER_VALUE.md
├── SCALABILITY.md
├── .env.example
├── pom.xml  (or build.gradle)
├── pii-detector/src/
│   ├── main/java/com/example/
│   │   ├── PiiDetector.java
│   │   ├── ColumnDescriptor.java
│   │   ├── DetectionResult.java
│   │   └── PiiPatternLibrary.java
│   └── test/java/com/example/
│       ├── PiiDetectorTest.java
│       ├── schema_test_cases.json
│       └── eval_report.md
├── rag/
│   ├── src/main/java/com/example/rag/
│   │   ├── DocumentIngestionService.java
│   │   └── HybridRetrievalService.java
│   ├── corpus/
│   └── eval/
├── masking-generator/src/
│   ├── main/java/com/example/MaskingConfigGenerator.java
│   └── test/java/com/example/
│       ├── MaskingConfigGeneratorTest.java
│       └── IntegrationPipelineTest.java
└── agent/src/
    ├── main/java/com/example/
    │   ├── SchemaIntelligenceAgent.java
    │   └── tools/
    └── test/java/com/example/
        ├── AgentQualityTest.java
        ├── AbBaselineTest.java
        └── ab_baseline_results.md
```

### Root README.md must include:
1. **First line:** `Implementation: Python` or `Implementation: Spring AI`
2. **Architecture diagram** (ASCII) — data flow from schema input to masking config output
3. **Setup and run instructions** — one-command setup preferred (`pip install -r requirements.txt` or `mvn spring-boot:run`)
4. **Design decisions** — 5 bullets on non-obvious choices and why (including why you chose Python vs Spring AI)
5. **What you would do differently** with more time — honest reflection required
6. **Test coverage summary** — what is tested, what is not, and why

---

## Scoring Weights

| Area | Weight | Highest-value signal |
|---|---|---|
| QA mindset (QUALITY_CRITERIA + test suite depth) | 30% | Quality criteria written before implementation; all 6 quality test types present |
| PII detection accuracy + testing | 20% | Recall reported on labelled set; review queue correctly populated |
| RAG pipeline quality | 15% | Hybrid retrieval implemented; Recall@3 ≥ 0.70 |
| Agent correctness | 20% | All 7 interaction types correct; grounding enforced |
| Customer value + scalability write-ups | 15% | Specific metrics; honest about limitations |

Both Python and Spring AI submissions are scored against the same criteria. Language choice does not affect your score.

**Full rubric:** See `scoring-sheet-jd-r025606.csv`

---

## Rules

- You **may** use LLMs to assist with coding — be prepared to explain every line in the review
- You **may not** skip the quality tests — a submission without the 6 quality test types scores 0 on the QA category
- `QUALITY_CRITERIA.md` must be the **first commit** — we will check the commit timestamp
- External LLM APIs permitted; local models (Ollama) are also acceptable
- Keep LLM API costs reasonable — use smaller models where quality allows
- If you are blocked, include `BLOCKERS.md` — partial work with honest documentation scores higher than silence

---

## Submission

Send a GitHub repository link (private — add `abderrahmane.zahrir@broadcom.com` as collaborator) to abderrahmane.zahrir@broadcom.com by **2026-05-25 at 10:00 IST**.

Subject line: `AI Architect Task Submission — R025606`
