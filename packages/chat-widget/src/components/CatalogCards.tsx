import { useState } from "react";
import type { BookView, ChatMetadata, MovieView } from "../types/presentation";

export function MovieCard({ movie }: { movie: MovieView }) {
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  return <article className="agichat-catalog-card" aria-label={`Película: ${movie.title}`}>
    <div className="agichat-poster">
      {movie.poster_url && !failed ? <>
        {!loaded && <span role="status">Cargando póster…</span>}
        <img src={movie.poster_url} alt={`Póster de ${movie.title}`} loading="lazy"
          referrerPolicy="no-referrer" onLoad={() => setLoaded(true)} onError={() => setFailed(true)} />
      </> : <span role="img" aria-label={`Póster no disponible para ${movie.title}`}>Póster no disponible</span>}
    </div>
    <div><h3>{movie.title}</h3>
      {movie.release_date && <p>Estreno: {movie.release_date.slice(0, 4)}</p>}
      {movie.genres.length > 0 && <p>{movie.genres.join(" · ")}</p>}
      {movie.rating != null && <p>TMDB: {movie.rating.toFixed(1)}/10{movie.vote_count != null && ` (${movie.vote_count} votos)`}</p>}
      {movie.overview && <p>{movie.overview.length > 380 ? `${movie.overview.slice(0, 380)}…` : movie.overview}</p>}
      <a href={movie.source_url} target="_blank" rel="noopener noreferrer">Fuente: TMDB</a>
      {movie.imdb_url && <> · <a href={movie.imdb_url} target="_blank" rel="noopener noreferrer">Ver en IMDb</a></>}
    </div>
  </article>;
}

export function BookCard({ book }: { book: BookView }) {
  return <article className="agichat-book-card" aria-label={`Libro: ${book.title}`}>
    <h3>{book.title}</h3>
    <p>{book.authors.length ? book.authors.join(", ") : "Autor no disponible"}</p>
    {book.published_date && <p>Publicación: {book.published_date}</p>}
    {book.description && <p>{book.description.slice(0, 500)}{book.description.length > 500 ? "…" : ""}</p>}
    {book.identifiers.length > 0 && <p>{book.identifiers.join(" · ")}</p>}
    <a href={book.source_url} target="_blank" rel="noopener noreferrer">Ver en Google Books</a>
  </article>;
}

export function CatalogCards({ data }: { data: ChatMetadata }) {
  return <div className="agichat-catalog">
    {data.movies.length > 0 && <section aria-label="Películas consultadas">
      {data.movies.map((movie) => <MovieCard key={`${movie.id}:${movie.poster_url}`} movie={movie} />)}
    </section>}
    {data.books.length > 0 && <section aria-label="Libros consultados">
      {data.books.map((book) => <BookCard key={book.id} book={book} />)}
    </section>}
    {data.comparisons.map((c) => <section className="agichat-comparison" aria-label="Comparación libro y película" key={`${c.movie_id}:${c.book_id}`}>
      <h3>Libro y película</h3>
      <p><strong>{data.movies.find((m) => m.id === c.movie_id)?.title}</strong> ↔ {data.books.find((b) => b.id === c.book_id)?.title}</p>
      <p><strong>{c.relation === "confirmed" ? "Relación respaldada por las fuentes" : "Relación no confirmada"}</strong></p>
      <h4>Información de las fuentes</h4><ul>{c.confirmed_information.map((fact, i) => <li key={i}>{fact}</li>)}</ul>
      {c.differences.length > 0 && <><h4>Diferencias verificables de metadatos</h4><ul>{c.differences.map((fact, i) => <li key={i}>{fact}</li>)}</ul></>}
      {c.opinion && <><h4>Opinión de Damián (IA)</h4><p>{c.opinion}</p></>}
      <h4>Límites de la comparación</h4><ul>{c.limitations.map((limit, i) => <li key={i}>{limit}</li>)}</ul>
    </section>)}
  </div>;
}
