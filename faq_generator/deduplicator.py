from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from faq_generator.models import QAPair


def _normalize(question: str) -> str:
    """Lowercase and collapse all whitespace runs to a single space."""
    return " ".join(question.lower().split())


def _make_union_find(n: int) -> list[int]:
    return list(range(n))


def _find(parent: list[int], x: int) -> int:
    while parent[x] != x:
        parent[x] = parent[parent[x]]  # path compression
        x = parent[x]
    return x


def _union(parent: list[int], x: int, y: int) -> None:
    rx, ry = _find(parent, x), _find(parent, y)
    if rx != ry:
        parent[ry] = rx


def deduplicate(
    pairs: list[QAPair], similarity_threshold: float = 0.85
) -> tuple[list[QAPair], int]:
    """Return (deduplicated_pairs, removed_count)."""

    # --- Pass 1: Exact match ---
    seen: set[str] = set()
    pass1_pairs: list[tuple[QAPair, str]] = []  # (pair, normalized_question)

    for pair in pairs:
        norm = _normalize(pair.question)
        if norm not in seen:
            seen.add(norm)
            pass1_pairs.append((pair, norm))

    # --- Pass 2: TF-IDF cluster pass ---
    if len(pass1_pairs) <= 1:
        surviving = [p for p, _ in pass1_pairs]
    else:
        normalized_questions = [norm for _, norm in pass1_pairs]

        vectorizer = TfidfVectorizer()
        tfidf_matrix = vectorizer.fit_transform(normalized_questions)
        sim_matrix = cosine_similarity(tfidf_matrix)

        n = len(pass1_pairs)
        parent = _make_union_find(n)

        for i in range(n):
            for j in range(i + 1, n):
                if sim_matrix[i, j] >= similarity_threshold:
                    _union(parent, i, j)

        # Group indices by cluster root
        clusters: dict[int, list[int]] = {}
        for i in range(n):
            root = _find(parent, i)
            clusters.setdefault(root, []).append(i)

        # From each cluster, keep the pair with greatest len(q) + len(a);
        # ties broken by earliest index in pass1_pairs
        surviving = []
        for indices in clusters.values():
            best_idx = max(
                indices,
                key=lambda i: (
                    len(pass1_pairs[i][0].question) + len(pass1_pairs[i][0].answer),
                    -i,  # negate index so max() prefers smallest (earliest) index
                ),
            )
            surviving.append(pass1_pairs[best_idx][0])

        # Restore original relative order (order by position in pass1_pairs)
        pass1_index = {id(p): idx for idx, (p, _) in enumerate(pass1_pairs)}
        surviving.sort(key=lambda p: pass1_index[id(p)])

    # --- Pass 3: Per-document preservation ---
    surviving_doc_paths: set = {p.doc_path for p in surviving}
    all_doc_paths: set = {p.doc_path for p in pairs}
    missing_docs = all_doc_paths - surviving_doc_paths

    for doc_path in missing_docs:
        # Find best pair from the *original* input for this doc
        candidates = [
            (idx, p) for idx, p in enumerate(pairs) if p.doc_path == doc_path
        ]
        # max by (len(q)+len(a), -original_index) → earliest on tie
        _, best = max(
            candidates,
            key=lambda t: (len(t[1].question) + len(t[1].answer), -t[0]),
        )
        surviving.append(best)

    removed_count = len(pairs) - len(surviving)
    print(f"Removed {removed_count} duplicate(s)")
    return surviving, removed_count
