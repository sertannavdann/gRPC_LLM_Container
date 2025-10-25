/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  // Don't bake env vars into the build - let them be read at runtime
  experimental: {
    outputFileTracingIncludes: {
      '/api/**': ['./proto/**/*'],
    },
  },
}

module.exports = nextConfig
