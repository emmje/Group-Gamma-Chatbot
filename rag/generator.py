import os
from typing import Generator, List, Union
from pathlib import Path
from groq import Groq

from rag.vector_store import RetrievedChunk

SYSTEM_PROMPT = (
    "You are an informational chatbot for Uganda Christian University (UCU). "
    "Answer the user's question accurately using ONLY the information provided in the Context below. "
    "RULES:\n"
    "1. Use ONLY facts explicitly stated in the Context. NEVER add, infer, or assume information that is not there.\n"
    "2. Cite sources naturally, e.g. 'According to the Student Code of Conduct, ...' — do NOT use brackets like [Document] or [Source].\n"
    "3. If multiple documents mention the topic, synthesise carefully without conflating or mixing up details.\n"
    "4. Give a clear, concise, conversational answer. Do NOT copy-paste raw text.\n"
    "5. If the Context does not contain enough information, say so honestly — do NOT guess or make things up.\n"
    "6. Do NOT output any internal formatting, tags, or raw context blocks."
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
        return title.title()
    return f"Document {idx + 1}"


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
        f"Source: {_chunk_label(idx, chunk)}\nContent: {chunk.text}"
        for idx, chunk in enumerate(chunks)
    )
    return (
        "Here is the authentic information from official UCU documents:\n"
        "--------------------------------------------------\n"
        f"{context_text}\n"
        "--------------------------------------------------\n\n"
        f"The user is asking: '{question}'\n\n"
        "IMPORTANT:\n"
        "- Answer using ONLY facts from the documents above. Do NOT add information that is not there.\n"
        "- Cite sources naturally (e.g. 'According to the UCU Buildings page, ...' or 'The Student Code of Conduct states that ...').\n"
        "- Do NOT use brackets like [Document] or [Source] — write source names as normal text.\n"
        "- Provide a clear, conversational answer. Do NOT copy-paste raw text.\n"
        "- If the documents do not contain the answer, say so — do NOT guess."
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
