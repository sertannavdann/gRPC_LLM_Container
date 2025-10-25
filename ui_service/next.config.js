/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  env: {
    AGENT_SERVICE_ADDRESS: process.env.AGENT_SERVICE_ADDRESS || 'localhost:50054',
  },
}

module.exports = nextConfig
