import { describe, expect, it } from "vitest";
import { parseMetadata, validAction, type ChatMetadata } from "../src/types/presentation";
import { decodeMessage } from "../src/transport/decode-message";
import { metadata, wireReply } from "./presentation-fixture";

describe("validated presentation contract", () => {
  it("preserves metadata and accepts the old text-only contract", () => {
    expect(parseMetadata(metadata)).toEqual(metadata);
    expect(parseMetadata(null)).toBeUndefined();
    expect(parseMetadata(undefined)).toBeUndefined();
    expect(decodeMessage(wireReply.message).metadata).toEqual(metadata);
    expect(decodeMessage({ ...wireReply.message, metadata: null }).metadata).toBeUndefined();
  });
  it.each([null, {}, { ...wireReply.message, role: "tool" }, { ...wireReply.message, metadata: "bad" }])(
    "rejects invalid messages", (message) => expect(() => decodeMessage(message)).toThrow(),
  );
  it.each([null, {}, { ...metadata.actions[0], id: "" }, { ...metadata.actions[0], kind: "exec" },
    { ...metadata.actions[0], reference_id: "../bad" }, { ...metadata.actions[0], target: "other" },
    { ...metadata.actions[0], reference_id: "bad" },
    { ...metadata.actions[0], url: "javascript:alert(1)" },
    { ...metadata.actions[0], url: "https://www.imdb.com.evil/title/tt1234567/" },
    { ...metadata.actions[1], url: "https://books.google.com/books?id=test_volume#evil" },
  ])("rejects unsafe external actions", (action) => expect(validAction(action)).toBe(false));
  it.each([42, {}, { ...metadata, movies: "bad" }, { ...metadata, books: "bad" },
    { ...metadata, comparisons: "bad" }, { ...metadata, actions: "bad" },
    { ...metadata, movies: Array(6).fill(metadata.movies[0]) },
    { ...metadata, books: Array(6).fill(metadata.books[0]) },
    { ...metadata, comparisons: Array(4).fill(metadata.comparisons[0]) },
    { ...metadata, actions: Array(3).fill(metadata.actions[0]) },
  ])("bounds metadata containers", (data) => expect(() => parseMetadata(data)).toThrow());

  const mutations: Array<(m: ChatMetadata) => void> = [
    (m) => { m.movies[0]!.id = -1; }, (m) => { m.movies[0]!.title = ""; },
    (m) => { m.movies[0]!.genres = ["x".repeat(5000)]; },
    (m) => { m.movies[0]!.overview = "x".repeat(4001); },
    (m) => { m.movies[0]!.release_date = "x".repeat(31); },
    (m) => { m.movies[0]!.rating = Infinity; }, (m) => { m.movies[0]!.rating = -1; },
    (m) => { m.movies[0]!.rating = 11; }, (m) => { m.movies[0]!.vote_count = -1; },
    (m) => { m.movies[0]!.source_url = "https://evil.test"; },
    (m) => { m.movies[0]!.poster_url = "data:image/svg+xml,bad"; },
    (m) => { m.movies[0]!.imdb_id = "bad"; }, (m) => { m.movies[0]!.imdb_url = "https://evil.test"; },
    (m) => { m.books[0]!.id = "../bad"; }, (m) => { m.books[0]!.title = ""; },
    (m) => { m.books[0]!.authors = Array(21).fill("author"); },
    (m) => { m.books[0]!.identifiers = Array(21).fill("id"); },
    (m) => { m.books[0]!.description = "x".repeat(4001); },
    (m) => { m.books[0]!.published_date = "x".repeat(31); },
    (m) => { m.books[0]!.source_url = "javascript:bad"; },
    (m) => { m.comparisons[0]!.movie_id = 999; }, (m) => { m.comparisons[0]!.book_id = "unknown"; },
    (m) => { m.comparisons[0]!.relation = "bad" as "confirmed"; },
    (m) => { m.comparisons[0]!.confirmed_information = Array(11).fill("fact"); },
    (m) => { m.comparisons[0]!.differences = Array(11).fill("fact"); },
    (m) => { m.comparisons[0]!.opinion = "x".repeat(2001); },
    (m) => { m.comparisons[0]!.limitations = Array(11).fill("fact"); },
    (m) => { m.actions[0]!.reference_id = "tt7654321"; m.actions[0]!.url = "https://www.imdb.com/title/tt7654321/"; },
    (m) => { m.actions[1]!.reference_id = "unknown"; m.actions[1]!.url = "https://books.google.com/books?id=unknown"; },
  ];
  it.each(mutations.map((mutate, index) => ({ mutate, index })))("rejects invalid field $index", ({ mutate }) => {
    const value = JSON.parse(JSON.stringify(metadata)) as ChatMetadata;
    mutate(value);
    expect(() => parseMetadata(value)).toThrow();
  });
});
