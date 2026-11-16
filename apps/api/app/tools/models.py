from typing import Annotated, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Query = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
VolumeID = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,80}$")]
Genre = Literal[
    "fantasía",
    "comedia",
    "drama",
    "acción",
    "aventura",
    "terror",
    "ciencia ficción",
    "animación",
    "romance",
    "misterio",
    "suspenso",
    "familia",
]
GENRES = dict(
    zip(get_args(Genre), [14, 35, 18, 28, 12, 27, 878, 16, 10749, 9648, 53, 10751], strict=True)
)


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SearchMovies(Arguments):
    query: Query
    year: int | None = Field(default=None, ge=1870, le=2100)


class DiscoverMovies(Arguments):
    genre: Genre
    min_rating: float = Field(default=6.0, ge=0, le=10, allow_inf_nan=False)


class MovieDetails(Arguments):
    movie_id: int = Field(gt=0, le=2_147_483_647)


class SearchBooks(Arguments):
    title: Query | None = None
    author: Query | None = None

    @model_validator(mode="after")
    def require_query(self) -> "SearchBooks":
        if not self.title and not self.author:
            raise ValueError("title o author es obligatorio")
        return self


class BookDetails(Arguments):
    volume_id: VolumeID


INPUTS: dict[str, type[Arguments]] = {
    "search_movies": SearchMovies,
    "discover_movies": DiscoverMovies,
    "movie_details": MovieDetails,
    "search_books": SearchBooks,
    "book_details": BookDetails,
}


ShortText = Annotated[str, StringConstraints(max_length=300)]


class WritingCredit(BaseModel):
    name: ShortText
    job: ShortText


class Movie(BaseModel):
    kind: Literal["movie"] = "movie"
    id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=500)
    overview: str | None = Field(default=None, max_length=4000)
    release_date: str | None = Field(default=None, max_length=30)
    genres: list[ShortText] = Field(default_factory=list, max_length=20)
    rating: float | None = Field(default=None, ge=0, le=10, allow_inf_nan=False)
    vote_count: int | None = Field(default=None, ge=0)
    poster_url: str | None = Field(
        default=None, pattern=r"^https://image\.tmdb\.org/t/p/w500/[A-Za-z0-9_.-]+$"
    )
    imdb_url: str | None = Field(
        default=None, pattern=r"^https://www\.imdb\.com/title/tt\d{5,12}/$"
    )
    source_url: str = Field(pattern=r"^https://www\.themoviedb\.org/movie/[0-9]+$")
    keywords: list[ShortText] = Field(default_factory=list, max_length=30)
    writing_credits: list[WritingCredit] = Field(default_factory=list, max_length=20)


class Book(BaseModel):
    kind: Literal["book"] = "book"
    id: VolumeID
    title: str = Field(min_length=1, max_length=500)
    authors: list[ShortText] = Field(default_factory=list, max_length=20)
    description: str | None = Field(default=None, max_length=4000)
    published_date: str | None = Field(default=None, max_length=30)
    identifiers: list[ShortText] = Field(default_factory=list, max_length=20)
    source_url: str = Field(pattern=r"^https://books\.google\.com/books\?id=[A-Za-z0-9_-]{1,80}$")


class ToolResult(BaseModel):
    source: Literal["tmdb", "google_books"]
    items: list[Movie | Book] = Field(default_factory=list, max_length=5)
    error: (
        Literal[
            "configuration",
            "authentication",
            "rate_limit",
            "timeout",
            "connection",
            "unavailable",
            "invalid_response",
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def check_source(self) -> "ToolResult":
        for item in self.items:
            expected = (
                f"https://www.themoviedb.org/movie/{item.id}"
                if isinstance(item, Movie)
                else f"https://books.google.com/books?id={item.id}"
            )
            if item.source_url != expected or (self.source == "tmdb") != isinstance(item, Movie):
                raise ValueError("Fuente inconsistente")
        if self.error and self.items:
            raise ValueError("Un error no puede contener resultados")
        return self
