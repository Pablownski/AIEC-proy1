import type { ChatMetadata } from "../src/types/presentation";
import type { ChatMessage } from "../src/types/chat";

export const metadata: ChatMetadata = {
  movies: [{ id: 11, title: "Obra de prueba", overview: "Una aventura de fantasía.",
    release_date: "2001-01-01", genres: ["Fantasía"], rating: 7.5, vote_count: 123,
    poster_url: "https://image.tmdb.org/t/p/w500/test.jpg", imdb_id: "tt1234567",
    imdb_url: "https://www.imdb.com/title/tt1234567/", source_url: "https://www.themoviedb.org/movie/11" }],
  books: [{ id: "test_volume", title: "Obra de prueba", authors: ["Autor Prueba"],
    description: "La obra original.", published_date: "1990", identifiers: ["ISBN_13:123"],
    source_url: "https://books.google.com/books?id=test_volume" }],
  comparisons: [{ movie_id: 11, book_id: "test_volume", relation: "confirmed",
    confirmed_information: ["TMDB acredita al autor con el rol Novel."],
    differences: ["El libro se publicó en 1990; la película se estrenó en 2001."],
    opinion: "Puede valer la pena por su género; es una opinión.",
    limitations: ["No hay evidencia de diferencias de escenas."] }],
  actions: [{ id: "action-imdb", kind: "open_external", target: "imdb", reference_id: "tt1234567",
    url: "https://www.imdb.com/title/tt1234567/" },
    { id: "action-books", kind: "open_external", target: "google_books", reference_id: "test_volume",
      url: "https://books.google.com/books?id=test_volume" }],
};
export const richReply: ChatMessage = { id: "rich", role: "assistant", content: "Aquí está la comparación.",
  createdAt: "2026-01-01T00:00:00Z", metadata };
export const wireReply = { conversation_id: "test", message: { id: richReply.id, role: "assistant",
  content: richReply.content, created_at: richReply.createdAt, metadata } };
