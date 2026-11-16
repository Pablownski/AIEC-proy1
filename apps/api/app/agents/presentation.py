"""Resolve LLM-selected identities against actual tool artifacts, within the turn lock."""

import re
import unicodedata
from uuid import uuid4

from pydantic import ValidationError

from app.schemas.presentation import (
    ChatMetadata,
    ComparisonView,
    ExternalAction,
    MovieView,
    PresentationSelection,
)
from app.tools.models import Book, Movie, ToolResult


def normalized(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", value.casefold()) if char.isalnum()
    )


def wants_references(text: str) -> bool:
    return bool(reference_targets(text))


def reference_targets(text: str) -> set[str]:
    text = "".join(
        c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c)
    )
    if re.search(r"\bno\s+(?:quiero\s+)?(?:abr\w*|compar\w*)", text):
        return set()
    if re.search(r"\b(compar\w*|adaptacion)\b", text):
        return {"imdb", "google_books"}
    if not re.search(r"\b(abre|abreme|abrir|open)\b", text):
        return set()
    targets = set()
    if "imdb" in text:
        targets.add("imdb")
    if "books" in text or "libro" in text:
        targets.add("google_books")
    return targets or {"imdb", "google_books"}


def parse_selection(text: str) -> tuple[str, PresentationSelection | None]:
    try:
        selection = PresentationSelection.model_validate_json(text)
        return selection.content, selection
    except ValidationError:
        return text, None  # Plain-text agents and older clients remain supported.


def build_metadata(
    results: list[ToolResult], selection: PresentationSelection | None, user_text: str
) -> ChatMetadata | None:
    movies: dict[int, Movie] = {}
    books: dict[str, Book] = {}
    for result in results:
        for item in result.items:
            if isinstance(item, Movie):
                previous = movies.get(item.id)
                data = item.model_dump(exclude_none=True)
                if previous:
                    data = {**previous.model_dump(), **{k: v for k, v in data.items() if v != []}}
                movies[item.id] = Movie.model_validate(data)
            else:
                books[item.id] = item
    movie_ids = list(dict.fromkeys(selection.movie_ids)) if selection else list(movies)[-5:]
    book_ids = list(dict.fromkeys(selection.book_ids)) if selection else list(books)[-5:]
    if selection:
        movie_ids = list(dict.fromkeys([*movie_ids, *(c.movie_id for c in selection.comparisons)]))[
            :5
        ]
        book_ids = list(dict.fromkeys([*book_ids, *(c.book_id for c in selection.comparisons)]))[:5]
    views = []
    for movie_id in movie_ids:
        if movie_id in movies:
            movie = movies[movie_id]
            imdb = re.fullmatch(r"https://www\.imdb\.com/title/(tt\d{5,12})/", movie.imdb_url or "")
            views.append(MovieView(**movie.model_dump(), imdb_id=imdb[1] if imdb else None))
    selected_books = [books[book_id] for book_id in book_ids if book_id in books]
    valid_movies = {movie.id for movie in views}
    valid_books = {book.id for book in selected_books}
    comparisons = []
    for chosen in selection.comparisons if selection else []:
        if chosen.movie_id not in valid_movies or chosen.book_id not in valid_books:
            continue
        movie, book = movies[chosen.movie_id], books[chosen.book_id]
        authors = {normalized(author) for author in book.authors}
        credit_match = any(
            credit.job == "Novel" and normalized(credit.name) in authors
            for credit in movie.writing_credits
        )
        confirmed = credit_match and normalized(movie.title) == normalized(book.title)
        info = [f"TMDB: {movie.title}", f"Google Books: {book.title}"]
        if confirmed:
            info.append("Coinciden el título y el autor acreditado por TMDB con el rol Novel.")
        differences = (
            [f"Publicación del libro: {book.published_date}; estreno: {movie.release_date}."]
            if book.published_date and movie.release_date
            else []
        )
        comparisons.append(
            ComparisonView(
                movie_id=movie.id,
                book_id=book.id,
                relation="confirmed" if confirmed else "unconfirmed",
                confirmed_information=info,
                differences=differences,
                opinion=chosen.opinion,
                limitations=[
                    "Los metadatos no permiten verificar diferencias de escenas ni fidelidad."
                ]
                + ([] if confirmed else ["No se puede confirmar la relación con estas fuentes."]),
            )
        )
    actions = []
    targets = reference_targets(user_text)
    if targets:
        action_movies = (
            [m for m in views if m.id == comparisons[0].movie_id] if comparisons else views
        )
        action_books = (
            [b for b in selected_books if b.id == comparisons[0].book_id]
            if comparisons
            else selected_books
        )
        candidates = [
            ("imdb", movie.imdb_id, movie.imdb_url) for movie in action_movies if movie.imdb_id
        ][:1]
        candidates += [("google_books", book.id, book.source_url) for book in action_books][:1]
        for target, reference, url in candidates:
            if target not in targets:
                continue
            actions.append(
                ExternalAction.model_validate(
                    {"id": uuid4().hex, "target": target, "reference_id": reference, "url": url}
                )
            )
    if not views and not selected_books:
        return None
    return ChatMetadata(
        movies=views, books=selected_books, comparisons=comparisons, actions=actions
    )
