/** @type {import('next').NextConfig} */
const DEFAULT_LOCAL_API_URL = 'http://localhost:8000';

const nextConfig = {
  output: 'standalone',
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || DEFAULT_LOCAL_API_URL;
    return [
      {
        source: '/api/:path*',
        destination: `${apiUrl}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
