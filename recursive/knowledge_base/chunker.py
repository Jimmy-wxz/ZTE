from typing import List, Dict, Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

from .document_parser import parse_file


DEFAULT_SEPARATORS = ["\n\n", "\n", ".", "。", "!", "?", "；", ";", "，", ",", " ", ""]


def chunk_documents(
    file_paths: List[str],
    knowledge_base_name: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> List[Dict[str, Any]]:
    """Parse files and split them into chunks with metadata."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=DEFAULT_SEPARATORS,
        length_function=len,
    )

    chunks = []
    for file_path in file_paths:
        try:
            text = parse_file(file_path)
        except Exception as e:
            from loguru import logger
            logger.warning("Skipping file {} due to parse error: {}".format(file_path, e))
            continue

        if not text.strip():
            continue

        file_name = file_path.split("/")[-1]
        split_texts = splitter.split_text(text)
        for idx, chunk_text in enumerate(split_texts):
            if len(chunk_text.strip()) < 20:
                continue
            chunks.append({
                "id": "{}:{}:{}".format(knowledge_base_name, file_name, idx),
                "text": chunk_text,
                "metadata": {
                    "source": file_name,
                    "file_path": file_path,
                    "chunk_index": idx,
                    "knowledge_base_name": knowledge_base_name,
                },
            })

    return chunks
