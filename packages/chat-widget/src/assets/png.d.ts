declare module "*.png" {
  // Vite returns a URL; Next.js returns static image metadata.
  const image: string | { src: string };
  export default image;
}
