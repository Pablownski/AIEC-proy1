import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CatalogCards, MovieCard, BookCard } from "../src/components/CatalogCards";
import { ChatWidget } from "../src/components/ChatWidget";
import { metadata, richReply } from "./presentation-fixture";

describe("provider cards", () => {
  it("renders movies, books, comparison evidence, opinion and limitations separately", () => {
    render(<CatalogCards data={metadata} />);
    expect(screen.getByText("TMDB: 7.5/10 (123 votos)")).toBeVisible();
    expect(screen.getByText("Relación respaldada por las fuentes")).toBeVisible();
    expect(screen.getByText("Opinión de Damián (IA)")).toBeVisible();
    expect(screen.getByRole("link", { name: "Ver en Google Books" })).toHaveAttribute("rel", "noopener noreferrer");
    const image = screen.getByAltText("Póster de Obra de prueba");
    expect(screen.getByRole("status")).toHaveTextContent("Cargando póster");
    fireEvent.load(image);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
  it("handles multiple recommendations, long summaries and failed poster requests", () => {
    render(<CatalogCards data={{ ...metadata, movies: [metadata.movies[0]!, { ...metadata.movies[0]!,
      id: 12, title: "Otra obra", overview: "x".repeat(400) }], comparisons: [], books: [] }} />);
    expect(screen.getAllByRole("article")).toHaveLength(2);
    fireEvent.error(screen.getByAltText("Póster de Otra obra"));
    expect(screen.getByRole("img", { name: "Póster no disponible para Otra obra" })).toBeVisible();
  });
  it("does not fabricate missing images, ratings, authors, dates or relationships", () => {
    const movie = { ...metadata.movies[0]!, poster_url: null, rating: null, vote_count: null,
      release_date: null, overview: null, genres: [], imdb_url: null };
    render(<><MovieCard movie={movie} /><BookCard book={{ ...metadata.books[0]!, authors: [],
      description: "x".repeat(550), published_date: null, identifiers: [] }} />
      <CatalogCards data={{ movies: [], books: [], actions: [], comparisons: [{ ...metadata.comparisons[0]!,
        relation: "unconfirmed", opinion: "", differences: [] }] }} /></>);
    expect(screen.getByText("Autor no disponible")).toBeVisible();
    expect(screen.getByText("Relación no confirmada")).toBeVisible();
    expect(screen.queryByText(/TMDB: /)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Ver en IMDb" })).not.toBeInTheDocument();
  });
  it("integrates cards, automatic-action fallback and visible capabilities in the widget", async () => {
    vi.spyOn(window, "open").mockReturnValue(null);
    const user = userEvent.setup();
    render(<ChatWidget agentName="Damián" transport={{ sendMessage: vi.fn().mockResolvedValue(richReply) }} />);
    expect(screen.getByText(/Asistente de inteligencia artificial:/)).toBeVisible();
    await user.type(screen.getByLabelText("Escribe un mensaje"), "Compárala con su libro{Enter}");
    const status = await screen.findByText("No se pudieron abrir algunas referencias. Ábrelas aquí:");
    expect(within(status.parentElement!).getByRole("link", { name: "Abrir IMDb" })).toHaveAttribute("href", metadata.actions[0]!.url);
    expect(await screen.findByText("Aquí está la comparación.")).toBeVisible();
    expect(screen.getByLabelText("Créditos de datos e imágenes")).toHaveTextContent("This product uses the TMDB API");
    vi.restoreAllMocks();
  });
});
