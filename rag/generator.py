import os
from typing import Generator, List, Union
from pathlib import Path
from groq import Groq

from rag.vector_store import RetrievedChunk

SYSTEM_PROMPT = (
    "You are an informational chatbot for Uganda Christian University (UCU). "
    "Answer the user's question accurately using ONLY the information provided in the Context below. "
    "If the answer is found in the Context, state it clearly and concisely. "
    "Always cite the source document name, e.g., 'According to the [Document Title], ...'. "
    "Do NOT output raw context blocks or internal formatting. "
    "If the Context does not contain enough information to answer the question, say so honestly."
)

def llm_translate(text: str, target_language: str, model: str = None) -> str:
    if not model:
        model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return text

    client = _build_groq_client(api_key)
    prompt = (
        f"Translate the following text directly into {target_language}. "
        "IMPORTANT RULES:\n"
        "1. Capture the conversational intent, not just literal word-for-word meaning (e.g. greetings should translate to greetings, not literal nouns).\n"
        "2. Respond ONLY with the translated text, with no conversational filler, markdown formatting, or quotes.\n\n"
        f"Text to translate: {text}"
    )
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception:
        return text




def _build_groq_client(api_key: str) -> Groq:
    raw_base_url = os.getenv("GROQ_BASE_URL", "").strip()
    if not raw_base_url:
        return Groq(api_key=api_key)

    normalized = raw_base_url.rstrip("/")
    if normalized.endswith("/openai/v1"):
        normalized = normalized[: -len("/openai/v1")]

    return Groq(api_key=api_key, base_url=normalized)


def _chunk_label(idx: int, chunk: RetrievedChunk) -> str:
    """Build a human-readable label for a context block."""
    title = chunk.metadata.get("title", "")
    if not title:
        source = chunk.metadata.get("source", "")
        if source:
            title = Path(source).stem.replace("_", " ").replace("-", " ").strip()
    if title:
        return f'[Document: {title}]'
    return f"[Document {idx + 1}]"


# Accept both RetrievedChunk lists (new) and plain strings (legacy callers)
ContextInput = Union[List[RetrievedChunk], List[str]]


def _normalise_chunks(context: ContextInput) -> List[RetrievedChunk]:
    """Ensure we always work with RetrievedChunk objects."""
    if not context:
        return []
    if isinstance(context[0], str):
        return [
            RetrievedChunk(text=t, metadata={}, distance=0.0)
            for t in context  # type: ignore[union-attr]
        ]
    return context  # type: ignore[return-value]


def build_prompt(question: str, context: ContextInput) -> str:
    chunks = _normalise_chunks(context)
    context_text = "\n\n".join(
        f"Document: {_chunk_label(idx, chunk)}\nContent: {chunk.text}"
        for idx, chunk in enumerate(chunks)
    )
    return (
        "You are a helpful, conversational chatbot for Uganda Christian University.\n"
        "Here is the authentic information from our official documents:\n"
        "--------------------------------------------------\n"
        f"{context_text}\n"
        "--------------------------------------------------\n\n"
        f"The user is asking: '{question}'\n\n"
        "CRITICAL INSTRUCTIONS:\n"
        "1. Provide a natural-sounding, conversational answer based ONLY on the documents provided.\n"
        "2. You MUST include the exact Document name in your answer to prove it is authentic (e.g., 'According to the [Document Title], ...').\n"
        "3. Do NOT just copy-paste the raw text. Synthesize a good response.\n"
        "4. If the documents do not contain the answer, politely say you don't have that information."
    )


def generate_answer(question: str, context: ContextInput, model: str) -> str:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is required for answer generation.")

    prompt = build_prompt(question, context)
    client = _build_groq_client(api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=300,
    )
    return (response.choices[0].message.content or "").strip()


def generate_answer_stream(
    question: str, context: ContextInput, model: str
) -> Generator[str, None, None]:
    """Stream tokens one by one."""
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is required for answer generation.")

    prompt = build_prompt(question, context)
    client = _build_groq_client(api_key)
    stream = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=300,
        stream=True,
    )
    for chunk in stream:
        token = chunk.choices[0].delta.content
        if token:
            yield token
