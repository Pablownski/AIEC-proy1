import { TMDB_LOGO } from "./tmdb-logo";

export function TmdbAttribution() {
  return <footer className="agichat-attribution" aria-label="Créditos de datos e imágenes">
    <a href="https://www.themoviedb.org" target="_blank" rel="noopener noreferrer">
      <img src={TMDB_LOGO} width="78" height="10" alt="TMDB" />
    </a>
    <span>This product uses the TMDB API but is not endorsed or certified by TMDB.</span>
  </footer>;
}
