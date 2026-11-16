export interface MovieView {
  id: number;
  title: string;
  overview?: string | null;
  release_date?: string | null;
  genres: string[];
  rating?: number | null;
  vote_count?: number | null;
  poster_url?: string | null;
  imdb_id?: string | null;
  imdb_url?: string | null;
  source_url: string;
}

export interface BookView {
  id: string;
  title: string;
  authors: string[];
  description?: string | null;
  published_date?: string | null;
  identifiers: string[];
  source_url: string;
}

export interface ComparisonView {
  movie_id: number;
  book_id: string;
  relation: "confirmed" | "unconfirmed";
  confirmed_information: string[];
  differences: string[];
  opinion: string;
  limitations: string[];
}

export interface ExternalAction {
  id: string;
  kind: "open_external";
  target: "imdb" | "google_books";
  reference_id: string;
  url: string;
}

export interface ChatMetadata {
  movies: MovieView[];
  books: BookView[];
  comparisons: ComparisonView[];
  actions: ExternalAction[];
}

export function validAction(value: unknown): value is ExternalAction {
  if (!value || typeof value !== "object") return false;
  const a = value as Record<string, unknown>;
  if (typeof a.id !== "string" || !a.id || a.id.length > 100 || a.kind !== "open_external") return false;
  if (typeof a.reference_id !== "string" || !/^[A-Za-z0-9_-]{1,80}$/.test(a.reference_id)) return false;
  if (a.target === "imdb") {
    return /^tt\d{5,12}$/.test(a.reference_id) &&
      a.url === `https://www.imdb.com/title/${a.reference_id}/`;
  }
  return a.target === "google_books" &&
    a.url === `https://books.google.com/books?id=${a.reference_id}`;
}

const text = (v: unknown, max = 4000): v is string => typeof v === "string" && v.length <= max;
const optionalText = (v: unknown, max = 4000) => v == null || text(v, max);
const strings = (v: unknown, max = 20): v is string[] =>
  Array.isArray(v) && v.length <= max && v.every((s) => text(s));

export function parseMetadata(value: unknown): ChatMetadata | undefined {
  if (value == null) return undefined;
  if (typeof value !== "object") throw new Error("Metadatos inválidos");
  const m = value as Record<string, unknown>;
  if (!Array.isArray(m.movies) || m.movies.length > 5 || !Array.isArray(m.books) || m.books.length > 5 ||
      !Array.isArray(m.comparisons) || m.comparisons.length > 3 || !Array.isArray(m.actions) || m.actions.length > 2) {
    throw new Error("Metadatos inválidos");
  }
  for (const row of m.movies) {
    const x = row as MovieView;
    if (!x || !Number.isSafeInteger(x.id) || x.id <= 0 || !text(x.title, 500) || !x.title ||
        !strings(x.genres) || !optionalText(x.overview) || !optionalText(x.release_date, 30) ||
        (x.rating != null && (!Number.isFinite(x.rating) || x.rating < 0 || x.rating > 10)) ||
        (x.vote_count != null && (!Number.isSafeInteger(x.vote_count) || x.vote_count < 0)) ||
        x.source_url !== `https://www.themoviedb.org/movie/${x.id}` ||
        (x.poster_url != null && !/^https:\/\/image\.tmdb\.org\/t\/p\/w500\/[A-Za-z0-9_.-]+$/.test(x.poster_url)) ||
        (x.imdb_id != null && !/^tt\d{5,12}$/.test(x.imdb_id)) ||
        (x.imdb_url != null && (!x.imdb_id || x.imdb_url !== `https://www.imdb.com/title/${x.imdb_id}/`))) {
      throw new Error("Película inválida");
    }
  }
  for (const row of m.books) {
    const b = row as BookView;
    if (!b || !text(b.id, 80) || !/^[A-Za-z0-9_-]{1,80}$/.test(b.id) || !text(b.title, 500) || !b.title ||
        !strings(b.authors) || !strings(b.identifiers) || !optionalText(b.description) ||
        !optionalText(b.published_date, 30) || b.source_url !== `https://books.google.com/books?id=${b.id}`) {
      throw new Error("Libro inválido");
    }
  }
  const movies = m.movies as MovieView[], books = m.books as BookView[];
  for (const row of m.comparisons) {
    const c = row as ComparisonView;
    if (!c || !movies.some((x) => x.id === c.movie_id) || !books.some((b) => b.id === c.book_id) ||
        !["confirmed", "unconfirmed"].includes(c.relation) || !strings(c.confirmed_information, 10) ||
        !strings(c.differences, 10) || !text(c.opinion, 2000) || !strings(c.limitations, 10)) {
      throw new Error("Comparación inválida");
    }
  }
  for (const a of m.actions) {
    if (!validAction(a) || !(a.target === "imdb" ? movies.some((x) => x.imdb_id === a.reference_id) :
      books.some((b) => b.id === a.reference_id))) throw new Error("Acción inválida");
  }
  return { movies, books, comparisons: m.comparisons as ComparisonView[], actions: m.actions as ExternalAction[] };
}
