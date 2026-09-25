# Build and operate a LangGraph RAG agent

This course teaches you to run the supplied project, understand each part, change it safely and deploy a small commercial pilot on a VPS or AWS. You do not need to be an experienced programmer. You do need to practise the commands and recognise when a test has failed.

Your first goal is a document assistant that answers from approved material and shows its evidence. Your later goal is to reuse the same structure for another business. Work through the lessons in order. Keep real customer data out of the learning environment until you finish the operating and commercial checks.

## Learning route

| Stage | Practical result | Suggested sessions |
|---|---|---|
| Understand the parts | Explain a question's journey through the system | 1 to 2 |
| Run the demo | Upload a document and inspect a source citation | 1 |
| Follow the code | Find the upload, retrieval and generation functions | 2 |
| Use live AI | Compare real semantic retrieval with the free demo | 1 |
| Modify and evaluate | Make a small change and check it against examples | 2 to 3 |
| Deploy | Run the same service on a VPS, then repeat on EC2 | 2 to 4 |
| Operate a pilot | Restore a backup and onboard an isolated customer | 2 to 3 |

Treat these as 45 to 90 minute practice sessions, not promises about how quickly you will become a production engineer. The course gives you a working foundation; handling real customers still requires judgement and ongoing maintenance.

## Lesson 1 Understand what you are building

An AI model generates text. Your application decides what information the model receives and what it may do. LangGraph connects those application steps into a workflow. A RAG assistant adds retrieval: it searches your approved material before asking the model to answer.

RAG means retrieval augmented generation. It does not train the model or permanently teach it your documents. When you update a policy, you update the searchable document collection. The model then receives the relevant new passages at question time.

This repository's main graph is deliberately bounded. It rewrites a follow-up question, retrieves passages, answers or declines, and saves the conversation. It does not choose arbitrary tools or perform business transactions. The later tool lesson shows that distinction in code.

Think of the system as a small service with different responsibilities:

| Part | Plain meaning | Responsibility here |
|---|---|---|
| Browser workspace | A simple control screen | Upload and ask questions |
| FastAPI | The service's front door | Receive HTTP requests, check keys and validate inputs |
| LangGraph | The workflow controller | Decide which step runs next and carry state between steps |
| AI model | The language generator | Rewrite questions and generate answers from passages |
| Embedding model | A text-to-number converter | Turn document chunks and questions into comparable vectors |
| Qdrant | A searchable vector store | Find passages similar to the question |
| PostgreSQL | A structured database | Store document status, request counters and chat checkpoints |
| Docker | A repeatable runtime package | Run the service and databases in separate containers |
| Caddy | The HTTPS entry point | Receive public HTTPS traffic and forward it to FastAPI |
| Git and GitHub | Version history and remote hosting for code | Keep changes reviewable and run automated checks |

A vector is a list of numbers representing text for a particular embedding model. Similar meanings often produce nearby vectors. The similarity score is not the probability that an answer is correct. Two different embedding models can output the same number of values but still use incompatible vector spaces.

**Checkpoint:** Explain why this project needs both Qdrant and PostgreSQL. Qdrant retrieves text by vector similarity. PostgreSQL records structured application state and conversations. Either database could support more features, but these responsibilities are deliberately separated here.

## Lesson 2 Follow ingestion and answering

Ingestion happens when an administrator uploads a file. The API checks the key and reads a bounded amount of data. The parser extracts text, breaks it into chunks, and preserves PDF page numbers. The embedding model converts each chunk into a vector. Qdrant stores vectors together with text and metadata. PostgreSQL marks the document ready only after all writes succeed.

Chunking means splitting a large document into smaller pieces. The default is 1,200 characters with 200 characters repeated between adjacent chunks. The overlap helps preserve a sentence or idea near a boundary. These are character counts, not token counts. PDFs are split within pages to keep source page references straightforward.

At question time, FastAPI identifies the customer from the API key. LangGraph may rewrite a follow-up into a standalone question. The embedding model converts that question into a vector. Qdrant searches only ready documents belonging to that customer. The model receives the selected passages and generates an answer with citation numbers. If no passages meet the threshold, the graph declines without asking the answer model to invent something.

The server checks that citation numbers refer to passages it actually retrieved. This prevents made-up source numbers, but it does not verify that the passage logically supports every statement. That is why answer evaluation remains necessary.

Conversation memory and document knowledge have different purposes. A checkpoint remembers what happened in a conversation. Qdrant holds the approved material the assistant searches. Do not use a remembered previous answer as proof of the current policy.

**Exercise:** Sketch the ingestion path and question path on paper. Mark where a paid model call occurs. Ingestion needs embedding calls; a question needs a query embedding and, when evidence exists, an answer call. Follow-ups can also need a rewrite call.

## Lesson 3 Run the first demo

Install Python 3 and a Docker Desktop version supported by your operating system. On Windows, use the supported WSL 2 setup and enable hardware virtualisation if Docker requests it. Check Docker's current Windows requirements before upgrading an older machine. You can also use the VPS lesson if your local computer cannot run Docker comfortably.

Extract the source ZIP. Open the `nimble-rag-agent` folder in your editor. A code editor such as VS Code helps you see files, but you can run the project from a normal terminal. Open a terminal in that folder; `compose.yaml` must be visible there.

On Windows PowerShell:

```powershell
py -3 --version
docker version
docker compose version
py -3 scripts/setup_env.py
docker compose up -d --build
docker compose ps
```

On macOS/Linux, use `python3` instead of `py -3`. Do not type the commentary lines printed by a command back into the terminal. If `docker version` cannot connect to the engine, start Docker Desktop and wait for it to finish starting.

The setup command creates `.env` with random credentials and displays an admin key and reader key. Save those keys. A `.env` file holds private configuration; it is not the application source code and must not be committed to Git. Running setup a second time refuses to overwrite it.

Open http://localhost:8000. Paste the admin key, press Connect, upload `examples/refund-policy.md`, and ask “What is the refund period?” Expect an excerpt mentioning 30 days and a clickable source section. The free demo uses simple word matching and returns an excerpt, so it cannot demonstrate fluent answers, true semantic matching or intelligent follow-ups.

**Checkpoint:** Use the reader key. It should still answer a question, but upload should be rejected. Stop and restart the stack with `docker compose stop` and `docker compose start`. Your uploaded document should remain because the databases use named volumes.

## Lesson 4 Learn just enough Python and HTTP

A variable gives a value a name. A dictionary stores values under keys, such as `{"question": "Refund period?"}`. A function is a named block of work with an input and a result. A type hint such as `question: str` says the value should be text. An import lets one file use code from another. An exception signals that a step failed.

JSON is the text format used for most API requests and responses. HTTP methods describe actions: GET reads, POST submits work, and DELETE removes a resource. An endpoint is an address such as `/v1/chat`. A status code tells you the outcome: 200 means success, 401 means an invalid credential, 403 means insufficient permission, and 503 means a dependency could not complete the work.

The browser workspace sends the same API requests you can send from another application. On your local demo, open http://localhost:8000/docs, use Authorize to enter `X-API-Key`, and try `POST /v1/chat` with this JSON:

```json
{
  "question": "What is the refund period?",
  "thread_id": null
}
```

The response returns a `thread_id`. Reuse it for the next message if you want a continuing conversation. Use `null` for a fresh conversation. Never add a `tenant_id` to the request: the server derives the customer identity from the key and rejects unrecognised request fields.

**Exercise:** Find `ChatRequest` in `app/schemas.py`. Change the question maximum length from 2,000 to 1,500 characters, rebuild the API and try a longer question. Then revert the edit. You have changed input validation, not model behaviour.

## Lesson 5 Read the project in the right order

Do not try to understand every dependency first. Follow the path of one upload and one question.

| File | Look for | What you learn |
|---|---|---|
| `app/schemas.py` | ChatRequest and ChatResponse | The API input and output shapes |
| `app/main.py` | upload and chat routes | How an HTTP call enters the application |
| `app/security.py` | authenticate and internal_thread | How customer identity and conversation isolation work |
| `app/runtime.py` | ingest and delete_document | The document lifecycle and cross-database coordination |
| `app/parsing.py` | parse_and_chunk | Extraction, chunking and validation |
| `app/vectors.py` | scope and search | Mandatory tenant filters and Qdrant queries |
| `app/graph.py` | build_graph | Workflow nodes, branches and saved state |
| `app/models.py` | FakeAI and OpenAIAI | How the offline and paid backends differ |
| `app/store.py` | PostgresStore | Structured records, quotas and locks |
| `app/config.py` | Settings | Environment variables and startup checks |

The files in `tests` exercise important behaviours. `compose.yaml` describes the local containers. `compose.prod.yaml` adds production settings and the HTTPS proxy. `scripts` holds repeatable operating tasks. `docs` explains how to use and maintain the system.

Configuration is different from code. Changing `.env` normally requires recreating the API container. Changing a Python file requires rebuilding the image in the provided Docker workflow. The image contains a copy of your application; it is not automatically watching your source folder.

**Checkpoint:** Identify the exact function that adds the tenant filter to every vector search. Then find the code that excludes documents whose status is still `indexing` or `deleting`.

## Lesson 6 Build a tiny LangGraph yourself

Install `uv` using its official installation instructions, then run these commands from the project folder:

```bash
uv sync --frozen
uv run python examples/lesson_graph.py
```

`uv sync` creates a project-specific Python environment and installs the versions recorded in `uv.lock`. It keeps project libraries separate from your computer's other Python programs. The `--frozen` option uses the existing lock file instead of silently changing dependency choices.

Open `examples/lesson_graph.py`. `State` describes the values carried through the workflow. The `answer` function is a node. An edge connects one node to the next. START and END mark the entry and completion. `compile` assembles the graph and `invoke` runs it with input data.

Change the example's answer function to return the question in uppercase. Run it again. Next, add a second node that prefixes “Result ” to the answer, connect the first node to it, and connect it to END. This exercise has no network calls or model fees, so you can experiment safely.

Now inspect `app/graph.py`. Its conditional edge chooses `generate` when passages exist and `abstain` otherwise. Its checkpointer saves state in PostgreSQL. The public conversation UUID is combined with the authenticated tenant and active collection before it becomes a checkpoint thread ID.

**Checkpoint:** Explain the difference between the state, a node, an edge and a checkpoint without looking at the code.

## Lesson 7 Use a real model and inspect retrieval

Create a provider API key for this application and configure its budget controls. Edit `.env`, set `AI_BACKEND=openai`, and add `OPENAI_API_KEY`. The supplied defaults use GPT-4.1 mini for language generation and text-embedding-3-small for vectors. These are configurable examples, not a claim that they are the best model for every task.

```bash
docker compose up -d --force-recreate api
```

Upload the example again. The collection changes because fake and live embeddings must never mix. Ask the direct refund question, then a paraphrase such as “How much time do I have to return an unused order?” Then ask something the policy cannot answer, such as the owner's favourite colour.

Inspect the sources. If the right passage was retrieved but the answer is poor, investigate the prompt or model. If the right passage was never retrieved, investigate document content, chunk boundaries, embedding quality and search settings. Increasing the model size will not reliably fix missing evidence.

`TOP_K` controls how many passages are retrieved. `SCORE_THRESHOLD` controls the minimum similarity score. A higher threshold can reduce irrelevant matches but also cause more refusals. A lower threshold can find more material but include weak matches. The live default 0.30 is a starting value to tune against your documents, not a calibrated confidence cutoff. Fake mode uses at most 0.10 to support its simple word-matching demonstration.

**Exercise:** In a test environment, compare three threshold values on the same ten questions. Record the retrieved source, answer quality and refusals. Change one setting at a time. Do not experiment directly on customer production data.

## Lesson 8 Reuse the project for another business

Suppose your next customer needs an internal product-support assistant. Duplicate the source into a new project, give it a distinct Compose project name and credentials if it will run on the same host, and add a customer-specific test set. Changing the folder name alone does not change the explicit Compose project name in `compose.yaml`.

Start with that customer's approved manuals and support policies. Change the system instructions in `OpenAIAI.answer` to describe the assistant's role and tone while preserving the evidence-only and citation rules. Change the browser title and explanatory text in `app/static/index.html`. Rebuild, upload the manuals and run the evaluation set.

Do not rewrite authentication, tenant filtering or deletion just to customise wording. If a new project needs a different document format, add parsing support and tests for that format. If it needs live inventory data, add a controlled read-only integration instead of pretending a periodically uploaded document is current stock.

Keep a small change log: what you changed, why, how you checked it, and how to undo it. A good reuse exercise is to make a second fictional policy assistant with different documents and demonstrate that none of the first project's data appears.

## Lesson 9 See a model choose a tool

A tool is a function the model may request the application to run. `examples/tool_agent.py` is a separate learning script with one harmless tool that converts minutes to seconds. Unlike the bounded RAG graph, its model can decide to call a tool, inspect the result, and continue. The graph has a recursion limit so it cannot loop indefinitely.

The script requires live API access and is not part of the web application's endpoints. After setting your API key in `.env`, run it from the project folder:

```bash
uv run --env-file .env python examples/tool_agent.py
```

Read the `@tool` function, the model's `bind_tools` call, `ToolNode`, and the conditional edge. A tool call is a structured request, not permission to do anything the model asks. The application still validates arguments and controls which functions exist.

For a future tool that sends an email or changes a business system, add a durable human approval step and an audit record. Also add idempotency so retrying the same approved action does not send it twice. Those features are not in the supplied RAG service and should be built before attaching write-capable tools.

## Lesson 10 Use tests and version control

Run the project checks after a meaningful change:

```bash
uv run ruff check .
uv run pytest -q
```

Ruff catches certain code mistakes and formatting problems. Tests check behaviour such as whether another tenant can retrieve your document or whether failed ingestion remains hidden. Passing these tests does not measure real model accuracy or prove the cloud deployment works. The verification guide records exactly what was exercised.

Git stores snapshots of source changes. A branch lets you experiment without immediately changing the main version. A commit is a named checkpoint in code history; it is unrelated to a LangGraph conversation checkpoint.

If your source ZIP has no `.git` folder, initialise it with `git init -b main`, then add files with `git add .` and inspect `git status` before committing. Confirm `.env`, private keys and backups are absent. Commit with `git commit -m "Create the RAG starter"`. Configure your own Git name and email if Git requests them.

To publish manually, create an empty **private** GitHub repository named `nimble-rag-agent`, without an initial README. Follow GitHub's displayed commands to add its remote and push this existing repository. Authenticate through the approved GitHub CLI or credential flow; never paste a token into source files. If a remote has already been created for this project, use that repository rather than creating a second one.

GitHub Actions runs `.github/workflows/ci.yml` after pushes. It checks Python code, starts a disposable PostgreSQL service, exercises restart persistence and builds/starts the Docker stack. Investigate a red run before deploying that commit. The workflow does not deploy to your server or create AWS resources.

## Lesson 11 Deploy and recover

Read `VPS.md` for the first public deployment. Repeat the same application setup using `AWS.md` to understand EC2, security groups, EBS and costs. Read `OPERATIONS.md` before deleting anything or accepting customer files. Complete a restore exercise; having a backup file is not sufficient.

Use a VPS first if your immediate goal is learning the application and operating a small pilot. Use the EC2 path when learning AWS is itself part of the goal or the customer needs AWS. Managed cloud services can reduce some maintenance duties, but they add networking, permissions and billing decisions.

## Lesson 12 Decide whether you are ready for a pilot

You should be able to explain a request end to end, add a document, create and revoke a customer key, inspect a cited answer, diagnose a failed request, restore a backup, and update to a known code version. If any of those depend on guessing commands, practise them with fictional data before accepting a paid service obligation.

Then use `COMMERCIAL.md` to define the scope, evaluate real answers, calculate your costs and agree operating responsibilities. Start with an internal assistant and a human fallback. Expand the product only when a customer need and test evidence justify the next feature.

## Further reading

See `SOURCES.md` for the official documentation used for this project and the reference repository. The companion guides are also included as full chapters in the downloadable training document.
