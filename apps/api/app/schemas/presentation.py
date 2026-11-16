"""Optional public presentation contract. URLs come from validated provider identities."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.tools.models import Book, Movie


class MovieView(Movie):
    imdb_id: str | None = Field(default=None, pattern=r"^tt\d{5,12}$")


class ComparisonView(BaseModel):
    movie_id: int
    book_id: str
    relation: Literal["confirmed", "unconfirmed"]
    confirmed_information: list[str] = Field(default_factory=list, max_length=10)
    differences: list[str] = Field(default_factory=list, max_length=10)
    opinion: str = Field(default="", max_length=2000)
    limitations: list[str] = Field(default_factory=list, max_length=10)


class ExternalAction(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    kind: Literal["open_external"] = "open_external"
    target: Literal["imdb", "google_books"]
    reference_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    url: str

    @model_validator(mode="after")
    def canonical_url(self) -> ExternalAction:
        import re

        if self.target == "imdb":
            if not re.fullmatch(r"tt\d{5,12}", self.reference_id):
                raise ValueError("IMDb ID inválido")
            expected = f"https://www.imdb.com/title/{self.reference_id}/"
        else:
            expected = f"https://books.google.com/books?id={self.reference_id}"
        if self.url != expected:
            raise ValueError("Destino externo inválido")
        return self


class ChatMetadata(BaseModel):
    movies: list[MovieView] = Field(default_factory=list, max_length=5)
    books: list[Book] = Field(default_factory=list, max_length=5)
    comparisons: list[ComparisonView] = Field(default_factory=list, max_length=3)
    actions: list[ExternalAction] = Field(default_factory=list, max_length=2)

    @model_validator(mode="after")
    def known_references(self) -> ChatMetadata:
        for movie in self.movies:
            if movie.source_url != f"https://www.themoviedb.org/movie/{movie.id}":
                raise ValueError("Fuente TMDB inconsistente")
            if movie.imdb_url and movie.imdb_url != f"https://www.imdb.com/title/{movie.imdb_id}/":
                raise ValueError("Fuente IMDb inconsistente")
        for book in self.books:
            if book.source_url != f"https://books.google.com/books?id={book.id}":
                raise ValueError("Fuente Books inconsistente")
        movies = {movie.id for movie in self.movies}
        books = {book.id for book in self.books}
        if any(c.movie_id not in movies or c.book_id not in books for c in self.comparisons):
            raise ValueError("Comparación sin fuentes")
        for action in self.actions:
            allowed = {movie.imdb_id for movie in self.movies} if action.target == "imdb" else books
            if action.reference_id not in allowed:
                raise ValueError("Acción sin fuente")
        return self


class AgentReply(BaseModel):
    content: str = Field(min_length=1)
    metadata: ChatMetadata | None = None


class ComparisonSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    movie_id: int
    book_id: str = Field(max_length=80)
    opinion: str = Field(default="", max_length=2000)


class PresentationSelection(BaseModel):
    """The LLM supplies IDs and labelled opinion, never executable URLs."""

    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=12000)
    movie_ids: list[int] = Field(default_factory=list, max_length=5)
    book_ids: list[str] = Field(default_factory=list, max_length=5)
    comparisons: list[ComparisonSelection] = Field(default_factory=list, max_length=3)
